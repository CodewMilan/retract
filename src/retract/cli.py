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
    from .mcp_tools import LocalApi
    # Reuse the transport's HTTPS/redirect/credential rules for CLI requests.
    client = LocalApi(base_url)
    route = "/" + path.strip("/")
    if route in ("/projects", "/dashboard"):
        headers = {"Content-Type": "application/json"}
        if client.api_key:
            headers["Authorization"] = "Bearer " + client.api_key
        request = Request(client.base + route, data=json.dumps(body).encode(), headers=headers)
        try:
            with client.open(request, timeout=15) as response:
                return client.read_json(response)
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code}: request rejected") from None
        except URLError:
            raise RuntimeError("Memory service unavailable") from None
    return client.call(route, body)


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
            raise RuntimeError("Another Retract service owns this graph on this machine") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def load_env_file(path: Path = Path(".env")) -> None:
    """Read simple KEY=value lines; variables already exported take precedence."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("'\"")
        if key and value:
            os.environ.setdefault(key, value)


def main():
    load_env_file()
    parser = argparse.ArgumentParser(description="Retract local project memory")
    parser.add_argument("--url", default=os.getenv("RETRACT_URL", "http://127.0.0.1:8100"))
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=int(os.getenv("PORT", os.getenv("RETRACT_PORT", "8100"))))
    mcp = commands.add_parser("mcp", help="Serve memory tools over MCP stdio")
    mcp.add_argument("--activity-log", type=Path, help="Append actual tool metadata to a local JSONL log")
    request = commands.add_parser("call", help="POST a structured JSON file to an API route")
    request.add_argument("route", choices=["projects", "remember", "updates", "updates/natural", "plans", "plans/revise", "handoffs", "handoffs/claim", "recall", "history"])
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
        if args.command == "mcp":
            from .mcp import serve as serve_mcp
            serve_mcp(args.url, args.activity_log)
            return
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
                    hosted = None
                    mode = os.getenv("RETRACT_MODE", "local")
                    if mode == "hosted":
                        from .hosted import HostedConfig, HostedWorkspaces
                        hosted = HostedWorkspaces(HostedConfig.from_env(), store)
                    elif mode != "local":
                        raise ValueError("RETRACT_MODE must be local or hosted")
                    server = make_server(MemoryService(store), args.port, hosted=hosted)
                    print(f"Retract {mode} listening on port {server.server_port}", flush=True)
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
    except (RuntimeError, ValueError, OSError, ImportError, KeyError) as exc:
        print(f"retract: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
