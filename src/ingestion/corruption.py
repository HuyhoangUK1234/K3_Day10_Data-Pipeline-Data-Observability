from __future__ import annotations

from datetime import datetime, timedelta
import random
from typing import Any

import pandas as pd

from core.utils import now_utc, write_json
from ingestion.cleaning import build_text_for_embedding

# Fixed seed: the corruption has to be reproducible for the comparison to mean anything.
SEED = 20251006

DROP_LATEST_ROWS = 3
BLANK_SUMMARY_ROWS = 3
NOISY_SUMMARY_ROWS = 3
TRUNCATED_TITLE_ROWS = 3
STALE_DATE_ROWS = 3
DUPLICATE_ROWS = 2

TITLE_TRUNCATE_CHARS = 12
STALE_SHIFT_DAYS = 1500

NOISE_TOKENS = [
    "<div class=\"ad\"><span>",
    "&amp;#8203;&amp;nbsp;",
    "???? ?? ???",
    "LOREM IPSUM DOLOR SIT AMET CONSECTETUR",
    "%%%RAW_HTML_BLOCK%%%",
    "[[UNPARSED_JATS]]",
]


def _pick(rng: random.Random, pool: list[int], count: int) -> list[int]:
    """Draw up to `count` row positions without reusing rows across corruption steps."""
    take = min(count, len(pool))
    chosen = rng.sample(pool, take) if take else []
    for position in chosen:
        pool.remove(position)
    return sorted(chosen)


def _inject_noise(rng: random.Random, summary: str) -> str:
    words = summary.split()
    if not words:
        return " ".join(rng.sample(NOISE_TOKENS, 3))
    # Splice markup/garbage into the middle of the abstract and clip the tail.
    cut = max(len(words) // 3, 1)
    noisy = words[:cut] + [rng.choice(NOISE_TOKENS)] + words[cut : cut * 2] + [rng.choice(NOISE_TOKENS)]
    return " ".join(noisy)


def _shift_date(published: str, days: int) -> str:
    try:
        parsed = datetime.strptime(str(published)[:10], "%Y-%m-%d").date()
    except ValueError:
        return published
    return (parsed - timedelta(days=days)).isoformat()


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Inject realistic, targeted data defects into a cleaned corpus.

    Each defect maps to a failure mode an ingestion pipeline actually hits: a truncated
    incremental load, empty extractions, unparsed markup, a truncating column, stale
    publication dates, and a re-run that double-inserts rows.
    """
    if df is None or df.empty:
        raise ValueError("Cannot corrupt an empty cleaned dataset; run the baseline pipeline first.")

    rng = random.Random(SEED)
    work = df.copy().reset_index(drop=True)
    steps: list[dict[str, Any]] = []
    input_rows = len(work)

    # 1. Missing records: a failed incremental load silently drops the newest papers.
    dropped = work.head(min(DROP_LATEST_ROWS, len(work) - 1))
    steps.append(
        {
            "step": "drop_latest_records",
            "description": "Removed the most recently published papers, simulating a truncated incremental load.",
            "count": int(len(dropped)),
            "affected_paper_ids": dropped["paper_id"].tolist(),
        }
    )
    work = work.drop(index=dropped.index).reset_index(drop=True)

    pool = list(range(len(work)))

    # 2. Empty summaries: the abstract extractor returned nothing.
    positions = _pick(rng, pool, BLANK_SUMMARY_ROWS)
    for position in positions:
        work.at[position, "summary"] = ""
    steps.append(
        {
            "step": "blank_summary",
            "description": "Blanked the summary field, simulating a failed abstract extraction.",
            "count": len(positions),
            "affected_paper_ids": [work.at[position, "paper_id"] for position in positions],
        }
    )

    # 3. Noisy summaries: unparsed markup and boilerplate leaked into the text.
    positions = _pick(rng, pool, NOISY_SUMMARY_ROWS)
    for position in positions:
        work.at[position, "summary"] = _inject_noise(rng, str(work.at[position, "summary"]))
    steps.append(
        {
            "step": "inject_summary_noise",
            "description": "Spliced unparsed markup and boilerplate into the summary text.",
            "count": len(positions),
            "affected_paper_ids": [work.at[position, "paper_id"] for position in positions],
        }
    )

    # 4. Truncated titles: a downstream column too narrow for the real value.
    positions = _pick(rng, pool, TRUNCATED_TITLE_ROWS)
    for position in positions:
        work.at[position, "title"] = str(work.at[position, "title"])[:TITLE_TRUNCATE_CHARS]
    steps.append(
        {
            "step": "truncate_title",
            "description": f"Truncated titles to {TITLE_TRUNCATE_CHARS} characters, breaking exact-title lookup.",
            "count": len(positions),
            "affected_paper_ids": [work.at[position, "paper_id"] for position in positions],
        }
    )

    # 5. Stale dates: a backfill rewrote publication dates to a much older value.
    positions = _pick(rng, pool, STALE_DATE_ROWS)
    for position in positions:
        work.at[position, "published"] = _shift_date(work.at[position, "published"], STALE_SHIFT_DAYS)
        work.at[position, "updated"] = _shift_date(work.at[position, "updated"], STALE_SHIFT_DAYS)
        work.at[position, "age_days"] = int(work.at[position, "age_days"]) + STALE_SHIFT_DAYS
    steps.append(
        {
            "step": "stale_publication_date",
            "description": f"Shifted publication dates {STALE_SHIFT_DAYS} days into the past.",
            "count": len(positions),
            "affected_paper_ids": [work.at[position, "paper_id"] for position in positions],
        }
    )

    # 6. Duplicates: the loader replayed part of a batch.
    duplicate_count = min(DUPLICATE_ROWS, len(work))
    duplicated = work.head(duplicate_count).copy()
    work = pd.concat([work, duplicated], ignore_index=True)
    steps.append(
        {
            "step": "duplicate_rows",
            "description": "Appended duplicate rows, simulating a replayed load batch.",
            "count": int(duplicate_count),
            "affected_paper_ids": duplicated["paper_id"].tolist(),
        }
    )

    # 7. Rebuild derived columns so the corruption actually reaches the vector store.
    work["title_chars"] = work["title"].astype(str).str.len()
    work["summary_chars"] = work["summary"].astype(str).str.len()
    work["text_for_embedding"] = [build_text_for_embedding(row) for row in work.to_dict(orient="records")]

    log = {
        "generated_at": now_utc().isoformat(),
        "seed": SEED,
        "input_rows": input_rows,
        "output_rows": int(len(work)),
        "net_row_change": int(len(work)) - input_rows,
        "steps": steps,
    }
    write_json(output_log_path, log)
    return work
