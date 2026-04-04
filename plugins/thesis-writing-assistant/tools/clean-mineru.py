#!/usr/bin/env python3
"""
clean-mineru.py — 清洗 MinerU 输出的 Markdown 文件（通用噪音清理）

仅做噪音清洗，不做标题层级推断。标题层级由 per-book fix-headings.py 处理。

清洗内容：
1. 删除 CDN/HTTP 图片行
2. 删除孤立页码行
3. LaTeX 还原（脚注、页码范围、排版噪音、TeX 命令剥离、间距数字折叠）
4. 重复 # 标题去重（出现 2 次以上只保留首次）
5. 段落合并（修复 PDF 换页导致的段落截断）

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
_MATH_INLINE_RE = re.compile(r'\$([^$\n]{1,120})\$')

# TeX 命令壳：\mathrm{X}, \textrm{X}, \mathbf{X}, \text{X}, \textbf{X}, \textit{X}
_TEX_CMD_RE = re.compile(
    r'\\(?:mathrm|textrm|mathbf|textbf|textit|text|rm|bf|it'
    r'|operatorname|boldsymbol)\s*'
    r'\{\s*([^{}]*(?:\{[^{}]*\}[^{}]*)*)\s*\}'
)

# 花括号包裹的标点/字符：{ - }, { : }, { . }, { , }
_BRACE_PUNCT_RE = re.compile(r'\{\s*(-|–|:|\.|\,)\s*\}')

# 上标表示法：^ { ... }
_SUPERSCRIPT_RE = re.compile(r'\^\s*\{\s*([^{}]*(?:\{[^{}]*\}[^{}]*)*)\s*\}')

# 下标表示法：_ { ... }
_SUBSCRIPT_RE = re.compile(r'_\s*\{\s*([^{}]*(?:\{[^{}]*\}[^{}]*)*)\s*\}')

# 间距数字：连续的 "数字(组) 空格" 模式（如 "6 5 3"→"653", "28 5"→"285", "6 8"→"68"）
_SPACED_DIGITS_RE = re.compile(r'(?<!\w)(\d+(?:\s+\d+){1,})(?!\w)')

# 残余空花括号
_EMPTY_BRACES_RE = re.compile(r'\{\s*\}')

# 单字符/短内容花括号包裹：{ I }, { B }, { o }, { I7 } 等
_SINGLETON_BRACES_RE = re.compile(r'\{\s*([A-Za-z0-9]{1,4})\s*\}')

# LaTeX 空格命令 → 普通空格
# 短命令：\, \: \; \!  长命令：\thinspace \enspace \quad \qquad \hfill
# 带参数：\hspace{...} \hskip...
_TEX_SPACE_RE = re.compile(
    r'\\(?:thinspace|enspace|quad|qquad|hfill|medspace|thickspace|negthinspace)\s*'
    r'|\\hspace\s*\{[^{}]*\}'
    r'|\\hskip\s*[^a-zA-Z{}\s]*\s*'
    r'|\\[,:;!]\s*'
)

# 残余反斜杠空格（\  或 \ ）
_BACKSLASH_SPACE_RE = re.compile(r'\\\s+')

# 连续空格压缩
_MULTI_SPACE_RE = re.compile(r'  +')


def _is_typeset_noise(content: str) -> bool:
    """判断 $...$ 内容是否为纯排版噪音。"""
    noise_cmds = r'\\(?:mathrm|times|mathbf|text|rm|bf|it|tt|sf|sc|mm|cm|pt|linewidth)'
    return bool(re.search(noise_cmds, content))


def _strip_tex_deep(s: str) -> str:
    """递归剥离 $...$ 内部的 TeX 命令壳、花括号标点、上下标等。"""
    # \left( → (, \left[ → [, \right) → ), \right] → ], bare \left/\right → ''
    s = re.sub(r'\\left\s*([(\[|])', r'\1', s)
    s = re.sub(r'\\right\s*([)\]|])', r'\1', s)
    s = re.sub(r'\\(?:left|right)\s*[.]?', '', s)
    # 常见符号命令替换
    _SYMBOL_MAP = {
        r'\S': '§', r'\circ': '°', r'\AA': 'Å', r'\yen': '¥',
        r'\dag': '†', r'\ddag': '‡', r'\P': '¶', r'\copyright': '©',
    }
    for cmd, repl in _SYMBOL_MAP.items():
        s = s.replace(cmd, repl)
    prev = None
    while prev != s:
        prev = s
        s = _TEX_CMD_RE.sub(r'\1', s)
        s = _BRACE_PUNCT_RE.sub(r'\1', s)
        s = _SUPERSCRIPT_RE.sub(r'\1', s)
        s = _SUBSCRIPT_RE.sub(r'\1', s)
        s = _TEX_SPACE_RE.sub(' ', s)          # before singleton braces (protects \hspace{...})
        s = _SINGLETON_BRACES_RE.sub(r'\1', s)
        s = _EMPTY_BRACES_RE.sub('', s)
        s = _BACKSLASH_SPACE_RE.sub(' ', s)
        # ~ is LaTeX non-breaking space
        s = s.replace('~', ' ')
    # 折叠间距数字
    s = _SPACED_DIGITS_RE.sub(lambda m: m.group(0).replace(' ', ''), s)
    # 将 { - } 风格的连字符还原为 en-dash
    s = s.replace('{ - }', '–').replace('{-}', '–')
    # 清理残余的独立 ^ 符号
    s = re.sub(r'\s*\^\s*', '', s)
    # 数字间的独立连字符转 en-dash：653 - 4 → 653–4, 681 - 2 → 681–2
    s = re.sub(r'(\d)\s*-\s*(\d)', r'\1–\2', s)
    # 压缩多余空格
    s = _MULTI_SPACE_RE.sub(' ', s).strip()
    return s


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

    # 6. 行内 $...$ 深度处理
    def handle_math(m):
        content = m.group(1)
        stripped = _strip_tex_deep(content)
        # 如果剥离后只剩标点/空白/数字/字母（无残余 \cmd），直接输出文本
        if not re.search(r'\\[a-zA-Z]', stripped):
            return stripped
        # 仍含 TeX 命令，判断是否为纯排版噪音
        if _is_typeset_noise(content):
            return ''
        return m.group(0)  # 保留原样（可能是真数学公式）
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

        # 2. 孤立页码行（仅数字和空格，或 MinerU [数字] 格式）
        if re.match(r'^\s*\d+\s*$', stripped) or re.match(r'^\s*\[\d+\]\s*$', stripped):
            continue

        # 2b. 间距字母行：MinerU 将 PDF 大写间距排版（如 "C H A P T E R  1"）OCR 为
        #     "c h a p t e r 1" 等行，这些行紧跟真正的 # 标题，删除不丢信息。
        if re.match(r'^[A-Za-z](?:\s+[A-Za-z0-9])+\s*$', stripped):
            continue

        # 2c. PDF 软连字符 OCR 残留：如 "diffiÂ culty" → "difficulty"
        stripped = re.sub(r'([A-Za-z])Â\s*([A-Za-z])', r'\1\2', stripped)

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
# 段落合并（修复 PDF 换页导致的段落截断）
# ──────────────────────────────────────────────────────────────────────────────

# 句末标点：段落正常结束的标志
_SENTENCE_END_RE = re.compile(r'[.?!;:"\'\)\]）」』。？！；：）\u201d]\s*$')

# 续行开头：小写字母、逗号、分号、左括号、开引号（表示句子未结束）
_CONTINUATION_RE = re.compile(r"^[a-z,;(\u2018\u201c\"']")

# MinerU 页码标记：[数字] 格式（如 [417]、[431]）
_PAGE_MARKER_RE = re.compile(r'^\[\d+\]\s*$')


def merge_page_breaks(lines: list[str]) -> list[str]:
    """
    合并因 PDF 换页而被截断的段落。

    规则：若 line_A 不以句末标点结尾，中间是空行，line_B 以小写字母开头，
    则将 line_A 和 line_B 合并为一行，删除中间空行。
    """
    if len(lines) < 3:
        return lines

    result = []
    i = 0
    merge_count = 0

    while i < len(lines):
        line_a = lines[i]

        # 五行合并：line_A + 空行 + [NNN]页码 + 空行 + line_B（跨页断词）
        if (i + 4 < len(lines)
                and lines[i].strip()
                and not lines[i + 1].strip()
                and _PAGE_MARKER_RE.match(lines[i + 2].strip())
                and not lines[i + 3].strip()
                and lines[i + 4].strip()
                and not HEADING_RE.match(lines[i])
                and not HEADING_RE.match(lines[i + 4])
                and not lines[i].strip().startswith('>')
                and not lines[i].strip().startswith('<!--')
                and not _SENTENCE_END_RE.search(lines[i])
        ):
            la5 = lines[i].rstrip()
            lb5 = lines[i + 4].lstrip()
            merged = la5[:-1] + lb5 if la5.endswith('-') else la5 + lb5
            result.append(merged)
            i += 5
            merge_count += 1
            continue

        # 检查是否符合三行合并条件
        if (i + 2 < len(lines)
                and line_a.strip()                          # line_A 非空
                and not lines[i + 1].strip()                # 中间是空行
                and lines[i + 2].strip()                    # line_B 非空
                and not HEADING_RE.match(line_a)            # line_A 不是标题
                and not HEADING_RE.match(lines[i + 2])      # line_B 不是标题
                and not line_a.strip().startswith('>')       # 不是 blockquote
                and not line_a.strip().startswith('<!--')    # 不是 HTML 注释
                and not _SENTENCE_END_RE.search(line_a)     # line_A 不以句末标点结尾
                and _CONTINUATION_RE.match(lines[i + 2].strip())  # line_B 以小写开头
        ):
            # 合并 line_A + line_B，跳过空行；若 line_A 以连字符结尾则去掉连字符直接拼接
            la = line_a.rstrip()
            lb = lines[i + 2].lstrip()
            merged = la[:-1] + lb if la.endswith('-') else la + ' ' + lb
            result.append(merged)
            i += 3  # 跳过 line_A, 空行, line_B
            merge_count += 1
            continue

        result.append(line_a)
        i += 1

    if merge_count:
        print(f'段落合并：修复 {merge_count} 处换页断裂')

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

    merged = merge_page_breaks(raw_lines)
    print(f'合并后 {len(merged)} 行（合并 {len(raw_lines) - len(merged)} 处）')

    cleaned = clean_noise(merged)
    print(f'清洗后 {len(cleaned)} 行（删除 {len(merged) - len(cleaned)} 行噪音）')

    dst.write_text('\n'.join(cleaned) + '\n', encoding='utf-8')
    print(f'输出到 {dst}')


if __name__ == '__main__':
    main()
