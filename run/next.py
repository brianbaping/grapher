#!/usr/bin/env python3
"""Graph-build harness node state tracker."""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_PATH = Path("plan/manifest.json")
STATE_DIR = Path("run/state")


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


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


def cmd_begin_verify(node_id):
    s = load_state(node_id)
    worktree = s.get("worktree")
    if not worktree:
        print(f"ERROR: node {node_id} has no worktree set", file=sys.stderr)
        sys.exit(1)

    try:
        toplevel = git("rev-parse", "--show-toplevel", cwd=worktree)
    except OSError:
        print(f"ERROR: worktree {worktree} does not exist or is not accessible", file=sys.stderr)
        sys.exit(1)
    if toplevel.returncode != 0 or Path(toplevel.stdout.strip()).resolve() != Path(worktree).resolve():
        print(f"ERROR: worktree {worktree} is not a real git worktree", file=sys.stderr)
        sys.exit(1)

    dirty = git("status", "--porcelain", "--untracked-files=no", cwd=worktree)
    if dirty.returncode != 0:
        print(f"ERROR: git status failed in worktree {worktree}", file=sys.stderr)
        sys.exit(1)
    if dirty.stdout.strip():
        print(f"ERROR: worktree {worktree} has uncommitted tracked changes", file=sys.stderr)
        sys.exit(1)

    head = git("rev-parse", "HEAD", cwd=worktree)
    if head.returncode != 0:
        print(f"ERROR: git rev-parse HEAD failed in worktree {worktree}", file=sys.stderr)
        sys.exit(1)

    s["status"] = "verifying"
    s["pre_verify_head"] = head.stdout.strip()
    save_state(node_id, s)


def cmd_record(node_id, verdict, notes):
    s = load_state(node_id)
    status = s["status"]
    if status not in ("building", "verifying"):
        print(f"ERROR: node {node_id} is not awaiting verification (status: {status})", file=sys.stderr)
        sys.exit(1)
    if status == "building" and verdict == "pass":
        print(f"ERROR: node {node_id} cannot be recorded pass without begin-verify (status: building)", file=sys.stderr)
        sys.exit(1)

    pre_head = s.get("pre_verify_head")
    if pre_head:
        worktree = s["worktree"]
        try:
            head_result = git("rev-parse", "HEAD", cwd=worktree)
            dirty_result = git("status", "--porcelain", "--untracked-files=no", cwd=worktree)
        except OSError:
            head_result = None
            dirty_result = None
        if (
            head_result is None
            or dirty_result is None
            or head_result.returncode != 0
            or dirty_result.returncode != 0
            or head_result.stdout.strip() != pre_head
            or dirty_result.stdout.strip()
        ):
            verdict = "fail"
            notes = "structural guard: verifier modified tracked files"

    s["pre_verify_head"] = None
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
    elif cmd == "begin-verify":
        cmd_begin_verify(sys.argv[2])
    elif cmd == "record":
        cmd_record(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
