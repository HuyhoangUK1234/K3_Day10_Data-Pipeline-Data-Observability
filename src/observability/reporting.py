from __future__ import annotations

from typing import Any

from core.utils import now_utc, write_text

METRIC_KEYS = [
    ("retrieval_hit_rate", "Retrieval hit rate", "ratio"),
    ("mean_token_f1", "Mean token F1", "ratio"),
    ("judge_accuracy", "Judge accuracy", "ratio"),
    ("mean_judge_score", "Mean judge score (1-5)", "score"),
]


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}" if isinstance(value, float) else str(value)
    return str(value)


def _fmt_metric(value: Any) -> str:
    """Metrics render with a fixed width so the comparison tables line up."""
    return f"{float(value):.4f}" if isinstance(value, (int, float)) and not isinstance(value, bool) else _fmt(value)


def _fmt_delta(current: Any, reference: Any) -> str:
    if not isinstance(current, (int, float)) or not isinstance(reference, (int, float)):
        return "n/a"
    delta = float(current) - float(reference)
    arrow = "=" if abs(delta) < 1e-9 else ("v" if delta < 0 else "^")
    return f"{delta:+.4f} {arrow}"


def _quality_table(quality: dict[str, Any]) -> list[str]:
    lines = [
        "| Check | Severity | Expectation | Observed | Result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for check in quality.get("checks", []):
        if check.get("success"):
            status = "PASS"
        else:
            status = "**FAIL**" if check.get("severity") == "critical" else "WARN"
        lines.append(
            f"| `{check.get('name')}` | {check.get('severity')} | {check.get('expectation')} "
            f"| {_fmt(check.get('observed'))} | {status} |"
        )
    return lines


def _quality_headline(quality: dict[str, Any]) -> str:
    verdict = "PASS" if quality.get("success") else "FAIL"
    warnings = quality.get("warning_checks") or []
    suffix = f", {len(warnings)} warning(s): {', '.join(warnings)}" if warnings else ""
    return (
        f"**{verdict}** ({_fmt(quality.get('success_count'))}/{_fmt(quality.get('check_count'))} checks passed"
        f"{suffix})"
    )


def _freshness_lines(freshness: dict[str, Any]) -> list[str]:
    return [
        f"- Status: **{freshness.get('status', 'n/a')}** (is_fresh = {_fmt(freshness.get('is_fresh'))})",
        f"- Threshold: {_fmt(freshness.get('threshold_days'))} days",
        f"- Latest published: {_fmt(freshness.get('latest_published'))}",
        f"- Oldest published: {_fmt(freshness.get('oldest_published'))}",
        f"- Stale rows: {_fmt(freshness.get('stale_rows'))} / {_fmt(freshness.get('total_rows'))} "
        f"(ratio {_fmt(freshness.get('stale_ratio'))})",
        f"- Forward-dated rows: {_fmt(freshness.get('future_dated_rows'))}",
        f"- Age days min / median / max: {_fmt(freshness.get('min_age_days'))} / "
        f"{_fmt(freshness.get('median_age_days'), 1)} / {_fmt(freshness.get('max_age_days'))}",
    ]


def _ragas_lines(metrics: dict[str, Any]) -> list[str]:
    ragas = metrics.get("ragas")
    if not isinstance(ragas, dict) or not ragas:
        return ["- Ragas: not available"]
    return [f"- `{key}`: {_fmt(value)}" for key, value in ragas.items()]


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write the baseline Markdown report from the artifacts produced by phase 1."""
    lines: list[str] = [
        "# Phase 1 - Baseline Report",
        "",
        f"Generated at: `{now_utc().isoformat()}`",
        "",
        "## 1. Source and dataset",
        "",
        "| Field | Value |",
        "| --- | --- |",
    ]
    for key, value in source_summary.items():
        lines.append(f"| `{key}` | {_fmt(value)} |")

    lines += [
        "",
        "## 2. Evaluation metrics (baseline)",
        "",
        f"Evaluated on {_fmt(metrics.get('samples'))} questions from the frozen evaluation set.",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    for key, label, _kind in METRIC_KEYS:
        lines.append(f"| {label} | {_fmt_metric(metrics.get(key))} |")

    lines += [
        "",
        "> Interpretation: the QA layer answers extractively from indexed metadata and the ground",
        "> truth is derived from the same fields, so a clean corpus is expected to score at or near",
        "> the ceiling. The baseline is therefore a reference point for measuring degradation, not",
        "> evidence that the agent generalizes.",
        "",
        "### Ragas",
        "",
    ] + _ragas_lines(metrics)

    lines += [
        "",
        "## 3. Data quality",
        "",
        f"Overall: {_quality_headline(quality)}",
        "",
        "A dataset fails only when a `critical` check fails; `warning` checks are surfaced but",
        "do not block the pipeline.",
        "",
    ] + _quality_table(quality)

    if quality.get("critical_failed_checks"):
        lines += ["", f"Critical failures: {', '.join(quality['critical_failed_checks'])}"]

    lines += ["", "## 4. Freshness", ""] + _freshness_lines(freshness)

    lines += [
        "",
        "## 5. How to reproduce",
        "",
        "```bash",
        "python script/run_phase1.py",
        "```",
        "",
    ]
    write_text(report_path, "\n".join(lines))


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Write the baseline / corrupted / repaired comparison report."""
    lines: list[str] = [
        "# Phase 2 - Corruption, Repair and Comparison Report",
        "",
        f"Generated at: `{now_utc().isoformat()}`",
        "",
        "All three states are evaluated on the **same frozen evaluation set**, so the deltas below",
        "are attributable to the dataset, not to a different set of questions.",
        "",
        "## 1. Metric comparison",
        "",
        "| Metric | Baseline | Corrupted | Repaired | Corrupted vs baseline | Repaired vs baseline |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for key, label, _kind in METRIC_KEYS:
        base = baseline_metrics.get(key)
        corrupt = corrupted_metrics.get(key)
        repair = repaired_metrics.get(key)
        lines.append(
            f"| {label} | {_fmt_metric(base)} | {_fmt_metric(corrupt)} | {_fmt_metric(repair)} "
            f"| {_fmt_delta(corrupt, base)} | {_fmt_delta(repair, base)} |"
        )

    lines += [
        "",
        f"Sample counts - baseline: {_fmt(baseline_metrics.get('samples'))}, "
        f"corrupted: {_fmt(corrupted_metrics.get('samples'))}, "
        f"repaired: {_fmt(repaired_metrics.get('samples'))}.",
        "",
        "## 2. Data quality",
        "",
        "| State | Result | Passed / total | Critical failures | Warnings |",
        "| --- | --- | --- | --- | --- |",
    ]
    for label, quality in (("Corrupted", corrupted_quality), ("Repaired", repaired_quality)):
        critical = ", ".join(quality.get("critical_failed_checks", [])) or "-"
        warnings = ", ".join(quality.get("warning_checks", [])) or "-"
        lines.append(
            f"| {label} | {'PASS' if quality.get('success') else '**FAIL**'} "
            f"| {_fmt(quality.get('success_count'))}/{_fmt(quality.get('check_count'))} "
            f"| {critical} | {warnings} |"
        )

    lines += ["", "### Corrupted dataset checks", ""] + _quality_table(corrupted_quality)
    lines += ["", "### Repaired dataset checks", ""] + _quality_table(repaired_quality)

    lines += ["", "## 3. Freshness", "", "### Corrupted", ""] + _freshness_lines(corrupted_freshness)
    lines += ["", "### Repaired", ""] + _freshness_lines(repaired_freshness)

    # Conclusions are derived from the numbers above rather than asserted by hand.
    lines += ["", "## 4. Observations", ""]
    degraded = [
        label
        for key, label, _kind in METRIC_KEYS
        if isinstance(corrupted_metrics.get(key), (int, float))
        and isinstance(baseline_metrics.get(key), (int, float))
        and corrupted_metrics[key] < baseline_metrics[key]
    ]
    recovered = [
        label
        for key, label, _kind in METRIC_KEYS
        if isinstance(repaired_metrics.get(key), (int, float))
        and isinstance(corrupted_metrics.get(key), (int, float))
        and repaired_metrics[key] > corrupted_metrics[key]
    ]

    lines.append(
        f"- Corruption degraded {len(degraded)}/{len(METRIC_KEYS)} metrics"
        + (f": {', '.join(degraded)}." if degraded else ".")
    )
    lines.append(
        f"- Repair improved {len(recovered)}/{len(METRIC_KEYS)} metrics over the corrupted state"
        + (f": {', '.join(recovered)}." if recovered else ".")
    )
    lines.append(
        f"- Data quality moved from {'PASS' if corrupted_quality.get('success') else 'FAIL'} (corrupted) "
        f"to {'PASS' if repaired_quality.get('success') else 'FAIL'} (repaired)."
    )
    lines.append(
        f"- Freshness: corrupted = {corrupted_freshness.get('status')} with "
        f"{_fmt(corrupted_freshness.get('stale_rows'))}/{_fmt(corrupted_freshness.get('total_rows'))} stale rows "
        f"(oldest {_fmt(corrupted_freshness.get('oldest_published'))}); repaired = "
        f"{repaired_freshness.get('status')} with {_fmt(repaired_freshness.get('stale_rows'))}/"
        f"{_fmt(repaired_freshness.get('total_rows'))} stale rows "
        f"(oldest {_fmt(repaired_freshness.get('oldest_published'))})."
    )

    lines += [
        "",
        "## 5. How to reproduce",
        "",
        "```bash",
        "python script/run_phase1.py",
        "python script/run_corruption_flow.py",
        "```",
        "",
    ]
    write_text(report_path, "\n".join(lines))
