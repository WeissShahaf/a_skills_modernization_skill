#!/usr/bin/env python3
"""skill-optimizer apply tool.

Applies a run's confirmed decisions to disk, reversibly. Dry-run is the default;
nothing is written without --apply, and --apply refuses unless every affected
decision carries user_confirmed: true. Every file about to change is copied to
backups/<timestamp>/ and byte-checked first. Disable means moving the skill
folder to a sibling _disabled/; nothing is ever deleted. The tool prints the
exact undo commands for what it did, and --undo <backup-dir> replays them.

Invocation (any shell):  uv run scripts/apply.py [--run-dir DIR] [--apply] [--undo BACKUP_DIR]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ANTHROPIC_READONLY = "anthropic-official"


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"apply: {path} not found - run audit.py inventory/usage and record decisions first.")
    except json.JSONDecodeError as e:
        sys.exit(f"apply: {path} is not valid JSON ({e}).")


def latest_run_dir(runs_dir: Path) -> Path:
    runs = sorted(p for p in runs_dir.iterdir() if p.is_dir() and (p / "decisions.json").exists())
    if not runs:
        sys.exit(f"apply: no run with decisions.json under {runs_dir}.")
    return runs[-1]


def plan_actions(inventory: dict, decisions: dict, run_dir: Path) -> list[dict]:
    """Turn decisions into concrete filesystem actions. Reads the filesystem only to detect a completed earlier apply."""
    by_id = {s.get("id", s["name"]): s for s in inventory["skills"]}
    actions = []
    for d in decisions["skills"]:
        skill = by_id.get(d["id"])
        if skill is None:
            actions.append({"kind": "skip", "id": d["id"], "reason": "not in inventory"})
            continue
        readonly = skill.get("readonly_reason")
        if readonly == ANTHROPIC_READONLY or not skill.get("writable", True):
            actions.append({"kind": "skip", "id": d["id"],
                            "reason": f"read-only ({readonly or 'not writable'}); report-only"})
            continue
        skill_dir = Path(skill["path"])
        if skill_dir.name.lower() == "skill.md":  # inventory paths point at SKILL.md
            skill_dir = skill_dir.parent
        action = d.get("action")
        if action == "disable":
            dst = skill_dir.parent / "_disabled" / skill_dir.name
            if dst.is_dir() and not skill_dir.exists():  # re-run after an earlier --apply
                actions.append({"kind": "skip", "id": d["id"], "reason": f"already disabled at {dst}"})
                continue
            actions.append({"kind": "move", "id": d["id"], "confirmed": bool(d.get("user_confirmed")),
                            "src": str(skill_dir), "dst": str(dst)})
        elif action == "optimize":
            rewritten = run_dir / "rewritten" / skill_dir.name
            if not rewritten.is_dir():
                actions.append({"kind": "skip", "id": d["id"],
                                "reason": f"no rewritten copy at {rewritten} (Phase 3/4 not complete)"})
                continue
            files = [p for p in rewritten.rglob("*") if p.is_file()]
            actions.append({"kind": "write", "id": d["id"], "confirmed": bool(d.get("user_confirmed")),
                            "src_dir": str(rewritten), "dst_dir": str(skill_dir),
                            "files": [str(p.relative_to(rewritten)) for p in files]})
        else:
            actions.append({"kind": "skip", "id": d["id"], "reason": f"action '{action}' needs no write"})
    return actions


def backup(paths: list[Path], backup_root: Path) -> None:
    manifest: dict[str, str] = {}  # backup-relative path -> original path, so --undo restores exactly
    for src in paths:
        if not src.exists():
            continue
        rel = Path(*src.parts[1:]) if src.is_absolute() else src  # drop drive/root
        dst = backup_root / rel
        manifest[rel.as_posix()] = str(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
            if dst.stat().st_size != src.stat().st_size:
                sys.exit(f"apply: backup size mismatch for {src}; nothing has been changed.")
    backup_root.mkdir(parents=True, exist_ok=True)
    (backup_root / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


def execute(actions: list[dict], run_dir: Path, do_apply: bool) -> list[str]:
    undo: list[str] = []
    live = [a for a in actions if a["kind"] in ("move", "write")]
    unconfirmed = [a["id"] for a in live if not a.get("confirmed")]
    if do_apply and unconfirmed:
        sys.exit("apply: refusing --apply; these decisions lack user_confirmed: true -> " + ", ".join(unconfirmed))

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = run_dir / "backups" / stamp

    for a in actions:
        if a["kind"] == "skip":
            print(f"  skip   {a['id']}: {a['reason']}")
        elif a["kind"] == "move":
            print(f"  move   {a['src']}  ->  {a['dst']}")
        else:
            print(f"  write  {len(a['files'])} file(s) into {a['dst_dir']}")
    if not live:
        print("nothing to apply.")
        return undo
    if not do_apply:
        print(f"dry run: {len(live)} action(s) planned, nothing written. Re-run with --apply to execute.")
        return undo

    backup([Path(a["src"]) if a["kind"] == "move" else Path(a["dst_dir"]) for a in live], backup_root)
    print(f"backup written to {backup_root}")

    for a in live:
        if a["kind"] == "move":
            src, dst = Path(a["src"]), Path(a["dst"])
            if dst.exists():
                sys.exit(f"apply: {dst} already exists; refusing to overwrite a previous disable.")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            undo.append(f'move "{dst}" "{src}"')
        else:
            src_dir, dst_dir = Path(a["src_dir"]), Path(a["dst_dir"])
            for rel in a["files"]:
                target = dst_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_dir / rel, target)
            undo.append(f'restore "{dst_dir}" from "{backup_root}"')
    undo_text = "\n".join(undo) + "\n"
    (run_dir / "undo.txt").write_text(undo_text, encoding="utf-8")            # latest apply
    (backup_root / "undo.txt").write_text(undo_text, encoding="utf-8")        # per-backup, survives later applies
    print("undo commands (also in undo.txt, and in the backup dir):")
    for line in undo:
        print("  " + line)
    print(f"  or: uv run scripts/apply.py --run-dir {run_dir} --undo {backup_root}")
    return undo


def undo_from_backup(run_dir: Path, backup_root: Path) -> None:
    if not backup_root.is_dir():
        sys.exit(f"apply: backup dir {backup_root} not found.")
    undo_file = backup_root / "undo.txt"  # per-backup list; older runs only wrote run_dir/undo.txt
    if not undo_file.exists():
        undo_file = run_dir / "undo.txt"
    if undo_file.exists():
        for line in undo_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("move "):
                _, dst, src = line.split('"')[0], line.split('"')[1], line.split('"')[3]
                if Path(dst).exists():
                    shutil.move(dst, src)
                    print(f"  moved back {dst} -> {src}")
    manifest_file = backup_root / "manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8")) if manifest_file.exists() else {}
    for src in backup_root.rglob("*"):
        if src.is_file() and src not in (manifest_file, backup_root / "undo.txt"):
            rel = src.relative_to(backup_root)
            target = None
            for key, orig in manifest.items():  # longest manifest prefix wins
                if rel.as_posix() == key or rel.as_posix().startswith(key + "/"):
                    if target is None or len(key) > len(target[0]):
                        target = (key, Path(orig) / rel.relative_to(key))
            if target is not None:
                target = target[1]
            else:  # legacy backup without manifest: assume absolute original
                drive = Path(rel.parts[0] + ":/") if len(rel.parts[0]) == 1 else Path("/")
                target = Path("/") / rel if not sys.platform.startswith("win") else drive / Path(*rel.parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
    print(f"restored files from {backup_root}")


def main() -> int:
    ap = argparse.ArgumentParser(description="skill-optimizer apply tool (dry-run by default)")
    ap.add_argument("--run-dir", help="run folder holding inventory.json + decisions.json (default: latest under runs/)")
    ap.add_argument("--runs-dir", default=str(Path(__file__).resolve().parent.parent / "runs"))
    ap.add_argument("--apply", action="store_true", help="execute the planned actions (needs user_confirmed on each)")
    ap.add_argument("--undo", metavar="BACKUP_DIR", help="restore from a backup dir written by an earlier --apply")
    args = ap.parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else latest_run_dir(Path(args.runs_dir))
    if args.undo:
        undo_from_backup(run_dir, Path(args.undo))
        return 0
    inventory = load_json(run_dir / "inventory.json")
    decisions = load_json(run_dir / "decisions.json")
    print(f"run: {run_dir}")
    actions = plan_actions(inventory, decisions, run_dir)
    execute(actions, run_dir, args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
