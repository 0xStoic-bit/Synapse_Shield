"""
Synapse Shield CLI Runner
"""

import argparse
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

    args = parser.parse_args()

    if args.command == "run" or args.command is None:
        port = getattr(args, "port", 8000)
        host = getattr(args, "host", "0.0.0.0")
        print(f"🛡️  Starting Synapse Shield on http://{host}:{port} ...")
        uvicorn.run("synapse_shield.main:app", host=host, port=port, reload=True)
    elif args.command == "test":
        from .live_attacker import main as run_attack_suite
        run_attack_suite()

if __name__ == "__main__":
    main()
