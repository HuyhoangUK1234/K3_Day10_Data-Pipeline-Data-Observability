from __future__ import annotations

from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import now_utc, safe_slug, write_json

MIN_ROWS = 10
MIN_TITLE_CHARS = 10
MIN_SUMMARY_CHARS = 80


def _check(
    name: str,
    expectation: str,
    success: bool,
    observed: Any,
    expected: Any,
    severity: str = "critical",
) -> dict[str, Any]:
    return {
        "name": name,
        "expectation": expectation,
        "success": bool(success),
        "observed": observed,
        "expected": expected,
        "severity": severity,
    }


def _blank_count(series: pd.Series) -> int:
    filled = series.fillna("").astype(str).str.strip()
    return int((filled == "").sum())


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Validate the cleaned corpus and persist the result under `data/quality/`.

    Runs the same suite for the baseline, corrupted and repaired datasets so the three
    states are directly comparable.
    """
    slug = safe_slug(report_name)
    total_rows = int(len(df))

    if total_rows == 0:
        checks = [_check("row_count_minimum", f"row_count >= {MIN_ROWS}", False, 0, MIN_ROWS)]
    else:
        duplicate_ids = int(df["paper_id"].duplicated().sum())
        duplicate_titles = int(df["title"].str.lower().duplicated().sum())
        short_titles = int((df["title"].fillna("").astype(str).str.len() < MIN_TITLE_CHARS).sum())
        short_summaries = int((df["summary"].fillna("").astype(str).str.len() < MIN_SUMMARY_CHARS).sum())
        empty_summaries = _blank_count(df["summary"])
        empty_embed_text = _blank_count(df["text_for_embedding"])
        stale_rows = int((df["age_days"] > settings.freshness_threshold_days).sum())
        future_dated = int((df["age_days"] < 0).sum())

        checks = [
            _check("row_count_minimum", f"row_count >= {MIN_ROWS}", total_rows >= MIN_ROWS, total_rows, MIN_ROWS),
            _check("paper_id_not_null", "paper_id has no blank value", _blank_count(df["paper_id"]) == 0,
                   _blank_count(df["paper_id"]), 0),
            _check("paper_id_unique", "paper_id is unique", duplicate_ids == 0, duplicate_ids, 0),
            _check("title_not_null", "title has no blank value", _blank_count(df["title"]) == 0,
                   _blank_count(df["title"]), 0),
            _check("title_min_length", f"title length >= {MIN_TITLE_CHARS}", short_titles == 0,
                   short_titles, 0),
            _check("title_unique", "no duplicate titles", duplicate_titles == 0, duplicate_titles, 0,
                   severity="warning"),
            _check("summary_not_empty", "summary is populated", empty_summaries == 0, empty_summaries, 0),
            _check("summary_min_length", f"summary length >= {MIN_SUMMARY_CHARS}", short_summaries == 0,
                   short_summaries, 0),
            _check("text_for_embedding_not_empty", "text_for_embedding is populated", empty_embed_text == 0,
                   empty_embed_text, 0),
            _check("published_not_in_future", "publication date is not ahead of the run date",
                   future_dated == 0, future_dated, 0, severity="warning"),
            # Source freshness is a monitoring signal, not a schema violation: an upstream
            # publisher backlog should raise a flag without failing the whole dataset.
            _check("freshness_within_threshold",
                   f"age_days <= {settings.freshness_threshold_days} for every row",
                   stale_rows == 0, stale_rows, 0, severity="warning"),
        ]

    failed = [item for item in checks if not item["success"]]
    critical_failures = [item for item in failed if item["severity"] == "critical"]
    warnings = [item for item in failed if item["severity"] != "critical"]

    payload = {
        "report_name": report_name,
        "generated_at": now_utc().isoformat(),
        "total_rows": total_rows,
        "checks": checks,
        "check_count": len(checks),
        "success_count": len(checks) - len(failed),
        "failure_count": len(failed),
        "success_rate": round((len(checks) - len(failed)) / len(checks), 4) if checks else 0.0,
        # A dataset passes when no critical check fails; warnings are surfaced, not fatal.
        "success": not critical_failures,
        "failed_checks": [item["name"] for item in failed],
        "critical_failed_checks": [item["name"] for item in critical_failures],
        "warning_checks": [item["name"] for item in warnings],
    }

    write_json(settings.paths.quality_dir / f"{slug}_quality.json", payload)

    # Great-Expectations-shaped mirror of the same result, for tooling that expects that vocabulary.
    write_json(
        settings.paths.gx_dir / f"{slug}_expectation_suite_result.json",
        {
            "suite_name": f"{slug}_suite",
            "engine": "pandas (expectation-style checks, no GX data context)",
            "evaluated_expectations": len(checks),
            "successful_expectations": payload["success_count"],
            "unsuccessful_expectations": payload["failure_count"],
            "success": payload["success"],
            "results": [
                {
                    "expectation_type": item["name"],
                    "kwargs": {"expected": item["expected"], "severity": item["severity"]},
                    "success": item["success"],
                    "result": {"observed_value": item["observed"]},
                }
                for item in checks
            ],
        },
    )
    return payload


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Summarize how current the corpus is and write the JSON freshness artifact."""
    total_rows = int(len(df))
    threshold = settings.freshness_threshold_days

    if total_rows == 0:
        payload = {
            "generated_at": now_utc().isoformat(),
            "threshold_days": threshold,
            "total_rows": 0,
            "latest_published": None,
            "oldest_published": None,
            "stale_rows": 0,
            "stale_ratio": 0.0,
            "future_dated_rows": 0,
            "min_age_days": None,
            "median_age_days": None,
            "max_age_days": None,
            "is_fresh": False,
            "status": "EMPTY",
        }
        write_json(report_path, payload)
        return payload

    published = [value for value in df["published"].fillna("").astype(str).tolist() if value]
    ages = pd.to_numeric(df["age_days"], errors="coerce").dropna()
    stale_rows = int((ages > threshold).sum())

    # Fresh means the newest paper is inside the window and nothing has gone stale.
    newest_age = int(ages.min()) if not ages.empty else None
    is_fresh = bool(stale_rows == 0 and newest_age is not None and newest_age <= threshold)

    payload = {
        "generated_at": now_utc().isoformat(),
        "threshold_days": threshold,
        "total_rows": total_rows,
        "latest_published": max(published) if published else None,
        "oldest_published": min(published) if published else None,
        "stale_rows": stale_rows,
        "stale_ratio": round(stale_rows / total_rows, 4),
        "future_dated_rows": int((ages < 0).sum()),
        "min_age_days": newest_age,
        "median_age_days": float(ages.median()) if not ages.empty else None,
        "max_age_days": int(ages.max()) if not ages.empty else None,
        "is_fresh": is_fresh,
        "status": "FRESH" if is_fresh else "STALE",
    }

    write_json(report_path, payload)
    return payload
