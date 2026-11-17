"""Server-side half of the SDK cross tests: runs the real synapse_shield verifier on tokens built by the SDKs.

Usage (JSON on stdout):
  salt <difficulty>                     -> {"salt": "..."} from tokens.generate_pow_salt
  verify [<pow_salt> <nonce>]           -> token read from stdin (it can exceed the command-line limit);
                                           verify_and_consume_token (+ verify_and_consume_pow) and, when the token is
                                           valid, analyze_behavior with and without the telemetry's `input_events`
"""

import json
import sys

from synapse_shield import tokens


def main(argv: list[str]) -> dict:
    cmd = argv[0]
    if cmd == "salt":
        return {"salt": tokens.generate_pow_salt(difficulty=int(argv[1]))}
    if cmd == "verify":
        ok, reason, telemetry = tokens.verify_and_consume_token(sys.stdin.read().strip())
        out: dict = {"ok": ok, "reason": reason}
        if len(argv) >= 3:
            out["pow"] = tokens.verify_and_consume_pow(argv[1], argv[2])
        if ok:
            from synapse_shield.engine import analyze_behavior

            with_ie = analyze_behavior(dict(telemetry))
            without = analyze_behavior({k: v for k, v in telemetry.items() if k != "input_events"})
            out.update(
                {
                    "input_events": telemetry.get("input_events"),
                    "score_with": with_ie[0],
                    "score_without": without[0],
                    "key_count_with": with_ie[3].get("features", with_ie[3]).get("key_count"),
                    "key_count_without": without[3].get("features", without[3]).get("key_count"),
                }
            )
        return out
    raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1:]), default=str))
