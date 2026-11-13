"""Load versioned alert-threshold defaults and apply an operator override.

The checked-in file `alerts.defaults.json` is the v1 default document.
An operator may point collectors at an `alert.thresholds.override/v1`
file; omitted keys keep the defaults. This module does not collect
metrics or send alerts.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    from .validate import SCHEMA_DIR, SchemaError, Validator
except ImportError:  # unittest discover adds this directory to sys.path
    from validate import SCHEMA_DIR, SchemaError, Validator

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULTS_PATH = PACKAGE_DIR / "alerts.defaults.json"
THRESHOLDS_SCHEMA = "alert-thresholds.schema.json"
OVERRIDE_SCHEMA = "alert-thresholds-override.schema.json"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise SchemaError(f"{path}: expected a JSON object")
    return data


def load_thresholds(
    override_path: Path | None = None,
    *,
    defaults_path: Path = DEFAULTS_PATH,
    schema_dir: Path = SCHEMA_DIR,
) -> dict[str, Any]:
    """Return a complete alert.thresholds/v1 document.

    If override_path is set, validate it as an override and merge it on
    top of the defaults. Destinations in an override replace the default
    list; thresholds and actions merge key by key.
    """
    validator = Validator(schema_dir)
    defaults = _load_json(defaults_path)
    validator.validate_file(defaults, THRESHOLDS_SCHEMA)
    if override_path is None:
        return defaults

    override = _load_json(Path(override_path))
    validator.validate_file(override, OVERRIDE_SCHEMA)
    if override.get("schema_version") != defaults["schema_version"]:
        raise SchemaError("override schema_version does not match the defaults")

    merged = deepcopy(defaults)
    if "destinations" in override:
        merged["destinations"] = list(override["destinations"])
    if "thresholds" in override:
        merged["thresholds"].update(override["thresholds"])
    if "actions" in override:
        merged["actions"].update(override["actions"])
    validator.validate_file(merged, THRESHOLDS_SCHEMA)
    return merged
