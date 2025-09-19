"""Utility script for record-level diffs between two Feature Service items.

Usage examples:
    python examples/test_compare_records.py \
        --host-profile host_admin --guest-profile guest_admin \
        --host-item <HOST_ITEM_ID> --guest-item <GUEST_ITEM_ID> --json

    python examples/test_compare_records.py --host-item abc --guest-item def \
        --where "STATUS = 'Active'" --ignore-fields GlobalID OBJECTID

Authentication flags mirror those in other examples and can be supplied via
CLI, environment variables (MYGIS_HOST_*, MYGIS_GUEST_*), or config files.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Optional

from arcgis.gis import GIS

from mygis_core import config as config_mod
from mygis_core import log as log_mod
from mygis_core.collab import compare_feature_service_records


def _configure_logging_and_load_config(args) -> config_mod.Config:
    paths = [args.config] if args.config else None
    cfg = config_mod.load_config(paths=paths, env_override=not args.no_env_override)
    level = args.log_level or cfg.get("log_level")
    fmt = args.log_format or cfg.get("log_format")
    file = args.log_file or cfg.get("log_file")
    json_format: Optional[bool] = None if fmt is None else str(fmt).lower() == "json"
    log_mod.configure_logging(level=level, json_format=json_format, file=file)
    return cfg


def _gis_from_args_env(prefix: str, args, cfg: config_mod.Config) -> GIS:
    pfx = prefix.lower()
    profile = (
        getattr(args, f"{pfx}_profile", None)
        or os.environ.get(f"MYGIS_{pfx.upper()}_PROFILE")
        or cfg.get(f"{pfx}_profile")
    )
    if profile:
        return GIS(profile=str(profile))

    portal = (
        getattr(args, f"{pfx}_portal", None)
        or os.environ.get(f"MYGIS_{pfx.upper()}_PORTAL_URL")
        or os.environ.get(f"MYGIS_{pfx.upper()}_PORTAL")
        or cfg.get(f"{pfx}_portal_url")
        or cfg.get(f"{pfx}_portal")
    )
    username = (
        getattr(args, f"{pfx}_username", None)
        or os.environ.get(f"MYGIS_{pfx.upper()}_USERNAME")
        or cfg.get(f"{pfx}_username")
    )
    password = (
        getattr(args, f"{pfx}_password", None)
        or os.environ.get(f"MYGIS_{pfx.upper()}_PASSWORD")
        or cfg.get(f"{pfx}_password")
    )

    if portal and username and password:
        return GIS(str(portal), str(username), str(password))

    auth = getattr(args, f"{pfx}_auth", None) or cfg.get(f"{pfx}_auth", None)
    if auth:
        return GIS(str(auth))

    return GIS("pro")


def _split_fields(values: Optional[list[str]]) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    for value in values:
        if not value:
            continue
        result.extend(part for part in str(value).split(",") if part)
    return [v.strip() for v in result if v.strip()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Compare Feature Service records across two portals")
    p.add_argument("--host-item", dest="host_item", required=True, help="Host Feature Service item ID")
    p.add_argument("--guest-item", dest="guest_item", required=True, help="Guest Feature Service item ID")

    # Host auth
    p.add_argument("--host-profile", dest="host_profile", help="Host saved ArcGIS profile name")
    p.add_argument("--host-portal", dest="host_portal", help="Host portal URL")
    p.add_argument("--host-username", dest="host_username", help="Host username")
    p.add_argument("--host-password", dest="host_password", help="Host password")
    p.add_argument("--host-auth", dest="host_auth", choices=["pro", "home"], help="Host auth mode (ArcGIS Pro/Home)")

    # Guest auth
    p.add_argument("--guest-profile", dest="guest_profile", help="Guest saved ArcGIS profile name")
    p.add_argument("--guest-portal", dest="guest_portal", help="Guest portal URL")
    p.add_argument("--guest-username", dest="guest_username", help="Guest username")
    p.add_argument("--guest-password", dest="guest_password", help="Guest password")
    p.add_argument("--guest-auth", dest="guest_auth", choices=["pro", "home"], help="Guest auth mode (ArcGIS Pro/Home)")

    p.add_argument("--where", dest="where", help="Optional where clause to filter records")
    p.add_argument(
        "--ignore-fields",
        dest="ignore_fields",
        nargs="*",
        help="Field names (space or comma separated) to ignore in comparisons",
    )
    p.add_argument(
        "--layer-keys",
        dest="layer_keys",
        nargs="*",
        help="Limit comparison to specific layer/table keys (matching names)",
    )
    p.add_argument(
        "--chunk-size",
        dest="chunk_size",
        type=int,
        default=2000,
        help="Pagination size when fetching records (0 to fetch all in one request)",
    )

    p.add_argument("--json", action="store_true", help="Print full result JSON to stdout")
    p.add_argument("--quiet", action="store_true", help="Suppress info logs")

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

    host_gis = _gis_from_args_env("host", args, cfg)
    guest_gis = _gis_from_args_env("guest", args, cfg)

    ignore_fields = _split_fields(args.ignore_fields)
    layer_keys = _split_fields(args.layer_keys)

    res = compare_feature_service_records(
        host_gis,
        guest_gis,
        args.host_item,
        args.guest_item,
        where=args.where or "1=1",
        ignore_fields=ignore_fields or None,
        layer_keys=layer_keys or None,
        chunk_size=args.chunk_size,
        verbose=not args.quiet,
    )

    if args.json:
        print(json.dumps(res, ensure_ascii=False))
        return 0

    title = res.get("title")
    status = res.get("status")
    print(f"{title or ''} -> {status}")
    for section in ("layers", "tables"):
        group = res.get(section, []) or []
        for entry in group:
            entry_status = entry.get("status")
            if entry_status == "ok":
                continue
            name = entry.get("name")
            host_count = entry.get("host_count")
            guest_count = entry.get("guest_count")
            print(f" - {section[:-1]} '{name}' -> {entry_status} ({host_count} vs {guest_count})")
            if entry_status == "mismatch":
                host_only = entry.get("host_only") or []
                guest_only = entry.get("guest_only") or []
                if host_only:
                    print(f"   host-only: {len(host_only)} unique rows (showing up to 3)")
                    for row in host_only[:3]:
                        print(f"     count={row.get('count')}, attrs={row.get('attributes')}")
                if guest_only:
                    print(f"   guest-only: {len(guest_only)} unique rows (showing up to 3)")
                    for row in guest_only[:3]:
                        print(f"     count={row.get('count')}, attrs={row.get('attributes')}")
            elif entry_status in {"missing_on_guest", "missing_on_host"}:
                print(f"   counts: host={host_count} guest={guest_count}")
            elif entry_status == "error":
                print(f"   error: {entry.get('message')}")
            elif entry_status == "skipped":
                print(f"   note: {entry.get('message')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
