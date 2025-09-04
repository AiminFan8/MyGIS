"""Core utilities for logging and configuration.

Usage:
    from mygis_core import log, config
    log.configure_logging()  # reads env vars by default
    cfg = config.load_config()
    logger = log.get_logger(__name__)
    logger.info("Ready", extra={"cfg_keys": list(cfg.keys())})
"""

from . import log, config  # re-export for convenience

__all__ = ["log", "config"]

