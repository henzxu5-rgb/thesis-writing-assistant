#!/usr/bin/env python3
"""
clean-mineru.py — 清洗 MinerU 输出的 Markdown 文件（通用噪音清理）

仅做噪音清洗，不做标题层级推断。标题层级由 per-book fix-headings.py 处理。

清洗内容：
1. 删除 CDN/HTTP 图片行
2. 删除孤立页码行
3. LaTeX 还原（脚注、页码范围、排版噪音）
4. 重复 # 标题去重（出现 2 次以上只保留首次）

用法: python3 tools/clean-mineru.py <输入文件> <输出文件>
"""

import re
import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────────────────────────────────────

HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$')

# ──────────────────────────────────────────────────────────────────────────────
# LaTeX 清洗
# ──────────────────────────────────────────────────────────────────────────────

# 排版规格行特征：含 \mathrm、\times、\mm、\cm、\pt 等纯排版命令
_TYPESET_LINE_RE = re.compile(
    r'\$[^$]*\\(?:mathrm|times|mathbf|text|rm|bf|it|tt|sf|sc)[^$]*\$'
)

# 页码范围 $N\sim M$ → N–M（含可选方括号和重复）
_PAGE_RANGE_RE = re.compile(
    r'\$\[?(\d+)\\sim(\d+)\]?\$'
    r'(?:\s*\$\[?(\d+)\\sim(\d+)\]?\$)?'
)

# 简单数字范围 $N-M$ → N–M
_NUM_RANGE_DASH_RE = re.compile(r'\$(\d+)-(\d+)\$')

# 独立数字 $N$ → N（仅限纯数字）
_ISOLATED_NUM_RE = re.compile(r'\$(\d+)\$')

# 脚注编号还原
_FOOTNOTE_CIRCLED_RE = re.compile(r'\$\s*([①②③④⑤⑥⑦⑧⑨⑩])\s*\$')
_FOOTNOTE_BRACKETED_RE = re.compile(r'\$\[(\d+)\]\$')

# 行首游离方括号 "[ $①$" → "①"
_LEADING_BRACKET_RE = re.compile(r'^\[\s*\$\s*([①-⑩\d]+)\s*\$')

# 行内 $...$ 处理
_MATH_INLINE_RE = re.compile(r'\$([^$\n]{1,60})\$')


def _is_typeset_noise(content: str) -> bool:
    """判断 $...$ 内容是否为纯排版噪音。"""
    noise_cmds = r'\\(?:mathrm|times|mathbf|text|rm|bf|it|tt|sf|sc|mm|cm|pt|linewidth)'
    return bool(re.search(noise_cmds, content))


def clean_latex(line: str) -> str:
    """对一行文本做 LaTeX 清洗，返回清洗后的行。"""
    # 1. 行首游离方括号
    line = _LEADING_BRACKET_RE.sub(lambda m: m.group(1), line)

    # 2. 脚注编号还原
    line = _FOOTNOTE_CIRCLED_RE.sub(r'\1', line)
    line = _FOOTNOTE_BRACKETED_RE.sub(r'[\1]', line)

    # 3. 页码范围
    def replace_page_range(m):
        n1, m1 = m.group(1), m.group(2)
        return f'{n1}–{m1}'
    line = _PAGE_RANGE_RE.sub(replace_page_range, line)

    # 4. 简单数字连字符范围
    line = _NUM_RANGE_DASH_RE.sub(r'\1–\2', line)

    # 5. 独立纯数字
    line = _ISOLATED_NUM_RE.sub(r'\1', line)

    # 6. 行内 $...$ 处理
    def handle_math(m):
        content = m.group(1)
        if _is_typeset_noise(content):
            return ''
        return content
    line = _MATH_INLINE_RE.sub(handle_math, line)

    return line


# ──────────────────────────────────────────────────────────────────────────────
# 噪音清洗（行级）
# ──────────────────────────────────────────────────────────────────────────────

def clean_noise(lines: list[str]) -> list[str]:
    # 预先统计 # 级标题出现次数，用于去重
    h1_count: dict[str, int] = {}
    for line in lines:
        m = HEADING_RE.match(line.rstrip('\n'))
        if m and len(m.group(1)) == 1:
            key = m.group(2).strip()
            h1_count[key] = h1_count.get(key, 0) + 1

    seen_h1: set[str] = set()
    result = []

    for line in lines:
        stripped = line.rstrip('\n')

        # 1. 删除 CDN/HTTP 图片行
        if re.match(r'^!\[image\]\(https?://', stripped):
            continue

        # 2. 孤立页码行（仅数字和空格）
        if re.match(r'^\s*\d+\s*$', stripped) and stripped.strip():
            continue

        # 3. 排版规格整行删除
        if _TYPESET_LINE_RE.search(stripped):
            noise_free = _MATH_INLINE_RE.sub('', stripped).strip()
            if len(noise_free) < 10:
                continue

        # 4. LaTeX 行内清洗
        stripped = clean_latex(stripped)

        # 5. 重复 # 标题去重（出现 2 次以上只保留第一次）
        m = HEADING_RE.match(stripped)
        if m and len(m.group(1)) == 1:
            key = m.group(2).strip()
            if h1_count.get(key, 0) > 1:
                if key in seen_h1:
                    continue
                seen_h1.add(key)

        result.append(stripped)

    return result


# ──────────────────────────────────────────────────────────────────────────────
# 主程序
# ──────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print(f'用法: python3 {sys.argv[0]} <输入文件> <输出文件>')
        sys.exit(1)

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])

    if not src.exists():
        print(f'错误: 文件不存在 {src}')
        sys.exit(1)

    dst.parent.mkdir(parents=True, exist_ok=True)

    raw_lines = src.read_text(encoding='utf-8').splitlines(keepends=False)
    print(f'读取 {len(raw_lines)} 行')

    cleaned = clean_noise(raw_lines)
    print(f'清洗后 {len(cleaned)} 行（删除 {len(raw_lines) - len(cleaned)} 行噪音）')

    dst.write_text('\n'.join(cleaned) + '\n', encoding='utf-8')
    print(f'输出到 {dst}')


if __name__ == '__main__':
    main()
