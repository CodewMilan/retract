import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def call(base_url: str, path: str, body: dict) -> dict:
    request = Request(f"{base_url.rstrip('/')}/{path.lstrip('/')}",
                      data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=60 if path.strip("/") == "updates/natural" else 15) as response:
            return json.load(response)
    except HTTPError as exc:
        result = json.load(exc)
        raise RuntimeError(f"HTTP {exc.code}: {result.get('error', 'request failed')}") from None
    except URLError as exc:
        raise RuntimeError("Local service unavailable; start retract serve first") from exc


@contextmanager
def writer_lock():
    """Prevent accidental second service processes for the same local graph."""
    identity = ":".join(os.getenv(key, default) for key, default in (
        ("FALKORDB_HOST", "127.0.0.1"), ("FALKORDB_PORT", "6380"), ("FALKORDB_GRAPH", "retract")))
    digest = hashlib.sha256(identity.encode()).hexdigest()[:20]
    path = Path(tempfile.gettempdir()) / f"retract-writer-{digest}.lock"
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another RETRACT service owns this graph on this machine") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def main():
    parser = argparse.ArgumentParser(description="RETRACT local project memory")
    parser.add_argument("--url", default=os.getenv("RETRACT_URL", "http://127.0.0.1:8100"))
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=int(os.getenv("RETRACT_PORT", "8100")))
    request = commands.add_parser("call", help="POST a structured JSON file to an API route")
    request.add_argument("route", choices=["projects", "remember", "updates", "updates/natural", "plans", "recall", "history"])
    request.add_argument("file", type=Path)
    seed = commands.add_parser("seed", help="Seed explicitly once; existing memory is never reset")
    seed.add_argument("file", type=Path, nargs="?", default=Path("fixtures/demo-seed.json"))
    recall = commands.add_parser("recall")
    recall.add_argument("project_id")
    recall.add_argument("scope")
    recall.add_argument("--subject", action="append", default=[])
    history = commands.add_parser("history")
    history.add_argument("project_id")
    target = history.add_mutually_exclusive_group(required=True)
    target.add_argument("--fact")
    target.add_argument("--event")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            from .api import make_server
            from .graph import GraphStore
            from .service import MemoryService

            logging.basicConfig(level=logging.INFO)
            with writer_lock():
                store = GraphStore()
                server = None
                try:
                    store.initialize()
                    server = make_server(MemoryService(store), args.port)
                    print(f"RETRACT listening on http://127.0.0.1:{server.server_port}", flush=True)
                    server.serve_forever()
                finally:
                    if server:
                        server.server_close()
                    store.close()
            return
        if args.command == "call":
            result = call(args.url, args.route, json.loads(args.file.read_text()))
        elif args.command == "seed":
            fixture = json.loads(args.file.read_text())
            project = call(args.url, "projects", fixture["project"])
            if project["revision"] != 0:
                raise RuntimeError("Project already contains memory; seed refused to preserve existing state")
            results = [call(args.url, action["route"], action["body"]) for action in fixture["actions"]]
            result = {"project": project["id"], "results": results}
        elif args.command == "recall":
            result = call(args.url, "recall", {"project_id": args.project_id, "scope": args.scope,
                                               "subjects": args.subject})
        else:
            result = call(args.url, "history", {"project_id": args.project_id,
                                               **({"fact_id": args.fact} if args.fact else {"event_id": args.event})})
        print(json.dumps(result, indent=2))
    except KeyboardInterrupt:
        pass
    except (RuntimeError, ValueError, OSError, ImportError) as exc:
        print(f"retract: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
