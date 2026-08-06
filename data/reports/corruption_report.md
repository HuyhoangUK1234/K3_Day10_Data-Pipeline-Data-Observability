# Phase 2 - Corruption, Repair and Comparison Report

Generated at: `2026-08-06T04:04:41.188691+00:00`

All three states are evaluated on the **same frozen evaluation set**, so the deltas below
are attributable to the dataset, not to a different set of questions.

## 1. Metric comparison

| Metric | Baseline | Corrupted | Repaired | Corrupted vs baseline | Repaired vs baseline |
| --- | --- | --- | --- | --- | --- |
| Retrieval hit rate | 1.0000 | 0.8000 | 1.0000 | -0.2000 v | +0.0000 = |
| Mean token F1 | 1.0000 | 0.7593 | 1.0000 | -0.2407 v | +0.0000 = |
| Judge accuracy | 1.0000 | 0.7500 | 1.0000 | -0.2500 v | +0.0000 = |
| Mean judge score (1-5) | 5.0000 | 4.0000 | 5.0000 | -1.0000 v | +0.0000 = |

Sample counts - baseline: 20, corrupted: 20, repaired: 20.

## 2. Data quality

| State | Result | Passed / total | Critical failures | Warnings |
| --- | --- | --- | --- | --- |
| Corrupted | **FAIL** | 6/11 | paper_id_unique, summary_not_empty, summary_min_length | title_unique, freshness_within_threshold |
| Repaired | PASS | 10/11 | - | freshness_within_threshold |

### Corrupted dataset checks

| Check | Severity | Expectation | Observed | Result |
| --- | --- | --- | --- | --- |
| `row_count_minimum` | critical | row_count >= 10 | 23 | PASS |
| `paper_id_not_null` | critical | paper_id has no blank value | 0 | PASS |
| `paper_id_unique` | critical | paper_id is unique | 2 | **FAIL** |
| `title_not_null` | critical | title has no blank value | 0 | PASS |
| `title_min_length` | critical | title length >= 10 | 0 | PASS |
| `title_unique` | warning | no duplicate titles | 2 | WARN |
| `summary_not_empty` | critical | summary is populated | 3 | **FAIL** |
| `summary_min_length` | critical | summary length >= 80 | 3 | **FAIL** |
| `text_for_embedding_not_empty` | critical | text_for_embedding is populated | 0 | PASS |
| `published_not_in_future` | warning | publication date is not ahead of the run date | 0 | PASS |
| `freshness_within_threshold` | warning | age_days <= 180 for every row | 4 | WARN |

### Repaired dataset checks

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

## 3. Freshness

### Corrupted

- Status: **STALE** (is_fresh = no)
- Threshold: 180 days
- Latest published: 2026-07-30
- Oldest published: 2022-03-21
- Stale rows: 4 / 23 (ratio 0.1739)
- Forward-dated rows: 0
- Age days min / median / max: 7 / 25.0 / 1599

### Repaired

- Status: **STALE** (is_fresh = no)
- Threshold: 180 days
- Latest published: 2026-08-03
- Oldest published: 2026-02-04
- Stale rows: 1 / 24 (ratio 0.0417)
- Forward-dated rows: 0
- Age days min / median / max: 3 / 21.5 / 183

## 4. Observations

- Corruption degraded 4/4 metrics: Retrieval hit rate, Mean token F1, Judge accuracy, Mean judge score (1-5).
- Repair improved 4/4 metrics over the corrupted state: Retrieval hit rate, Mean token F1, Judge accuracy, Mean judge score (1-5).
- Data quality moved from FAIL (corrupted) to PASS (repaired).
- Freshness: corrupted = STALE with 4/23 stale rows (oldest 2022-03-21); repaired = STALE with 1/24 stale rows (oldest 2026-02-04).

## 5. How to reproduce

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```
