from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import re
import subprocess
import sys

from core.config import Settings, load_settings
from core.utils import read_json
from pipelines.common import step

METRIC_KEYS = ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score")
METRIC_TOLERANCE = 1e-4

SECRET_PATTERNS = {
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "openai_api_key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "anthropic_api_key": re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"),
    "huggingface_token": re.compile(r"hf_[A-Za-z0-9]{30,}"),
}


@dataclass
class Result:
    """One verification outcome. `critical` failures make the whole run exit non-zero."""

    name: str
    passed: bool
    detail: str
    critical: bool = True

    @property
    def label(self) -> str:
        if self.passed:
            return "PASS"
        return "FAIL" if self.critical else "WARN"


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str, critical: bool = True) -> None:
        result = Result(name, passed, detail, critical)
        self.results.append(result)
        print(f"    [{result.label}] {name}: {detail}")

    @property
    def critical_failures(self) -> list[Result]:
        return [r for r in self.results if not r.passed and r.critical]

    @property
    def warnings(self) -> list[Result]:
        return [r for r in self.results if not r.passed and not r.critical]


def _close(left: float, right: float) -> bool:
    return abs(float(left) - float(right)) <= METRIC_TOLERANCE


def _question_fingerprint(items: list[dict]) -> list[tuple[str, str]]:
    """Identity of an evaluation set: which question ids carry which questions."""
    return sorted((str(item.get("id")), str(item.get("question"))) for item in items)


# --- 1. artifacts exist --------------------------------------------------------------


def check_artifacts_exist(report: Report, settings: Settings) -> None:
    paths = settings.paths
    required = {
        "raw response": paths.raw_api_response,
        "raw records": paths.raw_records_json,
        "clean json": paths.clean_json,
        "clean csv": paths.clean_csv,
        "corrupted clean json": paths.corrupted_clean_json,
        "repaired clean json": paths.repaired_clean_json,
        "embeddings manifest": paths.embeddings_json,
        "corrupted embeddings": paths.corrupted_embeddings_json,
        "repaired embeddings": paths.repaired_embeddings_json,
        "evaluation set": paths.eval_testset,
        "baseline metrics": paths.baseline_metrics,
        "corrupted metrics": paths.corrupted_metrics,
        "repaired metrics": paths.repaired_metrics,
        "baseline answers": paths.baseline_answers,
        "corrupted answers": paths.corrupted_answers,
        "repaired answers": paths.repaired_answers,
        "corruption log": paths.corruption_log,
        "freshness report": paths.freshness_report,
        "baseline report": paths.baseline_report,
        "comparison report": paths.comparison_report,
    }
    missing = [name for name, path in required.items() if not path.exists()]
    report.add(
        "artifacts_present",
        not missing,
        f"{len(required) - len(missing)}/{len(required)} required artifacts found"
        + (f"; missing: {', '.join(missing)}" if missing else ""),
    )


# --- 2. the evaluation set stays frozen across all three states ----------------------


def check_frozen_test_set(report: Report, settings: Settings) -> None:
    """Baseline, corrupted and repaired must be scored on the same questions.

    Regenerating the test set from corrupted data would derive ground truth from the very
    rows that are broken, and every comparison downstream would be meaningless.
    """
    paths = settings.paths
    if not paths.eval_testset.exists():
        report.add("frozen_test_set", False, "evaluation set missing, cannot compare states")
        return

    expected = _question_fingerprint(read_json(paths.eval_testset))
    states = {
        "baseline": paths.baseline_answers,
        "corrupted": paths.corrupted_answers,
        "repaired": paths.repaired_answers,
    }
    mismatched = []
    for state, path in states.items():
        if not path.exists():
            mismatched.append(f"{state} (missing)")
            continue
        if _question_fingerprint(read_json(path)) != expected:
            mismatched.append(state)

    report.add(
        "frozen_test_set",
        not mismatched,
        f"{len(expected)} questions shared by baseline/corrupted/repaired"
        if not mismatched
        else f"question set differs in: {', '.join(mismatched)}",
    )


# --- 3. repair rebuilds from raw instead of patching corrupted rows ------------------


def check_repair_fidelity(report: Report, settings: Settings) -> None:
    paths = settings.paths
    if not (paths.clean_json.exists() and paths.repaired_clean_json.exists()):
        report.add("repair_matches_baseline", False, "clean or repaired dataset missing")
        return

    baseline_rows = read_json(paths.clean_json)
    repaired_rows = read_json(paths.repaired_clean_json)
    identical = baseline_rows == repaired_rows
    report.add(
        "repair_matches_baseline",
        identical,
        f"repaired dataset reproduces baseline exactly ({len(baseline_rows)} rows)"
        if identical
        else f"repaired {len(repaired_rows)} rows differ from baseline {len(baseline_rows)} rows",
    )


# --- 4. metrics move the way corruption and repair predict --------------------------


def check_metric_trajectory(report: Report, settings: Settings) -> None:
    paths = settings.paths
    files = {
        "baseline": paths.baseline_metrics,
        "corrupted": paths.corrupted_metrics,
        "repaired": paths.repaired_metrics,
    }
    if any(not path.exists() for path in files.values()):
        report.add("metric_trajectory", False, "one or more metrics files missing")
        return

    metrics = {state: read_json(path) for state, path in files.items()}

    sample_counts = {state: data.get("samples") for state, data in metrics.items()}
    report.add(
        "same_sample_count",
        len(set(sample_counts.values())) == 1,
        f"samples={sample_counts}",
    )

    degraded = [key for key in METRIC_KEYS if metrics["corrupted"][key] < metrics["baseline"][key]]
    report.add(
        "corruption_degrades_metrics",
        bool(degraded),
        f"{len(degraded)}/{len(METRIC_KEYS)} metrics dropped after corruption: {', '.join(degraded)}"
        if degraded
        else "no metric dropped; corruption did not reach the agent",
    )

    unrecovered = [
        key for key in METRIC_KEYS if not _close(metrics["repaired"][key], metrics["baseline"][key])
    ]
    report.add(
        "repair_restores_metrics",
        not unrecovered,
        "all four metrics returned to the baseline value"
        if not unrecovered
        else f"still off baseline: {', '.join(unrecovered)}",
    )


# --- 5. quality and freshness signals react before the metrics do -------------------


def check_quality_signals(report: Report, settings: Settings) -> None:
    quality_dir = settings.paths.quality_dir
    files = {
        "baseline": quality_dir / "baseline_quality.json",
        "corrupted": quality_dir / "corrupted_quality.json",
        "repaired": quality_dir / "repaired_quality.json",
    }
    if any(not path.exists() for path in files.values()):
        report.add("quality_signals", False, "one or more quality reports missing")
        return

    quality = {state: read_json(path) for state, path in files.items()}
    expected_success = {"baseline": True, "corrupted": False, "repaired": True}
    wrong = {
        state: quality[state]["success"]
        for state, want in expected_success.items()
        if quality[state]["success"] is not want
    }
    summary = ", ".join(
        f"{state}={'PASS' if data['success'] else 'FAIL'} "
        f"({data['success_count']}/{data['check_count']})"
        for state, data in quality.items()
    )
    report.add(
        "quality_signals",
        not wrong,
        summary if not wrong else f"unexpected quality verdicts {wrong}; got {summary}",
    )

    report.add(
        "corruption_raises_critical_failures",
        bool(quality["corrupted"]["critical_failed_checks"]),
        f"critical failures on corrupted data: {quality['corrupted']['critical_failed_checks']}"
        if quality["corrupted"]["critical_failed_checks"]
        else "corruption produced no critical quality failure",
    )


def check_freshness_signals(report: Report, settings: Settings) -> None:
    base = settings.paths.freshness_report
    files = {
        "baseline": base,
        "corrupted": base.with_name(f"{base.stem}_corrupted{base.suffix}"),
        "repaired": base.with_name(f"{base.stem}_repaired{base.suffix}"),
    }
    if any(not path.exists() for path in files.values()):
        report.add("freshness_signals", False, "one or more freshness reports missing")
        return

    freshness = {state: read_json(path) for state, path in files.items()}
    stale = {state: data["stale_rows"] for state, data in freshness.items()}
    report.add(
        "freshness_reacts_to_corruption",
        stale["corrupted"] > stale["baseline"] and stale["repaired"] == stale["baseline"],
        f"stale_rows baseline={stale['baseline']} corrupted={stale['corrupted']} "
        f"repaired={stale['repaired']}",
    )

    future_dated = {state: data["future_dated_rows"] for state, data in freshness.items()}
    report.add(
        "no_future_dated_rows",
        all(count == 0 for count in future_dated.values()),
        f"future_dated_rows={future_dated}",
    )


# --- 6. the corruption log is traceable --------------------------------------------


def check_corruption_log(report: Report, settings: Settings) -> None:
    paths = settings.paths
    if not paths.corruption_log.exists():
        report.add("corruption_log_traceable", False, "corruption log missing")
        return

    log = read_json(paths.corruption_log)
    problems = []
    if log.get("seed") is None:
        problems.append("no seed recorded")
    for entry in log.get("steps", []):
        if not entry.get("affected_paper_ids"):
            problems.append(f"{entry.get('step')} lists no affected paper ids")

    report.add(
        "corruption_log_traceable",
        not problems,
        f"seed={log.get('seed')}, {len(log.get('steps', []))} steps, "
        f"rows {log.get('input_rows')} -> {log.get('output_rows')}"
        if not problems
        else "; ".join(problems),
    )

    if paths.corrupted_clean_json.exists():
        actual_rows = len(read_json(paths.corrupted_clean_json))
        report.add(
            "corruption_log_matches_dataset",
            actual_rows == log.get("output_rows"),
            f"log says {log.get('output_rows')} rows, corrupted dataset has {actual_rows}",
        )


# --- 7. the written report matches the artifacts -----------------------------------


def _markdown_metric_row(text: str, metric: str) -> list[str] | None:
    """Pull baseline/corrupted/repaired numbers out of a Markdown comparison table.

    A metric name shows up in several tables of the report, so match every row and keep the
    first one whose leading three cells are all numeric - that is the comparison table.
    """
    pattern = re.compile(rf"^\|\s*`?{re.escape(metric)}`?\s*\|(.+)$", re.MULTILINE)
    for match in pattern.finditer(text):
        cells = [cell.strip().strip("*` ") for cell in match.group(1).split("|")]
        if len(cells) < 3:
            continue
        try:
            [float(cell) for cell in cells[:3]]
        except ValueError:
            continue
        return cells
    return None


def check_report_matches_artifacts(report: Report, settings: Settings, group_report: Path) -> None:
    """Guard against the one failure mode a passing pipeline cannot catch: a report that
    quotes numbers the artifacts do not contain."""
    if not group_report.exists():
        report.add("report_matches_artifacts", False, f"{group_report.name} not found", critical=False)
        return

    paths = settings.paths
    if any(
        not path.exists()
        for path in (paths.baseline_metrics, paths.corrupted_metrics, paths.repaired_metrics)
    ):
        report.add("report_matches_artifacts", False, "metrics files missing", critical=False)
        return

    text = group_report.read_text(encoding="utf-8")
    actual = {
        "baseline": read_json(paths.baseline_metrics),
        "corrupted": read_json(paths.corrupted_metrics),
        "repaired": read_json(paths.repaired_metrics),
    }

    mismatches = []
    checked = 0
    for metric in METRIC_KEYS:
        cells = _markdown_metric_row(text, metric)
        if cells is None or len(cells) < 3:
            mismatches.append(f"{metric}: no comparison row found in report")
            continue
        for offset, state in enumerate(("baseline", "corrupted", "repaired")):
            try:
                claimed = float(cells[offset])
            except ValueError:
                mismatches.append(f"{metric}/{state}: '{cells[offset]}' is not a number")
                continue
            checked += 1
            if not _close(claimed, actual[state][metric]):
                mismatches.append(
                    f"{metric}/{state}: report says {claimed:.4f}, artifact says {actual[state][metric]:.4f}"
                )

    report.add(
        "report_matches_artifacts",
        not mismatches,
        f"{checked} reported numbers match data/results/"
        if not mismatches
        else "; ".join(mismatches),
    )


# --- 8. hygiene: no secrets, no machine-specific paths -----------------------------


def check_no_secrets(report: Report, settings: Settings, scan_dirs: list[Path]) -> None:
    hits = []
    for directory in scan_dirs:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".log", ".csv", ".txt"}:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(content):
                    hits.append(f"{label} in {path.relative_to(settings.paths.project_dir)}")

    report.add(
        "no_secrets_in_artifacts",
        not hits,
        f"scanned {len(scan_dirs)} directories, no credential pattern found"
        if not hits
        else "; ".join(hits),
    )

    try:
        tracked = subprocess.run(
            ["git", "ls-files", ".env"],
            cwd=settings.paths.project_dir,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    except OSError:
        tracked = ""
    report.add(
        "env_file_not_tracked",
        not tracked,
        ".env is not tracked by git" if not tracked else f"git tracks: {tracked}",
    )


def check_portable_paths(report: Report, settings: Settings) -> None:
    """Absolute paths baked into an artifact make it machine-specific, so a teammate
    re-running the pipeline gets a diff that is noise rather than a real change."""
    paths = settings.paths
    offenders = []
    for path in (paths.embeddings_json, paths.corrupted_embeddings_json, paths.repaired_embeddings_json):
        if not path.exists():
            continue
        manifest = read_json(path)
        persist = str(manifest.get("persist_path", ""))
        if re.match(r"^[A-Za-z]:[\\/]|^/", persist):
            offenders.append(f"{path.name} stores an absolute persist_path")

    report.add(
        "artifacts_are_portable",
        not offenders,
        "no absolute paths stored in embedding manifests"
        if not offenders
        else "; ".join(offenders) + " (differs per machine; consider storing it relative to the project)",
        critical=False,
    )


# --- entry point -------------------------------------------------------------------


def main() -> int:
    """Verify that the artifacts on disk support the claims made in the reports."""
    # Report details can quote Vietnamese table cells; the default Windows console codepage
    # would raise UnicodeEncodeError before the summary is ever printed.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    settings = load_settings()
    report = Report()

    print("=" * 72)
    print("ARTIFACT AND REPORT VERIFICATION")
    print("=" * 72)

    step(1, "Artifact inventory")
    check_artifacts_exist(report, settings)

    step(2, "Evaluation set is frozen across all three states")
    check_frozen_test_set(report, settings)

    step(3, "Repair rebuilds the baseline dataset")
    check_repair_fidelity(report, settings)

    step(4, "Metric trajectory: baseline -> corrupted -> repaired")
    check_metric_trajectory(report, settings)

    step(5, "Data quality signals")
    check_quality_signals(report, settings)

    step(6, "Freshness signals")
    check_freshness_signals(report, settings)

    step(7, "Corruption log traceability")
    check_corruption_log(report, settings)

    step(8, "Reported numbers vs artifacts")
    check_report_matches_artifacts(report, settings, settings.paths.project_dir / "report" / "group_report.md")

    step(9, "Hygiene")
    check_no_secrets(
        report,
        settings,
        [settings.paths.project_dir / "report", settings.paths.project_dir / "data" / "reports"],
    )
    check_portable_paths(report, settings)

    passed = sum(1 for r in report.results if r.passed)
    print("\n" + "-" * 72)
    print(f"{passed}/{len(report.results)} checks passed, "
          f"{len(report.critical_failures)} failed, {len(report.warnings)} warnings")
    print("-" * 72)

    for failure in report.critical_failures:
        print(f"FAIL {failure.name}: {failure.detail}")
    for warning in report.warnings:
        print(f"WARN {warning.name}: {warning.detail}")

    summary_path = settings.paths.project_dir / "data" / "reports" / "verification_report.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "check_count": len(report.results),
                "success_count": passed,
                "failure_count": len(report.critical_failures),
                "warning_count": len(report.warnings),
                "success": not report.critical_failures,
                "checks": [
                    {
                        "name": r.name,
                        "status": r.label,
                        "critical": r.critical,
                        "detail": r.detail,
                    }
                    for r in report.results
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"wrote {summary_path}")

    return 1 if report.critical_failures else 0
