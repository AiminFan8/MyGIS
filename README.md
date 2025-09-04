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
```

Common flags:

- `--log-level`, `--log-format` (`plain`|`json`), `--log-file`
- `--config` to point to a specific config file
- `--no-env-override` to ignore environment variables

## Configuration Sources

- Files (first found wins): `mygis.toml`, `mygis.yaml`, `mygis.yml`, `mygis.json`, `mygis.ini`, `.env`
- Environment variables override when prefixed with `MYGIS_` (e.g., `MYGIS_SERVICE_URL`)
- Types are coerced from strings when defaults are provided (e.g., booleans/ints).

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

## Notes

- YAML support is optional; install `pyyaml` or prefer TOML/JSON/INI/.env.
- Existing scripts can adopt logging gradually: replace `print` with `logger.info/warning/error`.
