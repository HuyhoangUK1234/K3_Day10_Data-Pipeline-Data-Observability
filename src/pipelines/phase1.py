from __future__ import annotations

from core.config import load_settings
from core.utils import now_utc, read_json, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from pipelines.common import llm_status, save_dataset, step
from retrieval.index import LocalEmbeddingIndex

DEMO_QUESTION_LIMIT = 3


def main() -> None:
    """Run the clean-data baseline end to end and emit every phase 1 artifact."""
    settings = load_settings()
    paths = settings.paths
    run_date = now_utc()

    print("=" * 72)
    print("PHASE 1 - BASELINE PIPELINE (clean data)")
    print("=" * 72)

    llm_ready, llm_detail = llm_status(settings)
    if llm_ready:
        print(f"LLM provider: {llm_detail}")
    else:
        print(f"WARNING: {llm_detail}")
        print("         Continuing with the heuristic fallback judge; judge_* metrics are not LLM-based.")

    # 1. Raw ingestion -------------------------------------------------------------
    step(1, "Load raw records")
    if settings.refresh_source or not paths.raw_records_json.exists():
        records = fetch_source_records(settings)
    else:
        records = load_raw_records(paths.raw_records_json)
        print(f"    reused snapshot {paths.raw_records_json.name} ({len(records)} records)")
        print("    set REFRESH_SOURCE=1 to re-fetch from Crossref")

    if not records:
        raise RuntimeError("Crossref returned no usable records; widen the query or filter in core/config.py.")

    # 2. Cleaning ------------------------------------------------------------------
    step(2, "Clean and model the dataset")
    df = build_clean_dataframe(records, run_date=run_date)
    if df.empty:
        raise RuntimeError("Cleaning dropped every record; inspect data/raw/ before continuing.")
    print(f"    {len(records)} raw -> {len(df)} clean rows, {len(df.columns)} columns")
    save_dataset(df, paths.clean_csv, paths.clean_json)

    # 3. Embedding + vector store --------------------------------------------------
    step(3, "Build the embedding index")
    index = LocalEmbeddingIndex.build(df, settings, paths.embeddings_json)
    print(f"    collection '{index.collection_name}' with {len(index.documents)} documents")

    # 4. Evaluation set ------------------------------------------------------------
    step(4, "Prepare the evaluation set")
    if settings.refresh_test_set or not paths.eval_testset.exists():
        test_set = build_test_set(df, paths.eval_testset)
        print(f"    built {len(test_set)} questions -> {paths.eval_testset.name}")
    else:
        test_set = read_json(paths.eval_testset)
        print(f"    reused frozen test set ({len(test_set)} questions)")
        print("    set REFRESH_TEST_SET=1 to rebuild it")

    # 5. Evaluate ------------------------------------------------------------------
    step(5, "Evaluate the agent on the baseline corpus")
    bundle = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=paths.eval_testset,
        metrics_output_path=paths.baseline_metrics,
        answers_output_path=paths.baseline_answers,
    )
    for key in ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"):
        print(f"    {key}: {bundle.summary[key]:.4f}")

    # 6. Observability -------------------------------------------------------------
    step(6, "Run data quality checks")
    quality = run_data_quality_checks(df, settings, report_name="baseline")
    print(f"    {quality['success_count']}/{quality['check_count']} checks passed "
          f"({'PASS' if quality['success'] else 'FAIL'})")

    step(7, "Build the freshness report")
    freshness = build_freshness_report(df, settings, paths.freshness_report)
    print(f"    status={freshness['status']} stale_rows={freshness['stale_rows']}/{freshness['total_rows']}")

    # 7. Report --------------------------------------------------------------------
    step(8, "Write the baseline Markdown report")
    source_summary = {
        "run_date": run_date.isoformat(),
        "source_api": settings.source_api,
        "query": settings.source_query,
        "filter": settings.source_filter,
        "max_results": settings.max_results,
        "raw_records": len(records),
        "clean_rows": len(df),
        "embedding_model": settings.embedding_model,
        "collection_name": index.collection_name,
        "top_k": settings.top_k,
        "llm_provider": llm_detail if llm_ready else "unavailable (heuristic fallback judge)",
        "evaluation_samples": len(test_set),
    }
    generate_phase1_report(paths.baseline_report, source_summary, bundle.summary, quality, freshness)
    print(f"    wrote {paths.baseline_report}")

    # 8. Optional agent demo -------------------------------------------------------
    step(9, "Demo the tool-calling agent")
    if llm_ready:
        _run_agent_demo(settings, index, test_set)
    else:
        print("    skipped: no LLM provider configured")

    print("\nBaseline complete. Next: python script/run_corruption_flow.py")


def _run_agent_demo(settings, index, test_set) -> None:
    """Exercise the LangChain agent on a few questions and store the transcript."""
    from retrieval.agent import build_agent, run_agent_question

    try:
        agent = build_agent(settings, index)
    except Exception as error:  # pragma: no cover - depends on provider availability
        print(f"    skipped: could not build the agent ({error})")
        return

    demo: list[dict[str, str]] = []
    for item in test_set[:DEMO_QUESTION_LIMIT]:
        try:
            answer = run_agent_question(agent, item["question"])
        except Exception as error:  # pragma: no cover - network/provider errors
            answer = f"<agent error: {error}>"
        demo.append({"question": item["question"], "ground_truth": item["ground_truth"], "agent_answer": answer})
        print(f"    Q: {item['question']}")
        print(f"    A: {str(answer)[:160]}")

    write_json(settings.paths.demo_answers, demo)
    print(f"    wrote {settings.paths.demo_answers.name}")
