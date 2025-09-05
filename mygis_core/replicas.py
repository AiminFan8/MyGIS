from __future__ import annotations
from datetime import datetime
from typing import Optional
import re
from arcgis.features import FeatureLayerCollection
from arcgis.gis import GIS
from . import log as mylog
from . import auth as myauth

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

