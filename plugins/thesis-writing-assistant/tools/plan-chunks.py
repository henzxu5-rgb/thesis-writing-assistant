#!/usr/bin/env python3
"""
plan-chunks.py — 生成切分草案（draft-chunks.md）
分析 source-fixed.md 的标题结构，按字数目标给出切分建议。
用法: python3 tools/plan-chunks.py <source-fixed.md路径>

支持中文（CJK字符计数）和英文（词数计数），自动检测语言。
ToC（目录）节自动检测并以 toc-NN 前缀单独输出，不参与正常 chunk 编号。
"""

import re
import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# 默认配置（中文）
# ──────────────────────────────────────────────────────────────────────────────
ZH_TARGET_MIN  = 400    # 合并阈值（CJK字符数）
ZH_TARGET_MAX  = 2500   # 普通目标上限
ZH_FORCE_SPLIT = 5000   # 强制切分上限

EN_TARGET_MIN  = 150    # 合并阈值（英文词数）
EN_TARGET_MAX  = 1200   # 普通目标上限
EN_FORCE_SPLIT = 2500   # 强制切分上限

HEADING_RE    = re.compile(r'^(#{1,6})\s+(.+)$')
_TRAILING_NUM = re.compile(r'\s+\d+\s*$')
_CHAPTER_TOC  = re.compile(r'^(Chapter|Appendix|Part|Book)\s+', re.IGNORECASE)


# ──────────────────────────────────────────────────────────────────────────────
# 文本度量与语言检测
# ──────────────────────────────────────────────────────────────────────────────

def count_cjk(text: str) -> int:
    """统计中日韩字符数（作为中文字数近似）。"""
    return sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f')


def count_words(text: str) -> int:
    """统计英文词数（空白分隔的词元数量）。"""
    return len(text.split())


def detect_language(lines: list[str]) -> str:
    """
    检测文件主体语言，返回 'zh' 或 'en'。
    取前500行作为样本；若 CJK 字符占非空白字符比例 > 20%，判为中文。
    """
    sample = ''.join(lines[:500])
    cjk   = sum(1 for c in sample if '\u4e00' <= c <= '\u9fff')
    total = sum(1 for c in sample if not c.isspace())
    return 'zh' if total and cjk / total > 0.2 else 'en'


# ──────────────────────────────────────────────────────────────────────────────
# ToC 区段检测
# ──────────────────────────────────────────────────────────────────────────────

def is_toc_section(section: dict) -> bool:
    """
    判断一个节（section）是否为目录（Table of Contents）节。
    检测规则（满足任意一条即判为 ToC）：
      1. 标题本身含 "contents" 等关键词
      2. 非空行中，末尾带页码（空白+数字结尾）的比例 ≥ 60%，且平均词数 < 18，
         且总词数 ≤ 600（超过此量说明节内包含了大量正文，不是纯目录）
      3. 内容中有 ≥ 3 行未标记的"Chapter/Appendix N..."条目，
         且总词数 ≤ 400（小节内容主要是目录行）
    """
    heading_lower = section['heading'].lower()
    if any(kw in heading_lower for kw in ['contents', 'table of contents']):
        return True

    text_lines = [l for l in section.get('content', '').splitlines() if l.strip()]
    if not text_lines:
        return False

    total_words = sum(len(l.split()) for l in text_lines)

    # 规则2：末尾页码比例（加词数上限保护）
    trailing_ratio = sum(1 for l in text_lines if _TRAILING_NUM.search(l)) / len(text_lines)
    avg_words      = sum(len(l.split()) for l in text_lines) / len(text_lines)
    if trailing_ratio >= 0.6 and avg_words < 18 and total_words <= 600:
        return True

    # 规则3：未标记的 Chapter/Appendix 条目（加词数上限保护）
    chapter_toc_count = sum(
        1 for l in text_lines
        if _CHAPTER_TOC.match(l.strip()) and _TRAILING_NUM.search(l)
    )
    if chapter_toc_count >= 3 and total_words <= 400:
        return True

    return False


# ──────────────────────────────────────────────────────────────────────────────
# 解析节
# ──────────────────────────────────────────────────────────────────────────────

def parse_sections(lines: list[str], count_fn) -> list[dict]:
    """
    将文件解析为节（section），每节包含：
    - heading: 标题文本
    - level:   标题层级（1=# 2=## …）
    - start:   起始行号（1-indexed）
    - end:     结束行号（含）
    - char_count: 文本量（中文为CJK字数，英文为词数）
    - content: 节的完整文本（用于 ToC 检测）
    """
    sections: list[dict] = []
    current: dict | None = None

    for i, line in enumerate(lines, 1):
        m = HEADING_RE.match(line)
        if m:
            level   = len(m.group(1))
            heading = m.group(2).strip()
            if current is not None:
                current['end']        = i - 1
                current['content']    = '\n'.join(lines[current['start'] - 1: i - 1])
                current['char_count'] = count_fn(current['content'])
                sections.append(current)
            current = {'heading': heading, 'level': level, 'start': i, 'end': None}

    if current is not None:
        current['end']        = len(lines)
        current['content']    = '\n'.join(lines[current['start'] - 1:])
        current['char_count'] = count_fn(current['content'])
        sections.append(current)

    return sections


# ──────────────────────────────────────────────────────────────────────────────
# 段落断点查找
# ──────────────────────────────────────────────────────────────────────────────

def find_paragraph_breaks(lines: list[str], start_line: int, end_line: int) -> list[int]:
    """在给定行范围内找到段落空行的行号（1-indexed）。"""
    breaks = []
    for i in range(start_line, end_line):
        if not lines[i - 1].strip() and i > start_line:
            breaks.append(i)
    return breaks


# ──────────────────────────────────────────────────────────────────────────────
# 切分规划
# ──────────────────────────────────────────────────────────────────────────────

def _split_at_level(group: list[dict], level: int) -> list[list[dict]]:
    """将 section 列表按指定标题层级切分为子组。"""
    sub_groups: list[list[dict]] = []
    current: list[dict] = []
    for sec in group:
        if sec['level'] <= level and current:
            sub_groups.append(current)
            current = [sec]
        else:
            current.append(sec)
    if current:
        sub_groups.append(current)
    return sub_groups


def _merge_sub_groups(
    sub_groups: list[list[dict]],
    target_min: int,
    target_max: int,
    max_heading_level: int,
) -> list[list[dict]]:
    """将子组合并到目标大小范围内。"""
    merged: list[list[dict]] = []
    cur: list[dict] = []
    for sg in sub_groups:
        sc = sum(s['char_count'] for s in sg)
        cs = sum(s['char_count'] for s in cur)
        if cur and cs + sc > target_max and cs >= target_min:
            merged.append(cur)
            cur = list(sg)
        else:
            cur.extend(sg)
    if cur:
        merged.append(cur)
    return merged


def _group_range(g: list[dict]) -> tuple[int, int]:
    return g[0]['start'], g[-1]['end']


def _group_chars(g: list[dict]) -> int:
    return sum(s['char_count'] for s in g)


def _group_heading(g: list[dict], max_level: int = 2) -> str:
    for s in g:
        if s['level'] <= max_level:
            return s['heading']
    return g[0]['heading']


def plan_chunks(
    sections:    list[dict],
    lines:       list[str],
    target_min:  int,
    target_max:  int,
    force_split: int,
) -> tuple[list[dict], list[dict]]:
    """
    将 sections 合并/切分，返回：
      (chunks, toc_chunks)
    - chunks:     正常内容块列表，每项: {start, end, heading, char_count, warnings}
    - toc_chunks: ToC块列表，格式相同，由调用者单独输出
    """
    chunks:     list[dict] = []
    toc_chunks: list[dict] = []

    # 以 ## 为基本单元分组
    groups = _split_at_level(sections, level=2)

    def group_main_section(g):
        """返回组内层级最低（最高级）的节，用于 ToC 检测。"""
        return min(g, key=lambda s: s['level'])

    def try_split_group(g: list[dict], min_level: int = 3) -> list[dict]:
        """
        尝试按 ###→####→##### 递进切分超大组，返回 chunk 列表。
        min_level 指定从哪个层级开始尝试（避免重复尝试已失败的层级）。
        """
        result_chunks = []
        total_chars = _group_chars(g)

        # 依次尝试按 level min_level..5 切分
        for split_level in range(min_level, 6):
            sub_groups = _split_at_level(g, split_level)
            if len(sub_groups) <= 1:
                continue  # 该层级无法切分，尝试下一层

            merged = _merge_sub_groups(sub_groups, target_min, target_max, split_level)

            # 检查合并后是否所有子组都在范围内
            all_ok = True
            for ms in merged:
                ms_chars = _group_chars(ms)
                if ms_chars > target_max:
                    all_ok = False
                    break

            if all_ok:
                # 全部在范围内，直接输出
                for ms in merged:
                    ms_chars = _group_chars(ms)
                    ms_start, ms_end = _group_range(ms)
                    ms_heading = _group_heading(ms, split_level)
                    warns = []
                    if ms_chars < target_min:
                        warns.append(f'↑ 不足{target_min}字，建议与相邻块合并')
                    result_chunks.append({
                        'start': ms_start, 'end': ms_end,
                        'heading': ms_heading, 'char_count': ms_chars,
                        'warnings': warns,
                    })
                return result_chunks

            # 部分子组仍超出——对超出的递归尝试更深层级
            for ms in merged:
                ms_chars = _group_chars(ms)
                ms_start, ms_end = _group_range(ms)
                ms_heading = _group_heading(ms, split_level)
                if ms_chars <= target_max:
                    warns = []
                    if ms_chars < target_min:
                        warns.append(f'↑ 不足{target_min}字，建议与相邻块合并')
                    result_chunks.append({
                        'start': ms_start, 'end': ms_end,
                        'heading': ms_heading, 'char_count': ms_chars,
                        'warnings': warns,
                    })
                else:
                    # 递归尝试更深层级（从下一级开始）
                    deeper = try_split_group(ms, min_level=split_level + 1)
                    if deeper:
                        result_chunks.extend(deeper)
                    else:
                        # 无法再切分，作为一个大块输出
                        result_chunks.append(_make_oversized_chunk(
                            ms, ms_start, ms_end, ms_chars, ms_heading, lines
                        ))
            return result_chunks

        # 所有层级都无法切分
        return []

    def _make_oversized_chunk(g, start, end, chars, heading, lines):
        warns = [f'⚠️ 超过{force_split if chars > force_split else target_max}字']
        para_breaks = find_paragraph_breaks(lines, start, end)
        if para_breaks:
            n = max(chars // target_max, 1)
            step = max(len(para_breaks) // n, 1)
            candidates = para_breaks[step::step][:max(n, 3)]
            warns.append(f'候选拆分点：行{"、".join(str(x) for x in candidates)}（段落空行）')
        return {
            'start': start, 'end': end,
            'heading': heading, 'char_count': chars,
            'warnings': warns,
        }

    i = 0
    while i < len(groups):
        g           = groups[i]
        main_sec    = group_main_section(g)
        total_chars = _group_chars(g)
        start_line, end_line = _group_range(g)

        # ── ToC 检测：单独输出，不参与正常编号 ──────────────────────────────
        if is_toc_section(main_sec):
            toc_chunks.append({
                'start':      start_line,
                'end':        end_line,
                'heading':    _group_heading(g),
                'char_count': total_chars,
                'warnings':   ['[ToC节，仅供人工参考，不纳入检索索引]'],
            })
            i += 1
            continue

        # ── 过小：与下一组合并 ────────────────────────────────────────────
        if total_chars < target_min and i + 1 < len(groups):
            next_g = groups[i + 1]
            next_main = group_main_section(next_g)
            if not is_toc_section(next_main):
                groups[i + 1] = g + next_g
                i += 1
                continue

        # ── 在目标范围内：直接作为一个 chunk ─────────────────────────────
        if total_chars <= target_max:
            warns = []
            if total_chars < target_min:
                warns.append(f'↑ 不足{target_min}字，建议与相邻块合并')
            chunks.append({
                'start':      start_line,
                'end':        end_line,
                'heading':    _group_heading(g),
                'char_count': total_chars,
                'warnings':   warns,
            })
            i += 1
            continue

        # ── 超出 target_max：递进式切分（###→####→#####→段落） ──────────
        split_result = try_split_group(g)
        if split_result:
            chunks.extend(split_result)
        else:
            # 完全无法切分，输出为大块
            chunks.append(_make_oversized_chunk(
                g, start_line, end_line, total_chars,
                _group_heading(g), lines
            ))
        i += 1

    return chunks, toc_chunks


# ──────────────────────────────────────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────────────────────────────────────

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

    # 语言检测与阈值选择
    lang = detect_language(lines)
    if lang == 'en':
        count_fn    = count_words
        target_min  = EN_TARGET_MIN
        target_max  = EN_TARGET_MAX
        force_split = EN_FORCE_SPLIT
        unit_label  = '词'
        print(f'检测到语言: 英文（en），阈值: MIN={target_min} MAX={target_max} FORCE={force_split} {unit_label}')
    else:
        count_fn    = count_cjk
        target_min  = ZH_TARGET_MIN
        target_max  = ZH_TARGET_MAX
        force_split = ZH_FORCE_SPLIT
        unit_label  = '字'
        print(f'检测到语言: 中文（zh），阈值: MIN={target_min} MAX={target_max} FORCE={force_split} {unit_label}')

    sections = parse_sections(lines, count_fn)
    print(f'解析 {len(sections)} 个节')

    chunks, toc_chunks = plan_chunks(sections, lines, target_min, target_max, force_split)

    # 输出草案
    draft_path = src.parent / 'draft-chunks.md'
    out_lines  = ['## 切分草案\n']

    total_units = sum(c['char_count'] for c in chunks)
    toc_count   = len(toc_chunks)
    out_lines.append(
        f'共 {len(chunks)} 个内容块'
        + (f'，另有 {toc_count} 个 ToC 块（以 toc- 前缀输出，write-chunks.py 将跳过）' if toc_count else '')
        + f'，内容块总计约 {total_units:,} {unit_label}\n'
    )

    # ToC 块（toc- 前缀，write-chunks.py 不会写出）
    for idx, chunk in enumerate(toc_chunks, 1):
        warn_str  = ' | '.join(chunk['warnings'])
        head_str  = chunk['heading'][:60] if chunk['heading'] else '（无标题）'
        out_lines.append(
            f"toc-{idx:02d} [行{chunk['start']}-{chunk['end']}, {chunk['char_count']}{unit_label}]"
            f" # {head_str} | {warn_str}"
        )

    if toc_chunks:
        out_lines.append('')  # 空行分隔

    # 正常内容块
    for idx, chunk in enumerate(chunks, 1):
        warn_str = ' | '.join(chunk['warnings']) if chunk['warnings'] else ''
        head_str = chunk['heading'][:60] if chunk['heading'] else '（无标题）'
        line     = f"chunk-{idx:02d} [行{chunk['start']}-{chunk['end']}, {chunk['char_count']}{unit_label}] # {head_str}"
        if warn_str:
            line += f' | {warn_str}'
        out_lines.append(line)

    draft_path.write_text('\n'.join(out_lines) + '\n', encoding='utf-8')
    print(f'草案输出到 {draft_path}')

    warn_count = sum(1 for c in chunks if c['warnings'])
    print(f'需关注的块: {warn_count} 个（含警告）')


if __name__ == '__main__':
    main()
