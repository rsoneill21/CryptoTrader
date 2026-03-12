#!/usr/bin/env python3
"""Record usage data for a model.

Usage: python log_usage.py <model_name> --tokens <count> --requests <count>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import get_connection, validate_model, log_event


def main():
    if len(sys.argv) < 2:
        print("Usage: python log_usage.py <model_name> --tokens <count> --requests <count>")
        sys.exit(1)

    model = validate_model(sys.argv[1])
    tokens = 0
    requests = 0

    if "--tokens" in sys.argv:
        idx = sys.argv.index("--tokens")
        if idx + 1 < len(sys.argv):
            tokens = int(sys.argv[idx + 1])

    if "--requests" in sys.argv:
        idx = sys.argv.index("--requests")
        if idx + 1 < len(sys.argv):
            requests = int(sys.argv[idx + 1])

    if tokens == 0 and requests == 0:
        print("ERROR: Provide at least --tokens or --requests")
        sys.exit(1)

    conn = get_connection()
    conn.execute(
        "INSERT INTO usage_tracking (model_name, tokens_used, requests_made) VALUES (?, ?, ?)",
        (model, tokens, requests),
    )
    log_event(conn, "usage_logged", model_name=model,
              details=f"tokens={tokens}, requests={requests}")
    conn.commit()
    conn.close()

    print(f"Logged: {model} used {tokens} tokens, {requests} requests")


if __name__ == "__main__":
    main()
