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
# Core operations
# -----------------------------
def credman_list_arcgis(service: str = "arcgis_python_api_profile_passwords"):
    """
    Return a list of ArcGIS credential entries from Windows Credential Manager.

    Each item is a dict: {'name': <profile-or-username>, 'user': <UserName>, 'target': <TargetName>}
    'name' is derived from the credential target (service:username) or falls back to 'user'.
    """
    import os
    results = []

    # Preferred: use pywin32 if present
    try:
        import win32cred  # pip install pywin32
        creds = win32cred.CredEnumerate(None, 0)  # all creds
        for c in creds or []:
            target = c.get("TargetName", "")
            if not target:
                continue
            # keyring's Windows backends typically format target like "service:username"
            if target == service or target.endswith(service):
                # derive name from suffix after "service:"
                key = target.split(":", 1)[1].strip() if ":" in target else ""
                user = c.get("UserName", "") or ""
                name = key or user or "(unknown)"
                results.append({"name": name, "user": user, "target": target})
        if results:
            return results
    except Exception:
        pass  # fall through to cmdkey fallback

    # Fallback: parse `cmdkey /list`
    try:
        import subprocess, re
        out = subprocess.run(["cmdkey", "/list"], capture_output=True, text=True, check=True).stdout
        blocks = out.split("\n\n")
        for b in blocks:
            if service in b:
                # Target: <value>
                m_t = re.search(r"Target:\s*(.+)", b)
                target = (m_t.group(1).strip() if m_t else service)
                # User: <value>
                m_u = re.search(r"User\s*:\s*(.+)", b)
                user = (m_u.group(1).strip() if m_u else "")
                # derive name from target suffix after "service:"
                suffix = target.split(":", 1)[1].strip() if ":" in target else ""
                name = suffix or user or "(unknown)"
                results.append({"name": name, "user": user, "target": target})
    except Exception:
        pass

    return results

def create_profile(
    name: str,
    url: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    api_key: Optional[str] = None,   # <— re-enable
    verify_cert: bool = True,
) -> None:
    if api_key:
        gis = GIS(url=url or None, api_key=api_key, profile=name, verify_cert=verify_cert)
    else:
        if not url:
            raise SystemExit("--url is required for username/password profiles.")
        if not username:
            raise SystemExit("--username is required for username/password profiles.")
        if not password:
            password = getpass.getpass("Password: ")
        gis = GIS(url=url, username=username, password=password, profile=name, verify_cert=verify_cert)

def show_profile(name: str) -> None:
    p = Path.home() / ".arcgis" / "python_api" / "profiles" / name
    try:
        gis = GIS(profile=name)
        who = getattr(getattr(gis, "users", None), "me", None)
        me = who.username if who else "<anonymous>"
        baseurl = getattr(getattr(gis, "_con", None), "baseurl", "<unknown>")
        print(f"Profile: {name}\n  Portal: {baseurl}\n  User:   {me}")
    except Exception:
        print(f"Profile: {name}\n  Location: {p}")


def test_profile(name: str, no_verify: bool = False) -> None:
    gis = GIS(profile=name, verify_cert=not no_verify)
    who = getattr(getattr(gis, "users", None), "me", None)
    me = who.username if who else "<anonymous>"
    baseurl = getattr(getattr(gis, "_con", None), "baseurl", "<unknown>")
    _ = getattr(gis, "properties", {})
    print(f"OK: profile '{name}' works → user: {me} | portal: {baseurl}")
# -----------------------------
# CLI
# -----------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage ArcGIS Python API authentication profiles",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_cm = sub.add_parser("list", help="List ArcGIS entries in Windows Credential Manager")
    p_cm.add_argument("--service", default="arcgis_python_api_profile_passwords",
                      help="Service name to filter (default: arcgis_python_api_profile_passwords)")
    p_cm.add_argument("--show", choices=["name", "name+user", "target"], default="name",
                      help="Output format")
    # show
    p_show = sub.add_parser("show", help="Show info about a profile")
    p_show.add_argument("--name", required=True, help="Profile name")

    # test
    p_test = sub.add_parser("test", help="Test a profile by logging in")
    p_test.add_argument("--name", required=True, help="Profile name")
    p_test.add_argument("--no-verify", action="store_true", help="Disable TLS certificate verification during test")

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

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "list":
        rows = credman_list_arcgis(args.service)
        if not rows:
            print("(none found)")
            return 0
        if args.show == "target":
            import json as _json
            print(_json.dumps(rows, indent=2))
        elif args.show == "name+user":
            for r in rows:
                print(f"{r['name']}\t{r['user']}")
        else:
            for r in rows:
                print(r['name'])
        return 0
    if args.cmd == "show":
        show_profile(args.name)
        return 0

    if args.cmd == "create":
        create_profile(
            name=args.name,
            url=args.url,
            username=args.username,
            password=args.password,
            api_key=args.api_key,
            verify_cert=not args.no_verify,
        )
        return 0

    if args.cmd == "test":
        test_profile(args.name, no_verify=args.no_verify)
        return 0

    return 1


if __name__ == "__main__":
    import sys
    # Use sys.exit for a clean exit code without a traceback in normal CLI use.
    # In notebooks/IDEs that treat SystemExit as an error, avoid exiting.
    in_ipynb = "ipykernel" in sys.modules or "PYCHARM_HOSTED" in os.environ
    code = main()
    if in_ipynb:
        # don't abort the interactive session; just report non‑zero code
        if code:
            print(f"Exit code: {code}", file=sys.stderr)
    else:
        sys.exit(code)
