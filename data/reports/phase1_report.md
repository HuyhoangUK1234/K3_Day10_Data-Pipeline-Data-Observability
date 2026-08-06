# Phase 1 - Baseline Report

Generated at: `2026-08-06T03:45:24.275347+00:00`

## 1. Source and dataset

| Field | Value |
| --- | --- |
| `run_date` | 2026-08-06T03:45:16.308087+00:00 |
| `source_api` | Crossref REST API |
| `query` | agentic retrieval augmented generation large language model |
| `filter` | from-pub-date:2026-02-07,has-abstract:true |
| `max_results` | 24 |
| `raw_records` | 24 |
| `clean_rows` | 24 |
| `embedding_model` | sentence-transformers/all-MiniLM-L6-v2 |
| `collection_name` | papers-baseline |
| `top_k` | 4 |
| `llm_provider` | unavailable (heuristic fallback judge) |
| `evaluation_samples` | 20 |

## 2. Evaluation metrics (baseline)

Evaluated on 20 questions from the frozen evaluation set.

| Metric | Value |
| --- | --- |
| Retrieval hit rate | 1.0000 |
| Mean token F1 | 1.0000 |
| Judge accuracy | 1.0000 |
| Mean judge score (1-5) | 5.0000 |

> Interpretation: the QA layer answers extractively from indexed metadata and the ground
> truth is derived from the same fields, so a clean corpus is expected to score at or near
> the ceiling. The baseline is therefore a reference point for measuring degradation, not
> evidence that the agent generalizes.

### Ragas

- `skipped`: Set RUN_RAGAS=1 to enable the slower Ragas pass.

## 3. Data quality

Overall: **PASS** (10/11 checks passed, 1 warning(s): freshness_within_threshold)

A dataset fails only when a `critical` check fails; `warning` checks are surfaced but
do not block the pipeline.

| Check | Severity | Expectation | Observed | Result |
| --- | --- | --- | --- | --- |
| `row_count_minimum` | critical | row_count >= 10 | 24 | PASS |
| `paper_id_not_null` | critical | paper_id has no blank value | 0 | PASS |
| `paper_id_unique` | critical | paper_id is unique | 0 | PASS |
| `title_not_null` | critical | title has no blank value | 0 | PASS |
| `title_min_length` | critical | title length >= 10 | 0 | PASS |
| `title_unique` | warning | no duplicate titles | 0 | PASS |
| `summary_not_empty` | critical | summary is populated | 0 | PASS |
| `summary_min_length` | critical | summary length >= 80 | 0 | PASS |
| `text_for_embedding_not_empty` | critical | text_for_embedding is populated | 0 | PASS |
| `published_not_in_future` | warning | publication date is not ahead of the run date | 0 | PASS |
| `freshness_within_threshold` | warning | age_days <= 180 for every row | 1 | WARN |

## 4. Freshness

- Status: **STALE** (is_fresh = no)
- Threshold: 180 days
- Latest published: 2026-08-03
- Oldest published: 2026-02-04
- Stale rows: 1 / 24 (ratio 0.0417)
- Forward-dated rows: 0
- Age days min / median / max: 3 / 21.5 / 183

## 5. How to reproduce

```bash
python script/run_phase1.py
```
