#!/usr/bin/env python3
"""Build the submission archive.

    python3 scripts/make_submission.py --scan-only     # only check AI transcripts for secrets / personal data
    python3 scripts/make_submission.py                 # scan, then build dist/vidora-submission.zip

The zip contains:
  repo/                 a fresh `git clone` of this repository: full .git history, CLAUDE.md, .claude/,
                        no ignored files (.env, TZ.docx, node_modules never get in)
  ai-transcripts/       every *.jsonl of this project from ~/.claude/projects/<project>/ (main sessions
                        and subagents), byte-for-byte, as required by the assignment
  SUBMISSION_INFO.txt   what is where, commit, date

Transcripts are NOT modified. The scan reports findings with masked snippets so the human can decide.
Exit code 2 if the scan found something (the zip is still built unless --strict).
"""

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PATTERNS = {
    # local part >= 2 chars and not glued to a JSON escape (\n@router.get is code, not an email)
    "email": re.compile(
        r"(?<![\\A-Za-z0-9._%+-])[A-Za-z0-9][A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
    ),
    "phone": re.compile(r"(?<![\w-])(?:\+?375|\+?7|8)[\s(-]*\d{2,3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?![\w-])"),
    "github_token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    "api_key": re.compile(
        r"\b(?:sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})\b"
    ),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    # a value that looks random (upper + lower + digit), not code like `password: str`
    "password_like": re.compile(
        r"(?i:password|passwd|secret|token)[\"']?\s*[=:]\s*[\"'\\]*"
        r"(?=[A-Za-z0-9!@#$%^&*_-]*[A-Z])(?=[A-Za-z0-9!@#$%^&*_-]*[a-z])(?=[A-Za-z0-9!@#$%^&*_-]*\d)"
        r"[A-Za-z0-9!@#$%^&*_-]{8,}"
    ),
    # validation errors that echo the input (that is how one generated password leaked once)
    "echoed_input": re.compile(r"input_value='[^']{10,}'"),
}
# Addresses that are part of the project itself (demo data, docs, Co-Authored-By) are expected.
ALLOWED_EMAIL = re.compile(
    r"@(?:example\.com|vidora\.example\.com|anthropic\.com|users\.noreply\.github\.com)$", re.I
)


def project_transcripts_dir() -> Path:
    """~/.claude/projects/<cwd with separators replaced by '-'>"""
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    name = re.sub(r"[^A-Za-z0-9]", "-", str(ROOT))
    return home / "projects" / name


def env_secret_values() -> dict[str, str]:
    """Values from .env that are secrets (read locally, never printed)."""
    values = {}
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                if any(w in key for w in ("PASSWORD", "SECRET", "KEY")) and len(value) >= 8 and "ACCESS_KEY" not in key:
                    values[key] = value
    return values


def mask(text: str) -> str:
    text = text.strip()
    if len(text) <= 6:
        return "*" * len(text)
    return f"{text[:3]}{'*' * min(len(text) - 5, 12)}{text[-2:]}"


def scan(files: list[Path], terms: list[str]) -> list[str]:
    secrets = env_secret_values()
    term_rx = [re.compile(re.escape(t), re.I) for t in terms if t.strip()]
    findings: list[str] = []
    for path in files:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, start=1):
                for key, value in secrets.items():
                    if value in line:
                        findings.append(f"{path.name}:{lineno}: current .env value of {key} (value not shown)")
                for rx in term_rx:
                    if rx.search(line):
                        findings.append(f"{path.name}:{lineno}: term '{rx.pattern}' (personal data?)")
                for kind, rx in PATTERNS.items():
                    for m in rx.finditer(line):
                        hit = m.group(0)
                        if kind == "email" and ALLOWED_EMAIL.search(hit):
                            continue
                        findings.append(f"{path.name}:{lineno}: {kind}: {mask(hit)}")
    # collapse identical findings per file to keep the report readable
    seen: dict[str, int] = {}
    for f in findings:
        key = f.split(":", 2)[0] + ":" + f.split(":", 2)[2]
        seen[key] = seen.get(key, 0) + 1
    return [f"{k}  (x{v})" if v > 1 else k for k, v in seen.items()]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan-only", action="store_true")
    ap.add_argument("--strict", action="store_true", help="do not build the zip if the scan finds anything")
    ap.add_argument("--transcripts", type=Path, help="override ~/.claude/projects/<project>")
    ap.add_argument(
        "--term", action="append", default=[], help="extra word to look for (name, city...), repeatable"
    )
    ap.add_argument("--out", type=Path, default=ROOT / "dist" / "vidora-submission.zip")
    args = ap.parse_args()

    tdir = args.transcripts or project_transcripts_dir()
    if not tdir.is_dir():
        print(f"transcripts folder not found: {tdir}", file=sys.stderr)
        return 1
    jsonl = sorted(p for p in tdir.rglob("*.jsonl") if "memory" not in p.parts)
    print(f"transcripts: {len(jsonl)} *.jsonl in {tdir}")

    findings = scan(jsonl, args.term)
    if findings:
        print(f"\nSCAN: {len(findings)} finding(s) (snippets are masked, files are NOT modified):")
        for f in findings:
            print("  " + f)
    else:
        print("SCAN: nothing found")
    if args.scan_only or (findings and args.strict):
        return 2 if findings else 0

    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    if status.strip():
        print("\nwarning: uncommitted changes are NOT in the archive (it contains a clean clone)")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(repo)], check=True)
        # the clone points at this local folder; reset to the published remote if there is one
        remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True)
        if remote.returncode == 0:
            subprocess.run(["git", "remote", "set-url", "origin", remote.stdout.strip()], cwd=repo, check=True)
        else:
            subprocess.run(["git", "remote", "remove", "origin"], cwd=repo, check=True)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        if args.out.exists():
            args.out.unlink()
        with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            # Zips made on Windows carry no unix permissions: after unzip on Linux ./deploy.sh would
            # be "Permission denied". Take the modes from git (100755 = executable).
            executable = {
                line.split("	", 1)[1]
                for line in subprocess.run(
                    ["git", "ls-files", "-s"], cwd=repo, capture_output=True, text=True, check=True
                ).stdout.splitlines()
                if line.startswith("100755")
            }
            for path in sorted(repo.rglob("*")):
                if path.is_file():
                    rel = path.relative_to(repo).as_posix()
                    info = zipfile.ZipInfo.from_file(path, f"repo/{rel}")
                    info.create_system = 3  # unix, so unzip applies the mode bits below
                    info.external_attr = (0o100755 if rel in executable else 0o100644) << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    z.writestr(info, path.read_bytes())
            for path in jsonl:
                z.write(path, Path("ai-transcripts") / path.relative_to(tdir))
            info = (
                "Vidora - test assignment submission\n"
                f"built: {dt.datetime.now().isoformat(timespec='seconds')}\n"
                f"commit: {commit}\n\n"
                "repo/            git repository with full history (.git), CLAUDE.md, .claude/ (agents, commands, settings.json)\n"
                "ai-transcripts/  Claude Code session files (*.jsonl) of this project, unmodified, incl. subagents\n"
                "                 (no .mcp.json: no project-level MCP servers were configured, see repo/docs/ai-workflow.md)\n"
                "Start: repo/README.md\n"
            )
            z.writestr("SUBMISSION_INFO.txt", info)
    size = args.out.stat().st_size / 1024 / 1024
    print(f"\narchive: {args.out} ({size:.1f} MB), commit {commit[:10]}")
    return 2 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
