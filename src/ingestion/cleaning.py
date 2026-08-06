from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord

MIN_TITLE_CHARS = 10
MIN_SUMMARY_CHARS = 80

# Column contract shared by the index builder, quality checks, corruption and reporting.
CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors_joined",
    "categories_joined",
    "primary_category",
    "published",
    "updated",
    "age_days",
    "title_chars",
    "summary_chars",
    "author_count",
    "abs_url",
    "pdf_url",
    "comment",
    "text_for_embedding",
]


def build_text_for_embedding(row: dict) -> str:
    """Render the single string that gets embedded for a paper.

    Kept public so the corruption flow can rebuild it after mutating fields; otherwise
    corrupted summaries would never reach the vector store.
    """
    return (
        f"Title: {row.get('title', '')}\n"
        f"Authors: {row.get('authors_joined', '')}\n"
        f"Categories: {row.get('categories_joined', '')}\n"
        f"Published: {row.get('published', '')}\n"
        f"Summary: {row.get('summary', '')}"
    ).strip()


def _parse_date(value: str) -> date | None:
    text = (value or "").strip()[:10]
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def compute_age_days(published: str, run_date: date) -> int | None:
    """Signed days between publication and the pipeline run, or None if unparsable.

    The value is deliberately *not* clamped at zero: Crossref carries forward-dated
    issue dates for online-first articles, and a negative age is the signal that
    surfaces them instead of hiding them behind a fake zero.
    """
    published_date = _parse_date(published)
    if published_date is None:
        return None
    return (run_date - published_date).days


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Normalize raw records into the embedding-ready clean schema."""
    reference_date = run_date.date() if isinstance(run_date, datetime) else run_date
    rows: list[dict] = []
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()

    for record in records:
        raw = asdict(record) if isinstance(record, PaperRecord) else dict(record)

        paper_id = normalize_whitespace(str(raw.get("paper_id", ""))).lower()
        title = normalize_whitespace(str(raw.get("title", "")))
        summary = normalize_whitespace(str(raw.get("summary", "")))
        published = (str(raw.get("published", "")) or "").strip()[:10]

        # Drop records that cannot support retrieval or freshness reasoning.
        if not paper_id or len(title) < MIN_TITLE_CHARS or len(summary) < MIN_SUMMARY_CHARS:
            continue
        if _parse_date(published) is None:
            continue

        title_key = title.lower()
        if paper_id in seen_ids or title_key in seen_titles:
            continue
        seen_ids.add(paper_id)
        seen_titles.add(title_key)

        authors = [normalize_whitespace(str(item)) for item in raw.get("authors") or []]
        authors = [item for item in authors if item]
        categories = [normalize_whitespace(str(item)) for item in raw.get("categories") or []]
        categories = [item for item in categories if item]

        row = {
            "paper_id": paper_id,
            "title": title,
            "summary": summary,
            "authors_joined": compact_join(authors) or "Unknown",
            "categories_joined": compact_join(categories) or "Uncategorized",
            "primary_category": normalize_whitespace(str(raw.get("primary_category", "")))
            or (categories[0] if categories else "Uncategorized"),
            "published": published,
            "updated": (str(raw.get("updated", "")) or published).strip()[:10],
            "age_days": compute_age_days(published, reference_date),
            "title_chars": len(title),
            "summary_chars": len(summary),
            "author_count": len(authors),
            "abs_url": normalize_whitespace(str(raw.get("abs_url", ""))),
            "pdf_url": normalize_whitespace(str(raw.get("pdf_url", ""))),
            "comment": normalize_whitespace(str(raw.get("comment", ""))),
        }
        row["text_for_embedding"] = build_text_for_embedding(row)
        rows.append(row)

    df = pd.DataFrame(rows, columns=CLEAN_COLUMNS)
    if df.empty:
        return df

    # Newest first: freshness is the signal the corruption flow later degrades.
    df = df.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
    return df
