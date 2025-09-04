import argparse
import json
import sys
from typing import Optional

from . import config as config_mod
from . import log as log_mod


def _add_common_args(p: argparse.ArgumentParser):
    p.add_argument("--log-level", dest="log_level", help="Set log level (DEBUG, INFO, WARNING, ERROR)")
    p.add_argument("--log-format", dest="log_format", choices=["plain", "json"], help="Log output format")
    p.add_argument("--log-file", dest="log_file", help="Write logs to file path")
    p.add_argument(
        "--config",
        dest="config_path",
        help="Config file path (toml/yaml/json/ini/.env). Overrides default search order.",
    )
    p.add_argument(
        "--no-env-override",
        action="store_true",
        help="Do not let environment variables override file/defaults.",
    )


def _configure_from_args(args) -> config_mod.Config:
    paths = [args.config_path] if args.config_path else None
    cfg = config_mod.load_config(paths=paths, env_override=not args.no_env_override)

    level = args.log_level or cfg.get("log_level")
    fmt = args.log_format or cfg.get("log_format")
    file = args.log_file or cfg.get("log_file")
    json_format: Optional[bool] = None if fmt is None else (str(fmt).lower() == "json")

    log_mod.configure_logging(level=level, json_format=json_format, file=file)
    return cfg


def _cmd_config_show(args) -> int:
    cfg = _configure_from_args(args)
    data = cfg.data
    if args.pretty:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(data, ensure_ascii=False))
    return 0


def _cmd_log_test(args) -> int:
    _configure_from_args(args)
    logger = log_mod.get_logger("mygis")
    logger.debug("debug message", extra={"example": True})
    logger.info("info message", extra={"example": True})
    logger.warning("warning message", extra={"example": True})
    logger.error("error message", extra={"example": True})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mygis", description="MyGIS utilities CLI")
    _add_common_args(parser)

    subparsers = parser.add_subparsers(dest="command", required=True)

    p_cfg = subparsers.add_parser("config", help="Configuration helpers")
    _add_common_args(p_cfg)
    sp_cfg = p_cfg.add_subparsers(dest="subcommand", required=True)
    p_cfg_show = sp_cfg.add_parser("show", help="Show effective configuration as JSON")
    _add_common_args(p_cfg_show)
    p_cfg_show.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    p_cfg_show.set_defaults(func=_cmd_config_show)

    p_log = subparsers.add_parser("log", help="Logging helpers")
    _add_common_args(p_log)
    sp_log = p_log.add_subparsers(dest="subcommand", required=True)
    p_log_test = sp_log.add_parser("test", help="Emit test log messages at all levels")
    _add_common_args(p_log_test)
    p_log_test.set_defaults(func=_cmd_log_test)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if not func:
        parser.print_help()
        return 2
    return int(func(args))


if __name__ == "__main__":
    sys.exit(main())

