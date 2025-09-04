import configparser
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

try:  # Python 3.11+
    import tomllib  # type: ignore
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore

try:
    import yaml  # type: ignore
except Exception:  # avoid hard dependency
    yaml = None  # type: ignore


def _deep_merge(base: dict, new: dict) -> dict:
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _coerce_type(value: str, like: Any) -> Any:
    if like is None:
        # Try common coercions
        lowered = str(value).strip().lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            if "." in value:
                return float(value)
            return int(value)
        except Exception:
            return value
    if isinstance(like, bool):
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(like, int):
        try:
            return int(value)
        except Exception:
            return like
    if isinstance(like, float):
        try:
            return float(value)
        except Exception:
            return like
    return value


@dataclass
class Config:
    data: Dict[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def keys(self):
        return self.data.keys()

    def items(self):
        return self.data.items()

    def __getattr__(self, item: str) -> Any:
        try:
            return self.data[item]
        except KeyError as e:
            raise AttributeError(item) from e


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_toml(path: Path) -> dict:
    if not tomllib:
        return {}
    with path.open("rb") as f:  # tomllib expects bytes
        return tomllib.load(f)


def _read_yaml(path: Path) -> dict:
    if not yaml:
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _read_ini(path: Path) -> dict:
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    result: dict = {}
    # Merge DEFAULT and a section named "mygis" if present, else flatten first section
    if parser.defaults():
        result.update({k: v for k, v in parser.defaults().items()})
    if parser.has_section("mygis"):
        result.update({k: v for k, v in parser.items("mygis")})
    else:
        for section in parser.sections():
            result.update({f"{section}.{k}": v for k, v in parser.items(section)})
            break
    return result


def _read_env_file(path: Path) -> dict:
    data = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def _find_first(paths: Iterable[str]) -> Optional[Path]:
    for p in paths:
        path = Path(p)
        if path.exists() and path.is_file():
            return path
    return None


def load_config(
    *,
    defaults: Optional[Dict[str, Any]] = None,
    paths: Optional[Iterable[str]] = None,
    env_prefix: str = "MYGIS_",
    env_override: bool = True,
) -> Config:
    """Load configuration from file and environment variables.

    - File search order (first found wins): mygis.toml, mygis.yaml, mygis.yml,
      mygis.json, mygis.ini, .env
    - Environment variables with the given prefix override file values.
    - Types are coerced based on provided defaults when possible.
    """
    cfg: Dict[str, Any] = dict(defaults or {})

    search_order = paths or (
        "mygis.toml",
        "mygis.yaml",
        "mygis.yml",
        "mygis.json",
        "mygis.ini",
        ".env",
    )

    found = _find_first(search_order)
    file_data: dict = {}
    if found:
        suffix = found.suffix.lower()
        try:
            if suffix == ".toml":
                file_data = _read_toml(found)
            elif suffix in {".yaml", ".yml"}:
                file_data = _read_yaml(found)
            elif suffix == ".json":
                file_data = _read_json(found)
            elif suffix == ".ini":
                file_data = _read_ini(found)
            else:  # .env
                file_data = _read_env_file(found)
        except Exception:
            # Fail soft: leave file_data empty
            file_data = {}

    # Flatten top-level tables for toml/yaml/json where appropriate
    if isinstance(file_data, dict):
        if "mygis" in file_data and isinstance(file_data["mygis"], dict):
            file_layer = file_data["mygis"]
        else:
            file_layer = file_data
        _deep_merge(cfg, file_layer)

    if env_override:
        for k, v in os.environ.items():
            if not k.startswith(env_prefix):
                continue
            key = k[len(env_prefix) :].lower()
            like = cfg.get(key)
            cfg[key] = _coerce_type(v, like)

    return Config(cfg)


def load_and_apply_logging(cfg: Optional[Config] = None):
    """Helper that reads logging-related keys and configures logging.

    Supported keys (any not provided fall back to env vars):
    - log_level (str/int)
    - log_format ("json" or "plain")
    - log_file (path)
    """
    from . import log as log_mod

    cfg = cfg or load_config()
    level = cfg.get("log_level")
    fmt = cfg.get("log_format")
    file = cfg.get("log_file")
    json_format = None if fmt is None else str(fmt).lower() == "json"

    log_mod.configure_logging(level=level, json_format=json_format, file=file)
    return cfg

