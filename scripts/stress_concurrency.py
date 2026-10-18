"""Concurrent reads and writes through the real HTTP service and FalkorDB.

Uses a disposable UUID graph and deletes only that graph. Measures one service
process: writes are serialized by MemoryService.lock and guarded by the project
revision. This is a correctness check under contention, not a throughput claim.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import argparse
import json
import math
import os
from pathlib import Path
import statistics
import sys
from threading import Thread
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from retract.api import make_server
from retract.graph import GraphStore
from retract.models import PlanInput, RememberInput, parse
from retract.service import MemoryService


def distribution(samples):
    ordered = sorted(samples)
    return {"samples": len(ordered), "p50_ms": round(statistics.median(ordered), 2),
            "p95_ms": round(ordered[math.ceil(len(ordered) * .95) - 1], 2), "max_ms": round(ordered[-1], 2)}


class Client:
    def __init__(self, port):
        self.base = f"http://127.0.0.1:{port}"

    def post(self, route, body):
        started = time.perf_counter()
        request = Request(self.base + route, data=json.dumps(body).encode(),
                          headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=30) as response:
                status, result = response.status, json.loads(response.read())
        except HTTPError as exc:
            status, result = exc.code, json.loads(exc.read() or b"{}")
        return status, result, (time.perf_counter() - started) * 1000


def fact(project, index, revision=None):
    return {"project_id": project, "scope": "load/main", "subject": f"subject-{index}",
            "predicate": "value", "value": f"value {index}", "expected_revision": revision,
            "source": {"id": f"S-{project}-{index}", "kind": "developer", "title": "Load test",
                       "content": f"Value {index}", "authority": "developer"}}


def seed(service):
    fixture = json.loads((ROOT / "fixtures/demo-seed.json").read_text())
    service.create_project(**fixture["project"])
    for action in fixture["actions"]:
        if action["route"] == "remember":
            service.remember(parse(RememberInput, action["body"]))
        else:
            service.record_plan(parse(PlanInput, action["body"]))
    for tenant in ("tenant-a", "tenant-b"):
        service.create_project(tenant, tenant)


def run(writers, readers, racers, workers):
    from falkordb import FalkorDB

    client = FalkorDB(host=os.getenv("FALKORDB_HOST", "127.0.0.1"), port=int(os.getenv("FALKORDB_PORT", "6380")),
                      password=os.getenv("FALKORDB_PASSWORD") or None, socket_timeout=30)
    name = f"retract-stress-{uuid4().hex}"
    graph = client.select_graph(name)
    store = GraphStore(graph)
    store.initialize()
    service = MemoryService(store)
    server = make_server(service, 0)
    Thread(target=server.serve_forever, daemon=True).start()
    api = Client(server.server_port)
    checks = {}
    try:
        seed(service)
        start_revision = service.project("tenant-a")["revision"]

        # 1. Mixed load: independent writes to two tenants plus recall reads, all at once.
        jobs = ([("/remember", fact(tenant, i)) for i in range(writers) for tenant in ("tenant-a", "tenant-b")]
                + [("/recall", {"project_id": "account-settings", "scope": "web-client/main"})] * readers)
        started = time.perf_counter()
        with ThreadPoolExecutor(workers) as pool:
            results = list(pool.map(lambda job: (job[0], *api.post(*job)), jobs))
        elapsed = time.perf_counter() - started
        writes = [r for r in results if r[0] == "/remember"]
        reads = [r for r in results if r[0] == "/recall"]
        recalled = {t: service.recall(t, "load/main") for t in ("tenant-a", "tenant-b")}
        tenant_facts = {t: r["active_facts"] for t, r in recalled.items()}
        checks["mixed_load"] = {
            "requests": len(results), "seconds": round(elapsed, 3),
            "requests_per_second": round(len(results) / elapsed, 1),
            "writes_ok": sum(r[1] == 200 for r in writes), "writes_failed": sum(r[1] != 200 for r in writes),
            "reads_ok": sum(r[1] == 200 for r in reads), "reads_failed": sum(r[1] != 200 for r in reads),
            "write_latency": distribution([r[3] for r in writes]),
            "read_latency": distribution([r[3] for r in reads]),
            "lost_writes": {t: writers - len(f) for t, f in tenant_facts.items()},
            "final_revision_tenant_a": service.project("tenant-a")["revision"],
            "expected_revision_tenant_a": start_revision + writers,
            "cross_tenant_leaks": sum(not link["source"]["id"].startswith(f"S-{t}-")
                                      for t, r in recalled.items() for link in r["sources"]),
        }
        reads_consistent = all(r[2].get("active_facts") == reads[0][2].get("active_facts") for r in reads)
        checks["mixed_load"]["reads_consistent"] = reads_consistent

        # 2. Stale writers: everyone read the same revision, then writes at once.
        revision = service.project("tenant-a")["revision"]
        stale = [fact("tenant-a", 10_000 + i, revision) for i in range(racers)]
        with ThreadPoolExecutor(workers) as pool:
            outcomes = [status for status, _, _ in pool.map(lambda body: api.post("/remember", body), stale)]
        checks["stale_revision_race"] = {"writers": racers, "accepted": outcomes.count(200),
                                         "rejected_conflict": outcomes.count(409),
                                         "other": len(outcomes) - outcomes.count(200) - outcomes.count(409)}

        # 3. Handoff race: many agents claim one open handoff.
        api.post("/handoffs", {"project_id": "account-settings", "scope": "web-client/main", "handoff_id": "H-race",
                               "from_agent": "agent-sender", "plan_id": "P1", "note": "Race test",
                               "fact_ids": ["F1", "F4"]})
        claims = [{"project_id": "account-settings", "handoff_id": "H-race", "agent": f"agent-{i}"}
                  for i in range(racers)]
        with ThreadPoolExecutor(workers) as pool:
            claimed = list(pool.map(lambda body: api.post("/handoffs/claim", body), claims))
        winners = [r[1]["handoff"]["claimed_by"] for r in claimed if r[0] == 200]
        stored = service.store.get("Handoff", "account-settings", "H-race")
        checks["handoff_claim_race"] = {"claimers": racers, "winners": len(winners),
                                        "rejected_conflict": sum(r[0] == 409 for r in claimed),
                                        "stored_claimed_by_matches_winner": winners == [stored["claimed_by"]]}
    finally:
        server.shutdown()
        server.server_close()
        graph.delete()
        client.connection.close()

    mixed = checks["mixed_load"]
    passed = (mixed["writes_failed"] == 0 and mixed["reads_failed"] == 0 and mixed["reads_consistent"]
              and not any(mixed["lost_writes"].values()) and mixed["cross_tenant_leaks"] == 0
              and mixed["final_revision_tenant_a"] == mixed["expected_revision_tenant_a"]
              and checks["stale_revision_race"]["accepted"] == 1
              and checks["stale_revision_race"]["rejected_conflict"] == racers - 1
              and checks["handoff_claim_race"]["winners"] == 1
              and checks["handoff_claim_race"]["stored_claimed_by_matches_winner"])
    return {"status": "passed" if passed else "failed", "measured_at": datetime.now(timezone.utc).isoformat(),
            "setup": {"service_processes": 1, "client_threads": workers, "graph": "disposable FalkorDB graph"},
            "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--writers", type=int, default=100, help="writes per tenant")
    parser.add_argument("--readers", type=int, default=200)
    parser.add_argument("--racers", type=int, default=24)
    parser.add_argument("--workers", type=int, default=24, help="concurrent client threads (server allows 32)")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run(args.writers, args.readers, args.racers, args.workers)
    encoded = json.dumps(report, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded + "\n")
    print(encoded)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
