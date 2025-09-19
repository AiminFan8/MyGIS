from __future__ import annotations

from typing import Optional

from collections import Counter
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



def _map_flc_by_key(flc: FeatureLayerCollection) -> dict[str, dict[str, object]]:
    layers = getattr(flc, "layers", []) or []
    tables = getattr(flc, "tables", []) or []
    mapped: dict[str, dict[str, object]] = {}
    for lyr in layers:
        mapped.setdefault("layers", {})[_layer_key(lyr)] = lyr
    for tbl in tables:
        mapped.setdefault("tables", {})[_layer_key(tbl)] = tbl
    return mapped


def _get_comparable_fields(layer, extra_ignored: Optional[set[str]] = None) -> list[str]:
    props = getattr(layer, "properties", None) or {}
    fields_meta = getattr(props, "fields", None)
    if fields_meta is None and isinstance(props, dict):
        fields_meta = props.get("fields")
    if fields_meta is None:
        fields_meta = getattr(layer, "fields", None)
    if not fields_meta:
        return []

    ignore_lower = {str(f).lower() for f in (extra_ignored or set())}
    auto_ignore_lower: set[str] = set()
    for attr in ("objectIdField", "globalIdField", "shapeFieldName", "geometryField"):
        value = getattr(props, attr, None)
        if value is None and isinstance(props, dict):
            value = props.get(attr)
        if value:
            auto_ignore_lower.add(str(value).lower())
    auto_ignore_lower.update({"shape", "shape_length", "shape_area"})

    comparable: list[str] = []
    for field in fields_meta:
        name = None
        field_type = None
        if hasattr(field, "get"):
            name = field.get("name")
            field_type = field.get("type")
        if name is None:
            name = getattr(field, "name", None)
        if field_type is None:
            field_type = getattr(field, "type", None)
        if not name:
            continue
        lname = str(name).lower()
        if lname in ignore_lower or lname in auto_ignore_lower:
            continue
        if field_type and str(field_type).lower() == "esrifieldtypegeometry":
            continue
        comparable.append(str(name))

    if not comparable:
        oid_field = getattr(props, "objectIdField", None)
        if oid_field is None and isinstance(props, dict):
            oid_field = props.get("objectIdField")
        if oid_field:
            comparable.append(str(oid_field))

    return comparable


def _layer_supports_pagination(layer) -> bool:
    props = getattr(layer, "properties", None) or {}
    for attr in ("supportsPagination", "supportsPaginationOnLayer"):
        value = getattr(props, attr, None)
        if value is None and isinstance(props, dict):
            value = props.get(attr)
        if value:
            return True
    return False


def _extract_features(feature_set) -> list:
    if feature_set is None:
        return []
    try:
        features = getattr(feature_set, "features", None)
    except Exception:
        features = None
    if features is None and isinstance(feature_set, dict):
        features = feature_set.get("features")
    return features or []


def _feature_attributes(feature) -> Optional[dict]:
    attrs = getattr(feature, "attributes", None)
    if attrs is None and isinstance(feature, dict):
        attrs = feature.get("attributes") or feature
    if attrs is None:
        return None
    return dict(attrs)


def _iter_layer_feature_tuples(layer, field_names: list[str], where: str, chunk_size: int):
    if not field_names:
        return
    where_clause = (where or "1=1")
    seen: set[str] = set()
    clean_fields: list[str] = []
    for name in field_names:
        if not name:
            continue
        name_str = str(name)
        if name_str in seen:
            continue
        seen.add(name_str)
        clean_fields.append(name_str)
    if not clean_fields:
        return
    out_fields = ",".join(clean_fields)
    query_kwargs = {
        "where": where_clause,
        "out_fields": out_fields if out_fields else "*",
        "return_geometry": False,
    }
    supports_pagination = _layer_supports_pagination(layer)
    if supports_pagination and chunk_size and chunk_size > 0:
        offset = 0
        while True:
            fs = layer.query(result_offset=offset, result_record_count=chunk_size, **query_kwargs)
            features = _extract_features(fs)
            if not features:
                break
            for feat in features:
                attrs = _feature_attributes(feat)
                if attrs is None:
                    continue
                yield tuple(attrs.get(name) for name in clean_fields)
            if len(features) < chunk_size:
                break
            offset += len(features)
    else:
        fs = layer.query(return_all_records=True, **query_kwargs)
        features = _extract_features(fs)
        if not features:
            return
        for feat in features:
            attrs = _feature_attributes(feat)
            if attrs is None:
                continue
            yield tuple(attrs.get(name) for name in clean_fields)


def _build_feature_counter(layer, canonical_order: list[str], field_map: dict[str, str], where: str, chunk_size: int) -> Counter:
    actual_fields = [field_map[name] for name in canonical_order]
    counter: Counter = Counter()
    for values in _iter_layer_feature_tuples(layer, actual_fields, where, chunk_size):
        counter[values] += 1
    return counter


def _counter_delta(host_counter: Counter, guest_counter: Counter, field_names: list[str]) -> tuple[list[dict], list[dict]]:
    host_only: list[dict] = []
    guest_only: list[dict] = []
    for key, host_count in host_counter.items():
        guest_count = guest_counter.get(key, 0)
        if host_count > guest_count:
            host_only.append({"count": host_count - guest_count, "attributes": dict(zip(field_names, key))})
    for key, guest_count in guest_counter.items():
        host_count = host_counter.get(key, 0)
        if guest_count > host_count:
            guest_only.append({"count": guest_count - host_count, "attributes": dict(zip(field_names, key))})
    return host_only, guest_only


def compare_feature_service_records(
    host_gis: GIS,
    guest_gis: GIS,
    host_item_id: str,
    guest_item_id: str,
    *,
    where: str = "1=1",
    ignore_fields: Optional[list[str]] = None,
    layer_keys: Optional[list[str]] = None,
    chunk_size: int = 2000,
    verbose: bool = True,
) -> dict:
    """Compare record-level differences between two hosted feature service items."""
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

    ignore_fields_set = {str(f) for f in (ignore_fields or [])}
    layer_key_filter = {str(k).lower() for k in (layer_keys or [])} or None
    where_clause = where or "1=1"
    try:
        chunk_size_val = int(chunk_size)
    except (TypeError, ValueError):
        chunk_size_val = 0
    if chunk_size_val < 0:
        chunk_size_val = 0

    host_map = _map_flc_by_key(host_flc)
    guest_map = _map_flc_by_key(guest_flc)

    def allow_key(key: str) -> bool:
        return not layer_key_filter or key.lower() in layer_key_filter

    def compare_collection(kind: str) -> list[dict]:
        results: list[dict] = []
        host_objs = host_map.get(kind, {})
        guest_objs = guest_map.get(kind, {})
        for key, host_layer in host_objs.items():
            if not allow_key(key):
                continue
            guest_layer = guest_objs.get(key)
            entry = {
                "kind": kind,
                "key": key,
                "name": getattr(getattr(host_layer, "properties", {}), "get", lambda *_, **__: None)("name")
                or getattr(host_layer, "name", key),
            }
            if guest_layer is None:
                entry.update({
                    "status": "missing_on_guest",
                    "host_count": _safe_count(host_layer),
                    "guest_count": None,
                    "host_only": [],
                    "guest_only": [],
                })
                results.append(entry)
                continue

            host_fields = _get_comparable_fields(host_layer, ignore_fields_set)
            guest_fields = _get_comparable_fields(guest_layer, ignore_fields_set)
            guest_lookup = {f.lower(): f for f in guest_fields}
            fields_info = []
            missing_on_guest: list[str] = []
            for host_field in host_fields:
                guest_field = guest_lookup.get(host_field.lower())
                if guest_field:
                    fields_info.append((host_field.lower(), host_field, guest_field))
                else:
                    missing_on_guest.append(host_field)

            if missing_on_guest:
                entry.update({
                    "status": "error",
                    "message": "Host fields missing on guest layer",
                    "missing_fields_on_guest": missing_on_guest,
                })
                results.append(entry)
                continue

            if not fields_info:
                entry.update({
                    "status": "skipped",
                    "message": "No comparable fields available after filtering",
                    "host_count": _safe_count(host_layer),
                    "guest_count": _safe_count(guest_layer),
                    "host_only": [],
                    "guest_only": [],
                })
                results.append(entry)
                continue

            field_order = [info[0] for info in fields_info]
            host_field_map = {info[0]: info[1] for info in fields_info}
            guest_field_map = {info[0]: info[2] for info in fields_info}
            result_field_names = [host_field_map[name] for name in field_order]

            try:
                host_counter = _build_feature_counter(host_layer, field_order, host_field_map, where_clause, chunk_size_val)
            except Exception as exc:
                entry.update({
                    "status": "error",
                    "message": f"Failed to query host layer: {exc}",
                })
                results.append(entry)
                continue

            try:
                guest_counter = _build_feature_counter(guest_layer, field_order, guest_field_map, where_clause, chunk_size_val)
            except Exception as exc:
                entry.update({
                    "status": "error",
                    "message": f"Failed to query guest layer: {exc}",
                })
                results.append(entry)
                continue

            host_only, guest_only = _counter_delta(host_counter, guest_counter, result_field_names)
            entry.update({
                "status": "ok" if not host_only and not guest_only else "mismatch",
                "fields_compared": result_field_names,
                "host_count": sum(host_counter.values()),
                "guest_count": sum(guest_counter.values()),
                "host_only": host_only,
                "guest_only": guest_only,
            })
            if where_clause and where_clause != "1=1":
                entry["where"] = where_clause
            if ignore_fields_set:
                entry["ignored_fields"] = sorted(ignore_fields_set)
            results.append(entry)

        for key, guest_layer in guest_objs.items():
            if key in host_objs or not allow_key(key):
                continue
            entry = {
                "kind": kind,
                "key": key,
                "name": getattr(getattr(guest_layer, "properties", {}), "get", lambda *_, **__: None)("name")
                or getattr(guest_layer, "name", key),
                "status": "missing_on_host",
                "host_count": None,
                "guest_count": _safe_count(guest_layer),
                "host_only": [],
                "guest_only": [],
            }
            results.append(entry)
        return results

    layer_results = compare_collection("layers")
    table_results = compare_collection("tables")
    statuses = [entry.get("status") for entry in layer_results + table_results]
    has_error = any(status == "error" for status in statuses)
    has_mismatch = any(status in {"mismatch", "missing_on_guest", "missing_on_host"} for status in statuses)
    overall_status = "error" if has_error else ("mismatch" if has_mismatch else "ok")

    result = {
        "status": overall_status,
        "host_item_id": host_item_id,
        "guest_item_id": guest_item_id,
        "title": getattr(host_item, "title", None),
        "host_url": getattr(host_flc, "url", None),
        "guest_url": getattr(guest_flc, "url", None),
        "where": where_clause,
        "layers": layer_results,
        "tables": table_results,
        "chunk_size": chunk_size_val,
    }
    if ignore_fields_set:
        result["ignored_fields"] = sorted(ignore_fields_set)
    if layer_keys:
        result["layer_keys"] = list(layer_keys)

    if verbose:
        logger.info(
            "Compared service records '%s' -> status: %s",
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


