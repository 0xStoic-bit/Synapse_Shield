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


def main():
    parser = argparse.ArgumentParser(description="Synapse Shield - CLI Controller")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run Server Command
    run_parser = subparsers.add_parser("run", help="Start the Synapse Shield server and cockpit")
    run_parser.add_argument("--host", default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    run_parser.add_argument("--port", type=int, default=8000, help="Port number (default: 8000)")
    run_parser.add_argument("--no-reload", action="store_true", help="Disable auto-reload (recommended in production)")

    # Run Tests Command
    subparsers.add_parser("test", help="Run the 9-vector Red Team bot attack simulator against a running server")

    # Benchmark Latency & Throughput Command
    bench_parser = subparsers.add_parser(
        "benchmark", help="Profile microsecond latency and throughput across pipeline stages"
    )
    bench_parser.add_argument(
        "--iterations", "-n", type=int, default=500, help="Number of benchmark iterations (default: 500)"
    )
    bench_parser.add_argument("--export", "-e", type=str, default=None, help="Export benchmark metrics to JSON file")

    # Active Learning Retrain Command
    retrain_parser = subparsers.add_parser(
        "retrain", help="Fine-tune the 1D-CNN using local SQLite telemetry logs (Active Learning)"
    )
    retrain_parser.add_argument(
        "--bootstrap", action="store_true", help="Generate balanced synthetic human & bot samples if database is empty"
    )
    retrain_parser.add_argument("--epochs", type=int, default=5, help="Number of training epochs (default: 5)")
    retrain_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Custom output path for retrained weights (default: ./synapse_weights.npz)",
    )

    # Red Team Plugin Orchestrator Command
    redteam_parser = subparsers.add_parser("redteam", help="Run the modular Red Team plugin orchestrator")
    redteam_parser.add_argument(
        "--category", type=str, default=None, help="Specific attack category to run (e.g. bot, tamper, crypto)"
    )

    # Telemetry CLI command
    subparsers.add_parser("telemetry", help="View Rust L1 Nonce & IP Ban cache metrics")

    # Doctor Health Audit Command
    subparsers.add_parser("doctor", help="Run comprehensive system diagnostics & security health audit")

    # Offline replay of recorded telemetry
    replay_parser = subparsers.add_parser(
        "replay", help="Replay recorded telemetry (.json/.jsonl, file or folder) and report what would be blocked"
    )
    replay_parser.add_argument("path", help="File or directory with telemetry objects")
    replay_parser.add_argument(
        "--label", choices=("human", "bot"), default=None, help="Ground truth: report FPR (human) or TPR (bot)"
    )
    replay_parser.add_argument("--threshold", type=float, default=50.0, help="Risk score that blocks (default: 50)")
    replay_parser.add_argument("--json", action="store_true", help="Print the result as JSON")

    args = parser.parse_args()

    if args.command == "run" or args.command is None:
        port = getattr(args, "port", 8000)
        host = getattr(args, "host", "0.0.0.0")
        print(f"🛡️  Starting Synapse Shield on http://{host}:{port} ...")
        try:
            import uvicorn
        except ImportError:
            print("❌ Uvicorn is required to run the cockpit server. Install via: pip install 'synapse-shield[server]'")
            sys.exit(1)
        try:
            import fastapi  # noqa: F401
        except ImportError:
            print("❌ FastAPI is required to run the cockpit server. Install via: pip install 'synapse-shield[server]'")
            sys.exit(1)
        uvicorn.run("synapse_shield.main:app", host=host, port=port, reload=not getattr(args, "no_reload", False))
    elif args.command == "test":
        try:
            from .live_attacker import main as run_attack_suite
        except ImportError:
            from live_attacker import main as run_attack_suite
        sys.exit(run_attack_suite())
    elif args.command == "benchmark":
        try:
            from .benchmark import run_micro_benchmarks
        except ImportError:
            from benchmark import run_micro_benchmarks
        run_micro_benchmarks(iterations=args.iterations, export_path=args.export)
    elif args.command == "retrain":
        try:
            from .train import retrain_fc2
        except ImportError:
            from train import retrain_fc2
        retrain_fc2(epochs=args.epochs, bootstrap=args.bootstrap, output_path=args.output)
    elif args.command == "redteam":
        import asyncio
        from . import live_attacker
        from .redteam_plugin import SynapseRedTeamOrchestrator

        if not live_attacker.server_reachable():
            print(f"❌ Server unreachable: {live_attacker.CHALLENGE_URL}", file=sys.stderr)
            print("   Start it first: synapse-shield run --port 8000", file=sys.stderr)
            sys.exit(2)

        async def run_redteam():
            orchestrator = SynapseRedTeamOrchestrator()
            if args.category:
                return await orchestrator.run_category(args.category)
            await orchestrator.run_full_scenario()
            return None

        asyncio.run(run_redteam())
    elif args.command == "telemetry":
        try:
            from . import synapse_core_rs

            if synapse_core_rs:
                import json

                stats = synapse_core_rs.get_state_engine_stats_rs()
                print("🛡️  Rust State Engine Telemetry:")
                print(json.dumps(stats, indent=2))
            else:
                print("synapse_core_rs is not available.")
        except Exception as e:
            print(f"Error reading telemetry: {e}")
    elif args.command == "doctor":
        try:
            from .doctor import run_doctor
        except ImportError:
            from doctor import run_doctor
        sys.exit(run_doctor())
    elif args.command == "replay":
        import json

        from .replay import format_report, load_telemetry, replay

        try:
            items = load_telemetry(args.path)
        except (OSError, ValueError) as e:
            print(f"❌ Could not read telemetry: {e}", file=sys.stderr)
            sys.exit(2)
        result = replay(items, threshold=args.threshold)
        print(json.dumps(result, indent=2) if args.json else format_report(result, args.label))


if __name__ == "__main__":
    main()
