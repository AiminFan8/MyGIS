from typing import Optional
from arcgis.gis import GIS
from . import config as myconfig

def get_gis(cfg: Optional[myconfig.Config] = None) -> GIS:
    """Create and return an ArcGIS `GIS` connection based on configuration/env.
    Resolution order (first match wins):
    1) profile: use a saved ArcGIS profile (e.g., `MYGIS_PROFILE=work`)
    2) auth: "pro" or "home" (ArcGIS Pro/Home sign-in)
    3) portal_url/portal + username + password
    Supported keys (file or env with prefix `MYGIS_`):
    - profile (or `arcgis_profile`, `agol_profile`)
    - auth: "pro" (default) | "home"
    - portal_url (or "portal"), username, password
    """
    cfg = cfg or myconfig.load_config()

    # 1) Saved profile
    profile = (
        cfg.get("profile")
        or cfg.get("arcgis_profile")
        or cfg.get("agol_profile")
    )
    if profile:
        return GIS(profile=str(profile))

    # 2) Pro/Home
    auth = str(cfg.get("auth", "pro")).lower()
    if auth in ("pro", "home"):
        return GIS(auth)

    # 3) Explicit portal credentials
    portal_url = cfg.get("portal_url") or cfg.get("portal")
    username = cfg.get("username")
    password = cfg.get("password")

    if portal_url and username and password:
        return GIS(str(portal_url), str(username), str(password))

    # Fallback to Pro sign-in if nothing else configured
    return GIS("pro")
