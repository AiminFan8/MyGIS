#!/usr/bin/env python3
"""
ArcGIS Python API – Authentication Profile Manager (CLI)

Create, list, show, test, rename, and delete ArcGIS Python API auth profiles.

Profiles let you connect with `GIS("<profilename>")` without re-entering credentials.
This tool focuses on the common, reliable flows:
  • Username / password (ArcGIS Online or Enterprise portal)
  • API key (optional; supported by ArcGIS Python API ≥1.9)

USAGE EXAMPLES
--------------
# Create a username/password profile (password prompted if omitted)
python arcgis_profile_manager.py create --name ente-admin \
  --url https://www.arcgis.com --username my_user

# Create using API key (default portal is ArcGIS Online)
python arcgis_profile_manager.py create --name ente-service --api-key <KEY>

# List profiles
python arcgis_profile_manager.py list

# Show basic info for a profile
python arcgis_profile_manager.py show --name ente-admin

# Test a profile by logging in and printing the current user and portal
python arcgis_profile_manager.py test --name ente-admin

# Rename or delete a profile
python arcgis_profile_manager.py rename --old ente-admin --new ente-admin-2
python arcgis_profile_manager.py delete --name ente-admin-2

NOTES
-----
• Where profiles live: typically at ~/.arcgis/python_api/profiles/<name>
• This script uses only public, stable API behavior (no private file formats).
• OAuth 2.0 app-login and Enterprise IWA/SAML-based flows are not managed here.
  For those, create and validate a profile interactively in your own code/notebooks,
  then you can still manage the resulting profile folder with this CLI.

"""
from __future__ import annotations

import argparse
import getpass
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional

try:
    from arcgis.gis import GIS
except Exception as e:  # pragma: no cover
    sys.stderr.write(
        "\n[ERROR] The 'arcgis' package is required. Install with:\n\n"
        "    pip install arcgis\n\n"
    )
    raise


# -----------------------------
# Helpers
# -----------------------------

def profiles_dir() -> Path:
    """Return the directory where ArcGIS Python API stores profiles.

    ArcGIS Python API typically uses: ~/.arcgis/python_api/profiles
    """
    return Path.home() / ".arcgis" / "python_api" / "profiles"


def ensure_profiles_dir() -> Path:
    p = profiles_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_profiles() -> List[str]:
    p = ensure_profiles_dir()
    if not p.exists():
        return []
    return sorted([d.name for d in p.iterdir() if d.is_dir()])


def profile_path(name: str) -> Path:
    return profiles_dir() / name


# -----------------------------
# Core operations
# -----------------------------

def create_profile(
    name: str,
    url: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    api_key: Optional[str] = None,
    verify_cert: bool = True,
) -> None:
    """Create a new ArcGIS profile using supported flows.

    • Username/password: provide url, username, and password (or omit password to prompt).
    • API key: provide api_key only (url optional; API key uses ArcGIS Online by default).
    """
    if profile_path(name).exists():
        raise SystemExit(f"Profile '{name}' already exists.")

    if api_key:
        # API Key auth (no username/password required). Default portal is AGO.
        # Users can still pass a custom URL if needed.
        gis = GIS(url or None, api_key=api_key, profile=name, verify_cert=verify_cert)
    else:
        if not url:
            raise SystemExit("--url is required for username/password profiles.")
        if not username:
            raise SystemExit("--username is required for username/password profiles.")
        if not password:
            password = getpass.getpass("Password: ")
        gis = GIS(url, username, password, profile=name, verify_cert=verify_cert)

    # Touch the connection to ensure credentials are valid and profile materializes
    try:
        who = getattr(getattr(gis, "users", None), "me", None)
        me = who.username if who else "<anonymous>"
        baseurl = getattr(getattr(gis, "_con", None), "baseurl", url or "<unknown>")
        print(f"Created profile '{name}' → user: {me} | portal: {baseurl}")
    except Exception as e:
        # If creation failed, try to clean up the partially created folder
        if profile_path(name).exists():
            shutil.rmtree(profile_path(name), ignore_errors=True)
        raise


def show_profile(name: str) -> None:
    p = profile_path(name)
    if not p.exists():
        raise SystemExit(f"Profile '{name}' not found.")

    # Try loading via API to retrieve safe, high-level info
    try:
        gis = GIS(name)
        who = getattr(getattr(gis, "users", None), "me", None)
        me = who.username if who else "<anonymous>"
        baseurl = getattr(getattr(gis, "_con", None), "baseurl", "<unknown>")
        print(f"Profile: {name}\n  Portal: {baseurl}\n  User:   {me}")
    except Exception as e:
        # Fall back to filesystem-only view
        print(f"Profile: {name}\n  Location: {p}")


def test_profile(name: str) -> None:
    p = profile_path(name)
    if not p.exists():
        raise SystemExit(f"Profile '{name}' not found.")
    gis = GIS(name)
    who = getattr(getattr(gis, "users", None), "me", None)
    me = who.username if who else "<anonymous>"
    baseurl = getattr(getattr(gis, "_con", None), "baseurl", "<unknown>")
    # Light-touch request to verify token usability: fetch portal properties
    _ = getattr(gis, "properties", {})
    print(f"OK: profile '{name}' works → user: {me} | portal: {baseurl}")


def rename_profile(old: str, new: str) -> None:
    src = profile_path(old)
    dst = profile_path(new)
    if not src.exists():
        raise SystemExit(f"Profile '{old}' not found.")
    if dst.exists():
        raise SystemExit(f"Target profile name '{new}' already exists.")
    src.rename(dst)
    print(f"Renamed '{old}' → '{new}'.")


def delete_profile(name: str) -> None:
    p = profile_path(name)
    if not p.exists():
        raise SystemExit(f"Profile '{name}' not found.")
    shutil.rmtree(p)
    print(f"Deleted profile '{name}'.")


# -----------------------------
# CLI
# -----------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage ArcGIS Python API authentication profiles",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # list
    p_list = sub.add_parser("list", help="List available profiles")

    # show
    p_show = sub.add_parser("show", help="Show info about a profile")
    p_show.add_argument("--name", required=True, help="Profile name")

    # test
    p_test = sub.add_parser("test", help="Test a profile by logging in")
    p_test.add_argument("--name", required=True, help="Profile name")

    # create
    p_create = sub.add_parser("create", help="Create a new profile")
    p_create.add_argument("--name", required=True, help="Profile name to create")
    p_create.add_argument("--url", help="Portal URL (e.g., https://www.arcgis.com)")
    p_create.add_argument("--username", help="Username for the portal")
    p_create.add_argument("--password", help="Password (omit to be prompted)")
    p_create.add_argument(
        "--api-key",
        help="API key (if provided, username/password are ignored)",
    )
    p_create.add_argument(
        "--no-verify",
        action="store_true",
        help="Disable TLS certificate verification",
    )

    # rename
    p_rename = sub.add_parser("rename", help="Rename a profile")
    p_rename.add_argument("--old", required=True, help="Existing profile name")
    p_rename.add_argument("--new", required=True, help="New profile name")

    # delete
    p_delete = sub.add_parser("delete", help="Delete a profile")
    p_delete.add_argument("--name", required=True, help="Profile name to delete")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "list":
        profs = list_profiles()
        if not profs:
            print("(no profiles found)")
        else:
            for n in profs:
                print(n)
        return 0

    if args.cmd == "show":
        show_profile(args.name)
        return 0

    if args.cmd == "test":
        test_profile(args.name)
        return 0

    if args.cmd == "create":
        create_profile(
            name=args.name,
            url=args.url,
            username=args.username,
            password=args.password,
            api_key=args.api_key,
            verify_cert=not args.no_verify   )
        return 0

    if args.cmd == "rename":
        rename_profile(args.old, args.new)
        return 0

    if args.cmd == "delete":
        delete_profile(args.name)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
