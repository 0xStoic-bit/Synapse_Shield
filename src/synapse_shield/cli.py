"""
Synapse Shield CLI Runner
"""

import argparse
import os
import sys

import uvicorn


def _force_utf8() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


def main():
    _force_utf8()

    parser = argparse.ArgumentParser(description="Synapse Shield - CLI Controller")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run Server Command
    run_parser = subparsers.add_parser("run", help="Start the Synapse Shield server and cockpit")
    run_parser.add_argument("--host", default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    run_parser.add_argument("--port", type=int, default=8000, help="Port number (default: 8000)")
    run_parser.add_argument("--reload", action="store_true", help="Enable auto-reload (development)")

    # Run Tests Command
    subparsers.add_parser("test", help="Run the 7-vector Red Team bot attack simulator")

    args = parser.parse_args()

    if args.command == "run" or args.command is None:
        port = getattr(args, "port", 8000)
        host = getattr(args, "host", "0.0.0.0")
        reload = getattr(args, "reload", False)
        print(f"[Synapse Shield] Starting on http://{host}:{port} ...")
        uvicorn.run("synapse_shield.main:app", host=host, port=port, reload=reload)
    elif args.command == "test":
        from .live_attacker import main as run_attack_suite
        run_attack_suite()


if __name__ == "__main__":
    main()
