"""Small executable entry point; application behavior lives in raphael/."""
from pathlib import Path
import argparse
import errno
import json
import logging
import sys

from raphael.config import load_config


def main():
    parser = argparse.ArgumentParser(description="Raphael local backend")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.toml"))
    parser.add_argument("--port", type=int)
    parser.add_argument("--data-dir", type=Path, help="Separate storage for tests or another local profile")
    parser.add_argument("--describe", action="store_true", help="Print launch settings without starting models")
    args = parser.parse_args()
    try:
        config = load_config(args.config, args.port, args.data_dir)
    except (OSError, ValueError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    if args.describe:
        print(json.dumps({"url": f"http://127.0.0.1:{config.server.port}",
                          "runtime": str(config.data_dir), "app": "raphael-modular",
                          "workspace": str(config.resolve(config.laptop.workspace)),
                          "laptop_enabled": config.laptop.enabled}))
        return 0
    from raphael.application import Application
    from raphael.http_api import LocalServer
    from raphael.logging_setup import configure_logging
    configure_logging(config.data_dir)
    app = Application(config)
    try:
        server = LocalServer(app)
    except OSError as error:
        if error.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", errno.EADDRINUSE), 10048):
            print("The Raphael port is already in use. Close the other copy or change server.port.", file=sys.stderr)
        else:
            print(f"Raphael could not open its local port: {error}", file=sys.stderr)
        return 2
    try:
        app.start()
        print(f"Raphael: http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        app.close()
        server.server_close()
        logging.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
