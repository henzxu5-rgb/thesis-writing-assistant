#!/usr/bin/env python3
"""
plan-chunks.py — 生成切分草案（draft-chunks.md）
分析 source-fixed.md 的标题结构，按字数目标给出切分建议。
用法: python3 tools/plan-chunks.py <source-fixed.md路径>
"""

import re
import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────────────────────────────────────
TARGET_MIN = 400    # 合并阈值
TARGET_MAX = 2500   # 普通目标上限
FORCE_SPLIT = 5000  # 强制切分上限

HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$')


def count_cjk(text: str) -> int:
    """统计中日韩字符数（作为中文字数近似）。"""
    return sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f')


def parse_sections(lines: list[str]) -> list[dict]:
    """
    将文件解析为节（section），每节包含：
    - heading: 标题文本
    - level: 标题层级
    - start: 起始行号（1-indexed）
    - end: 结束行号（含）
    - char_count: 中文字符数
    """
    sections = []
    current = None

    for i, line in enumerate(lines, 1):
        m = HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            heading = m.group(2).strip()
            if current is not None:
                current['end'] = i - 1
                current['content'] = '\n'.join(lines[current['start'] - 1: i - 1])
                current['char_count'] = count_cjk(current['content'])
                sections.append(current)
            current = {'heading': heading, 'level': level, 'start': i, 'end': None}

    if current is not None:
        current['end'] = len(lines)
        current['content'] = '\n'.join(lines[current['start'] - 1:])
        current['char_count'] = count_cjk(current['content'])
        sections.append(current)

    return sections


def find_paragraph_breaks(lines: list[str], start_line: int, end_line: int) -> list[int]:
    """在给定行范围内找到段落空行的行号（1-indexed）。"""
    breaks = []
    for i in range(start_line, end_line):
        if not lines[i - 1].strip() and i > start_line:
            breaks.append(i)
    return breaks


def plan_chunks(sections: list[dict], lines: list[str]) -> list[dict]:
    """
    将 sections 合并/切分，返回建议的 chunk 列表。
    每个 chunk: {start, end, heading, char_count, warnings}
    """
    chunks = []

    # 先将所有节合并到 ## 级别边界
    # 策略：以 ## 为基本单元，再根据字数决定是否进一步切分或合并
    groups: list[list[dict]] = []  # 每组是 ## + 其下属节
    current_group: list[dict] = []

    for sec in sections:
        if sec['level'] <= 2 and current_group:
            groups.append(current_group)
            current_group = [sec]
        else:
            current_group.append(sec)
    if current_group:
        groups.append(current_group)

    def group_range(g):
        return g[0]['start'], g[-1]['end']

    def group_chars(g):
        return sum(s['char_count'] for s in g)

    def group_heading(g):
        for s in g:
            if s['level'] <= 2:
                return s['heading']
        return g[0]['heading']

    # 处理每个组
    i = 0
    while i < len(groups):
        g = groups[i]
        total_chars = group_chars(g)
        start_line, end_line = group_range(g)

        # 过小：与下一组合并
        if total_chars < TARGET_MIN and i + 1 < len(groups):
            merged = g + groups[i + 1]
            groups[i + 1] = merged
            i += 1
            continue

        # 在目标范围内：直接作为一个 chunk
        if total_chars <= TARGET_MAX:
            chunks.append({
                'start': start_line,
                'end': end_line,
                'heading': group_heading(g),
                'char_count': total_chars,
                'warnings': [],
            })
            i += 1
            continue

        # 超出 TARGET_MAX：尝试按 ### 边界切分
        if total_chars > TARGET_MAX:
            # 找到 ### 级别的子节
            sub_groups: list[list[dict]] = []
            sub_current: list[dict] = []
            for sec in g:
                if sec['level'] <= 3 and sub_current:
                    sub_groups.append(sub_current)
                    sub_current = [sec]
                else:
                    sub_current.append(sec)
            if sub_current:
                sub_groups.append(sub_current)

            if len(sub_groups) <= 1:
                # 无法按 ### 切分，找段落切分点
                warns = []
                if total_chars > FORCE_SPLIT:
                    warns.append(f'⚠️ 超过{FORCE_SPLIT}字')
                else:
                    warns.append(f'⚠️ 超过{TARGET_MAX}字')
                # 找段落断点
                para_breaks = find_paragraph_breaks(lines, start_line, end_line)
                # 选几个等间距的候选切分点
                if para_breaks:
                    n = total_chars // TARGET_MAX
                    step = len(para_breaks) // max(n, 1)
                    candidates = para_breaks[step::step][:3]
                    warns.append(f'候选拆分点：行{"、".join(str(x) for x in candidates[:3])}（段落空行）')
                chunks.append({
                    'start': start_line,
                    'end': end_line,
                    'heading': group_heading(g),
                    'char_count': total_chars,
                    'warnings': warns,
                })
                i += 1
                continue

            # 按 ### 子组合并到合适大小
            merged_subs: list[list[dict]] = []
            cur_sub: list[dict] = []
            for sg in sub_groups:
                sc = sum(s['char_count'] for s in sg)
                cs = sum(s['char_count'] for s in cur_sub)
                if cur_sub and cs + sc > TARGET_MAX:
                    merged_subs.append(cur_sub)
                    cur_sub = sg
                else:
                    cur_sub.extend(sg)
            if cur_sub:
                merged_subs.append(cur_sub)

            for ms in merged_subs:
                ms_start = ms[0]['start']
                ms_end = ms[-1]['end']
                ms_chars = sum(s['char_count'] for s in ms)
                ms_heading = None
                for s in ms:
                    if s['level'] <= 3:
                        ms_heading = s['heading']
                        break
                if ms_heading is None:
                    ms_heading = ms[0]['heading']
                warns = []
                if ms_chars > FORCE_SPLIT:
                    warns.append(f'⚠️ 超过{FORCE_SPLIT}字')
                elif ms_chars > TARGET_MAX:
                    warns.append(f'⚠️ 超过{TARGET_MAX}字')
                elif ms_chars < TARGET_MIN:
                    warns.append(f'↑ 不足{TARGET_MIN}字，建议与相邻块合并')
                chunks.append({
                    'start': ms_start,
                    'end': ms_end,
                    'heading': ms_heading,
                    'char_count': ms_chars,
                    'warnings': warns,
                })
            i += 1
            continue

        i += 1

    return chunks


def main():
    if len(sys.argv) < 2:
        print(f'用法: python3 {sys.argv[0]} <source-fixed.md>')
        sys.exit(1)

    src = Path(sys.argv[1])
    if not src.exists():
        print(f'错误: 文件不存在 {src}')
        sys.exit(1)

    lines = src.read_text(encoding='utf-8').splitlines()
    print(f'读取 {len(lines)} 行')

    sections = parse_sections(lines)
    print(f'解析 {len(sections)} 个节')

    chunks = plan_chunks(sections, lines)

    # 输出草案
    draft_path = src.parent / 'draft-chunks.md'
    out_lines = ['## 切分草案\n']

    total_chars = sum(c['char_count'] for c in chunks)
    out_lines.append(f'共 {len(chunks)} 个候选块，总计约 {total_chars:,} 字\n')

    for idx, chunk in enumerate(chunks, 1):
        warn_str = ' | '.join(chunk['warnings']) if chunk['warnings'] else ''
        head_str = chunk['heading'][:50] if chunk['heading'] else '（无标题）'
        line = f"chunk-{idx:02d} [行{chunk['start']}-{chunk['end']}, {chunk['char_count']}字] # {head_str}"
        if warn_str:
            line += f' | {warn_str}'
        out_lines.append(line)

    draft_path.write_text('\n'.join(out_lines) + '\n', encoding='utf-8')
    print(f'草案输出到 {draft_path}')

    # 统计
    warn_count = sum(1 for c in chunks if c['warnings'])
    print(f'需关注的块: {warn_count} 个（含警告）')


if __name__ == '__main__':
    main()
