"""Validate settings and initialize application logging."""
import argparse
import sys

from common.config import ConfigError, load_config
from common.logger import LoggerManager


def main(argv: list[str] | None = None) -> int:
    """Return a nonzero exit status when application startup fails."""
    parser = argparse.ArgumentParser(description="SM Automation")
    parser.add_argument("--config", help="Path to a UTF-8 JSON configuration file")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    manager = None
    try:
        manager = LoggerManager()
        manager.configure(level=config.log_level, directory=config.log_directory)
        logger = manager.get_logger("main")
        logger.info("Application initialized environment=%s", config.environment)
        return 0
    except (OSError, ValueError, RuntimeError):
        print("Application logging initialization failed.", file=sys.stderr)
        return 1
    finally:
        if manager is not None:
            manager.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
