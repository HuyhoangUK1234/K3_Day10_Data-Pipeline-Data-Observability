from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.config import Settings, normalized_provider, require_llm_credentials
from core.utils import read_json, write_csv, write_json


def step(number: int, title: str) -> None:
    print(f"\n[{number}] {title}")


def save_dataset(df: pd.DataFrame, csv_path: Path, json_path: Path) -> None:
    """Persist a dataset in both artifact formats used by the lab."""
    write_csv(df, csv_path)
    write_json(json_path, df.to_dict(orient="records"))
    print(f"    saved {len(df)} rows -> {csv_path.name}, {json_path.name}")


def load_dataset(json_path: Path) -> pd.DataFrame:
    """Read a dataset artifact back. JSON is preferred over CSV: it round-trips dtypes."""
    if not json_path.exists():
        raise FileNotFoundError(
            f"Missing dataset artifact {json_path}. Run `python script/run_phase1.py` first."
        )
    return pd.DataFrame(read_json(json_path))


def llm_status(settings: Settings) -> tuple[bool, str]:
    """Report whether an LLM provider is usable, without aborting the pipeline.

    Evaluation still produces numbers without a provider because the judge falls back to a
    token-overlap heuristic; the caller records which mode was used so reports stay honest.
    """
    try:
        require_llm_credentials(settings)
    except RuntimeError as error:
        return False, str(error)
    return True, f"{normalized_provider(settings)}:{settings.model_name}"
