from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}: raise SystemExit("The sidecar may only bind to loopback")
    uvicorn.run("aida_sidecar.api:app", host=args.host, port=args.port, log_level="warning", access_log=False)


if __name__ == "__main__": main()

