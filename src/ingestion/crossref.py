from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
import html
from pathlib import Path
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import compact_join, normalize_whitespace, read_json, write_json

CROSSREF_API_URL = "https://api.crossref.org/works"

# Crossref is a shared public service; a descriptive User-Agent is the polite-pool convention.
USER_AGENT = "K3-Day10-DataObservabilityLab/0.1 (mailto:student@example.edu)"

REQUEST_TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 5
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

MIN_TITLE_CHARS = 10
MIN_SUMMARY_CHARS = 80


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _strip_markup(value: str) -> str:
    """Crossref abstracts arrive as JATS XML wrapped in escaped entities."""
    unescaped = html.unescape(value or "")
    without_tags = re.sub(r"<[^>]+>", " ", unescaped)
    text = normalize_whitespace(without_tags)
    # Many publishers prefix the abstract body with a redundant "Abstract" heading.
    return re.sub(r"^(abstract|summary)\s*[:.\-]?\s*", "", text, flags=re.IGNORECASE)


def _first_text(values: Any) -> str:
    if isinstance(values, list):
        for value in values:
            if isinstance(value, str) and value.strip():
                return normalize_whitespace(value)
        return ""
    if isinstance(values, str):
        return normalize_whitespace(values)
    return ""


def _date_from_parts(node: Any) -> str:
    """Convert a Crossref `date-parts` node into an ISO date string."""
    if not isinstance(node, dict):
        return ""
    parts = node.get("date-parts") or []
    if not parts or not isinstance(parts[0], list) or not parts[0]:
        # Some nodes only carry a full timestamp.
        timestamp = node.get("date-time")
        return timestamp[:10] if isinstance(timestamp, str) else ""
    values = [int(item) for item in parts[0] if isinstance(item, int)]
    if not values:
        return ""
    year = values[0]
    month = min(max(values[1] if len(values) > 1 else 1, 1), 12)
    day = min(max(values[2] if len(values) > 2 else 1, 1), 31)
    # Partial or malformed date-parts are common; fall back to the first of the month.
    for candidate in (day, 1):
        try:
            return date(year, month, candidate).isoformat()
        except ValueError:
            continue
    return ""


PUBLICATION_DATE_KEYS = ("published-online", "published", "issued", "published-print", "created")


def _published_date(item: dict, today: date | None = None) -> str:
    """Resolve the date the work actually became available.

    Journals routinely forward-date an issue (a paper registered in 2026 can carry an
    `issued` date of 2028), which would make every freshness signal meaningless. So we take
    the most recent candidate date that has already happened - normally the publication
    date itself, and the DOI registration date for forward-dated works.
    """
    reference = today or datetime.now(UTC).date()
    candidates: list[date] = []
    for key in PUBLICATION_DATE_KEYS:
        value = _date_from_parts(item.get(key))
        if not value:
            continue
        try:
            candidates.append(date.fromisoformat(value))
        except ValueError:
            continue

    if not candidates:
        return ""
    already_published = [item for item in candidates if item <= reference]
    return (max(already_published) if already_published else min(candidates)).isoformat()


def _updated_date(item: dict, fallback: str) -> str:
    for key in ("deposited", "indexed", "created"):
        value = _date_from_parts(item.get(key))
        if value:
            return value
    return fallback


def _authors(item: dict) -> list[str]:
    names: list[str] = []
    for author in item.get("author") or []:
        if not isinstance(author, dict):
            continue
        full = compact_join(
            [normalize_whitespace(author.get("given", "")), normalize_whitespace(author.get("family", ""))],
            sep=" ",
        )
        full = full or normalize_whitespace(author.get("name", ""))
        if full and full not in names:
            names.append(full)
    return names


def _categories(item: dict) -> list[str]:
    categories: list[str] = []
    for subject in item.get("subject") or []:
        if isinstance(subject, str) and subject.strip():
            cleaned = normalize_whitespace(subject)
            if cleaned not in categories:
                categories.append(cleaned)
    if not categories:
        # Not every Crossref member supplies subjects; fall back to the venue and work type.
        venue = _first_text(item.get("container-title"))
        work_type = normalize_whitespace(item.get("type", ""))
        categories = [value for value in (venue, work_type) if value]
    return categories


def _pdf_url(item: dict) -> str:
    for link in item.get("link") or []:
        if not isinstance(link, dict):
            continue
        if link.get("content-type") == "application/pdf" and link.get("URL"):
            return str(link["URL"])
    return ""


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse a Crossref `/works` payload into the shared `PaperRecord` schema.

    Records missing a DOI, a usable title, or a usable abstract are dropped here so that
    downstream cleaning starts from a consistent shape.
    """
    items = (payload or {}).get("message", {}).get("items", [])
    records: list[PaperRecord] = []
    seen_ids: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue

        paper_id = normalize_whitespace(item.get("DOI", ""))
        title = _first_text(item.get("title"))
        summary = _strip_markup(item.get("abstract", ""))

        if not paper_id or paper_id in seen_ids:
            continue
        if len(title) < MIN_TITLE_CHARS or len(summary) < MIN_SUMMARY_CHARS:
            continue

        published = _published_date(item)
        if not published:
            continue

        categories = _categories(item)
        seen_ids.add(paper_id)
        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=_authors(item),
                categories=categories,
                primary_category=categories[0] if categories else "",
                published=published,
                updated=_updated_date(item, published),
                abs_url=normalize_whitespace(item.get("URL", "")) or f"https://doi.org/{paper_id}",
                pdf_url=_pdf_url(item),
                comment=compact_join(
                    [
                        normalize_whitespace(item.get("type", "")),
                        _first_text(item.get("container-title")),
                        normalize_whitespace(item.get("publisher", "")),
                    ],
                    sep=" | ",
                ),
            )
        )

    return records


def _request_with_retry(params: dict[str, Any]) -> dict:
    """GET the Crossref works endpoint, backing off on rate limits and transient failures."""
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                CROSSREF_API_URL,
                params=params,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code in RETRY_STATUS_CODES:
                raise requests.HTTPError(f"Retryable status {response.status_code}", response=response)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            last_error = error
            if attempt == MAX_ATTEMPTS:
                break
            backoff = min(2 ** (attempt - 1), 16)
            print(f"  Crossref request failed ({error}); retrying in {backoff}s [{attempt}/{MAX_ATTEMPTS}]")
            time.sleep(backoff)

    raise RuntimeError(f"Crossref request failed after {MAX_ATTEMPTS} attempts: {last_error}")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch papers from Crossref, persist the raw response, and return parsed records."""
    # Over-fetch because parsing drops items without an abstract-quality payload.
    requested_rows = min(settings.max_results * 3, 100)
    params = {
        "query.bibliographic": settings.source_query,
        "filter": settings.source_filter,
        "rows": requested_rows,
        "sort": "issued",
        "order": "desc",
    }

    print(f"  GET {CROSSREF_API_URL} rows={requested_rows} filter={settings.source_filter}")
    payload = _request_with_retry(params)
    write_json(settings.paths.raw_api_response, payload)

    records = parse_crossref_payload(payload)[: settings.max_results]
    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    print(f"  Parsed {len(records)} valid records -> {settings.paths.raw_records_json.name}")
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Rehydrate `PaperRecord` objects from a raw records snapshot on disk."""
    payload = read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected a list of records in {path}, got {type(payload).__name__}.")

    fields = set(PaperRecord.__dataclass_fields__)
    records: list[PaperRecord] = []
    for item in payload:
        known = {key: value for key, value in item.items() if key in fields}
        missing = fields - known.keys()
        if missing:
            raise ValueError(f"Record {item.get('paper_id', '<unknown>')} is missing fields: {sorted(missing)}")
        records.append(PaperRecord(**known))
    return records
