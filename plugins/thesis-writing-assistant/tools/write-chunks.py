#!/usr/bin/env python3
"""
write-chunks.py — 根据 draft-chunks.md 自动写出所有 chunk 文件
用法: python3 tools/write-chunks.py <source-fixed.md> <draft-chunks.md> <输出目录> --label "文献标题"
"""

import re
import argparse
from pathlib import Path

CHUNK_LINE_RE = re.compile(
    r'^chunk-(\d+)\s+\[行(\d+)-(\d+),\s*\d+字\]\s+#\s*(.+?)(?:\s*\|.*)?$'
)


def parse_draft(draft_path: str) -> list[dict]:
    chunks = []
    for line in Path(draft_path).read_text(encoding='utf-8').splitlines():
        m = CHUNK_LINE_RE.match(line.strip())
        if m:
            chunks.append({
                'num':     int(m.group(1)),
                'start':   int(m.group(2)),   # 1-indexed
                'end':     int(m.group(3)),   # 1-indexed, inclusive
                'heading': m.group(4).strip(),
            })
    return chunks


def main():
    parser = argparse.ArgumentParser(
        description='根据 draft-chunks.md 自动写出所有 chunk 文件'
    )
    parser.add_argument('source',  help='source-fixed.md 路径')
    parser.add_argument('draft',   help='draft-chunks.md 路径')
    parser.add_argument('out_dir', help='chunk 文件输出目录')
    parser.add_argument('--label', default='未知文献', help='文献标题（用于来源注释行）')
    args = parser.parse_args()

    source = Path(args.source)
    draft  = Path(args.draft)

    if not source.exists():
        print(f'错误: 文件不存在 {source}')
        raise SystemExit(1)
    if not draft.exists():
        print(f'错误: 文件不存在 {draft}')
        raise SystemExit(1)

    lines  = source.read_text(encoding='utf-8').splitlines()
    chunks = parse_draft(str(draft))

    if not chunks:
        print('错误: draft-chunks.md 中未解析到任何 chunk，请检查格式')
        raise SystemExit(1)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    total = len(chunks)
    for c in chunks:
        content_lines = lines[c['start'] - 1 : c['end']]
        content = '\n'.join(content_lines)
        comment = f"<!-- 来源：{args.label} | 位置：{c['heading']} -->"
        prev_label = f"chunk-{c['num']-1:02d}.md" if c['num'] > 1 else "（无）"
        next_label = f"chunk-{c['num']+1:02d}.md" if c['num'] < total else "（无）"
        nav = f"<!-- 前块: {prev_label} | 后块: {next_label} -->"
        out_file = out_dir / f"chunk-{c['num']:02d}.md"
        out_file.write_text(comment + '\n' + nav + '\n\n' + content + '\n', encoding='utf-8')
        print(f"  写出 chunk-{c['num']:02d}.md  ({c['heading'][:50]})")

    print(f'\n共写出 {len(chunks)} 个 chunk 文件到 {out_dir}')


if __name__ == '__main__':
    main()
