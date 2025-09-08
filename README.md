# MyGIS Core Utilities

Lightweight Python utilities for consistent logging and configuration in MyGIS scripts and services.

## Install (editable for local dev)

```bash
pip install -e .
```

Optional YAML support:

```bash
pip install -e .[yaml]
```

## Quick Start

```python
from mygis_core import log, config

# Configure logging (respects env vars if args omitted)
log.configure_logging()  # MYGIS_LOG_LEVEL, MYGIS_LOG_FORMAT, MYGIS_LOG_FILE

# Load configuration (file -> env override)
cfg = config.load_config(
    defaults={
        "log_level": "INFO",
        "service_url": None,
        "max_items": 100,
    }
)

logger = log.get_logger(__name__)
logger.info("Service starting", extra={"service_url": cfg.get("service_url")})
```

## CLI

Install, then run:

```bash
mygis --log-level DEBUG log test
mygis config show --pretty
mygis --config mygis.toml config show
mygis replicas list "https://.../FeatureServer/0" --json
```

Common flags:

- `--log-level`, `--log-format` (`plain`|`json`), `--log-file`
- `--config` to point to a specific config file
- `--no-env-override` to ignore environment variables
 - `replicas list`: accepts a service root URL, a layer URL, or a Feature Service item ID. Use `--json` to print raw JSON.

## Configuration Sources

- Files (first found wins): `mygis.toml`, `mygis.yaml`, `mygis.yml`, `mygis.json`, `mygis.ini`, `.env`
- Environment variables override when prefixed with `MYGIS_` (e.g., `MYGIS_SERVICE_URL`)
- Types are coerced from strings when defaults are provided (e.g., booleans/ints).

## Authentication

`mygis_core.auth.get_gis()` builds an ArcGIS `GIS` connection from config/env.

- Resolution order:
  - `profile` (or `arcgis_profile` / `agol_profile`) → `GIS(profile=...)`
  - `auth` = `pro` or `home` → `GIS("pro"|"home")`
  - `portal_url` (or `portal`) + `username` + `password` → `GIS(url, user, pass)`
  - fallback → `GIS("pro")`

You can set these via config files or env vars prefixed with `MYGIS_`.

### Example auth config (TOML)

Put this in `mygis.toml` or `examples/mygis.toml` and set `--config examples/mygis.toml`:

```toml
[mygis]
# Use a saved ArcGIS profile
profile = "work"

# Or use Pro/Home sign-in
# auth = "pro"  # or "home"

# Or explicit portal credentials
# portal_url = "https://example.com/portal"
# username = "alice"
# password = "<SECRET>"

# Optional search scoping for examples/list_sync_enabled_services.py
# search_owner = "me"   # or a username, or "*" for any accessible owner
```

### Example auth config (YAML)

```yaml
mygis:
  profile: work
  # auth: pro
  # portal_url: https://example.com/portal
  # username: alice
  # password: <SECRET>

  # Optional search scoping for examples/list_sync_enabled_services.py
  # search_owner: me   # or username, or "*"
```

### Example env vars

```
MYGIS_PROFILE=work
# MYGIS_AUTH=pro
# MYGIS_PORTAL_URL=https://example.com/portal
# MYGIS_USERNAME=alice
# MYGIS_PASSWORD=secret

# Optional: scope listing to an owner in examples/list_sync_enabled_services.py
# MYGIS_SEARCH_OWNER=me
```

Security tip: prefer profiles or OS credential stores; avoid committing secrets.

### Logging via Env Vars

- `MYGIS_LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- `MYGIS_LOG_FORMAT`: `plain` (default) or `json`
- `MYGIS_LOG_FILE`: path to write logs (optional)

### Example `mygis.toml`

```toml
[mygis]
log_level = "DEBUG"
service_url = "https://example.com/arcgis/rest/services/FeatureServer"
max_items = 200
```

### Example `.env`

```
MYGIS_LOG_LEVEL=INFO
MYGIS_SERVICE_URL=https://example.com
```

## API

- `mygis_core.log.configure_logging(level=None, json_format=None, file=None, fmt=None, datefmt=None, reset=False)`
- `mygis_core.log.get_logger(name=None)`
- `mygis_core.config.load_config(defaults=None, paths=None, env_prefix="MYGIS_", env_override=True)`
- `mygis_core.config.load_and_apply_logging(cfg=None)`
- `mygis_core.replicas.list_replicas(service_url_or_itemid, verbose=True, gis=None)`
- `mygis_core.replicas.find_hosted_feature_services(gis=None, query=None, max_items=1000)`
- `mygis_core.replicas.list_replicas_for_sync_enabled_services(gis=None, query=None, max_items=1000, verbose=True)`
- `mygis_core.collab.compare_feature_service_items(host_gis, guest_gis, host_item_id, guest_item_id, verbose=True)`
- `mygis_core.collab.check_collaboration_groups(host_gis=..., guest_gis=..., host_group_id=..., guest_group_id=..., verbose=True)`

### Example: Check Collaboration Workspace

Run a health check for items shared between two collaboration groups (host vs guest):

```bash
python examples/check_collaboration_workspace.py \
  --host-profile host_admin \
  --guest-profile guest_admin \
  --host-group <HOST_GROUP_ID> \
  --guest-group <GUEST_GROUP_ID> \
  --json
```

You can also provide the group IDs via env or config:

```
export MYGIS_HOST_GROUP=<HOST_GROUP_ID>
export MYGIS_GUEST_GROUP=<GUEST_GROUP_ID>
python examples/check_collaboration_workspace.py --host-profile host_admin --guest-profile guest_admin
```

Or in config (TOML/YAML under the `mygis` table):

```toml
[mygis]
host_group = "<HOST_GROUP_ID>"
guest_group = "<GUEST_GROUP_ID>"
```

Or compare a single item pair directly:

```bash
python examples/check_collaboration_workspace.py \
  --host-profile host_admin \
  --guest-profile guest_admin \
  --host-item <HOST_ITEM_ID> \
  --guest-item <GUEST_ITEM_ID>
```

## Notes

- YAML support is optional; install `pyyaml` or prefer TOML/JSON/INI/.env.
- Existing scripts can adopt logging gradually: replace `print` with `logger.info/warning/error`.
