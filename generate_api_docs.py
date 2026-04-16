#!/usr/bin/env python3
"""
generate_api_docs.py — Scrape public C++ API surface from src/ headers
and emit API_REFERENCE.md.

Run from the TemporalBFI library root:
    python generate_api_docs.py

Excluded filename prefixes (data headers, not public API):
    transfer_curve*  True16_Calibration*  temporal_runtime_solver*
    calibration_profile*  example_*

The scraper extracts:
  - namespace / struct / class / enum declarations
  - public methods, static methods, inline free functions
  - constants (constexpr, static constexpr)
  - callback typedefs / using aliases
  - struct/class member variables (from public sections)

Descriptions default to empty — fill them in manually as needed.
Re-running the script preserves any existing descriptions already
present in API_REFERENCE.md by merging them back in.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SRC_DIR = Path(__file__).resolve().parent / "src"
OUTPUT_MD = Path(__file__).resolve().parent / "API_REFERENCE.md"
MERGE_CACHE = Path(__file__).resolve().parent / ".api_descriptions.json"

EXCLUDE_PREFIXES = (
    "transfer_curve",
    "True16_Calibration",
    "temporal_runtime_solver",
    "calibration_profile",
    "example_",
)

HEADER_EXTS = {".h"}

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Symbol:
    kind: str            # "struct", "class", "enum", "method", "static method",
                         # "inline function", "constant", "using", "field"
    name: str            # display name / signature fragment
    signature: str = ""  # full cleaned-up signature
    description: str = ""
    parent: str = ""     # owning class/struct/namespace

@dataclass
class FileAPI:
    path: str
    symbols: list[Symbol] = field(default_factory=list)

# ---------------------------------------------------------------------------
# Description merge helpers
# ---------------------------------------------------------------------------

def _merge_key(sym: Symbol) -> str:
    """Stable key for matching descriptions across regenerations."""
    return f"{sym.parent}::{sym.kind}::{sym.name}"


def load_descriptions(path: Path) -> dict[str, str]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_descriptions(descs: dict[str, str], path: Path) -> None:
    path.write_text(json.dumps(descs, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")

# ---------------------------------------------------------------------------
# C++ scraping helpers
# ---------------------------------------------------------------------------

# Strip C/C++ comments (block + line) for cleaner parsing.
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//[^\n]*")

def _strip_comments(text: str) -> str:
    text = _BLOCK_COMMENT.sub("", text)
    text = _LINE_COMMENT.sub("", text)
    return text

# Match struct/class forward declarations vs definitions.
_STRUCT_CLASS = re.compile(
    r"\b(struct|class)\s+(\w+)\s*\{", re.MULTILINE)

_ENUM = re.compile(
    r"\b(enum\s+class|enum)\s+(\w+)\s*(?::\s*\w+)?\s*\{([^}]*)\}", re.DOTALL)

_USING = re.compile(
    r"\busing\s+(\w+)\s*=\s*([^;]+);")

_CONSTEXPR = re.compile(
    r"\bstatic\s+constexpr\s+(\S+)\s+(\w+)\s*(?:=\s*[^;]+|(?:\[[^\]]*\]\s*=\s*\{[^}]*\}))\s*;")

_INLINE_FREE_FN = re.compile(
    r"^(?:static\s+)?inline\s+(\S+)\s+(\w+)\s*\(([^)]*)\)",
    re.MULTILINE)


def _clean_sig(s: str) -> str:
    """Collapse whitespace in a signature string."""
    return re.sub(r"\s+", " ", s).strip()


def _extract_block(text: str, start: int) -> str:
    """Return text from start up to the matching closing brace."""
    depth = 0
    i = start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    return text[start:]


def _visibility_at(body: str, pos: int) -> str:
    """Determine the most recent access specifier before `pos`."""
    vis = "public"  # structs default to public
    for m in re.finditer(r"\b(public|private|protected)\s*:", body):
        if m.start() < pos:
            vis = m.group(1)
    return vis


_METHOD_RE = re.compile(
    r"""
    (?:^|\n)\s*
    ((?:static\s+|virtual\s+|inline\s+|const\s+)*)   # qualifiers
    (\S+(?:\s*[*&]+)?)\s+                              # return type
    (\w+)\s*                                           # method name
    \(([^)]*)\)                                        # params
    \s*(const)?                                        # trailing const
    """,
    re.VERBOSE,
)


def _scrape_methods(body: str, parent_name: str, parent_kind: str) -> list[Symbol]:
    """Extract method signatures from a class/struct body."""
    syms: list[Symbol] = []
    for m in _METHOD_RE.finditer(body):
        quals = m.group(1).strip()
        ret = m.group(2).strip()
        name = m.group(3)
        params = _clean_sig(m.group(4))
        const = " const" if m.group(5) else ""

        # skip constructors / destructors by checking return type
        if ret in (parent_name, f"~{parent_name}", f"virtual"):
            continue
        if name == parent_name or name == f"~{parent_name}":
            continue

        vis = _visibility_at(body, m.start())
        if vis != "public":
            continue

        is_static = "static" in quals
        kind = "static method" if is_static else "method"
        sig = f"{ret} {name}({params}){const}"
        if is_static:
            sig = f"static {sig}"
        syms.append(Symbol(kind=kind, name=name, signature=_clean_sig(sig),
                           parent=parent_name))
    return syms


_FIELD_RE = re.compile(
    r"""
    (?:^|\n)\s*
    ((?:const\s+)?)                          # optional const
    (\w[\w:*&<> ]*?)\s+                      # type
    (\w+)\s*                                 # name
    (?:=\s*[^;]+)?\s*;                       # optional default
    """,
    re.VERBOSE,
)


def _scrape_fields(body: str, parent_name: str) -> list[Symbol]:
    """Extract public member fields from a struct/class body."""
    syms: list[Symbol] = []
    for m in _FIELD_RE.finditer(body):
        const_q = m.group(1).strip()
        ftype = m.group(2).strip()
        fname = m.group(3)
        # Skip things that look like methods, keywords, or access specifiers.
        if "(" in ftype or ftype in ("return", "if", "else", "for", "while",
                                      "switch", "case", "public", "private",
                                      "protected", "using", "typedef",
                                      "static", "constexpr", "virtual",
                                      "inline", "friend", "namespace"):
            continue
        vis = _visibility_at(body, m.start())
        if vis != "public":
            continue
        sig = f"{const_q} {ftype} {fname}".strip()
        syms.append(Symbol(kind="field", name=fname, signature=sig,
                           parent=parent_name))
    return syms


# ---------------------------------------------------------------------------
# Per-file scraping
# ---------------------------------------------------------------------------

def scrape_header(path: Path) -> FileAPI:
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = _strip_comments(raw)
    api = FileAPI(path=path.name)

    # -- enums ---------------------------------------------------------------
    for m in _ENUM.finditer(text):
        ekind = m.group(1)
        ename = m.group(2)
        members = [v.strip().split("=")[0].strip()
                   for v in m.group(3).split(",") if v.strip()]
        sig = f"{ekind} {ename} {{ {', '.join(members)} }}"
        api.symbols.append(Symbol(kind="enum", name=ename,
                                  signature=_clean_sig(sig)))

    # -- using aliases -------------------------------------------------------
    for m in _USING.finditer(text):
        uname = m.group(1)
        udef = _clean_sig(m.group(2))
        api.symbols.append(Symbol(kind="using", name=uname,
                                  signature=f"using {uname} = {udef}"))

    # -- constexpr constants -------------------------------------------------
    for m in _CONSTEXPR.finditer(text):
        ctype = m.group(1)
        cname = m.group(2)
        api.symbols.append(Symbol(kind="constant", name=cname,
                                  signature=f"static constexpr {ctype} {cname}"))

    # -- structs / classes ---------------------------------------------------
    for m in _STRUCT_CLASS.finditer(text):
        skind = m.group(1)
        sname = m.group(2)
        block = _extract_block(text, m.start())
        body = block[block.index("{") + 1 : block.rindex("}")]

        api.symbols.append(Symbol(kind=skind, name=sname,
                                  signature=f"{skind} {sname}"))

        api.symbols.extend(_scrape_methods(body, sname, skind))
        api.symbols.extend(_scrape_fields(body, sname))

    # -- namespace-level inline free functions --------------------------------
    # Only those outside any struct/class block.
    struct_ranges: list[tuple[int, int]] = []
    for m in _STRUCT_CLASS.finditer(text):
        block = _extract_block(text, m.start())
        struct_ranges.append((m.start(), m.start() + len(block)))

    def _inside_struct(pos: int) -> bool:
        return any(s <= pos < e for s, e in struct_ranges)

    for m in _INLINE_FREE_FN.finditer(text):
        if _inside_struct(m.start()):
            continue
        ret = m.group(1)
        fname = m.group(2)
        params = _clean_sig(m.group(3))
        sig = f"{ret} {fname}({params})"
        api.symbols.append(Symbol(kind="inline function", name=fname,
                                  signature=_clean_sig(sig)))

    return api

# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def _kind_sort_key(kind: str) -> int:
    order = {"enum": 0, "using": 1, "constant": 2, "struct": 3, "class": 4,
             "field": 5, "method": 6, "static method": 7,
             "inline function": 8}
    return order.get(kind, 99)


def render_markdown(files: list[FileAPI]) -> str:
    lines: list[str] = []
    lines.append("# TemporalBFI — API Reference\n")
    lines.append("> **Auto-generated** by `generate_api_docs.py`. "
                 "Descriptions can be filled in manually; re-running the "
                 "script preserves them via `.api_descriptions.json`.\n")
    lines.append("---\n")

    # Table of contents
    lines.append("## Contents\n")
    for f in files:
        anchor = f.path.replace(".", "").replace("_", "").lower()
        lines.append(f"- [{f.path}](#{anchor})")
    lines.append("")

    for f in files:
        lines.append(f"---\n")
        lines.append(f"## {f.path}\n")

        if not f.symbols:
            lines.append("_No public API symbols detected._\n")
            continue

        # Group by parent first (empty = file-level, then each struct/class).
        parents_order: list[str] = []
        by_parent: dict[str, list[Symbol]] = {}
        for s in f.symbols:
            key = s.parent or ""
            if key not in by_parent:
                parents_order.append(key)
                by_parent[key] = []
            by_parent[key].append(s)

        for parent in parents_order:
            group = by_parent[parent]
            if parent:
                lines.append(f"### `{parent}`\n")
            else:
                lines.append(f"### File-level\n")

            # Sort within group.
            group.sort(key=lambda s: (_kind_sort_key(s.kind), s.name))

            lines.append("| Kind | Signature | Description |")
            lines.append("|------|-----------|-------------|")
            for s in group:
                esc_sig = s.signature.replace("|", "\\|")
                desc = s.description.replace("|", "\\|") if s.description else ""
                lines.append(f"| {s.kind} | `{esc_sig}` | {desc} |")
            lines.append("")

    return "\n".join(lines) + "\n"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not SRC_DIR.is_dir():
        print(f"ERROR: src/ directory not found at {SRC_DIR}", file=sys.stderr)
        sys.exit(1)

    # Collect headers, excluding data-only files.
    headers: list[Path] = []
    for p in sorted(SRC_DIR.iterdir()):
        if p.suffix not in HEADER_EXTS:
            continue
        if any(p.name.startswith(pfx) for pfx in EXCLUDE_PREFIXES):
            continue
        headers.append(p)

    if not headers:
        print("No headers found to scrape.", file=sys.stderr)
        sys.exit(1)

    print(f"Scraping {len(headers)} header(s):")
    for h in headers:
        print(f"  {h.name}")

    # Load previous descriptions for merge-back.
    old_descs = load_descriptions(MERGE_CACHE)

    # Scrape.
    files: list[FileAPI] = []
    for h in headers:
        api = scrape_header(h)
        # Merge descriptions back in.
        for sym in api.symbols:
            key = _merge_key(sym)
            if key in old_descs and old_descs[key]:
                sym.description = old_descs[key]
        files.append(api)

    # Render.
    md = render_markdown(files)
    OUTPUT_MD.write_text(md, encoding="utf-8")
    print(f"\nWrote {OUTPUT_MD.name} ({len(md)} bytes)")

    # Save all current descriptions (including new empty ones).
    all_descs: dict[str, str] = {}
    for f in files:
        for sym in f.symbols:
            all_descs[_merge_key(sym)] = sym.description
    # Preserve old entries that might belong to symbols temporarily removed.
    for k, v in old_descs.items():
        if k not in all_descs and v:
            all_descs[k] = v
    save_descriptions(all_descs, MERGE_CACHE)
    print(f"Saved description cache ({len(all_descs)} entries)")


if __name__ == "__main__":
    main()
