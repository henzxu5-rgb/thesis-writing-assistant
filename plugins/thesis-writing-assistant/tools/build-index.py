#!/usr/bin/env python3
"""
build-index.py — 从 index-part-*.md 自动组装局部索引 index.md
用法: python3 tools/build-index.py <library-dir>

功能：
- 读取 index-part-*.md 中子 agent 生成的 chunk 描述
- 读取 draft-chunks.md 获取 chunk→行范围映射
- 读取 source-fixed.md 找出 ## 级标题（章级）用于分组
- 读取 meta.md 获取引用信息
- 按章分组输出 index.md

退出码：
  0 = 成功
  1 = 输入文件缺失或格式错误
  2 = chunk 数不匹配（index-part 中的 chunk 数 ≠ draft-chunks 中的 chunk 数）
"""

import re
import sys
from pathlib import Path

CHUNK_LINE_RE = re.compile(
    r'^chunk-(\d+)\s+\[行(\d+)-(\d+),\s*~?\d+[字词]\]\s+#\s*(.+?)(?:\s*\|.*)?$'
)
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$')

# index-part 中的 chunk 描述块起始行
INDEX_CHUNK_RE = re.compile(r'^chunk-(\d+)\.md:\s*(.+)$')


def parse_draft(draft_path: Path) -> list[dict]:
    """解析 draft-chunks.md，返回 chunk 列表 [{num, start, end, heading}]。"""
    chunks = []
    for line in draft_path.read_text(encoding='utf-8').splitlines():
        m = CHUNK_LINE_RE.match(line.strip())
        if m:
            chunks.append({
                'num':     int(m.group(1)),
                'start':   int(m.group(2)),
                'end':     int(m.group(3)),
                'heading': m.group(4).strip(),
            })
    return chunks


def find_chapter_headings(source_path: Path, first_chunk_line: int) -> list[dict]:
    """
    从 source-fixed.md 中找出章级标题及其行号。

    自动检测章级：取 source-fixed.md 中 first_chunk_line 之后出现的最高级别
    （最少 # 数）的标题作为章标题。通常为 # 或 ##。
    跳过 first_chunk_line 之前的标题（如书名行）。

    返回 [{line, heading}]，按行号排序。
    """
    source_lines = source_path.read_text(encoding='utf-8').splitlines()

    # 找出所有标题及其层级
    all_headings = []
    for i, line in enumerate(source_lines, 1):
        m = HEADING_RE.match(line)
        if m:
            all_headings.append({'line': i, 'level': len(m.group(1)), 'heading': m.group(2).strip()})

    # 只看 first_chunk_line 及之后的标题
    relevant = [h for h in all_headings if h['line'] >= first_chunk_line]
    if not relevant:
        return []

    # 最高级别（最小 level 值）即为章级
    min_level = min(h['level'] for h in relevant)

    chapters = [h for h in relevant if h['level'] == min_level]
    return chapters


def map_chunks_to_chapters(chunks: list[dict], chapters: list[dict]) -> dict[int, str]:
    """
    将每个 chunk 映射到其所属的章标题。
    基于 chunk 的 start 行号找到最近的前置章标题。
    返回 {chunk_num: chapter_heading}。
    """
    mapping = {}
    for c in chunks:
        chapter_heading = None
        for ch in chapters:
            if ch['line'] <= c['start']:
                chapter_heading = ch['heading']
            else:
                break
        if chapter_heading is None and chapters:
            chapter_heading = chapters[0]['heading']
        mapping[c['num']] = chapter_heading or c['heading']
    return mapping


def parse_index_parts(lib_dir: Path) -> dict[int, list[str]]:
    """
    解析所有 index-part-*.md 文件。
    返回 {chunk_num: [描述行列表]}，每个 chunk 的描述包含主描述、子话题和 Tags。
    """
    descriptions = {}
    part_files = sorted(lib_dir.glob('index-part-*.md'))

    if not part_files:
        return descriptions

    for pf in part_files:
        lines = pf.read_text(encoding='utf-8').splitlines()
        current_num = None
        current_lines = []

        for line in lines:
            m = INDEX_CHUNK_RE.match(line)
            if m:
                # 保存前一个 chunk
                if current_num is not None:
                    descriptions[current_num] = current_lines
                current_num = int(m.group(1))
                # 转换为 index.md 的格式：- **chunk-NN.md**: 描述
                current_lines = [f'- **chunk-{current_num:02d}.md**: {m.group(2)}']
            elif current_num is not None and line.strip():
                # 子话题或 Tags 行，保持缩进
                current_lines.append(f'    {line.strip()}')

        # 保存最后一个
        if current_num is not None:
            descriptions[current_num] = current_lines

    return descriptions


def extract_citation(meta_path: Path) -> str:
    """从 meta.md 提取引用信息行。"""
    in_citation = False
    citation_lines = []
    for line in meta_path.read_text(encoding='utf-8').splitlines():
        if line.strip() == '## 引用信息':
            in_citation = True
            continue
        if in_citation:
            if line.startswith('## '):
                break
            if line.strip():
                citation_lines.append(line.strip())
    return '\n'.join(citation_lines) if citation_lines else '[引用信息待补充]'


def extract_title(meta_path: Path) -> str:
    """从 meta.md 提取文献标题（第一个 # 标题）。"""
    for line in meta_path.read_text(encoding='utf-8').splitlines():
        if line.startswith('# '):
            return line[2:].strip()
    return '未知文献'


def main():
    if len(sys.argv) < 2:
        print(f'用法: python3 {sys.argv[0]} <library-dir>')
        print('  library-dir: 文献目录路径，如 library/Force and Freedom-Arthur Ripstein/')
        sys.exit(1)

    lib_dir = Path(sys.argv[1])
    if not lib_dir.is_dir():
        print(f'错误: 目录不存在 {lib_dir}')
        sys.exit(1)

    # 检查必要文件
    draft_path  = lib_dir / 'draft-chunks.md'
    source_path = lib_dir / 'source-fixed.md'
    meta_path   = lib_dir / 'meta.md'

    missing = []
    if not draft_path.exists():
        missing.append('draft-chunks.md')
    if not source_path.exists():
        missing.append('source-fixed.md')
    if not meta_path.exists():
        missing.append('meta.md')

    if missing:
        print(f'错误: 缺少必要文件: {", ".join(missing)}')
        sys.exit(1)

    # 检查 index-part 文件
    part_files = sorted(lib_dir.glob('index-part-*.md'))
    if not part_files:
        print('错误: 未找到 index-part-*.md 文件')
        sys.exit(1)

    # 解析数据
    title       = extract_title(meta_path)
    citation    = extract_citation(meta_path)
    chunks      = parse_draft(draft_path)
    first_chunk_line = min(c['start'] for c in chunks) if chunks else 1
    chapters    = find_chapter_headings(source_path, first_chunk_line)
    descriptions = parse_index_parts(lib_dir)
    chunk_to_ch = map_chunks_to_chapters(chunks, chapters)

    # 验证：chunk 数量匹配
    draft_nums = {c['num'] for c in chunks}
    desc_nums  = set(descriptions.keys())

    if draft_nums != desc_nums:
        missing_descs = draft_nums - desc_nums
        extra_descs   = desc_nums - draft_nums
        print(f'错误: chunk 数量不匹配')
        if missing_descs:
            print(f'  draft-chunks 中有但 index-part 中缺失: {sorted(missing_descs)}')
        if extra_descs:
            print(f'  index-part 中有但 draft-chunks 中不存在: {sorted(extra_descs)}')
        sys.exit(2)

    # 按章分组
    groups = []  # [(chapter_heading, [chunk_nums])]
    current_chapter = None
    current_nums = []

    for c in sorted(chunks, key=lambda x: x['num']):
        ch = chunk_to_ch[c['num']]
        if ch != current_chapter:
            if current_chapter is not None:
                groups.append((current_chapter, current_nums))
            current_chapter = ch
            current_nums = [c['num']]
        else:
            current_nums.append(c['num'])

    if current_chapter is not None:
        groups.append((current_chapter, current_nums))

    # 生成 index.md
    out_lines = []
    out_lines.append(f'# {title}局部索引')
    out_lines.append('')
    out_lines.append('## 引用')
    out_lines.append(citation)
    out_lines.append('')
    out_lines.append('## 块描述')
    out_lines.append('')
    out_lines.append(f'共 {len(chunks)} 个小块。')
    out_lines.append('')

    for chapter_heading, nums in groups:
        first, last = nums[0], nums[-1]
        out_lines.append('---')
        out_lines.append('')
        out_lines.append(f'### {chapter_heading} (chunk-{first:02d} ~ chunk-{last:02d})')
        out_lines.append('')

        for n in nums:
            if n in descriptions:
                for desc_line in descriptions[n]:
                    out_lines.append(desc_line)
            else:
                out_lines.append(f'- **chunk-{n:02d}.md**: [描述缺失]')
        out_lines.append('')

    index_path = lib_dir / 'index.md'
    index_path.write_text('\n'.join(out_lines) + '\n', encoding='utf-8')

    print(f'成功: 已生成 {index_path}')
    print(f'  文献: {title}')
    print(f'  章节分组: {len(groups)} 组')
    print(f'  chunk 总数: {len(chunks)}')


if __name__ == '__main__':
    main()
