#!/usr/bin/env python3
"""Graph-build harness node state tracker."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_PATH = Path("plan/manifest.json")
STATE_DIR = Path("run/state")


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text())


def state_path(node_id):
    return STATE_DIR / f"{node_id}.json"


def load_state(node_id):
    return json.loads(state_path(node_id).read_text())


def save_state(node_id, state):
    state["updated"] = datetime.now(timezone.utc).isoformat()
    state_path(node_id).write_text(json.dumps(state, indent=2) + "\n")


def detect_cycle(nodes_by_id):
    visiting = set()
    visited = set()

    def visit(node_id, path):
        if node_id in visited:
            return
        if node_id in visiting:
            cycle = " -> ".join(path + [node_id])
            print(f"ERROR: dependency cycle: {cycle}", file=sys.stderr)
            sys.exit(1)
        visiting.add(node_id)
        for dep in nodes_by_id[node_id].get("deps", []):
            visit(dep, path + [node_id])
        visiting.discard(node_id)
        visited.add(node_id)

    for node_id in nodes_by_id:
        visit(node_id, [])


def cmd_init():
    manifest = load_manifest()
    nodes_by_id = {n["id"]: n for n in manifest["nodes"]}
    detect_cycle(nodes_by_id)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    for node in manifest["nodes"]:
        if state_path(node["id"]).exists():
            continue
        save_state(node["id"], {
            "id": node["id"],
            "status": "pending",
            "attempts": 0,
            "worktree": None,
            "verdict": None,
            "notes": "",
            "pre_verify_head": None,
        })


def cmd_next():
    manifest = load_manifest()
    nodes_by_id = {n["id"]: n for n in manifest["nodes"]}
    states = {nid: load_state(nid) for nid in nodes_by_id}

    blocked = [nid for nid, s in states.items() if s["status"] == "blocked"]
    if blocked:
        for nid in blocked:
            print(f"BLOCKED {nid}")
        sys.exit(1)

    if all(s["status"] == "verified" for s in states.values()):
        print("DONE")
        return

    for nid, node in nodes_by_id.items():
        s = states[nid]
        if s["status"] not in ("pending", "failed"):
            continue
        if s["attempts"] >= 3:
            continue
        if all(states[dep]["status"] == "verified" for dep in node.get("deps", [])):
            print(nid)


def cmd_status():
    manifest = load_manifest()
    nodes_by_id = {n["id"]: n for n in manifest["nodes"]}
    print(f"{'id':<20} {'status':<10} {'attempts':<9} {'verdict'}")
    for nid in nodes_by_id:
        s = load_state(nid)
        print(f"{s['id']:<20} {s['status']:<10} {s['attempts']:<9} {s['verdict']}")


def cmd_start(node_id):
    s = load_state(node_id)
    s["status"] = "building"
    s["worktree"] = f".worktrees/{node_id}"
    save_state(node_id, s)


def cmd_record(node_id, verdict, notes):
    s = load_state(node_id)
    if verdict == "pass":
        s["status"] = "verified"
        s["verdict"] = "pass"
        s["notes"] = ""
    else:
        s["attempts"] += 1
        s["verdict"] = "fail"
        s["notes"] = notes
        s["status"] = "blocked" if s["attempts"] >= 3 else "failed"
    save_state(node_id, s)


def main():
    if len(sys.argv) == 1:
        cmd_next()
        return
    cmd = sys.argv[1]
    if cmd == "init":
        cmd_init()
    elif cmd == "status":
        cmd_status()
    elif cmd == "start":
        cmd_start(sys.argv[2])
    elif cmd == "record":
        cmd_record(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
