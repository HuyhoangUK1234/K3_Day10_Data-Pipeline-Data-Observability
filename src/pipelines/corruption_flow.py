from __future__ import annotations

from pathlib import Path

from core.config import load_settings
from core.utils import now_utc, read_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from pipelines.common import llm_status, load_dataset, save_dataset, step
from retrieval.index import LocalEmbeddingIndex


def _freshness_path(base: Path, suffix: str) -> Path:
    return base.with_name(f"{base.stem}_{suffix}{base.suffix}")


def main() -> None:
    """Corrupt the baseline corpus, measure the damage, repair from raw, and compare."""
    settings = load_settings()
    paths = settings.paths

    print("=" * 72)
    print("PHASE 2 - CORRUPTION, REPAIR AND COMPARISON")
    print("=" * 72)

    llm_ready, llm_detail = llm_status(settings)
    print(f"LLM provider: {llm_detail}" if llm_ready else f"WARNING: {llm_detail} (heuristic fallback judge)")

    # 1. Baseline inputs -----------------------------------------------------------
    step(1, "Load baseline artifacts")
    for required in (paths.clean_json, paths.eval_testset, paths.baseline_metrics):
        if not required.exists():
            raise FileNotFoundError(
                f"Missing baseline artifact {required}. Run `python script/run_phase1.py` first."
            )
    baseline_df = load_dataset(paths.clean_json)
    baseline_metrics = read_json(paths.baseline_metrics)
    test_set = read_json(paths.eval_testset)
    print(f"    baseline rows={len(baseline_df)} evaluation questions={len(test_set)}")
    print(f"    baseline retrieval_hit_rate={baseline_metrics.get('retrieval_hit_rate'):.4f}")

    # 2. Corrupt -------------------------------------------------------------------
    step(2, "Inject data corruption")
    corrupted_df = corrupt_clean_dataframe(baseline_df, paths.corruption_log)
    corruption_log = read_json(paths.corruption_log)
    for entry in corruption_log["steps"]:
        print(f"    {entry['step']}: {entry['count']} rows")
    print(f"    rows {corruption_log['input_rows']} -> {corruption_log['output_rows']}")
    save_dataset(corrupted_df, paths.corrupted_clean_csv, paths.corrupted_clean_json)

    # 3. Re-index and re-evaluate on the SAME frozen test set -----------------------
    step(3, "Rebuild the index on corrupted data and evaluate")
    corrupted_index = LocalEmbeddingIndex.build(corrupted_df, settings, paths.corrupted_embeddings_json)
    corrupted_bundle = evaluate_pipeline(
        settings=settings,
        index=corrupted_index,
        test_set_path=paths.eval_testset,
        metrics_output_path=paths.corrupted_metrics,
        answers_output_path=paths.corrupted_answers,
    )
    _print_metrics("corrupted", corrupted_bundle.summary)

    step(4, "Observability on the corrupted dataset")
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, report_name="corrupted")
    corrupted_freshness = build_freshness_report(
        corrupted_df, settings, _freshness_path(paths.freshness_report, "corrupted")
    )
    print(f"    quality={'PASS' if corrupted_quality['success'] else 'FAIL'} "
          f"({corrupted_quality['success_count']}/{corrupted_quality['check_count']}) "
          f"failed={corrupted_quality['failed_checks']}")
    print(f"    freshness={corrupted_freshness['status']} stale_rows={corrupted_freshness['stale_rows']}")

    # 4. Repair from the raw snapshot ----------------------------------------------
    step(5, "Repair the dataset from the raw source snapshot")
    raw_records = load_raw_records(paths.raw_records_json)
    repaired_df = build_clean_dataframe(raw_records, run_date=now_utc())
    print(f"    rebuilt {len(repaired_df)} rows from {len(raw_records)} raw records")
    save_dataset(repaired_df, paths.repaired_clean_csv, paths.repaired_clean_json)

    step(6, "Rebuild the index on repaired data and evaluate")
    repaired_index = LocalEmbeddingIndex.build(repaired_df, settings, paths.repaired_embeddings_json)
    repaired_bundle = evaluate_pipeline(
        settings=settings,
        index=repaired_index,
        test_set_path=paths.eval_testset,
        metrics_output_path=paths.repaired_metrics,
        answers_output_path=paths.repaired_answers,
    )
    _print_metrics("repaired", repaired_bundle.summary)

    step(7, "Observability on the repaired dataset")
    repaired_quality = run_data_quality_checks(repaired_df, settings, report_name="repaired")
    repaired_freshness = build_freshness_report(
        repaired_df, settings, _freshness_path(paths.freshness_report, "repaired")
    )
    print(f"    quality={'PASS' if repaired_quality['success'] else 'FAIL'} "
          f"({repaired_quality['success_count']}/{repaired_quality['check_count']})")
    print(f"    freshness={repaired_freshness['status']} stale_rows={repaired_freshness['stale_rows']}")

    # 5. Compare -------------------------------------------------------------------
    step(8, "Write the comparison report")
    generate_corruption_report(
        report_path=paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_bundle.summary,
        repaired_metrics=repaired_bundle.summary,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
    )
    print(f"    wrote {paths.comparison_report}")

    _print_comparison(baseline_metrics, corrupted_bundle.summary, repaired_bundle.summary)


def _print_metrics(label: str, summary: dict) -> None:
    for key in ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"):
        print(f"    {label} {key}: {summary[key]:.4f}")


def _print_comparison(baseline: dict, corrupted: dict, repaired: dict) -> None:
    print("\n" + "-" * 72)
    print(f"{'metric':<24}{'baseline':>12}{'corrupted':>12}{'repaired':>12}{'delta c-b':>12}")
    print("-" * 72)
    for key in ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"):
        base, corrupt, repair = baseline.get(key), corrupted.get(key), repaired.get(key)
        delta = corrupt - base if isinstance(base, (int, float)) and isinstance(corrupt, (int, float)) else 0.0
        print(f"{key:<24}{base:>12.4f}{corrupt:>12.4f}{repair:>12.4f}{delta:>+12.4f}")
    print("-" * 72)
