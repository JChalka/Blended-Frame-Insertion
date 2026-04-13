"""
tools_compile_check.py — Python syntax/compile check for TemporalBFI tools.

As a PIO extra_script (post:tools_compile_check.py in platformio.ini):
    Registers a post-link action that runs py_compile on every .py file
    under tools/ and writes TOOLS_COMPILE_REPORT.md.
    Only runs once per full build (skips if already checked this session).

Standalone:
    python tools_compile_check.py              # check + write report
    python tools_compile_check.py --json       # raw JSON to stdout
"""

import json
import os
import py_compile
import sys
from pathlib import Path

try:
    _THIS_DIR = Path(__file__).resolve().parent
except NameError:
    _THIS_DIR = None


def _project_dir():
    if _THIS_DIR is not None:
        return _THIS_DIR
    return Path.cwd()


def _tools_dir():
    return _project_dir() / "tools"


def _results_json():
    return _project_dir() / ".pio" / "build" / "tools_compile_results.json"


def _report_path():
    return _project_dir() / "TOOLS_COMPILE_REPORT.md"


def check_tools() -> dict:
    """Run py_compile on every .py under tools/. Returns {relpath: {status, error?}}."""
    tools = _tools_dir()
    results = {}
    if not tools.is_dir():
        return results

    for py_file in sorted(tools.rglob("*.py")):
        rel = py_file.relative_to(_project_dir()).as_posix()
        try:
            py_compile.compile(str(py_file), doraise=True)
            results[rel] = {"status": "OK"}
        except py_compile.PyCompileError as exc:
            results[rel] = {"status": "FAIL", "error": str(exc)}
    return results


def generate_report(results: dict) -> str:
    lines = ["# TemporalBFI Tools Compile Report\n"]

    if not results:
        lines.append("_No Python tools found under `tools/`._\n")
        return "\n".join(lines)

    passed = sum(1 for r in results.values() if r["status"] == "OK")
    total = len(results)
    lines.append(f"**{passed}/{total}** Python tools compiled successfully.\n")

    lines.append("| Tool | Status |")
    lines.append("|------|--------|")
    for rel, info in results.items():
        status = info["status"]
        cell = f"**{status}**" if status == "FAIL" else status
        lines.append(f"| `{rel}` | {cell} |")

    # Append errors at the bottom for any failures
    failures = {rel: info for rel, info in results.items() if info["status"] == "FAIL"}
    if failures:
        lines.append("")
        lines.append("## Errors\n")
        for rel, info in failures.items():
            lines.append(f"### `{rel}`\n")
            lines.append(f"```\n{info['error']}\n```\n")

    lines.append("")
    return "\n".join(lines)


def _save_results(results: dict):
    rj = _results_json()
    rj.parent.mkdir(parents=True, exist_ok=True)
    rj.write_text(json.dumps(results, indent=2), encoding="utf-8")


def _write_report(results: dict):
    report = generate_report(results)
    _report_path().write_text(report, encoding="utf-8")


# ── PlatformIO extra_script entry point ─────────────────────────────────────

_PIO_CHECK_DONE = False


def _pio_post_build(target, source, env):
    global _PIO_CHECK_DONE
    if _PIO_CHECK_DONE:
        return
    _PIO_CHECK_DONE = True

    results = check_tools()
    _save_results(results)
    _write_report(results)

    passed = sum(1 for r in results.values() if r["status"] == "OK")
    total = len(results)
    failed = total - passed
    if failed:
        print(f"[tools_compile_check] {failed}/{total} Python tools FAILED compilation — see TOOLS_COMPILE_REPORT.md")
    else:
        print(f"[tools_compile_check] {passed}/{total} Python tools OK")


try:
    Import("env")  # type: ignore[name-defined]   # noqa: F821
    _THIS_DIR = Path(env["PROJECT_DIR"])  # type: ignore[name-defined]   # noqa: F821
    env.AddPostAction("$BUILD_DIR/${PROGNAME}.elf", _pio_post_build)  # type: ignore[name-defined]   # noqa: F821
except NameError:
    pass


# ── Standalone CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Compile-check all Python tools under tools/.")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of Markdown")
    args = parser.parse_args()

    results = check_tools()
    _save_results(results)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        report = generate_report(results)
        print(report)
        _write_report(results)
        print(f"\nReport written to {_report_path()}", file=sys.stderr)
