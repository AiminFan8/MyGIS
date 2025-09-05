"""Small test script for listing replicas.

Usage examples:
    python examples/test_list_replicas.py "https://.../FeatureServer/0"
    python examples/test_list_replicas.py a1b2c3d4e5f6g7h8i9j0klmn --json
    python examples/test_list_replicas.py "https://.../FeatureServer" --config examples/mygis.toml

Authentication is resolved by mygis_core.auth using config or env vars. See
examples/mygis.toml and README.md for details.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Optional

from mygis_core import config as config_mod
from mygis_core import log as log_mod
from mygis_core.replicas import list_replicas


def _configure_logging_and_load_config(args) -> config_mod.Config:
    paths = [args.config] if args.config else None
    cfg = config_mod.load_config(paths=paths, env_override=not args.no_env_override)
    level = args.log_level or cfg.get("log_level")
    fmt = args.log_format or cfg.get("log_format")
    file = args.log_file or cfg.get("log_file")
    json_format: Optional[bool] = None if fmt is None else str(fmt).lower() == "json"
    log_mod.configure_logging(level=level, json_format=json_format, file=file)
    return cfg


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Test list_replicas helper")
    p.add_argument("service", nargs="?", help="FeatureService root URL, layer URL, or Item ID")
    p.add_argument("--service", dest="service_opt", help="Service URL or Item ID (alternative to positional)")
    p.add_argument("--json", action="store_true", help="Print replicas as JSON to stdout")
    p.add_argument("--quiet", action="store_true", help="Suppress summary table logging")

    # Logging + config common flags
    p.add_argument("--log-level", dest="log_level", help="Set log level (DEBUG, INFO, WARNING, ERROR)")
    p.add_argument("--log-format", dest="log_format", choices=["plain", "json"], help="Log output format")
    p.add_argument("--log-file", dest="log_file", help="Write logs to file path")
    p.add_argument("--config", dest="config", help="Config file path (toml/yaml/json/ini/.env)")
    p.add_argument("--no-env-override", action="store_true", help="Do not let env vars override file/defaults")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging_and_load_config(args)
    # Resolve service from positional -> --service -> env -> config
    service = (
        args.service
        or args.service_opt
        or os.environ.get("MYGIS_SERVICE")
    )
    if not service:
        # Try config keys (works with TOML/YAML/JSON/INI); also check prefixed key for .env files
        cfg = config_mod.load_config(paths=[args.config] if args.config else None, env_override=not args.no_env_override)
        service = (
            cfg.get("service")
            or cfg.get("service_url")
            or cfg.get("feature_service")
            or cfg.get("MYGIS_SERVICE")
        )

    if not service:
        parser.error("service is required (positional, --service, MYGIS_SERVICE, or config key 'service'/'service_url')")

    reps = list_replicas(service, verbose=not args.quiet)
    if args.json:
        print(json.dumps(reps, ensure_ascii=False))
    else:
        print(f"Found {len(reps)} replicas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
