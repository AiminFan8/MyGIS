"""List replicas for all hosted services with sync enabled.

Usage:
    python examples/list_sync_enabled_services.py [--json] [--config examples/mygis.toml]
"""

from __future__ import annotations

import argparse
import json
from typing import Optional

from mygis_core import config as config_mod
from mygis_core import log as log_mod
from mygis_core.replicas import list_replicas_for_sync_enabled_services


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
    p = argparse.ArgumentParser(description="List replicas for all hosted services with sync enabled")
    p.add_argument("--json", action="store_true", help="Print results as JSON to stdout")
    p.add_argument("--query", help="Custom search query for services (optional)")
    p.add_argument("--owner", help="Owner filter: username, 'me', or '*' for any")
    p.add_argument("--max-items", type=int, default=1000, help="Max services to inspect (default 1000)")

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
    cfg = _configure_logging_and_load_config(args)
    owner = args.owner or cfg.get("search_owner") or cfg.get("owner")
    results = list_replicas_for_sync_enabled_services(
        query=args.query, owner=owner, max_items=args.max_items, verbose=not args.json
    )
    if args.json:
        print(json.dumps(results, ensure_ascii=False))
    else:
        total_reps = sum(len(r.get("replicas", [])) for r in results)
        print(f"Services with sync enabled: {len(results)}; total replicas: {total_reps}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
