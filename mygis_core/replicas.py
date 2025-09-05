from __future__ import annotations
from datetime import datetime
from typing import Optional
import re
from arcgis.features import FeatureLayerCollection
from arcgis.gis import GIS
from . import log as mylog
from . import auth as myauth
from . import config as myconfig

def _to_fs_root(url: str) -> str:
    """Ensure we have the FeatureServer root URL (strip trailing layer /0, /1, ...)."""
    m = re.search(r"(.*?/FeatureServer)(?:/\d+)?$", url, flags=re.IGNORECASE)
    if not m:
        raise ValueError("URL must point to a FeatureServer (service or layer).")
    return m.group(1)


def _epoch_ms_to_iso(ms):
    if ms is None:
        return None
    try:
        ms = int(ms)
        if ms < 10_000_000_000:  # seconds -> ms
            ms *= 1000
        return datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(ms)


def list_replicas(service_url_or_itemid: str, *, verbose: bool = True, gis: Optional[GIS] = None):
    """List replicas for a Feature Service (AGOL/Enterprise).

    - Input: Feature Service root URL, a layer URL (…/FeatureServer/0), or an Item ID
    - Output: prints a summary (if verbose) and returns a list of replica dicts
    """
    logger = mylog.get_logger(__name__)

    # Resolve to Feature Service root URL
    if service_url_or_itemid.startswith("http"):
        fs_root = _to_fs_root(service_url_or_itemid)
        flc = FeatureLayerCollection(fs_root, gis=(gis or myauth.get_gis()))
    else:
        # treat as item id
        gis_obj = gis or myauth.get_gis()
        item = gis_obj.content.get(service_url_or_itemid)
        if item is None:
            raise ValueError("Item not found or not accessible.")
        flc = FeatureLayerCollection.fromitem(item)

    # Ensure sync is enabled (replicas require sync)
    props = flc.properties
    sync_enabled = getattr(props, "syncEnabled", None)
    if sync_enabled is False:
        if verbose:
            logger.warning("Service does not have sync enabled; replicas will not exist.")
            print("This service does not have sync enabled; replicas will not exist.")
        return []

    # Call the REST replicas resource (GET {FeatureServer}/replicas?f=json)
    res = flc._con.get(f"{flc.url}/replicas", params={"f": "json"})
    replicas = res.get("replicas", []) if isinstance(res, dict) else []

    if verbose and replicas:
        cols = [
            ("id", "replicaID"),
            ("name", "replicaName"),
            ("owner", "replicaOwner"),
            ("type", "replicaType"),
            ("created", "creationDate"),
            ("last_sync", "lastSyncDate"),
            ("state", "replicaState"),
        ]

        def row(r):
            return [
                str(r.get(src, "")) if src not in ("creationDate", "lastSyncDate")
                else (_epoch_ms_to_iso(r.get(src)))
                for _, src in cols
            ]

        headers = [h for h, _ in cols]
        widths = [max(len(h), 12) for h in headers]
        for r in replicas:
            for i, val in enumerate(row(r)):
                widths[i] = max(widths[i], len(str(val)))

        def fmt(vals):
            return "  ".join(str(v).ljust(widths[i]) for i, v in enumerate(vals))

        logger.info(fmt(headers))
        logger.info(fmt(["-" * w for w in widths]))
        for r in replicas:
            logger.info(fmt(row(r)))
        logger.info(f"Total replicas: {len(replicas)}")

    return replicas


def find_hosted_feature_services(
    *,
    gis: Optional[GIS] = None,
    query: Optional[str] = None,
    max_items: int = 1000,
    owner: Optional[str] = None,
) -> list:
    """Search for hosted Feature Service items in the portal.

    - Default query finds items of type "Feature Service" with hosted keywords.
    - Returns a list of `Item` objects.
    """
    gis_obj = gis or myauth.get_gis()

    # Determine owner from param or config
    if owner is None:
        cfg = myconfig.load_config()
        owner = cfg.get("search_owner") or cfg.get("owner") or None

    base_q = 'type:"Feature Service" AND (typekeywords:"Hosted Service" OR typekeywords:Hosted)'
    q = query or base_q

    # Append owner filter if requested
    if query is None and owner:
        o = str(owner).strip()
        if o.lower() in {"*", "any", "all"}:
            pass  # no owner restriction
        elif o.lower() in {"me", "@me"}:
            try:
                me = getattr(getattr(gis_obj, "users", None), "me", None)
                username = me.username if me else None
                if username:
                    q = f"{q} AND owner:{username}"
            except Exception:
                pass
        else:
            q = f"{q} AND owner:{o}"
    try:
        return gis_obj.content.search(q, max_items=max_items)
    except Exception:
        return []


def list_replicas_for_sync_enabled_services(
    *,
    gis: Optional[GIS] = None,
    query: Optional[str] = None,
    owner: Optional[str] = None,
    max_items: int = 1000,
    verbose: bool = True,
) -> list[dict]:
    """List replicas across all hosted services with sync enabled.

    Returns a list of dicts, each containing:
    - item_id, title, service_url, sync_enabled, replicas (list)
    """
    logger = mylog.get_logger(__name__)
    gis_obj = gis or myauth.get_gis()
    items = find_hosted_feature_services(gis=gis_obj, query=query, owner=owner, max_items=max_items)
    results: list[dict] = []

    for item in items:
        try:
            flc = FeatureLayerCollection.fromitem(item)
            props = flc.properties
            sync_enabled = getattr(props, "syncEnabled", None)
            if sync_enabled is not True:
                continue
            else:
                if verbose:
                    logger.info(f"Inspecting service: {getattr(item, 'title', '')} ({item.id})")
            reps = list_replicas(item.id, verbose=verbose, gis=gis_obj)
            results.append(
                {
                    "item_id": item.id,
                    "title": getattr(item, "title", ""),
                    "service_url": flc.url,
                    "sync_enabled": True,
                    "replicas": reps,
                }
            )
        except Exception as exc:
            if verbose:
                logger.warning(
                    "Failed to inspect service",
                    extra={"item_id": getattr(item, "id", None), "error": str(exc)},
                )
            continue

    if verbose:
        logger.info("Sync-enabled hosted services: %d", extra={"count": len(results)})
    return results
