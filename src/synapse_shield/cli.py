"""
Synapse Shield CLI Runner
"""

import argparse
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Synapse Shield - CLI Controller")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run Server Command
    run_parser = subparsers.add_parser("run", help="Start the Synapse Shield server and cockpit")
    run_parser.add_argument("--host", default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    run_parser.add_argument("--port", type=int, default=8000, help="Port number (default: 8000)")

    # Run Tests Command
    subparsers.add_parser("test", help="Run the 7-vector Red Team bot attack simulator")
    
    # Active Learning Retrain Command
    subparsers.add_parser("retrain", help="Fine-tune the 1D-CNN using local SQLite telemetry logs (Active Learning)")

    args = parser.parse_args()

    if args.command == "run" or args.command is None:
        port = getattr(args, "port", 8000)
        host = getattr(args, "host", "0.0.0.0")
        print(f"🛡️  Starting Synapse Shield on http://{host}:{port} ...")
        uvicorn.run("synapse_shield.main:app", host=host, port=port, reload=True)
    elif args.command == "test":
        try:
            from .live_attacker import main as run_attack_suite
        except ImportError:
            from live_attacker import main as run_attack_suite
        run_attack_suite()
    elif args.command == "retrain":
        try:
            from .train import retrain_fc2
        except ImportError:
            from train import retrain_fc2
        retrain_fc2()

if __name__ == "__main__":
    main()
