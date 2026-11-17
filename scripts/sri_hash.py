"""
Synapse Shield - Subresource Integrity (SRI) hash for the published browser SDK.

Prints the sha384 SRI value of synapse-sdk.js (exactly the bytes on disk, i.e. the bytes the server serves)
and a ready-to-paste <script> tag. Re-run after every SDK change: any byte change invalidates the hash.

Usage:
    py -3.10 scripts/sri_hash.py
    py -3.10 scripts/sri_hash.py --src https://cdn.example.com/synapse-sdk.js
    py -3.10 scripts/sri_hash.py path/to/synapse-sdk.js --check sha384-...   (exit 1 on mismatch, for CI)
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import sys
from pathlib import Path

DEFAULT_SDK = Path(__file__).resolve().parent.parent / "src" / "synapse_shield" / "static" / "synapse-sdk.js"


def sri_hash(path: Path | str, algorithm: str = "sha384") -> str:
    """Returns the SRI value ("sha384-<base64 digest>") of the file's raw bytes."""
    if algorithm not in ("sha256", "sha384", "sha512"):
        raise ValueError(f"unsupported SRI algorithm: {algorithm}")
    digest = hashlib.new(algorithm, Path(path).read_bytes()).digest()
    return f"{algorithm}-{base64.b64encode(digest).decode('ascii')}"


def script_tag(integrity: str, src: str) -> str:
    return f'<script src="{src}" integrity="{integrity}" crossorigin="anonymous"></script>'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="sha384 SRI hash for synapse-sdk.js")
    parser.add_argument("path", nargs="?", default=str(DEFAULT_SDK), help="SDK file (default: the packaged synapse-sdk.js)")
    parser.add_argument("--src", default="/static/synapse-sdk.js", help="script URL used in the printed tag")
    parser.add_argument("--check", metavar="SRI", help="expected SRI value; exit 1 if the file does not match")
    args = parser.parse_args(argv)

    integrity = sri_hash(args.path)
    if args.check is not None:
        if args.check.strip() != integrity:
            print(f"SRI mismatch: expected {args.check.strip()}, file is {integrity}", file=sys.stderr)
            return 1
        print(f"SRI OK: {integrity}")
        return 0
    print(f'integrity="{integrity}"')
    print(script_tag(integrity, args.src))
    return 0


if __name__ == "__main__":
    sys.exit(main())
