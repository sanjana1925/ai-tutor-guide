"""Evaluation report storage. A metric that has not actually been run is reported as not evaluated."""
import json
from pathlib import Path
from typing import Any, Dict

from backend import config

REPORT_PATH = config.DATA_DIR / "evaluation_report.json"
SCHEMA_VERSION = 2


def load_report(path: Path = REPORT_PATH) -> Dict[str, Any]:
    """
    Returns the latest verified evaluation report, or {"status": "no_data"}.
    Reports written before schema v2 are ignored: they were produced without checking that the
    evaluated document was indexed, so their numbers cannot be trusted.
    """
    if not path.exists():
        return {"status": "no_data"}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "no_data"}
    if report.get("schema_version") != SCHEMA_VERSION:
        return {"status": "no_data", "reason": "legacy report without verification; run `python evaluate.py`"}
    return report


def save_report(report: Dict[str, Any], path: Path = REPORT_PATH) -> None:
    report = {**report, "schema_version": SCHEMA_VERSION}
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
