#!/usr/bin/env python3
"""Generate the Lab 7 report and manifest from local, saved evidence only."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


REPORT_NAME = "tool-calling-report.html"
MANIFEST_NAME = "tool-calling-manifest.json"
CHECKER_VERSION = "1.0"
REQUIRED_TOOLS = ("current_time", "airport_info")
REQUIRED_ROLES = {"user", "assistant", "tool"}
SECRET_PATTERNS = (
    re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*['\"]?[^\s'\"]{8,}"),
    re.compile(r"\b(?:ghp|github_pat|sk|xox[baprs])_[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
)
ROLE_PATTERNS = {
    role: (
        re.compile(rf"(?im)^\s*(?:[-*]\s*)?(?:#{{1,6}}\s*)?{role}(?:\s*\([^\n)]*\)|\s*\[[^\]\n]*\])?\s*:"),
        re.compile(rf"['\"]role['\"]\s*:\s*['\"]{role}['\"]", re.IGNORECASE),
    )
    for role in REQUIRED_ROLES
}


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, check=False, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def check(name: str, present: bool, location: str, identifier: str, detail: str) -> dict[str, str]:
    return {
        "name": name,
        "status": "present" if present else "missing",
        "location": location,
        "identifier": identifier,
        "detail": detail,
    }


def contains_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def sanitize_repository_url(value: str) -> tuple[str, bool]:
    """Return a credential-free GitHub URL and whether the supplied URL was safe."""
    value = value.strip()
    scp_match = re.fullmatch(r"git@github\.com:([^/\s]+)/([^/\s]+?)(?:\.git)?", value)
    if scp_match:
        owner, repository = scp_match.groups()
        return f"https://github.com/{owner}/{repository.removesuffix('.git')}", True
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "invalid-url-redacted", False
    host = parsed.hostname or ""
    safe = urlunsplit((parsed.scheme, host, parsed.path, "", "")) or "invalid-url-redacted"
    parts = [part for part in parsed.path.removesuffix(".git").split("/") if part]
    valid = (
        parsed.scheme == "https" and host.lower() == "github.com"
        and parsed.username is None and parsed.password is None
        and not parsed.query and not parsed.fragment and len(parts) == 2
    )
    if not valid:
        return safe, False
    return f"https://github.com/{parts[0]}/{parts[1]}", True


def local_display_path(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return path.name


def transcript_roles(text: str) -> set[str]:
    return {
        role for role, patterns in ROLE_PATTERNS.items()
        if any(pattern.search(text) for pattern in patterns)
    }


def normalized(text: str) -> str:
    return " ".join(text.split()).casefold()


def transcript_check(text: str, tool: str | None, require_tool_role: bool) -> tuple[bool, str]:
    roles = transcript_roles(text)
    needed = REQUIRED_ROLES if require_tool_role else {"user", "assistant"}
    missing = sorted(needed - roles)
    tool_missing = bool(tool and tool.casefold() not in text.casefold())
    valid = bool(text.strip()) and not missing and not tool_missing
    details: list[str] = []
    if missing:
        details.append("missing role labels: " + ", ".join(missing))
    if tool_missing:
        details.append(f"does not name {tool}")
    return valid, "; ".join(details) if details else "Required labeled roles and tool name are present."


def evidence_section(title: str, location: str, content: str, withheld: bool) -> str:
    shown = "Content withheld because an obvious credential pattern was detected." if withheld else content
    return (
        f'<section><h3>{html.escape(title)}</h3><p><code>{html.escape(location)}</code></p>'
        f'<pre>{html.escape(shown)}</pre></section>'
    )


def render_report(
    learner: str,
    generated_at: str,
    revision_label: str,
    revision_link: str,
    checks: list[dict[str, str]],
    evidence: list[tuple[str, str, str]],
    implementation: list[tuple[str, str, str]],
    withheld: set[str],
) -> str:
    overall = "complete" if all(item["status"] == "present" for item in checks) else "incomplete"
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(item['name'])}</td>"
        f"<td class=\"{item['status']}\">{item['status']}</td>"
        f"<td>{html.escape(item['identifier'])}</td>"
        f"<td>{html.escape(item['detail'])}</td>"
        "</tr>" for item in checks
    )
    evidence_sections = "\n".join(
        evidence_section(title, location, content, location in withheld)
        for title, location, content in evidence
    )
    implementation_sections = "\n".join(
        evidence_section(title, location, content, location in withheld)
        for title, location, content in implementation
    )
    revision_html = (
        f'<a href="{html.escape(revision_link)}">{html.escape(revision_label)}</a>'
        if revision_link else f"<code>{html.escape(revision_label)}</code>"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lab 7 Tool-Calling Agent Submission Report</title>
  <style>
    body {{ color:#17202a; font:16px/1.45 system-ui,sans-serif; margin:2rem auto; max-width:76rem; padding:0 1rem; }}
    h1,h2,h3 {{ color:#102a43; }} table {{ border-collapse:collapse; width:100%; }}
    th,td {{ border:1px solid #bcccdc; padding:.55rem; text-align:left; vertical-align:top; }} th {{ background:#f0f4f8; }}
    pre {{ background:#f5f7fa; border:1px solid #bcccdc; overflow:auto; padding:1rem; white-space:pre-wrap; }}
    code {{ overflow-wrap:anywhere; }} .present,.complete {{ color:#176b3a; font-weight:700; }} .missing,.incomplete {{ color:#a61b1b; font-weight:700; }}
    .note {{ background:#fffbea; border-left:.3rem solid #d69e2e; padding:.7rem 1rem; }}
  </style>
</head>
<body>
  <h1>Lab 7: Building and Securing Tool-Calling Agents</h1>
  <table>
    <tr><th>Learner</th><td>{html.escape(learner)}</td></tr>
    <tr><th>Generated</th><td>{html.escape(generated_at)}</td></tr>
    <tr><th>Overall completeness</th><td class="{overall}">{overall}</td></tr>
    <tr><th>Repository revision or patch</th><td>{revision_html}</td></tr>
    <tr><th>Checker version</th><td>{CHECKER_VERSION}</td></tr>
  </table>

  <h2>Completeness</h2>
  <table><thead><tr><th>Required evidence</th><th>Status</th><th>Identifier</th><th>Detail</th></tr></thead><tbody>{rows}</tbody></table>

  <h2 id="saved-tool-and-transcript-evidence">Saved tool and transcript evidence</h2>
  {evidence_sections}

  <h2 id="implementation-evidence">Implementation evidence</h2>
  {implementation_sections}

  <h2>Staff spot checks</h2>
  <p class="note">This checker confirms objective evidence structure only. It does not call a model, determine whether the injection succeeded, judge the explanations, or assign a grade.</p>
  <ol>
    <li><strong>Capability:</strong> compare one before/after pair and explain how the added tool changed the answer.</li>
    <li><strong>Security:</strong> analyze the attempted injection, one trust risk, and one system-level safeguard.</li>
  </ol>

  <h2>Safety check</h2>
  <p>The checker scans included text for common plaintext credential patterns. Review the finished report yourself before uploading.</p>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the Lab 7 HTML report and JSON manifest without starting the agent or calling a model."
    )
    parser.add_argument("--learner", required=True)
    implementation = parser.add_mutually_exclusive_group(required=True)
    implementation.add_argument("--repository-url", help="GitHub URL for a clean committed implementation")
    implementation.add_argument("--patch", type=Path, help="Patch containing both added tool definitions")
    parser.add_argument(
        "--tool-source", action="append", default=[], type=Path,
        help="Implementation file at the reported revision; repeat for multiple files (repository mode only)",
    )
    parser.add_argument("--tool-listing", required=True, type=Path)
    parser.add_argument("--current-time-before", required=True, type=Path)
    parser.add_argument("--current-time-after", required=True, type=Path)
    parser.add_argument("--airport-info-before", required=True, type=Path)
    parser.add_argument("--airport-info-after", required=True, type=Path)
    parser.add_argument("--malicious-payload", required=True, type=Path)
    parser.add_argument("--injection-transcript", required=True, type=Path)
    parser.add_argument("--output-dir", default=Path("submission"), type=Path)
    args = parser.parse_args()
    if args.repository_url and not args.tool_source:
        parser.error("--repository-url requires at least one --tool-source")
    if args.patch and args.tool_source:
        parser.error("--tool-source is only valid with --repository-url")
    return args


def main() -> int:
    args = parse_args()
    root_result = run_git(Path.cwd(), "rev-parse", "--show-toplevel")
    if root_result.returncode != 0:
        print("Run this command from inside the lab-tool-calling-agents repository.", file=sys.stderr)
        return 2
    root = Path(root_result.stdout.strip())

    inputs = {
        "tool listing": args.tool_listing,
        "current_time before transcript": args.current_time_before,
        "current_time after transcript": args.current_time_after,
        "airport_info before transcript": args.airport_info_before,
        "airport_info after transcript": args.airport_info_after,
        "malicious stub payload": args.malicious_payload,
        "injection-attempt transcript": args.injection_transcript,
    }
    if args.patch:
        inputs["implementation patch"] = args.patch
    else:
        for index, source in enumerate(args.tool_source, start=1):
            inputs[f"implementation source {index}"] = source
    missing = [f"{label}: {path}" for label, path in inputs.items() if not path.is_file()]
    if missing:
        print("Missing required saved evidence:\n  " + "\n  ".join(missing), file=sys.stderr)
        return 2

    displayed = {label: local_display_path(root, path) for label, path in inputs.items()}
    content = {label: read_text(path) for label, path in inputs.items()}
    implementation_labels = [label for label in inputs if label.startswith("implementation")]
    implementation_text = "\n".join(content[label] for label in implementation_labels)
    definition_evidence_text = implementation_text

    repository_url = ""
    commit_sha = ""
    patch_sha256 = ""
    revision_ok = False
    revision_label = ""
    revision_link = ""
    if args.repository_url:
        head_result = run_git(root, "rev-parse", "HEAD")
        if head_result.returncode != 0:
            print("The repository has no commit to use as an immutable revision.", file=sys.stderr)
            return 2
        commit_sha = head_result.stdout.strip()
        repository_url, repository_valid = sanitize_repository_url(args.repository_url)
        origin_result = run_git(root, "remote", "get-url", "origin")
        origin_url, origin_valid = sanitize_repository_url(origin_result.stdout) if origin_result.returncode == 0 else ("origin-not-found", False)
        source_relpaths: list[str] = []
        sources_inside_root = True
        for source in args.tool_source:
            try:
                source_relpaths.append(str(source.resolve().relative_to(root.resolve())))
            except ValueError:
                sources_inside_root = False
        tracked = set(run_git(root, "ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines())
        source_tracked = sources_inside_root and all(path in tracked for path in source_relpaths)
        diff_result = run_git(root, "diff", "--quiet", "HEAD", "--", *source_relpaths)
        source_clean = diff_result.returncode == 0 if source_relpaths else False
        revision_ok = (
            repository_valid and origin_valid and repository_url.casefold() == origin_url.casefold()
            and source_tracked and source_clean
        )
        revision_label = commit_sha
        revision_link = f"{repository_url}/commit/{commit_sha}" if repository_valid else ""
        revision_detail = (
            "The implementation files are tracked and unchanged at HEAD, and the credential-free repository URL matches origin."
            if revision_ok else
            "Commit the implementation files unchanged at HEAD and provide the credential-free GitHub URL configured as origin."
        )
    else:
        patch_text = content["implementation patch"]
        patch_sha256 = hashlib.sha256(patch_text.encode()).hexdigest()
        revision_ok = bool(
            re.search(r"(?m)^diff --git a/.+ b/.+$", patch_text)
            and re.search(r"(?m)^\+[^+]", patch_text)
        )
        revision_label = f"patch sha256:{patch_sha256}"
        definition_evidence_text = "\n".join(
            line[1:] for line in patch_text.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        revision_detail = (
            "The saved patch has Git diff headers and added lines; its SHA-256 identifies the included evidence."
            if revision_ok else "Save a non-empty Git patch with diff headers and added implementation lines."
        )

    definitions_ok = all(tool in definition_evidence_text for tool in REQUIRED_TOOLS)
    tool_listing_text = content["tool listing"]
    listing_ok = all(tool in tool_listing_text for tool in REQUIRED_TOOLS)

    transcript_specs = (
        ("current_time_before_transcript", "current_time before transcript", None, False),
        ("current_time_after_transcript", "current_time after transcript", "current_time", True),
        ("airport_info_before_transcript", "airport_info before transcript", None, False),
        ("airport_info_after_transcript", "airport_info after transcript", "airport_info", True),
        ("injection_attempt_transcript", "injection-attempt transcript", "airport_info", True),
    )
    transcript_results: dict[str, tuple[bool, str, set[str]]] = {}
    for check_name, label, tool, require_tool_role in transcript_specs:
        valid, detail = transcript_check(content[label], tool, require_tool_role)
        transcript_results[check_name] = (valid, detail, transcript_roles(content[label]))

    payload_text = content["malicious stub payload"]
    injection_text = content["injection-attempt transcript"]
    payload_normalized = normalized(payload_text)
    payload_ok = len(payload_normalized) >= 20 and payload_normalized in normalized(injection_text)

    content_by_location = {displayed[label]: text for label, text in content.items()}
    withheld = {location for location, text in content_by_location.items() if contains_secret(text)}
    secrets_ok = not withheld

    report_location = REPORT_NAME
    checks = [
        check("immutable_repository_revision_or_patch", revision_ok, report_location, revision_label, revision_detail),
        check(
            "completed_tool_definitions", definitions_ok, f"{report_location}#implementation-evidence",
            ", ".join(REQUIRED_TOOLS) if definitions_ok else "required names missing",
            "The implementation evidence names both required tools." if definitions_ok else "Include definitions for current_time and airport_info in the committed sources or patch.",
        ),
        check(
            "tool_listing", listing_ok, f"{report_location}#saved-tool-and-transcript-evidence",
            ", ".join(REQUIRED_TOOLS) if listing_ok else "required names missing",
            "The saved tool listing names both required tools." if listing_ok else "Save tools/list output that names current_time and airport_info.",
        ),
    ]
    for check_name, label, _tool, _require_tool_role in transcript_specs:
        valid, detail, roles = transcript_results[check_name]
        checks.append(check(
            check_name, valid, f"{report_location}#saved-tool-and-transcript-evidence",
            ", ".join(sorted(roles)) or "no labeled roles found", detail,
        ))
    checks.extend((
        check(
            "malicious_stub_payload_in_transcript", payload_ok,
            f"{report_location}#saved-tool-and-transcript-evidence",
            hashlib.sha256(payload_text.encode()).hexdigest()[:16] if payload_text else "empty",
            "The non-empty saved payload appears in the injection transcript's tool output." if payload_ok else "Save a payload of at least 20 characters and include that exact payload in the injection transcript's tool output.",
        ),
        check(
            "obvious_credential_leakage", secrets_ok, report_location,
            "none detected" if secrets_ok else "content withheld",
            "No common plaintext credential pattern was found." if secrets_ok else "Remove and revoke plaintext credentials before regenerating; affected content was withheld.",
        ),
    ))

    evidence_labels = [label for label in inputs if not label.startswith("implementation")]
    evidence = [(label.title(), displayed[label], content[label]) for label in evidence_labels]
    implementation = [(label.title(), displayed[label], content[label]) for label in implementation_labels]
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    complete = all(item["status"] == "present" for item in checks)
    report = render_report(
        args.learner, generated_at, revision_label, revision_link, checks,
        evidence, implementation, withheld,
    )
    manifest = {
        "schema_version": "1.0",
        "lab": "Lab 7: Building and Securing Tool-Calling Agents",
        "learner": args.learner,
        "generated_at": generated_at,
        "checker_version": CHECKER_VERSION,
        "complete": complete,
        "report": REPORT_NAME,
        "identifiers": {
            "repository_url": repository_url or None,
            "commit_sha": commit_sha or None,
            "patch_sha256": patch_sha256 or None,
            "tools": list(REQUIRED_TOOLS),
        },
        "checks": checks,
        "manual_spot_checks": ["capability", "security"],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / REPORT_NAME).write_text(report, encoding="utf-8")
    (args.output_dir / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output_dir / REPORT_NAME}")
    print(f"Wrote {args.output_dir / MANIFEST_NAME}")
    print("Submission evidence is complete." if complete else "Submission evidence is incomplete; open the report for details.")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
