#!/usr/bin/env python3
"""Resolve symbolic footnote keys to sequential numbers and merge chapters.

Usage:
    python resolve-footnotes.py [thesis_root]

Reads `<thesis_root>/chapters/*.md` in canonical order (introduction,
chapter1, chapter2, …, conclusion), finds all `[^key]` citations,
assigns sequential numbers by first appearance, rewrites text markers
to `[N]`, collects unique `[^key]: definition` lines, and writes
`<thesis_root>/full_thesis.md` with a unified numbered reference block.

Design:
- Writing phase: each chapter/section uses stable symbolic keys like
  `[^kant-mm-p225]`. Definitions live alongside their section (standard
  Markdown footnote syntax), so each file previews correctly in Pandoc.
- Merge phase (this script): resolves all keys to numbers in one pass.
  Any content edit that inserts/removes/reorders a citation costs
  nothing — the script re-runs and every number is correct again.

Key convention (suggested, not enforced):
    <author>-<work>-p<page>         e.g. kant-mm-p225
    <author>-<work>-p<start>-<end>  e.g. kant-gms-p412-414
    <author>-<work>-ch<chunk>       e.g. willaschek-rc-ch03 (no page)

Same key referenced multiple times → single footnote, reused number.
"""

import re
import sys
from pathlib import Path

CHAPTER_ORDER = [
    "introduction",
    "chapter1", "chapter2", "chapter3", "chapter4",
    "chapter5", "chapter6", "chapter7", "chapter8",
    "conclusion",
]

CITE_RE = re.compile(r'\[\^([^\]\s]+)\]')
DEF_RE = re.compile(r'^\[\^([^\]\s]+)\]:\s*(.*)$')


def load_chapter_files(chapters_dir: Path) -> list[Path]:
    ordered: list[Path] = []
    seen: set[Path] = set()
    for name in CHAPTER_ORDER:
        p = chapters_dir / f"{name}.md"
        if p.exists():
            ordered.append(p)
            seen.add(p)
    for p in sorted(chapters_dir.glob("chapter*.md")):
        if p not in seen:
            ordered.append(p)
            seen.add(p)
    return ordered


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("thesis")
    chapters_dir = root / "chapters"
    if not chapters_dir.is_dir():
        print(f"错误：未找到 {chapters_dir}", file=sys.stderr)
        return 1

    files = load_chapter_files(chapters_dir)
    if not files:
        print(f"错误：{chapters_dir} 下没有章节文件", file=sys.stderr)
        return 1

    definitions: dict[str, str] = {}
    conflicts: list[tuple[str, str, str]] = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            m = DEF_RE.match(line)
            if m:
                key, defn = m.group(1), m.group(2).strip()
                if key in definitions and definitions[key] != defn:
                    conflicts.append((key, definitions[key], defn))
                definitions[key] = defn

    key_to_num: dict[str, int] = {}
    next_num = 1
    unknown_keys: set[str] = set()
    merged_parts: list[str] = []

    for f in files:
        new_lines: list[str] = []
        for line in f.read_text(encoding="utf-8").splitlines():
            if DEF_RE.match(line):
                continue

            def repl(m: re.Match[str]) -> str:
                nonlocal next_num
                key = m.group(1)
                if key not in key_to_num:
                    if key not in definitions:
                        unknown_keys.add(key)
                    key_to_num[key] = next_num
                    next_num += 1
                return f"[{key_to_num[key]}]"

            new_lines.append(CITE_RE.sub(repl, line))
        merged_parts.append("\n".join(new_lines).rstrip() + "\n")

    ref_lines = ["", "---", "", "## 参考文献", ""]
    for key, num in sorted(key_to_num.items(), key=lambda kv: kv[1]):
        defn = definitions.get(key, f"[!! 未找到定义: {key}]")
        ref_lines.append(f"[{num}] {defn}")
    ref_block = "\n".join(ref_lines) + "\n"

    out_path = root / "full_thesis.md"
    out_path.write_text("\n".join(merged_parts) + ref_block, encoding="utf-8")

    print(f"合并完成：{out_path}")
    print(f"  章节数：{len(files)}")
    print(f"  脚注总数（去重后）：{len(key_to_num)}")
    if unknown_keys:
        print(f"\n⚠️  {len(unknown_keys)} 个引用键未找到定义（正文中用了 [^key] 但没有对应的 [^key]: … 行）：")
        for k in sorted(unknown_keys):
            print(f"    - {k}")
    if conflicts:
        print(f"\n⚠️  {len(conflicts)} 个键在不同文件中有冲突定义（使用最后出现的版本）：")
        for k, old, new in conflicts:
            print(f"    - {k}")
            print(f"        旧: {old}")
            print(f"        新: {new}")
    return 0 if not unknown_keys else 2


if __name__ == "__main__":
    sys.exit(main())
