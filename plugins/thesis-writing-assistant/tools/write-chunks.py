#!/usr/bin/env python3
"""
write-chunks.py — 根据 draft-chunks.md 自动写出所有 chunk 文件
用法: python3 tools/write-chunks.py <source-fixed.md> <draft-chunks.md> <输出目录> --label "文献标题"

功能：
- 按 draft-chunks.md 中的行范围切分 source-fixed.md
- 为每个 chunk 添加来源注释和前后导航
- 检测 <!-- footnote N --> 标记，将脚注归集到 chunk 尾部 Notes 区域
"""

import re
import argparse
from pathlib import Path

CHUNK_LINE_RE = re.compile(
    r'^chunk-(\d+)\s+\[行(\d+)-(\d+),\s*~?\d+[字词]\]\s+#\s*(.+?)(?:\s*\|.*)?$'
)

_FOOTNOTE_MARKER_RE = re.compile(r'^<!--\s*footnote\s+(\d+)\s*-->')


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


def extract_footnotes(content_lines: list[str]) -> tuple[list[str], list[str]]:
    """
    从内容行中提取脚注段落。

    返回 (正文行列表, 脚注行列表)。
    脚注由 <!-- footnote N --> 标记行标识，包含标记行后的所有行直到下一个空行。
    """
    body_lines = []
    footnote_lines = []
    i = 0

    while i < len(content_lines):
        m = _FOOTNOTE_MARKER_RE.match(content_lines[i].strip())
        if m:
            # 跳过标记行本身
            i += 1
            # 收集脚注内容（直到空行或文件结束）
            fn_block = []
            while i < len(content_lines) and content_lines[i].strip():
                fn_block.append(content_lines[i])
                i += 1
            if fn_block:
                footnote_lines.extend(fn_block)
                footnote_lines.append('')  # 脚注之间留空行
            # 跳过脚注后的空行
            while i < len(content_lines) and not content_lines[i].strip():
                i += 1
        else:
            body_lines.append(content_lines[i])
            i += 1

    return body_lines, footnote_lines


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
    fn_total = 0

    for c in chunks:
        content_lines = lines[c['start'] - 1 : c['end']]

        # 脚注归集
        body_lines, footnote_lines = extract_footnotes(content_lines)

        content = '\n'.join(body_lines)
        comment = f"<!-- 来源：{args.label} | 位置：{c['heading']} -->"

        # 构建完整内容
        full_content = comment + '\n\n' + content

        # 添加脚注区域（如果有）
        if footnote_lines:
            # 去除尾部空行
            while footnote_lines and not footnote_lines[-1].strip():
                footnote_lines.pop()
            if footnote_lines:
                fn_count = sum(1 for l in footnote_lines if l.strip() and not l.startswith(' '))
                fn_total += fn_count
                full_content += '\n\n---\n\n**Notes**\n\n' + '\n'.join(footnote_lines)

        out_file = out_dir / f"chunk-{c['num']:02d}.md"
        out_file.write_text(full_content + '\n', encoding='utf-8')
        fn_tag = f"  (+{len([l for l in footnote_lines if l.strip()])} note lines)" if footnote_lines else ""
        print(f"  写出 chunk-{c['num']:02d}.md  ({c['heading'][:50]}){fn_tag}")

    print(f'\n共写出 {len(chunks)} 个 chunk 文件到 {out_dir}')
    if fn_total:
        print(f'脚注归集：共处理约 {fn_total} 条脚注')


if __name__ == '__main__':
    main()
