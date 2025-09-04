from mygis_core import config, log


def main():
    # Load config and configure logging from it
    cfg = config.load_and_apply_logging()
    logger = log.get_logger(__name__)

    logger.info("Example started", extra={"cfg_keys": list(cfg.keys())})
    # Do some work here...
    logger.debug("Max items", extra={"max_items": cfg.get("max_items", 100)})


if __name__ == "__main__":
    main()

