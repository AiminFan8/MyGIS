"""Check collaboration workspace item parity (counts and last edit times).

Compares hosted Feature Service items shared between two collaboration groups
on different portals (e.g., host and guest) using ArcGIS API for Python.

Usage examples:

  # Using saved profiles
  python examples/check_collaboration_workspace.py \
      --host-profile host_admin \
      --guest-profile guest_admin \
      --host-group <HOST_GROUP_ID> --guest-group <GUEST_GROUP_ID> --json

  # Using explicit credentials (env or args)
  set MYGIS_HOST_PORTAL_URL=https://host.domain/portal
  set MYGIS_HOST_USERNAME=admin
  set MYGIS_HOST_PASSWORD=***
  set MYGIS_GUEST_PORTAL_URL=https://guest.domain/portal
  set MYGIS_GUEST_USERNAME=admin
  set MYGIS_GUEST_PASSWORD=***
  python examples/check_collaboration_workspace.py --host-group abc --guest-group def

  # Compare a single item pair directly
  python examples/check_collaboration_workspace.py \
      --host-profile host_admin --guest-profile guest_admin \
      --host-item <HOST_ITEM_ID> --guest-item <GUEST_ITEM_ID>
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Optional

from arcgis.gis import GIS

from mygis_core import log as log_mod
from mygis_core import config as config_mod
from mygis_core.collab import (
    check_collaboration_groups,
    compare_feature_service_items,
)


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
    """Build a GIS connection using args/env/config with a given prefix.

    Prefix examples: 'host', 'guest'.
    Supported keys (args -> env -> cfg):
      - profile
      - portal_url (or portal)
      - username
      - password
    Env vars: MYGIS_{PREFIX}_PROFILE, MYGIS_{PREFIX}_PORTAL_URL, etc.
    """
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

    # 3) fallback: Pro/Home (if args provided)
    auth = getattr(args, f"{pfx}_auth", None) or cfg.get(f"{pfx}_auth", None)
    if auth:
        return GIS(str(auth))

    # Last resort: ArcGIS Pro sign-in
    return GIS("pro")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check collaboration workspace items across two portals")

    # Selection: either groups or a specific item pair
    p.add_argument("--host-group", dest="host_group", help="Host group ID for collaboration workspace")
    p.add_argument("--guest-group", dest="guest_group", help="Guest group ID for collaboration workspace")
    p.add_argument("--host-item", dest="host_item", help="Specific host item id (Feature Service)")
    p.add_argument("--guest-item", dest="guest_item", help="Specific guest item id (Feature Service)")

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

    p.add_argument("--json", action="store_true", help="Print results as JSON")
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

    if args.host_item and args.guest_item:
        res = compare_feature_service_items(host_gis, guest_gis, args.host_item, args.guest_item, verbose=not args.quiet)
        if args.json:
            print(json.dumps(res, ensure_ascii=False))
        else:
            status = res.get("status")
            title = res.get("title")
            print(f"{title or ''} -> {status}")
        return 0

    if not (args.host_group and args.guest_group):
        parser.error("Provide either --host-item/--guest-item or --host-group/--guest-group")

    results = check_collaboration_groups(
        host_gis=host_gis,
        guest_gis=guest_gis,
        host_group_id=args.host_group,
        guest_group_id=args.guest_group,
        verbose=not args.quiet,
    )

    if args.json:
        print(json.dumps(results, ensure_ascii=False))
    else:
        mismatches = [r for r in results if r.get("status") != "ok"]
        print(f"Compared {len(results)} item(s); mismatches: {len(mismatches)}")
        for r in mismatches:
            print(f"- {r.get('title','')} ({r.get('host_item_id')} -> {r.get('guest_item_id')}): {r.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
