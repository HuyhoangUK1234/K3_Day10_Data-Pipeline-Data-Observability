from __future__ import annotations

from typing import Any

import pandas as pd

from core.utils import first_sentence, write_json

MIN_DOCUMENTS = 4
DEFAULT_PAPERS = 5

# Question templates are phrased to match the intent keywords the QA layer keys on
# (`retrieval/qa.py::_extract_answer`), and quote the title so exact lookup can fire.
QUESTION_TEMPLATES: list[tuple[str, str, str]] = [
    ("summary", "What is the paper titled '{title}' about?", "summary"),
    ("authors", "Who authored the paper titled '{title}'?", "authors_joined"),
    ("date", "When was the paper titled '{title}' published?", "published"),
    ("categories", "What categories does the paper titled '{title}' cover?", "categories_joined"),
]


def _select_papers(df: pd.DataFrame, wanted: int) -> list[dict[str, Any]]:
    """Pick papers spread across the corpus so the set is not all newest-first."""
    # A quote inside the title would break the '...' capture the QA lookup relies on.
    usable = df[~df["title"].str.contains("'", regex=False, na=False)]
    usable = usable[usable["summary"].str.len() > 0]
    if usable.empty:
        usable = df

    records = usable.to_dict(orient="records")
    if len(records) <= wanted:
        return records

    step = len(records) / wanted
    return [records[min(int(index * step), len(records) - 1)] for index in range(wanted)]


def build_test_set(df: pd.DataFrame, output_path, max_papers: int = DEFAULT_PAPERS) -> list[dict[str, Any]]:
    """Derive a ground-truth QA set from the cleaned corpus and persist it as JSON.

    The same file is reused for the baseline, corrupted and repaired runs, so it is written
    once and treated as frozen unless the caller explicitly refreshes it.
    """
    if df is None or len(df) < MIN_DOCUMENTS:
        raise ValueError(
            f"Need at least {MIN_DOCUMENTS} cleaned documents to build a test set, got {0 if df is None else len(df)}."
        )

    papers = _select_papers(df, max_papers)
    test_set: list[dict[str, Any]] = []

    for paper in papers:
        for question_type, template, source_field in QUESTION_TEMPLATES:
            value = str(paper.get(source_field, "")).strip()
            if not value:
                continue
            ground_truth = first_sentence(value) if question_type == "summary" else value
            test_set.append(
                {
                    "id": f"{question_type}-{len(test_set):03d}",
                    "question_type": question_type,
                    "question": template.format(title=paper["title"]),
                    "ground_truth": ground_truth,
                    "ground_truth_doc_ids": [paper["paper_id"]],
                }
            )

    if not test_set:
        raise ValueError("Test set builder produced no samples; check the cleaned dataset columns.")

    write_json(output_path, test_set)
    return test_set
