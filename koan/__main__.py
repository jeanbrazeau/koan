# Entry point: `uv run koan` or `python -m koan`.
# Loads config, builds AppState, starts the Starlette server on 127.0.0.1.

from __future__ import annotations

import argparse
import asyncio

import uvicorn

from .config import load_koan_config
from .logger import setup_logging
from .state import AppState
from .web.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="koan")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--log-level", type=str, default="INFO")
    args = parser.parse_args()

    setup_logging(args.log_level)

    config = asyncio.run(load_koan_config())
    app_state = AppState(config=config)
    app = create_app(app_state)

    host = "127.0.0.1"
    uvicorn.run(app, host=host, port=args.port, log_level=args.log_level.lower())


if __name__ == "__main__":
    main()
