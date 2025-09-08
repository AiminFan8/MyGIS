from __future__ import annotations

from typing import Optional

from arcgis.features import FeatureLayerCollection
from arcgis.gis import GIS

from . import log as mylog


def _safe_get_last_edit_ms(layer) -> Optional[int]:
    try:
        props = getattr(layer, "properties", {}) or {}
        ei = getattr(props, "editingInfo", None) or getattr(props, "editinginfo", None)
        if isinstance(ei, dict):
            return ei.get("lastEditDate") or ei.get("last_edit_date")
        # Some services expose update dates directly
        return getattr(props, "lastEditDate", None) or getattr(props, "updateDate", None)
    except Exception:
        return None


def _safe_count(layer) -> Optional[int]:
    try:
        q = layer.query(where="1=1", returnCountOnly=True)
        if isinstance(q, dict):
            return int(q.get("count", 0))
        return int(getattr(q, "count", 0))
    except Exception:
        return None


def _layer_key(layer) -> str:
    """Stable key to align layers/tables across portals.
    Prefer layer.name; fall back to layerId/index.
    """
    try:
        name = getattr(layer, "properties", {}).get("name") or getattr(layer, "name", None)
        if name:
            return str(name)
    except Exception:
        pass
    try:
        lid = getattr(layer, "properties", {}).get("id")
        if lid is None:
            lid = getattr(layer, "properties", {}).get("layerId")
        if lid is None:
            lid = getattr(layer, "_layer_id", None)
        if lid is not None:
            return f"id:{lid}"
    except Exception:
        pass
    return str(id(layer))


def compare_feature_service_items(
    host_gis: GIS,
    guest_gis: GIS,
    host_item_id: str,
    guest_item_id: str,
    *,
    verbose: bool = True,
) -> dict:
    """Compare a pair of hosted feature service items across two portals.

    Compares per-layer record counts and last edit timestamps.
    Returns a result dict with details and overall status.
    """
    logger = mylog.get_logger(__name__)

    host_item = host_gis.content.get(host_item_id)
    guest_item = guest_gis.content.get(guest_item_id)
    if host_item is None or guest_item is None:
        return {
            "status": "error",
            "message": "One or both items not found",
            "host_item_id": host_item_id,
            "guest_item_id": guest_item_id,
        }

    try:
        host_flc = FeatureLayerCollection.fromitem(host_item)
        guest_flc = FeatureLayerCollection.fromitem(guest_item)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to open FeatureLayerCollection: {exc}",
            "host_item_id": host_item_id,
            "guest_item_id": guest_item_id,
        }

    # Build maps of layers and tables by name/key
    def map_by_key(flc: FeatureLayerCollection):
        layers = getattr(flc, "layers", []) or []
        tables = getattr(flc, "tables", []) or []
        m: dict[str, dict] = {}
        for lyr in layers:
            m.setdefault("layers", {})[_layer_key(lyr)] = lyr
        for tbl in tables:
            m.setdefault("tables", {})[_layer_key(tbl)] = tbl
        return m

    host_map = map_by_key(host_flc)
    guest_map = map_by_key(guest_flc)

    def compare_collection(kind: str) -> list[dict]:
        results: list[dict] = []
        host_objs = host_map.get(kind, {})
        guest_objs = guest_map.get(kind, {})
        for key, h in host_objs.items():
            g = guest_objs.get(key)
            entry = {
                "kind": kind,
                "key": key,
                "name": getattr(h, "properties", {}).get("name") or getattr(h, "name", key),
            }
            if g is None:
                entry.update({
                    "status": "missing_on_guest",
                    "host_count": _safe_count(h),
                    "host_last_edit": _safe_get_last_edit_ms(h),
                    "guest_count": None,
                    "guest_last_edit": None,
                })
                results.append(entry)
                continue

            hc = _safe_count(h)
            gc = _safe_count(g)
            ht = _safe_get_last_edit_ms(h)
            gt = _safe_get_last_edit_ms(g)
            entry.update({
                "status": "ok" if (hc == gc and (ht is None or gt is None or ht == gt)) else "mismatch",
                "host_count": hc,
                "guest_count": gc,
                "count_match": (hc == gc) if (hc is not None and gc is not None) else None,
                "host_last_edit": ht,
                "guest_last_edit": gt,
                "timestamp_match": (ht == gt) if (ht is not None and gt is not None) else None,
            })
            results.append(entry)
        # Detect extras on guest
        for key in guest_objs.keys():
            if key not in host_objs:
                g = guest_objs[key]
                results.append({
                    "kind": kind,
                    "key": key,
                    "name": getattr(g, "properties", {}).get("name") or getattr(g, "name", key),
                    "status": "extra_on_guest",
                    "host_count": None,
                    "guest_count": _safe_count(g),
                    "host_last_edit": None,
                    "guest_last_edit": _safe_get_last_edit_ms(g),
                })
        return results

    layer_results = compare_collection("layers")
    table_results = compare_collection("tables")

    any_mismatch = any(r.get("status") not in {"ok"} for r in layer_results + table_results)
    result = {
        "status": "ok" if not any_mismatch else "mismatch",
        "host_item_id": host_item_id,
        "guest_item_id": guest_item_id,
        "title": getattr(host_item, "title", None),
        "host_url": getattr(host_flc, "url", None),
        "guest_url": getattr(guest_flc, "url", None),
        "layers": layer_results,
        "tables": table_results,
    }

    if verbose:
        logger.info(
            "Compared service '%s' -> status: %s",
            extra={"title": result["title"], "status": result["status"]},
        )

    return result


def _extract_origin_host_id(item) -> Optional[str]:
    """Best-effort: find a source/origin item id on a replicated item.
    Checks several known property names, returns None if not present.
    """
    try:
        props = getattr(item, "_properties", None) or getattr(item, "properties", None) or {}
        for k in (
            "originItemID",
            "originItemId",
            "sourceItemID",
            "sourceItemId",
            "sourceitemid",
            "source_service_item_id",
        ):
            v = props.get(k)
            if v:
                return str(v)
    except Exception:
        return None
    return None


def pair_items_in_groups(
    host_gis: GIS,
    guest_gis: GIS,
    host_group_id: str,
    guest_group_id: str,
    *,
    strict_type: bool = True,
) -> list[tuple]:
    """Return best-effort pairs of Feature Service items between two groups.

    Matching priority:
    1) guest item's origin/source item id equals host item id
    2) title + type match (optionally restricted to Feature Service)
    """
    host_group = host_gis.groups.get(host_group_id)
    guest_group = guest_gis.groups.get(guest_group_id)
    if not host_group or not guest_group:
        return []

    def list_group_items(g):
        try:
            return g.content()
        except Exception:
            return []

    host_items = list_group_items(host_group) or []
    guest_items = list_group_items(guest_group) or []

    if strict_type:
        host_items = [i for i in host_items if getattr(i, "type", "") == "Feature Service"]
        guest_items = [i for i in guest_items if getattr(i, "type", "") == "Feature Service"]

    # Map guest items by origin id and by (title,type)
    guest_by_origin: dict[str, object] = {}
    guest_by_key: dict[tuple[str, str], object] = {}
    for gi in guest_items:
        oid = _extract_origin_host_id(gi)
        if oid:
            guest_by_origin[str(oid)] = gi
        key = (getattr(gi, "title", "") or "", getattr(gi, "type", "") or "")
        guest_by_key[key] = gi

    pairs: list[tuple] = []
    for hi in host_items:
        gi = guest_by_origin.get(hi.id)
        if gi is None:
            key = (getattr(hi, "title", "") or "", getattr(hi, "type", "") or "")
            gi = guest_by_key.get(key)
        if gi is not None:
            pairs.append((hi, gi))
    return pairs


def check_collaboration_groups(
    *,
    host_gis: GIS,
    guest_gis: GIS,
    host_group_id: str,
    guest_group_id: str,
    verbose: bool = True,
) -> list[dict]:
    """Compare all matched Feature Service items shared between two collaboration groups.

    Returns a list of comparison result dicts (one per matched item pair).
    """
    logger = mylog.get_logger(__name__)
    pairs = pair_items_in_groups(host_gis, guest_gis, host_group_id, guest_group_id)
    if verbose:
        logger.info(
            "Matched %d item pairs between groups",
            extra={"count": len(pairs), "host_group": host_group_id, "guest_group": guest_group_id},
        )
    results: list[dict] = []
    for hi, gi in pairs:
        res = compare_feature_service_items(host_gis, guest_gis, hi.id, gi.id, verbose=verbose)
        results.append(res)
    return results

