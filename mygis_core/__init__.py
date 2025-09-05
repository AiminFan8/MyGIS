"""Core utilities for logging, configuration, and auth.

Usage:
    from mygis_core import log, config
    log.configure_logging()  # reads env vars by default
    cfg = config.load_config()
    logger = log.get_logger(__name__)
    logger.info("Ready", extra={"cfg_keys": list(cfg.keys())})
"""

from . import log, config, auth  # re-export for convenience

__all__ = ["log", "config", "auth"]
