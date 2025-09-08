"""Small test script for comparing two collaborated Feature Service items.

Usage examples:
    # Using profiles for host and guest portals
    python examples/test_collab_items.py \
        --host-profile host_admin --guest-profile guest_admin \
        --host-item <HOST_ITEM_ID> --guest-item <GUEST_ITEM_ID> --json

    # Using explicit credentials via env or args
    set MYGIS_HOST_PORTAL_URL=https://host.domain/portal
    set MYGIS_HOST_USERNAME=admin
    set MYGIS_HOST_PASSWORD=***
    set MYGIS_GUEST_PORTAL_URL=https://guest.domain/portal
    set MYGIS_GUEST_USERNAME=admin
    set MYGIS_GUEST_PASSWORD=***
    python examples/test_collab_items.py --host-item abc --guest-item def

Authentication can be supplied via args, environment variables, or config:
  - Args: --host-profile/--guest-profile or --host-portal/--host-username/--host-password, etc.
  - Env:  MYGIS_HOST_PROFILE, MYGIS_HOST_PORTAL_URL, MYGIS_HOST_USERNAME, MYGIS_HOST_PASSWORD
          MYGIS_GUEST_PROFILE, MYGIS_GUEST_PORTAL_URL, MYGIS_GUEST_USERNAME, MYGIS_GUEST_PASSWORD
  - Config: keys host_profile/guest_profile, host_portal_url/guest_portal_url, etc.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Optional

from arcgis.gis import GIS

from mygis_core import config as config_mod
from mygis_core import log as log_mod
from mygis_core.collab import compare_feature_service_items


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
    # 1) profile
    profile = getattr(args, f"{pfx}_profile", None) or os.environ.get(f"MYGIS_{pfx.upper()}_PROFILE") or cfg.get(f"{pfx}_profile")
    if profile:
        return GIS(profile=str(profile))

    # 2) explicit portal credentials
    portal = (
        getattr(args, f"{pfx}_portal", None)
        or os.environ.get(f"MYGIS_{pfx.upper()}_PORTAL_URL")
        or os.environ.get(f"MYGIS_{pfx.upper()}_PORTAL")
        or cfg.get(f"{pfx}_portal_url")
        or cfg.get(f"{pfx}_portal")
    )
    username = getattr(args, f"{pfx}_username", None) or os.environ.get(f"MYGIS_{pfx.upper()}_USERNAME") or cfg.get(f"{pfx}_username")
    password = getattr(args, f"{pfx}_password", None) or os.environ.get(f"MYGIS_{pfx.upper()}_PASSWORD") or cfg.get(f"{pfx}_password")

    if portal and username and password:
        return GIS(str(portal), str(username), str(password))

    # 3) fallback: Pro/Home
    auth = getattr(args, f"{pfx}_auth", None) or cfg.get(f"{pfx}_auth", None)
    if auth:
        return GIS(str(auth))

    # Last resort
    return GIS("pro")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Test compare_feature_service_items across two portals")
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

    p.add_argument("--json", action="store_true", help="Print full result JSON to stdout")
    p.add_argument("--quiet", action="store_true", help="Suppress info logs")

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

    host_gis = _gis_from_args_env("host", args, cfg)
    guest_gis = _gis_from_args_env("guest", args, cfg)

    res = compare_feature_service_items(host_gis, guest_gis, args.host_item, args.guest_item, verbose=not args.quiet)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        status = res.get("status")
        title = res.get("title")
        print(f"{title or ''} -> {status}")
        # Print quick per-layer mismatches
        for section in ("layers", "tables"):
            for r in res.get(section, []) or []:
                if r.get("status") != "ok":
                    print(
                        f" - {section[:-1]} '{r.get('name')}' -> {r.get('status')} "
                        f"(counts: {r.get('host_count')} vs {r.get('guest_count')}, "
                        f"lastEdit: {r.get('host_last_edit')} vs {r.get('guest_last_edit')})"
                    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

