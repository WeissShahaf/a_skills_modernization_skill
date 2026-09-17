# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""skill-optimizer audit.py — inventory, usage evidence, lint, token totals, usage logging.

Subcommands: inventory | usage | lint | tokens | log-usage. Run with
`uv run scripts/audit.py <subcommand> --help` for exact flags.

Anti-fabrication invariant: every usage count, timestamp, and class this script
emits is backed by a parsed line it can point to. No sample data, no
placeholders that look like real evidence. Absent evidence is 0 / null /
"unknown" plus a coverage_gap sentence, never invented.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

# --------------------------------------------------------------------------
# Constants (documented here so a threshold's "why" lives next to its value)
# --------------------------------------------------------------------------

# Model ids/aliases Claude Code and the API currently recognise (reference_notes.md
# §4 + PLAN §3). A trailing "[1m]" long-context suffix is allowed on any of them.
KNOWN_MODEL_BASES = {
    "claude-fable-5-1", "claude-opus-5", "claude-opus-4-8", "claude-sonnet-5",
    "claude-haiku-4-5", "opusplan", "default", "best", "fable", "opus",
    "sonnet", "haiku", "inherit",
}
EFFORT_LEVELS = {"low", "medium", "high", "xhigh", "max"}
RESERVED_NAME_WORDS = {"anthropic", "claude"}
CONVENTIONAL_TOP_DIRS = {"scripts", "references", "templates", "assets"}
README_LIKE = {"readme.md", "changelog.md", "install.md"}

# BODY-009 "doc constants": numbers that show up legitimately in this very
# checklist (token/line budgets, cache minimums) and would otherwise be
# flagged as unexplained magic numbers on every skill that quotes them.
BODY009_DOC_CONSTANTS = {"20", "40", "64", "100", "500", "1024", "5000", "0.8"}

SHOUT_TOKEN_RE = re.compile(r"\b(ALWAYS|NEVER|MUST|CRITICAL|IMPORTANT|DO NOT)\b")
RITUAL_RE = re.compile(
    r"think step by step|show your reasoning|walk me through your reasoning|"
    r"explain your reasoning|double[- ]check|verify with a subagent|"
    r"think carefully|reason out loud",
    re.I,
)
API_KNOB_RE = re.compile(r"budget_tokens|\btemperature\b|\btop_p\b|\btop_k\b|prefill", re.I)
WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\|\\\\")  # matches C:\... or a \\UNC\ path
TIME_SENSITIVE_RE = re.compile(
    r"\b(as of (20\d\d|today)|currently|latest version|recently (added|released)|"
    r"until (20\d\d)|in (20\d\d) )\b",
    re.I,
)
OLD_SECTION_RE = re.compile(r"old patterns|deprecated|history", re.I)
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
MCP_RAW_RE = re.compile(r"\bmcp__[a-z0-9_]+__[a-z0-9_]+\b", re.I)
# Only bundled-file mentions count: references/... or scripts/..., optionally ./-prefixed,
# and not glued to a preceding word, dot or slash (so ".../x", "//host/scripts/x" and
# prose like "for scripts/servers" are not treated as bundled paths).
PATH_MENTION_RE = re.compile(r"(?<![\w./])((?:\./)?(?:references|scripts)/[\w./-]+)")
NOT_THIRD_PERSON_RE = re.compile(
    r"\b(I can|I will|I'll|you can|you will|you'll|use me|helps you)\b", re.I
)
WHEN_TO_USE_RE = re.compile(
    r"\b(use when|when the user|when asked|use for|triggers? on|use this)\b", re.I
)
NEGATIVE_TRIGGER_RE = re.compile(
    r"\b(not for|do not use|don't use|does not|not when|instead of|use .* instead)\b", re.I
)
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

SEVERITY_RANK = {"error": 0, "warn": 1, "info": 2}

# A line that is itself quoted material — a fenced block, a blockquote, or a line
# opening with a quotation mark — is usually an example of what NOT to write
# (modernize-prompt quotes bad prompts on purpose). The deterministic rules
# cannot tell instruction from illustration, so such hits are kept but downgraded
# to info and tagged, leaving the judgment to the auditor subagent.
QUOTED_LINE_RE = re.compile(r'^\s*(>|"|“|\'|`)')
QUOTED_TAG = "[quoted example] "

RULES: list[tuple[str, str, str]] = [
    ("FM-001", "error", "No valid YAML frontmatter."),
    ("FM-002", "error", "name missing, >64 chars, wrong shape, or a reserved word."),
    ("FM-003", "error", "name does not equal the skill directory name."),
    ("FM-004", "error", "description missing/empty, >1024 chars, or contains XML tags."),
    ("FM-005", "warn", "description is under 20 tokens_est."),
    ("FM-006", "warn", "description is not third person."),
    ("FM-007", "info", "description has no when-to-use cue."),
    ("FM-008", "info", "description has no negative trigger."),
    ("FM-009", "warn", "model: is set to an unrecognised id or alias."),
    ("FM-010", "warn", "effort: is set to an unrecognised level."),
    ("FM-011", "error", "effort: is present on a Haiku-routed skill."),
    ("FM-012", "info", "no model:/effort: at all (routing decision pending)."),
    ("BODY-001", "error", "body is 500 lines or more."),
    ("BODY-002", "warn", "body is 5000 tokens_est or more."),
    ("BODY-003", "info", "body is approaching 5000 tokens_est (>=3500)."),
    ("BODY-004", "warn", "shouting: ALWAYS/NEVER/MUST/CRITICAL/IMPORTANT/CAPS."),
    ("BODY-005", "error", "ritual phrase (think step by step, double-check, ...)."),
    ("BODY-006", "error", "API knob referenced (budget_tokens, temperature, ...)."),
    ("BODY-007", "warn", "Windows/backslash path."),
    ("BODY-008", "warn", "time-sensitive phrase outside an Old patterns/history section."),
    ("BODY-009", "info", "bare magic number with no stated reason."),
    ("BODY-010", "warn", "raw mcp__server__tool form instead of Server:tool."),
    ("REF-001", "error", "a referenced path does not exist on disk."),
    ("REF-002", "error", "a reference file sits more than one level under references/."),
    ("REF-003", "warn", "a reference file is >100 lines with no table of contents."),
    ("REF-004", "warn", "a reference file has no Load when/Keywords line."),
    ("REF-005", "info", "a reference file is never mentioned in SKILL.md."),
    ("FILE-001", "warn", "README.md/CHANGELOG.md/INSTALL.md inside the skill dir."),
    ("FILE-002", "info", "a file outside SKILL.md/scripts//references//templates//assets/."),
    ("SCRIPT-001", "info", "a scripts/*.py with no def main / __main__ guard."),
]

# --------------------------------------------------------------------------
# Small pure helpers (parsing, no I/O)
# --------------------------------------------------------------------------

def tokens_est(text: Optional[str]) -> int:
    if not text:
        return 0
    return math.ceil(len(text) / 4)

def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_iso(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp (a 'Z' suffix is accepted) into a tz-aware datetime."""
    if not ts or not isinstance(ts, str):
        return None
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def normalize_epoch_or_iso(value: Any) -> Optional[str]:
    """history.jsonl timestamps: epoch ms (>1e11), epoch s, or an ISO string."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        if v > 1e11:
            v = v / 1000.0
        try:
            dt = datetime.fromtimestamp(v, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, str):
        dt = parse_iso(value)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None
    return None

def parse_frontmatter(text: str) -> tuple[dict, Optional[str], str, int]:
    """Split SKILL.md text into (frontmatter_dict, error_or_None, body_text, body_line_offset).

    body_line_offset is the 0-indexed line where the body starts in text.split("\\n"),
    so absolute line numbers for body-relative scans are body_line_offset + i + 1.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, "missing frontmatter delimiters (file must start with '---')", text, 0
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, "missing closing '---' for frontmatter", text, 0
    fm_text = "\n".join(lines[1:end_idx])
    body_offset = end_idx + 1
    body_text = "\n".join(lines[body_offset:])
    try:
        loaded = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        return {}, f"invalid YAML: {exc}", body_text, body_offset
    if loaded is None:
        return {}, "frontmatter is empty", body_text, body_offset
    if not isinstance(loaded, dict):
        return {}, "frontmatter is not a mapping", body_text, body_offset
    return loaded, None, body_text, body_offset

def is_known_model(model: str) -> bool:
    m = model.strip()
    if m.endswith("[1m]"):
        m = m[: -len("[1m]")]
    return m in KNOWN_MODEL_BASES

def make_finding(rule_id: str, severity: str, file: str, line: Optional[int],
                  evidence: str, suggested_fix: str) -> dict:
    return {
        "rule_id": rule_id,
        "severity": severity,
        "file": file,
        "line": line,
        "evidence": (evidence or "")[:120],
        "suggested_fix": suggested_fix,
    }

def sort_findings(findings: list[dict]) -> list[dict]:
    return sorted(
        findings,
        key=lambda f: (SEVERITY_RANK.get(f["severity"], 9), f["line"] if f["line"] is not None else -1),
    )

# --------------------------------------------------------------------------
# I/O helpers
# --------------------------------------------------------------------------

def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)

def read_text(path: Path) -> str:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")

def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".audit-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=False)
            f.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

def load_inventory(path: Path) -> dict:
    if not path.is_file():
        fail(f"inventory file not found: {path.as_posix()}")
    try:
        text = read_text(path)
        data = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"could not parse inventory JSON at {path.as_posix()}: {exc}")
    if not isinstance(data, dict) or "skills" not in data:
        fail(f"{path.as_posix()} does not look like an audit.py inventory file")
    return data  # type: ignore[return-value]

# --------------------------------------------------------------------------
# inventory — discovery
# --------------------------------------------------------------------------

def default_usage() -> dict:
    return {
        "invocations": 0,
        "invocations_recent": 0,
        "last_used": None,
        "confidence": "none",
        "evidence": [],
        "coverage_gap": "usage not computed yet — run `audit.py usage`",
        "class_proposal": "unknown",
        "class_basis": "no usage run",
    }

def compute_has_toc(text: str) -> bool:
    if re.search(r"table of contents|^## contents", text, re.I | re.M):
        return True
    first40 = text.split("\n")[:40]
    anchor_count = sum(len(re.findall(r"\]\(#[\w-]+\)", line)) for line in first40)
    return anchor_count >= 3

def compute_has_load_when(text: str) -> bool:
    non_empty = [ln for ln in text.split("\n") if ln.strip()][:5]
    blob = "\n".join(non_empty)
    return bool(re.search(r"load when", blob, re.I)) and bool(re.search(r"keywords?:", blob, re.I))

def build_reference_item(skill_dir: Path, file_path: Path) -> dict:
    rel = file_path.relative_to(skill_dir / "references")
    rel_full = Path("references") / rel
    text = read_text(file_path)
    return {
        "path": rel_full.as_posix(),
        "lines": len(text.splitlines()),
        "chars": len(text),
        "tokens_est": tokens_est(text),
        "has_toc": compute_has_toc(text),
        "has_load_when": compute_has_load_when(text),
        "depth": len(rel.parts),
    }

def build_script_item(skill_dir: Path, file_path: Path) -> dict:
    rel_full = file_path.relative_to(skill_dir)
    text = read_text(file_path)
    return {"path": rel_full.as_posix(), "lines": len(text.splitlines())}

TOOLING_DIRS = {".venv", "venv", "__pycache__", "node_modules", ".git", ".mypy_cache", ".ruff_cache", ".pytest_cache"}


def collect_skill_files(skill_dir: Path) -> tuple[list[dict], list[dict], list[dict]]:
    references: list[dict] = []
    scripts: list[dict] = []
    others: list[dict] = []
    for p in sorted(skill_dir.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(skill_dir)
        if TOOLING_DIRS.intersection(rel.parts):  # a uv/npm environment beside the scripts is not skill content
            continue
        if rel.as_posix() == "SKILL.md":
            continue
        top = rel.parts[0]
        if top == "references":
            references.append(build_reference_item(skill_dir, p))
        elif top == "scripts":
            scripts.append(build_script_item(skill_dir, p))
        else:
            others.append({"path": rel.as_posix()})
    return references, scripts, others

def compute_writable(source: str, skill_md: Optional[Path]) -> tuple[bool, Optional[str]]:
    if source == "anthropic-official":
        return False, "anthropic-official"
    if source == "plugin":
        return False, "plugin-remote"
    if skill_md is not None and skill_md.exists() and not os.access(skill_md, os.W_OK):
        return False, "filesystem"
    return True, None

def build_skill_record(skill_md: Path, source: str, disabled: bool, dir_name: str) -> dict:
    text = read_text(skill_md)
    frontmatter_raw, frontmatter_error, body_text, _offset = parse_frontmatter(text)
    name = frontmatter_raw.get("name") if isinstance(frontmatter_raw.get("name"), str) else None
    description = frontmatter_raw.get("description") if isinstance(frontmatter_raw.get("description"), str) else None

    # Anthropic-official override: frontmatter name prefix or a path segment.
    if (name and name.startswith("anthropic-skills:")) or "anthropic-skills" in skill_md.parts:
        source = "anthropic-official"

    skill_dir = skill_md.parent
    references, scripts, others = collect_skill_files(skill_dir)
    writable, readonly_reason = compute_writable(source, skill_md)

    return {
        "id": None,  # assigned by the caller for global uniqueness
        "source": source,
        "path": skill_md.as_posix(),
        "dir_name": dir_name,
        "name": name,
        "dir_name_matches": (name == dir_name) if name else False,
        "description": description,
        "description_chars": len(description) if description else 0,
        "description_tokens_est": tokens_est(description),
        "body_lines": len(body_text.splitlines()),
        "body_chars": len(body_text),
        "l1_tokens_est": tokens_est((name or "") + (description or "")),
        "l2_tokens_est": tokens_est(text),
        "references": references,
        "scripts": scripts,
        "other_files": others,
        "frontmatter": {
            "description": description,
            "model": frontmatter_raw.get("model"),
            "effort": frontmatter_raw.get("effort"),
            "inherit": frontmatter_raw.get("inherit"),
        },
        "frontmatter_raw": frontmatter_raw,
        "frontmatter_error": frontmatter_error,
        "writable": writable,
        "readonly_reason": readonly_reason,
        "disabled": disabled,
        "usage": default_usage(),
        "findings": [],
        "findings_skipped": None,
    }

def build_anthropic_synthetic(name: str) -> dict:
    dir_name = name.split(":")[-1]
    return {
        "id": None,
        "source": "anthropic-official",
        "path": None,
        "dir_name": dir_name,
        "name": name,
        "dir_name_matches": None,
        "description": None,
        "description_chars": 0,
        "description_tokens_est": 0,
        "body_lines": 0,
        "body_chars": 0,
        "l1_tokens_est": 0,
        "l2_tokens_est": 0,
        "references": [],
        "scripts": [],
        "other_files": [],
        "frontmatter": {"description": None, "model": None, "effort": None, "inherit": None},
        "frontmatter_raw": {},
        "frontmatter_error": None,
        "writable": False,
        "readonly_reason": "anthropic-official",
        "disabled": False,
        "usage": default_usage(),
        "findings": [],
        "findings_skipped": None,
    }

def discover_simple_root(root: Path) -> list[tuple[Path, str, bool]]:
    """root/*/SKILL.md plus root/_disabled/*/SKILL.md -> (skill_md, dir_name, disabled)."""
    results: list[tuple[Path, str, bool]] = []
    if not root.is_dir():
        return results
    for child in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "_disabled"):
        f = child / "SKILL.md"
        if f.is_file():
            results.append((f, child.name, False))
    disabled_root = root / "_disabled"
    if disabled_root.is_dir():
        for child in sorted(p for p in disabled_root.iterdir() if p.is_dir()):
            f = child / "SKILL.md"
            if f.is_file():
                results.append((f, child.name, True))
    return results

def make_unique_id(base_id: str, used_ids: set[str]) -> str:
    if base_id not in used_ids:
        used_ids.add(base_id)
        return base_id
    n = 2
    while f"{base_id}#{n}" in used_ids:
        n += 1
    new_id = f"{base_id}#{n}"
    used_ids.add(new_id)
    return new_id

def require_dir(path_str: str, label: str) -> Path:
    p = Path(path_str)
    if not p.is_dir():
        fail(f"{label} not found or not a directory: {p.as_posix()}")
    return p

def cmd_inventory(args: argparse.Namespace) -> None:
    generated_at = iso_now()
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    skill_root = Path(__file__).resolve().parents[1]
    default_runs_dir = skill_root.parent / "runs"
    runs_dir = Path(args.runs_dir) if args.runs_dir else default_runs_dir
    out_path = Path(args.out) if args.out else runs_dir / run_id / "inventory.json"

    skills: list[dict] = []
    roots_scanned: list[dict] = []
    used_ids: set[str] = set()

    def add_skill(record: dict, base_id: str) -> None:
        record["id"] = make_unique_id(base_id, used_ids)
        skills.append(record)

    if args.personal:
        root = require_dir(args.personal, "--personal")
        found = discover_simple_root(root)
        for skill_md, dir_name, disabled in found:
            rec = build_skill_record(skill_md, "claude-code-personal", disabled, dir_name)
            add_skill(rec, f"{rec['source']}:{dir_name}")
        roots_scanned.append({"flag": "--personal", "path": root.as_posix(), "skills_found": len(found)})

    for proj in args.project or []:
        proj_root = require_dir(proj, "--project")
        skills_root = proj_root / ".claude" / "skills"
        found = discover_simple_root(skills_root)
        proj_name = proj_root.name
        for skill_md, dir_name, disabled in found:
            rec = build_skill_record(skill_md, "claude-code-project", disabled, dir_name)
            base_id = f"claude-code-project:{proj_name}/{dir_name}"
            if rec["source"] != "claude-code-project":
                base_id = f"{rec['source']}:{dir_name}"  # anthropic-official override
            add_skill(rec, base_id)
        roots_scanned.append({"flag": "--project", "path": proj_root.as_posix(), "skills_found": len(found)})

    if args.plugins:
        plugins_root = require_dir(args.plugins, "--plugins")
        matches = sorted(plugins_root.glob("**/skills/*/SKILL.md"))
        for skill_md in matches:
            dir_name = skill_md.parent.name
            rec = build_skill_record(skill_md, "plugin", False, dir_name)
            add_skill(rec, f"{rec['source']}:{dir_name}")
        roots_scanned.append({"flag": "--plugins", "path": plugins_root.as_posix(), "skills_found": len(matches)})

    for acct in args.account or []:
        root = require_dir(acct, "--account")
        found = discover_simple_root(root)
        for skill_md, dir_name, disabled in found:
            rec = build_skill_record(skill_md, "account", disabled, dir_name)
            add_skill(rec, f"{rec['source']}:{dir_name}")
        roots_scanned.append({"flag": "--account", "path": root.as_posix(), "skills_found": len(found)})

    for name in args.anthropic_name or []:
        rec = build_anthropic_synthetic(name)
        add_skill(rec, name)
        roots_scanned.append({"flag": "--anthropic-name", "path": name, "skills_found": 1})

    inventory = {
        "schema": "skill-optimizer/inventory/1",
        "run_id": run_id,
        "generated_at": generated_at,
        "roots_scanned": roots_scanned,
        "token_method": "chars/4",
        "skills": skills,
        "coverage": None,
        "tokens": None,
    }
    write_json_atomic(out_path, inventory)

    by_source: dict[str, int] = {}
    disabled_count = 0
    for sk in skills:
        by_source[sk["source"]] = by_source.get(sk["source"], 0) + 1
        if sk["disabled"]:
            disabled_count += 1
    print(f"inventory: {len(skills)} skills across {len(roots_scanned)} scanned roots")
    for src, n in sorted(by_source.items()):
        print(f"  {src}: {n}")
    print(f"  disabled: {disabled_count}")
    print(f"wrote {out_path.as_posix()}")

# --------------------------------------------------------------------------
# usage — evidence
# --------------------------------------------------------------------------

def find_skill_tool_uses(obj: Any) -> Iterable[dict]:
    if isinstance(obj, dict):
        if obj.get("type") == "tool_use" and obj.get("name") == "Skill":
            yield obj
        for v in obj.values():
            yield from find_skill_tool_uses(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from find_skill_tool_uses(item)

def build_match_index(skills: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for sk in skills:
        keys = set()
        if sk.get("dir_name"):
            keys.add(sk["dir_name"].lower())
        name = sk.get("name")
        if isinstance(name, str) and name:
            keys.add(name.lower())
            if ":" in name:
                keys.add(name.split(":")[-1].lower())
        for k in keys:
            index.setdefault(k, sk)
    return index

def match_evidence(raw_name: str, index: dict[str, dict]) -> Optional[dict]:
    n = raw_name.strip().lstrip("/").lower()
    if not n:
        return None
    if n in index:
        return index[n]
    if ":" in n:
        tail = n.split(":")[-1]
        if tail in index:
            return index[tail]
    return None

def empty_source_meta() -> dict:
    return {
        "present": False, "files": 0, "lines": 0, "parse_errors": 0,
        "earliest_ts": None, "latest_ts": None, "days_covered": 0, "covers_window": False,
    }

def note_ts(meta: dict, ts_iso: Optional[str]) -> None:
    if not ts_iso:
        return
    if meta["earliest_ts"] is None or ts_iso < meta["earliest_ts"]:
        meta["earliest_ts"] = ts_iso
    if meta["latest_ts"] is None or ts_iso > meta["latest_ts"]:
        meta["latest_ts"] = ts_iso

def finalize_meta(meta: dict, window_start: datetime) -> None:
    earliest = parse_iso(meta["earliest_ts"])
    latest = parse_iso(meta["latest_ts"])
    if earliest and latest:
        meta["days_covered"] = round((latest - earliest).total_seconds() / 86400)
    meta["covers_window"] = bool(earliest and earliest <= window_start)

def iter_jsonl_objects(fpath: Path, meta: dict) -> Iterable[tuple[int, dict]]:
    """Yield (line_no, obj) for each parsed JSON-object line; unparsable/non-object
    lines are skipped and counted in meta['parse_errors'] (never raised — a bad
    transcript line must not abort usage evidence collection)."""
    # Streamed line by line: a real ~/.claude/projects tree can hold hundreds of MB
    # of transcripts, and reading each file whole would double that in memory.
    with fpath.open("r", encoding="utf-8-sig", errors="replace", newline=None) as fh:
        for line_no, raw_line in enumerate(fh, start=1):
            if not raw_line.strip():
                continue
            meta["lines"] += 1
            try:
                obj = json.loads(raw_line)
            except json.JSONDecodeError:
                meta["parse_errors"] += 1
                continue
            if not isinstance(obj, dict):
                meta["parse_errors"] += 1
                continue
            yield line_no, obj

def parse_transcripts(projects_dir: Optional[str]) -> tuple[list[dict], dict]:
    """Returns (evidence_items, meta). evidence_items are pre-match dicts."""
    meta = empty_source_meta()
    items: list[dict] = []
    if not projects_dir:
        return items, meta
    root = Path(projects_dir)
    if not root.is_dir():
        return items, meta
    meta["present"] = True
    files = sorted(root.rglob("*.jsonl"))
    meta["files"] = len(files)
    for fpath in files:
        for line_no, obj in iter_jsonl_objects(fpath, meta):
            ts_iso = normalize_epoch_or_iso(obj.get("timestamp"))
            note_ts(meta, ts_iso)
            for block in find_skill_tool_uses(obj):
                tool_input = block.get("input") or {}
                skill_name = (
                    tool_input.get("skill") or tool_input.get("name") or tool_input.get("skill_name")
                )
                if not skill_name:
                    continue
                items.append({
                    "source": "transcript", "file": fpath.as_posix(), "line_no": line_no,
                    "ts": ts_iso, "project": obj.get("cwd") or fpath.parent.name,
                    "skill_as_written": str(skill_name).lstrip("/"),
                })
    return items, meta

def parse_history(history_file: Optional[str]) -> tuple[list[dict], dict]:
    meta = empty_source_meta()
    items: list[dict] = []
    if not history_file:
        return items, meta
    fpath = Path(history_file)
    if not fpath.is_file():
        return items, meta
    meta["present"] = True
    meta["files"] = 1
    slash_re = re.compile(r"^/([\w-]+)")
    for line_no, obj in iter_jsonl_objects(fpath, meta):
        ts_iso = normalize_epoch_or_iso(obj.get("timestamp"))
        note_ts(meta, ts_iso)
        display = obj.get("display")
        if not isinstance(display, str):
            continue
        m = slash_re.match(display.strip())
        if not m:
            continue
        items.append({
            "source": "history", "file": fpath.as_posix(), "line_no": line_no,
            "ts": ts_iso, "project": obj.get("project"), "skill_as_written": m.group(1),
        })
    return items, meta

def parse_usage_log(usage_log_file: Optional[str]) -> tuple[list[dict], dict]:
    meta = empty_source_meta()
    items: list[dict] = []
    if not usage_log_file:
        return items, meta
    fpath = Path(usage_log_file)
    if not fpath.is_file():
        return items, meta
    meta["present"] = True
    meta["files"] = 1
    for line_no, obj in iter_jsonl_objects(fpath, meta):
        if not obj.get("skill"):
            continue
        ts_iso = normalize_epoch_or_iso(obj.get("ts"))
        note_ts(meta, ts_iso)
        items.append({
            "source": "usage-log", "file": fpath.as_posix(), "line_no": line_no,
            "ts": ts_iso, "project": obj.get("project"),
            "skill_as_written": str(obj.get("skill")).lstrip("/"),
        })
    return items, meta

def classify_skill(sk: dict, window_days: int, recent_days: int, common_min: int,
                    recent_min: int, transcripts_meta: dict) -> tuple[str, str, Optional[str]]:
    inv = sk["usage"]["invocations"]
    inv_recent = sk["usage"]["invocations_recent"]
    inv_all = sk["usage"]["invocations_all_time"]
    source = sk["source"]

    if inv >= common_min or inv_recent >= recent_min:
        basis = (
            f"{inv} invocations in {window_days} days, {inv_recent} in last {recent_days} days "
            f"(transcripts: {transcripts_meta['files']} files, {transcripts_meta['days_covered']} days covered)"
        )
        return "common", basis, None

    if inv >= 1:
        basis = f"{inv} invocations in {window_days} days (below common threshold {common_min}; {inv_all} recorded all-time)"
        return "rare", basis, None

    # 0 invocations within the window (there may still be older, out-of-window evidence).
    if source in ("claude-code-personal", "claude-code-project", "plugin") and \
            transcripts_meta["present"] and transcripts_meta["covers_window"]:
        extra = f"; {inv_all} recorded further back, outside the window" if inv_all > inv else ""
        basis = (
            f"0 invocations in {window_days} days{extra}; transcripts present and cover the window "
            f"({transcripts_meta['days_covered']} days covered)"
        )
        return "never", basis, None

    if source == "account":
        gap = "account skill: Claude Code transcripts cannot observe Cowork usage"
    elif source == "anthropic-official":
        gap = "anthropic-official skill: Claude Code transcripts cannot observe this surface"
    elif not transcripts_meta["present"]:
        gap = "no transcripts available (--projects not given or not a directory)"
    elif transcripts_meta["files"] == 0:
        gap = "no transcript files found under --projects (cleanupPeriodDays purged them, or wrong directory)"
    else:
        gap = f"transcripts cover {transcripts_meta['days_covered']} of {window_days} days (cleanupPeriodDays?)"
    basis = f"0 invocations; {gap}"
    return "unknown", basis, gap

def cmd_usage(args: argparse.Namespace) -> None:
    inv_path = Path(args.inventory)
    inventory = load_inventory(inv_path)
    skills: list[dict] = inventory["skills"]
    out_path = Path(args.out) if args.out else inv_path

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=args.window_days)
    recent_start = now - timedelta(days=args.recent_days)

    transcript_items, transcripts_meta = parse_transcripts(args.projects)
    history_items, history_meta = parse_history(args.history)
    usage_log_items, usage_log_meta = parse_usage_log(args.usage_log)
    finalize_meta(transcripts_meta, window_start)
    finalize_meta(history_meta, window_start)
    finalize_meta(usage_log_meta, window_start)

    index = build_match_index(skills)
    matched: dict[str, list[dict]] = {sk["id"]: [] for sk in skills}
    unmatched: dict[str, int] = {}
    # history.jsonl slash commands that match no skill are usually Claude Code
    # built-ins (/compact, /model, ...), not missing skills, so they are kept in
    # their own bucket rather than mixed with unmatched Skill tool calls.
    unmatched_history: dict[str, int] = {}

    for item in transcript_items + history_items + usage_log_items:
        sk = match_evidence(item["skill_as_written"], index)
        if sk is None:
            key = item["skill_as_written"].strip().lstrip("/").lower()
            bucket = unmatched_history if item["source"] == "history" else unmatched
            bucket[key] = bucket.get(key, 0) + 1
            continue
        matched[sk["id"]].append(item)

    for sk in skills:
        items = matched[sk["id"]]
        items.sort(key=lambda it: it["ts"] or "", reverse=True)

        inv_all = len(items)
        inv_in_window = 0
        inv_recent = 0
        last_used = None
        for it in items:
            ts = it["ts"]
            if ts is None:
                inv_in_window += 1  # null-ts evidence still counts toward invocations
                continue
            dt = parse_iso(ts)
            if dt is not None and dt >= window_start:
                inv_in_window += 1
            if dt is not None and dt >= recent_start:
                inv_recent += 1
            if last_used is None or ts > last_used:
                last_used = ts

        evidence_out = [
            {
                "source": it["source"], "file": it["file"], "line_no": it["line_no"],
                "ts": it["ts"], "project": it["project"], "skill_as_written": it["skill_as_written"],
            }
            for it in items[:20]
        ]

        sk["usage"] = {
            "invocations": inv_in_window,
            "invocations_recent": inv_recent,
            "invocations_all_time": inv_all,
            "last_used": last_used,
            "confidence": "machine" if inv_all > 0 else "none",
            "evidence": evidence_out,
            "coverage_gap": None,
            "class_proposal": "unknown",
            "class_basis": "",
        }
        cls, basis, gap = classify_skill(
            sk, args.window_days, args.recent_days, args.common_min, args.recent_min, transcripts_meta
        )
        sk["usage"]["class_proposal"] = cls
        sk["usage"]["class_basis"] = basis
        sk["usage"]["coverage_gap"] = gap

    inventory["coverage"] = {
        "window_days": args.window_days,
        "recent_days": args.recent_days,
        "window_start": window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_at": iso_now(),
        "sources": {
            "transcripts": transcripts_meta,
            "history": history_meta,
            "usage_log": usage_log_meta,
        },
        "unmatched_skills": unmatched,
        "unmatched_history_commands": unmatched_history,
        "thresholds": {"common_min": args.common_min, "recent_min": args.recent_min},
    }
    write_json_atomic(out_path, inventory)

    class_counts: dict[str, int] = {}
    for sk in skills:
        c = sk["usage"]["class_proposal"]
        class_counts[c] = class_counts.get(c, 0) + 1
    print(f"usage: window={args.window_days}d recent={args.recent_days}d "
          f"transcripts(present={transcripts_meta['present']}, files={transcripts_meta['files']}, "
          f"covers_window={transcripts_meta['covers_window']})")
    for c in ("common", "rare", "never", "unknown"):
        if c in class_counts:
            print(f"  {c}: {class_counts[c]}")
    if unmatched:
        print(f"  unmatched skill names (transcripts/usage-log): {', '.join(sorted(unmatched))}")
    if unmatched_history:
        print(f"  unmatched history slash-commands (likely built-ins): {', '.join(sorted(unmatched_history))}")
    print(f"wrote {out_path.as_posix()}")

# --------------------------------------------------------------------------
# lint — deterministic rules
# --------------------------------------------------------------------------

def check_fm001(fm_error: Optional[str]) -> list[dict]:
    if not fm_error:
        return []
    return [make_finding("FM-001", "error", "SKILL.md", 1, fm_error,
                          "Add valid YAML frontmatter delimited by two '---' lines with at least name and description.")]

def check_fm002(name: Optional[str]) -> list[dict]:
    findings = []
    if not name:
        findings.append(make_finding("FM-002", "error", "SKILL.md", 1, "name is missing",
                                      "Add a name: field matching the skill directory name."))
        return findings
    if len(name) > 64:
        findings.append(make_finding("FM-002", "error", "SKILL.md", 1, f"name is {len(name)} chars (>64)",
                                      "Shorten name to 64 characters or fewer."))
    if not NAME_RE.match(name):
        findings.append(make_finding("FM-002", "error", "SKILL.md", 1, f"name '{name}' has the wrong shape",
                                      "Use lowercase letters, digits, and single hyphens only, e.g. my-skill-name."))
    if set(name.split("-")) & RESERVED_NAME_WORDS:
        findings.append(make_finding("FM-002", "error", "SKILL.md", 1, f"name '{name}' contains a reserved word",
                                      "Remove 'anthropic'/'claude' as a standalone word from the name."))
    return findings

def check_fm003(name: Optional[str], dir_name: str) -> list[dict]:
    if name and name != dir_name:
        return [make_finding("FM-003", "error", "SKILL.md", 1, f"name '{name}' != directory '{dir_name}'",
                              f"Rename the directory to '{name}', or set name: {dir_name}.")]
    return []

def check_fm004(description: Optional[str]) -> list[dict]:
    findings = []
    if not description:
        findings.append(make_finding("FM-004", "error", "SKILL.md", 1, "description is missing or empty",
                                      "Add a third-person description stating what the skill does and when to use it."))
        return findings
    if len(description) > 1024:
        findings.append(make_finding("FM-004", "error", "SKILL.md", 1, f"description is {len(description)} chars (>1024)",
                                      "Shorten the description to 1024 characters or fewer."))
    if re.search(r"[<>]", description):
        findings.append(make_finding("FM-004", "error", "SKILL.md", 1, "description contains '<' or '>'",
                                      "Remove XML/HTML-style tags from the description."))
    return findings

def check_fm005_to_008(description: Optional[str], tokens: int) -> list[dict]:
    if not description:
        return []
    findings = []
    if tokens < 20:
        findings.append(make_finding("FM-005", "warn", "SKILL.md", 1, f"description is ~{tokens} tokens_est (<20)",
                                      "Expand the description to state what it does and when to use it."))
    first_sentence = re.split(r"(?<=[.!?])\s", description.strip(), maxsplit=1)[0]
    if NOT_THIRD_PERSON_RE.search(first_sentence):
        findings.append(make_finding("FM-006", "warn", "SKILL.md", 1, first_sentence,
                                      "Rewrite in third person, e.g. 'Does X.' instead of 'I can do X.'"))
    if not WHEN_TO_USE_RE.search(description):
        findings.append(make_finding("FM-007", "info", "SKILL.md", 1, description[:100],
                                      "Add a when-to-use cue, e.g. 'Use when ...'."))
    if not NEGATIVE_TRIGGER_RE.search(description):
        findings.append(make_finding("FM-008", "info", "SKILL.md", 1, description[:100],
                                      "Add a negative trigger, e.g. 'Not for ...' or 'Use X instead.'"))
    return findings

def check_fm009_to_012(frontmatter: dict) -> list[dict]:
    findings = []
    model = frontmatter.get("model")
    effort = frontmatter.get("effort")
    inherit = frontmatter.get("inherit")
    if model and isinstance(model, str) and not is_known_model(model):
        findings.append(make_finding("FM-009", "warn", "SKILL.md", 1, f"model: {model}",
                                      "Use a recognised model id/alias, e.g. claude-sonnet-5."))
    if effort and isinstance(effort, str) and effort not in EFFORT_LEVELS:
        findings.append(make_finding("FM-010", "warn", "SKILL.md", 1, f"effort: {effort}",
                                      "Use one of low|medium|high|xhigh|max."))
    if effort and isinstance(model, str) and "haiku" in model.lower():
        findings.append(make_finding("FM-011", "error", "SKILL.md", 1, f"model: {model}, effort: {effort}",
                                      "Remove effort: — Haiku 4.5 has no effort parameter."))
    if not model and not effort and not inherit:
        findings.append(make_finding("FM-012", "info", "SKILL.md", 1, "no model:/effort:/inherit: set",
                                      "Pick a model/effort per the routing table, or set inherit: true."))
    return findings

def quoted_context(line: str, in_fence: bool, match_start: Optional[int] = None) -> bool:
    """True when the line is quoted material, or when the match sits inside an
    inline "..." / `...` span (an odd number of quote marks precede it)."""
    if in_fence or QUOTED_LINE_RE.match(line):
        return True
    if match_start is None:
        return False
    prefix = line[:match_start]
    return prefix.count('"') % 2 == 1 or prefix.count("`") % 2 == 1

def check_body_shouting(body_lines: list[str], offset: int) -> list[dict]:
    findings = []
    in_fence = False
    for i, line in enumerate(body_lines):
        if len(findings) >= 10:
            break
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        # Inline code spans hold identifiers (`EXTENSION_COMPUTE_DICT`), not emphasis.
        prose = re.sub(r"`[^`]*`", " ", line)
        token_hits = len(SHOUT_TOKEN_RE.findall(prose))
        shout = token_hits >= 2
        if not shout:
            run = 0
            for w in re.findall(r"[A-Za-z']+", prose):
                if w.isupper() and len(w) >= 4:
                    run += 1
                    if run >= 3:
                        shout = True
                        break
                else:
                    run = 0
        if shout:
            quoted = quoted_context(line, in_fence)
            # "ALWAYS/NEVER" (caps joined by a slash) names the words rather than using
            # them for emphasis - typical of a diff explanation or a rule description.
            mentioned = bool(re.search(r"\b[A-Z]{4,}/[A-Z]{4,}\b", prose)) and not quoted
            tag = QUOTED_TAG if quoted else ("[mentioned as words] " if mentioned else "")
            findings.append(make_finding(
                "BODY-004", "info" if (quoted or mentioned) else "warn", "SKILL.md", offset + i + 1,
                tag + line.strip(),
                "Replace CAPS/ALWAYS/NEVER with the wanted behaviour and the reason for it."
                + (" (quoted material: confirm it is an example, not an instruction)" if quoted else ""),
            ))
    return findings

def check_body_line_regex(body_lines: list[str], offset: int, pattern: re.Pattern, rule_id: str,
                           severity: str, suggested_fix: str, skip_code_fences: bool = False,
                           skip_deprecated_sections: bool = False,
                           downgrade_quoted: bool = False) -> list[dict]:
    findings = []
    in_fence = False
    in_old_section = False
    for i, line in enumerate(body_lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if skip_deprecated_sections:
            heading = HEADING_RE.match(line)
            if heading:
                in_old_section = bool(OLD_SECTION_RE.search(heading.group(1)))
        if skip_code_fences and in_fence:
            continue
        if skip_deprecated_sections and in_old_section:
            continue
        m = pattern.search(line)
        if m:
            quoted = downgrade_quoted and quoted_context(line, in_fence, m.start())
            findings.append(make_finding(
                rule_id, "info" if quoted else severity, "SKILL.md", offset + i + 1,
                (QUOTED_TAG if quoted else "") + stripped,
                suggested_fix + (" (quoted material: confirm it is an example, not an instruction)" if quoted else ""),
            ))
    return findings

def check_body_magic_numbers(body_lines: list[str], offset: int) -> list[dict]:
    findings = []
    in_fence = False
    num_re = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])")
    for i, line in enumerate(body_lines):
        if len(findings) >= 5:
            break
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or stripped.startswith("#") or stripped.startswith("|"):
            continue
        for m in num_re.finditer(line):
            num_str = m.group(1)
            try:
                val = float(num_str)
            except ValueError:
                continue
            if val < 10 or num_str in BODY009_DOC_CONSTANTS:
                continue
            start, end = m.span()
            before = line[max(0, start - 1):start]
            after = line[end:end + 1]
            if before in ("/", "-", ".", ":"):
                continue
            if after in ("/", "-", ".", ":"):
                continue
            # `providers.py:67` style source citations, and years 1990-2099 (citations, dates)
            if re.search(r"\.\w{1,5}:\d*$", line[:end]):
                continue
            if re.fullmatch(r"(19|20)\d\d", num_str):
                continue
            context_after = line[end:end + 40]
            if re.search(r"\b(because|since)\b", context_after, re.I) or context_after[:5].find("(") != -1:
                continue
            findings.append(make_finding("BODY-009", "info", "SKILL.md", offset + i + 1, stripped,
                                          "State why this number is what it is, e.g. '... because <reason>'."))
            break
    return findings

def check_ref_rules(skill_dir: Path, references: list[dict], full_text: str) -> list[dict]:
    findings = []
    for ref in references:
        ref_path = ref["path"]
        if ref["depth"] > 1:
            findings.append(make_finding("REF-002", "error", ref_path, None,
                                          f"{ref_path} is {ref['depth']} levels under references/",
                                          "Flatten references/ to one level below SKILL.md."))
        if not ref_path.lower().endswith(".md"):
            continue  # scripts/data under references/ are not prose; TOC and Load-when rules do not apply
        if ref["lines"] > 100 and not ref["has_toc"]:
            findings.append(make_finding("REF-003", "warn", ref_path, None,
                                          f"{ref['lines']} lines, no table of contents",
                                          "Add a table of contents near the top of the file."))
        if not ref["has_load_when"]:
            findings.append(make_finding("REF-004", "warn", ref_path, None,
                                          "no 'Load when ... / Keywords: ...' line",
                                          "Add 'Load when: ...' and 'Keywords: ...' as the first two lines."))
        if ref_path not in full_text and Path(ref_path).name not in full_text:
            findings.append(make_finding("REF-005", "info", ref_path, None,
                                          f"{ref_path} is never mentioned in SKILL.md",
                                          "Reference the file from SKILL.md, or delete it."))
    return findings

def check_ref_001(skill_dir: Path, full_text: str) -> list[dict]:
    findings = []
    lines = full_text.split("\n")
    for i, line in enumerate(lines):
        for m in PATH_MENTION_RE.finditer(line):
            mention = m.group(1).rstrip(").,:;\"'`>")
            if mention.startswith("./"):
                mention = mention[2:]
            candidate = (skill_dir / mention).resolve()
            try:
                candidate.relative_to(skill_dir.resolve())
            except ValueError:
                continue
            if not candidate.exists():
                top_dir = skill_dir / mention.split("/")[0]
                if top_dir.is_dir():
                    findings.append(make_finding("REF-001", "error", "SKILL.md", i + 1, mention,
                                                  f"Create {mention}, or remove the reference to it."))
                else:
                    # The skill has no such top-level folder at all, so this is more likely
                    # prose that happens to look like a path than a broken bundled reference.
                    findings.append(make_finding("REF-001", "warn", "SKILL.md", i + 1, mention,
                                                  f"No {top_dir.name}/ folder in this skill; if this is a "
                                                  f"real file, create it, otherwise reword so it does not "
                                                  f"read as a bundled path."))
    return findings

def check_file_rules(other_files: list[dict]) -> list[dict]:
    findings = []
    for item in other_files:
        p = item["path"]
        basename_lower = Path(p).name.lower()
        top = p.split("/")[0]
        if basename_lower in README_LIKE:
            findings.append(make_finding("FILE-001", "warn", p, None, p,
                                          "Fold this content into SKILL.md or references/, then delete it."))
            continue
        if top in ("templates", "assets"):
            continue
        findings.append(make_finding("FILE-002", "info", p, None, p,
                                      "Move this under scripts/, references/, templates/, or assets/, or delete it."))
    return findings

def check_script_rules(skill_dir: Path, scripts: list[dict]) -> list[dict]:
    findings = []
    for item in scripts:
        p = skill_dir / item["path"]
        if p.suffix != ".py" or not p.is_file():
            continue
        text = read_text(p)
        if "def main" not in text and "__main__" not in text:
            findings.append(make_finding("SCRIPT-001", "info", item["path"], None, "no def main / __main__ guard",
                                          "Add a main() and an if __name__ == '__main__': guard, or note it is a library."))
    return findings

def lint_skill(record: dict) -> list[dict]:
    skill_md = Path(record["path"])
    text = read_text(skill_md)
    frontmatter_raw, fm_error, body_text, offset = parse_frontmatter(text)
    body_lines = body_text.split("\n")
    skill_dir = skill_md.parent

    findings: list[dict] = []
    findings += check_fm001(fm_error)
    findings += check_fm002(record["name"])
    findings += check_fm003(record["name"], record["dir_name"])
    findings += check_fm004(record["description"])
    findings += check_fm005_to_008(record["description"], record["description_tokens_est"])
    findings += check_fm009_to_012(record["frontmatter"])

    body_lines_count = len(body_text.splitlines())
    body_tokens = tokens_est(body_text)
    if body_lines_count >= 500:
        findings.append(make_finding("BODY-001", "error", "SKILL.md", None, f"{body_lines_count} body lines",
                                      "Split background/examples into references/ files; keep the body under 500 lines."))
    if body_tokens >= 5000:
        findings.append(make_finding("BODY-002", "warn", "SKILL.md", None, f"~{body_tokens} body tokens_est",
                                      "Move background/examples/templates to references/ to shrink the always-loaded body."))
    elif body_tokens >= 3500:
        findings.append(make_finding("BODY-003", "info", "SKILL.md", None, f"~{body_tokens} body tokens_est",
                                      "Approaching the 5000-token body budget; consider moving content to references/."))

    findings += check_body_shouting(body_lines, offset)
    findings += check_body_line_regex(body_lines, offset, RITUAL_RE, "BODY-005", "error",
                                       "Remove the ritual phrase; give a runnable check (script/test) instead.",
                                       downgrade_quoted=True)
    findings += check_body_line_regex(body_lines, offset, API_KNOB_RE, "BODY-006", "error",
                                       "Remove the API knob; these models reject legacy sampling params.")
    findings += check_body_line_regex(body_lines, offset, WINDOWS_PATH_RE, "BODY-007", "warn",
                                       "Use forward-slash paths (e.g. ~/.claude/... or <skill-root>/...).",
                                       skip_code_fences=True, downgrade_quoted=True)
    findings += check_body_line_regex(body_lines, offset, TIME_SENSITIVE_RE, "BODY-008", "warn",
                                       "Move time-sensitive content to an 'Old patterns' / history section, or remove it.",
                                       skip_deprecated_sections=True)
    findings += check_body_magic_numbers(body_lines, offset)
    findings += check_body_line_regex(body_lines, offset, MCP_RAW_RE, "BODY-010", "warn",
                                       "Write MCP tools as Server:tool_name instead of the raw mcp__server__tool form.")

    findings += check_ref_001(skill_dir, text)
    findings += check_ref_rules(skill_dir, record["references"], text)
    findings += check_file_rules(record["other_files"])
    findings += check_script_rules(skill_dir, record["scripts"])

    return sort_findings(findings)

def apply_lint(record: dict) -> None:
    if not record.get("writable", False):
        reason = record.get("readonly_reason") or "unknown"
        record["findings"] = []
        record["findings_skipped"] = f"read-only: {reason}"
        return
    if record.get("path") is None:
        record["findings"] = []
        record["findings_skipped"] = "read-only: no source file on disk"
        return
    record["findings"] = lint_skill(record)
    record["findings_skipped"] = None

def print_rules_table() -> None:
    print("| rule_id | severity | description |")
    print("|---|---|---|")
    for rule_id, severity, desc in RULES:
        print(f"| {rule_id} | {severity} | {desc} |")

def print_findings_table(record: dict) -> None:
    findings = record["findings"]
    if record["findings_skipped"]:
        print(f"{record['id']}: findings skipped ({record['findings_skipped']})")
        return
    if not findings:
        print(f"{record['id']}: no findings")
        return
    print(f"{record['id']}: {len(findings)} findings")
    print("| rule_id | severity | line | evidence |")
    print("|---|---|---|---|")
    for f in findings:
        line = f["line"] if f["line"] is not None else ""
        print(f"| {f['rule_id']} | {f['severity']} | {line} | {f['evidence']} |")

def has_ci_error(skills: list[dict]) -> bool:
    return any(
        sk.get("writable") and any(f["severity"] == "error" for f in sk.get("findings", []))
        for sk in skills
    )

def cmd_lint(args: argparse.Namespace) -> None:
    if args.list_rules:
        print_rules_table()
        return
    if not args.inventory and not args.path:
        fail("lint requires --inventory FILE or --path SKILLDIR (or --list-rules)")
    if args.inventory and args.path:
        fail("lint: pass only one of --inventory or --path")

    if args.path:
        skill_dir = Path(args.path)
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            fail(f"--path {skill_dir.as_posix()} has no SKILL.md")
        record = build_skill_record(skill_md, "claude-code-personal", False, skill_dir.name)
        record["id"] = f"{record['source']}:{record['dir_name']}"
        apply_lint(record)
        print_findings_table(record)
        if args.out:
            inventory = {
                "schema": "skill-optimizer/inventory/1", "run_id": None, "generated_at": iso_now(),
                "roots_scanned": [], "token_method": "chars/4", "skills": [record],
                "coverage": None, "tokens": None,
            }
            write_json_atomic(Path(args.out), inventory)
            print(f"wrote {Path(args.out).as_posix()}")
        if args.ci and has_ci_error([record]):
            sys.exit(1)
        return

    inv_path = Path(args.inventory)
    inventory = load_inventory(inv_path)
    skills: list[dict] = inventory["skills"]
    for sk in skills:
        apply_lint(sk)
    out_path = Path(args.out) if args.out else inv_path
    write_json_atomic(out_path, inventory)

    linted = sum(1 for sk in skills if not sk["findings_skipped"])
    skipped = len(skills) - linted
    counts = {"error": 0, "warn": 0, "info": 0}
    for sk in skills:
        for f in sk["findings"]:
            counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    print(f"lint: {linted} skills linted, {skipped} skipped (read-only)")
    print(f"  errors: {counts['error']}  warn: {counts['warn']}  info: {counts['info']}")
    print(f"wrote {out_path.as_posix()}")
    if args.ci and has_ci_error(skills):
        sys.exit(1)

# --------------------------------------------------------------------------
# tokens
# --------------------------------------------------------------------------

def call_count_tokens_api(api_key: str, text: str) -> Optional[int]:
    body = json.dumps({
        "model": "claude-sonnet-5",
        "messages": [{"role": "user", "content": text}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages/count_tokens",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("input_tokens")

def cmd_tokens(args: argparse.Namespace) -> None:
    inv_path = Path(args.inventory)
    inventory = load_inventory(inv_path)
    skills: list[dict] = inventory["skills"]
    out_path = Path(args.out) if args.out else inv_path

    l1_total_all = sum(sk["l1_tokens_est"] for sk in skills)
    l1_total_by_source: dict[str, int] = {}
    for sk in skills:
        l1_total_by_source[sk["source"]] = l1_total_by_source.get(sk["source"], 0) + sk["l1_tokens_est"]
    l1_total_enabled = sum(sk["l1_tokens_est"] for sk in skills if not sk["disabled"])
    l2_total_all = sum(sk["l2_tokens_est"] for sk in skills)
    top_l1 = sorted(skills, key=lambda s: s["l1_tokens_est"], reverse=True)[:10]
    top_l2 = sorted(skills, key=lambda s: s["l2_tokens_est"], reverse=True)[:10]

    method = "chars/4"
    if args.api:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("tokens --api: ANTHROPIC_API_KEY not set, keeping chars/4 estimates")
        else:
            api_failures = 0
            api_used = 0
            for sk in skills:
                if not sk.get("path"):
                    continue
                try:
                    text = read_text(Path(sk["path"]))
                except OSError:
                    continue
                l1_text = (sk["name"] or "") + (sk["description"] or "")
                try:
                    l1_api = call_count_tokens_api(api_key, l1_text) if l1_text else None
                    l2_api = call_count_tokens_api(api_key, text)
                except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
                    api_failures += 1
                    continue
                if l1_api is not None:
                    sk["l1_tokens_api"] = l1_api
                if l2_api is not None:
                    sk["l2_tokens_api"] = l2_api
                api_used += 1
            if api_used:
                method = "api:count_tokens"
            if api_failures:
                print(f"tokens --api: {api_failures} skill(s) fell back to chars/4 after an API error")

    inventory["tokens"] = {
        "method": method,
        "l1_total_all": l1_total_all,
        "l1_total_by_source": l1_total_by_source,
        "l1_total_enabled": l1_total_enabled,
        "l2_total_all": l2_total_all,
        "top_l1": [{"id": s["id"], "l1_tokens_est": s["l1_tokens_est"]} for s in top_l1],
        "top_l2": [{"id": s["id"], "l2_tokens_est": s["l2_tokens_est"]} for s in top_l2],
    }
    write_json_atomic(out_path, inventory)

    print(f"tokens ({method}): L1 total {l1_total_all} (enabled {l1_total_enabled}), L2 total {l2_total_all}")
    for src, n in sorted(l1_total_by_source.items()):
        print(f"  L1 {src}: {n}")
    print(f"wrote {out_path.as_posix()}")

# --------------------------------------------------------------------------
# log-usage
# --------------------------------------------------------------------------

def cmd_log_usage(args: argparse.Namespace) -> None:
    try:
        raw = sys.stdin.read()
    except Exception as exc:  # never break the hook
        print(f"log-usage: could not read stdin: {exc}", file=sys.stderr)
        return
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(f"log-usage: could not parse stdin JSON: {exc}", file=sys.stderr)
        return
    if not isinstance(payload, dict) or payload.get("tool_name") != "Skill":
        return
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return
    skill_name = tool_input.get("skill") or tool_input.get("name") or tool_input.get("skill_name")
    if not skill_name:
        return

    if args.log:
        log_path = Path(args.log)
    elif os.environ.get("SKILL_OPTIMIZER_USAGE_LOG"):
        log_path = Path(os.environ["SKILL_OPTIMIZER_USAGE_LOG"])
    else:
        log_path = Path(__file__).resolve().parents[1] / "usage-log.jsonl"

    entry = {
        "ts": iso_now(),
        "skill": str(skill_name).lstrip("/"),
        "project": payload.get("cwd"),
        "session_id": payload.get("session_id"),
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as exc:
        print(f"log-usage: failed to write {log_path.as_posix()}: {exc}", file=sys.stderr)

# --------------------------------------------------------------------------
# argparse + main
# --------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="audit.py", description="skill-optimizer audit tool")
    sub = parser.add_subparsers(dest="command", required=True)

    p_inv = sub.add_parser("inventory", help="discover skills and write inventory.json")
    p_inv.add_argument("--personal", help="personal skills dir, e.g. ~/.claude/skills")
    p_inv.add_argument("--project", action="append", help="a project root (repeatable)")
    p_inv.add_argument("--plugins", help="plugins dir, e.g. ~/.claude/plugins")
    p_inv.add_argument("--account", action="append", help="an account-skill source folder (repeatable)")
    p_inv.add_argument("--anthropic-name", action="append", help="a name-only Anthropic skill, e.g. anthropic-skills:docx (repeatable)")
    p_inv.add_argument("--runs-dir", help="where run folders are written (default: runs/ next to the skill root)")
    p_inv.add_argument("--run-id", help="run id (default: UTC timestamp YYYYMMDD-HHMMSS)")
    p_inv.add_argument("--out", help="output inventory.json path (default: <runs-dir>/<run-id>/inventory.json)")
    p_inv.set_defaults(func=cmd_inventory)

    p_use = sub.add_parser("usage", help="attach usage evidence and a class_proposal to an inventory")
    p_use.add_argument("--inventory", required=True, help="inventory.json to update")
    p_use.add_argument("--projects", help="Claude Code projects dir, e.g. ~/.claude/projects")
    p_use.add_argument("--history", help="Claude Code history.jsonl")
    p_use.add_argument("--usage-log", help="this tool's own usage log (see log-usage)")
    p_use.add_argument("--window-days", type=int, default=90)
    p_use.add_argument("--recent-days", type=int, default=30)
    p_use.add_argument("--common-min", type=int, default=5)
    p_use.add_argument("--recent-min", type=int, default=2)
    p_use.add_argument("--out", help="output path (default: update --inventory in place)")
    p_use.set_defaults(func=cmd_usage)

    p_lint = sub.add_parser("lint", help="run deterministic lint rules")
    p_lint.add_argument("--inventory", help="inventory.json to lint (mutually exclusive with --path)")
    p_lint.add_argument("--path", help="a single skill directory to lint (mutually exclusive with --inventory)")
    p_lint.add_argument("--out", help="output path (default: update --inventory in place; --path only writes if given)")
    p_lint.add_argument("--ci", action="store_true", help="exit 1 if any error-severity finding is on a writable skill")
    p_lint.add_argument("--list-rules", action="store_true", help="print the rule table and exit")
    p_lint.set_defaults(func=cmd_lint)

    p_tok = sub.add_parser("tokens", help="compute L1/L2 token totals")
    p_tok.add_argument("--inventory", required=True, help="inventory.json to read/update")
    p_tok.add_argument("--out", help="output path (default: update --inventory in place)")
    p_tok.add_argument("--api", action="store_true", help="also call the count_tokens API if ANTHROPIC_API_KEY is set")
    p_tok.set_defaults(func=cmd_tokens)

    p_log = sub.add_parser("log-usage", help="append one Skill invocation from a PostToolUse hook payload on stdin")
    p_log.add_argument("--log", help="usage log file (default: $SKILL_OPTIMIZER_USAGE_LOG or <skill-root>/usage-log.jsonl)")
    p_log.set_defaults(func=cmd_log_usage)

    return parser

def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    if args.command == "log-usage":
        cmd_log_usage(args)
        sys.exit(0)
    args.func(args)

if __name__ == "__main__":
    main()
