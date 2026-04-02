#!/usr/bin/env python3
"""
fix-mineru.py — 修复 MinerU 输出的平铺型 Markdown 文件（通用版）
1. 噪音清洗（CDN 图片、孤立页码、LaTeX 排版规格、LaTeX 脚注/页码还原）
2. 标题层级推断（将平铺的 # 重写为多级；支持中文/英文/德文学术著作）
3. 续行合并（将断开的标题续行合并到前一行）
用法: python3 tools/fix-mineru.py <输入文件> <输出文件> [--report]
  --report  额外输出每条标题的规则对照表、未匹配标题列表和异常检测结果
"""

import re
import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# 辅助
# ──────────────────────────────────────────────────────────────────────────────

CN_NUM = r'[一二三四五六七八九十百千零]+'
AR_NUM = r'\d+'

# 罗马数字（独立行作为节标题）
ROMAN_RE = re.compile(r'^[IVX]+\.$')

HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$')


def infer_level(title: str) -> tuple[int, str]:
    """
    返回 (推断层级, 规则名)。
    层级：1=# 2=## 3=### 4=####，-1=保持原样（未匹配）。
    title 为去掉前导 # 和空格后的纯文本。
    """
    t = title.strip()
    # 去掉尾部页码（空格+数字）
    t_clean = re.sub(r'\s+\d+\s*$', '', t).strip()

    # ══════════════════════════════════════════════════════════════════════════
    # 中文学术著作规则
    # ══════════════════════════════════════════════════════════════════════════

    # ── 层级 1（书/部级）─────────────────────────────────────────────────────
    # 第X部/第X卷（含"第一部"单独成行和"第一部 副标题"两种形式）
    if re.match(rf'^第({CN_NUM})部(\s|$)', t_clean):
        return 1, 'zh:第X部'
    if re.match(rf'^第({CN_NUM})(大卷|卷)\s', t_clean):
        return 1, 'zh:第X大卷/卷(部级)'

    # ── 层级 2（章/大节级）───────────────────────────────────────────────────
    if re.match(rf'^第({CN_NUM}|{AR_NUM})章', t_clean):
        return 2, 'zh:第X章'
    if re.match(rf'^第({CN_NUM})篇', t_clean):
        return 2, 'zh:第X篇'
    if re.match(rf'^第({CN_NUM})部分', t_clean):
        return 2, 'zh:第X部分'
    # 第X卷（章级：不带"大卷"且匹配章级位置）
    if re.match(rf'^第({CN_NUM})卷[\s　]', t_clean) or re.match(rf'^第({CN_NUM})卷$', t_clean):
        return 2, 'zh:第X卷(章级)'
    # XXX导论/要素论/方法论/要素学/方法学（后缀匹配，与书名无关）
    if re.search(r'(导论|要素论|方法论|要素学|方法学)$', t_clean):
        return 2, 'zh:导论/要素论/方法论'
    # 通用学术大节关键词（与书名无关）
    zh_h2_exact = {
        '前言', '序言', '序', '引言', '导言',
        '目录',
        '摘要', '内容提要',
        '结论', '结语', '结束语', '总结', '后记', '跋', '尾声',
        '附录', '补录', '参考文献', '文献目录', '索引',
    }
    if t_clean in zh_h2_exact:
        return 2, 'zh:通用大节关键词'

    # ── 层级 3（节/小节级）───────────────────────────────────────────────────
    if re.match(rf'^第({CN_NUM}|{AR_NUM})节', t_clean):
        return 3, 'zh:第X节'
    if re.match(r'^§\s*\d+', t_clean):
        return 3, 'zh:§N'
    # 带顿号序号的标题（一、二、三…）
    if re.match(rf'^({CN_NUM}|[一二三四五六七八九十])、', t_clean):
        return 3, 'zh:中文顿号序号'
    # 纯中文数字独立行（如 "一" "二"，长度≤3）
    if re.match(rf'^({CN_NUM})$', t_clean) and len(t_clean) <= 3:
        return 3, 'zh:纯中文数字'
    # "N. 标题"形式（如 1. 道德情感，2. 良知）
    if re.match(r'^\d+\.\s+\S', t_clean):
        return 3, 'zh:N.标题'
    # 单个阿拉伯数字独立行
    if re.match(r'^\d+$', t_clean):
        return 3, 'zh:单个数字'

    # ── 层级 4（款/小款级）───────────────────────────────────────────────────
    if re.search(rf'第({CN_NUM}|{AR_NUM})款', t_clean):
        return 4, 'zh:第X款'
    if t_clean.startswith('决疑论'):
        return 4, 'zh:决疑论'
    # 附释：仅"附释"单独一词或"附释："加冒号 → ####；带内容的长附释 → ###
    if t_clean in ('附释',) or re.match(r'^附释\s*[:：]', t_clean):
        return 4, 'zh:附释(短)'
    if re.match(r'^附释\s+\S', t_clean):
        return 3, 'zh:附释(长)'
    # 小节级附录（"附录 XXX" 带内容）
    if re.match(r'^附录\s+\S', t_clean):
        return 4, 'zh:附录(小节)'
    # 拉丁文括号标题，如 (Cautio iuratoria...)
    if re.match(r'^\(.+\)$', t_clean) and len(t_clean) < 60:
        return 4, 'zh:拉丁括号'
    # 插入章
    if t_clean.startswith('插入章'):
        return 4, 'zh:插入章'

    # ══════════════════════════════════════════════════════════════════════════
    # 英文学术著作规则
    # ══════════════════════════════════════════════════════════════════════════

    tl = t_clean  # 用于大小写不敏感时转小写
    tl_lower = t_clean.lower()

    # ── 层级 1（书/部级）─────────────────────────────────────────────────────
    if re.match(r'^Part\s+[IVX]+', t_clean, re.IGNORECASE):
        return 1, 'en:Part'
    if re.match(r'^Book\s+[IVX\d]+', t_clean, re.IGNORECASE):
        return 1, 'en:Book'

    # ── 层级 2（章级）────────────────────────────────────────────────────────
    if re.match(r'^Chapter\s+\d+', t_clean, re.IGNORECASE):
        return 2, 'en:Chapter N'
    # 精确匹配常见大节标题（大小写不敏感）
    en_h2_exact = {
        'introduction', 'conclusion', 'conclusions', 'preface', 'foreword',
        'abstract', 'acknowledgements', 'acknowledgments', 'bibliography',
        'references', 'appendix', 'epilogue', 'prologue', 'afterword',
    }
    if tl_lower in en_h2_exact:
        return 2, 'en:大节关键词'
    # "Introduction to …" / "Concluding …"
    if re.match(r'^(Introduction to|Concluding)\b', t_clean, re.IGNORECASE):
        return 2, 'en:Introduction to/Concluding'

    # ── 层级 3（节级）────────────────────────────────────────────────────────
    if re.match(r'^Section\s+\d+', t_clean, re.IGNORECASE):
        return 3, 'en:Section N'
    if re.match(r'^§\s*\d+', t_clean):
        return 3, 'en:§N'
    # 罗马数字独立行（I. II. III. 等）
    if ROMAN_RE.match(t_clean):
        return 3, 'en:罗马数字节'

    # ── 层级 4（小节级）──────────────────────────────────────────────────────
    # N.M 形式（如 1.1 / 2.3）
    if re.match(r'^\d+\.\d+', t_clean):
        return 4, 'en:N.M节号'
    en_h4_exact = {'remark', 'corollary', 'note', 'lemma', 'proof', 'example', 'definition'}
    if tl_lower in en_h4_exact or re.match(r'^(Remark|Note|Corollary)\s+\d+', t_clean, re.IGNORECASE):
        return 4, 'en:小节关键词'
    # "Appendix A/B/…"
    if re.match(r'^Appendix\s+[A-Z\d]', t_clean, re.IGNORECASE):
        return 4, 'en:Appendix X'

    # ══════════════════════════════════════════════════════════════════════════
    # 德文学术著作规则
    # ══════════════════════════════════════════════════════════════════════════

    # ── 层级 2（章级）────────────────────────────────────────────────────────
    if re.match(r'^(Kapitel|Kap\.)\s+\d+', t_clean, re.IGNORECASE):
        return 2, 'de:Kapitel'
    de_h2_exact = {
        'einleitung', 'einführung', 'vorwort', 'schluss', 'fazit',
        'zusammenfassung', 'einleitung und überblick',
    }
    if t_clean.lower() in de_h2_exact:
        return 2, 'de:大节关键词'

    # ── 层级 3（节级）────────────────────────────────────────────────────────
    if re.match(r'^(Abschnitt|Absch\.)\s+\d+', t_clean, re.IGNORECASE):
        return 3, 'de:Abschnitt'
    if re.match(r'^§\s*\d+', t_clean):
        return 3, 'de:§N'

    # ── 层级 4（小节级）──────────────────────────────────────────────────────
    de_h4_exact = {'anmerkung', 'korollar', 'zusatz', 'anhang'}
    if t_clean.lower() in de_h4_exact:
        return 4, 'de:小节关键词'

    return -1, 'rule:未匹配'


# ──────────────────────────────────────────────────────────────────────────────
# LaTeX 清洗
# ──────────────────────────────────────────────────────────────────────────────

# 排版规格行特征：含 \mathrm、\times、\mm、\cm、\pt 等纯排版命令
_TYPESET_LINE_RE = re.compile(
    r'\$[^$]*\\(?:mathrm|times|mathbf|text|rm|bf|it|tt|sf|sc)[^$]*\$'
)

# 页码范围 $N\sim M$ → N–M（含可选方括号和重复）
_PAGE_RANGE_RE = re.compile(
    r'\$\[?(\d+)\\sim(\d+)\]?\$'       # $[N\sim M]$ 或 $N\sim M$
    r'(?:\s*\$\[?(\d+)\\sim(\d+)\]?\$)?'  # 可选的重复部分
)

# 简单数字范围 $N-M$ → N–M
_NUM_RANGE_DASH_RE = re.compile(r'\$(\d+)-(\d+)\$')

# 独立数字 $N$ → N（仅限纯数字，避免误伤数学符号）
_ISOLATED_NUM_RE = re.compile(r'\$(\d+)\$')

# 脚注编号还原
_FOOTNOTE_CIRCLED_RE = re.compile(r'\$\s*([①②③④⑤⑥⑦⑧⑨⑩])\s*\$')
_FOOTNOTE_BRACKETED_RE = re.compile(r'\$\[(\d+)\]\$')

# 行首游离方括号 "[ $①$" → "①"
_LEADING_BRACKET_RE = re.compile(r'^\[\s*\$\s*([①-⑩\d]+)\s*\$')

# 数学符号表达式 $= +a^{2}$ / $= 0$ / $= -a$ → 去 $ 保留内容
# 策略：将行内 $...$ 剥离美元符号（若内容不含 \cmd）
_MATH_INLINE_RE = re.compile(r'\$([^$\n]{1,60})\$')


def _is_typeset_noise(content: str) -> bool:
    """判断 $...$ 内容是否为纯排版噪音（不含可读信息）。"""
    noise_cmds = r'\\(?:mathrm|times|mathbf|text|rm|bf|it|tt|sf|sc|mm|cm|pt|linewidth)'
    return bool(re.search(noise_cmds, content))


def clean_latex(line: str) -> str:
    """
    对一行文本做 LaTeX 清洗，返回清洗后的行。
    不删除行，只做行内替换（行级删除在 clean_noise 中处理）。
    """
    # 1. 行首游离方括号
    line = _LEADING_BRACKET_RE.sub(lambda m: m.group(1), line)

    # 2. 脚注编号还原
    line = _FOOTNOTE_CIRCLED_RE.sub(r'\1', line)
    line = _FOOTNOTE_BRACKETED_RE.sub(r'[\1]', line)

    # 3. 页码范围 $[N\sim M]$ $N\sim M$ → N–M（含重复去重）
    def replace_page_range(m):
        n1, m1, n2, m2 = m.group(1), m.group(2), m.group(3), m.group(4)
        return f'{n1}–{m1}'
    line = _PAGE_RANGE_RE.sub(replace_page_range, line)

    # 4. 简单数字连字符范围 $N-M$ → N–M
    line = _NUM_RANGE_DASH_RE.sub(r'\1–\2', line)

    # 5. 独立纯数字 $N$ → N
    line = _ISOLATED_NUM_RE.sub(r'\1', line)

    # 6. 行内 $...$ 处理：排版噪音删除，数学内容保留去 $
    def handle_math(m):
        content = m.group(1)
        if _is_typeset_noise(content):
            return ''   # 排版命令：删除
        return content  # 其他内容：去 $ 保留
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

        # 3. 排版规格整行删除（如版权页的开本/印张信息）
        if _TYPESET_LINE_RE.search(stripped):
            # 整行以排版噪音为主时删除（含有大量非噪音文字的行保留）
            noise_free = _MATH_INLINE_RE.sub('', stripped).strip()
            if len(noise_free) < 10:  # 删除后剩余内容极少
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
# 标题层级重写 + 续行合并
# ──────────────────────────────────────────────────────────────────────────────

def rewrite_headings(lines: list[str], collect_report: bool = False) -> tuple[list[str], list[tuple]]:
    """将单 # 改为多级。返回 (改写后的行列表, report 数据)。"""
    result = []
    report = []
    for i, line in enumerate(lines, 1):
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) == 1:
            title = m.group(2)
            level, rule = infer_level(title)
            if level > 0:
                line = '#' * level + ' ' + title
            if collect_report:
                report.append((i, title[:70], level if level > 0 else 1, rule))
        result.append(line)
    return result, report


def merge_continuation_headings(lines: list[str]) -> list[str]:
    """
    若某行仍是单 #（未匹配），且前1-5行（忽略空行）已有更深层级的标题，
    则将本行内容合并到前一标题行末尾（处理 MinerU 将长标题断成多行的情况）。
    """
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) == 1:
            # 向前查找最近的非空行
            prev_heading_idx = None
            for j in range(len(result) - 1, max(len(result) - 6, -1), -1):
                if result[j].strip() == '':
                    continue
                pm = HEADING_RE.match(result[j])
                if pm and len(pm.group(1)) >= 2:
                    prev_heading_idx = j
                break
            if prev_heading_idx is not None:
                result[prev_heading_idx] = result[prev_heading_idx] + ' ' + m.group(2)
                i += 1
                continue
        result.append(line)
        i += 1
    return result


# ──────────────────────────────────────────────────────────────────────────────
# 主程序
# ──────────────────────────────────────────────────────────────────────────────

def main():
    report_mode = '--report' in sys.argv
    args = [a for a in sys.argv[1:] if a != '--report']

    if len(args) < 2:
        print(f'用法: python3 {sys.argv[0]} <输入文件> <输出文件> [--report]')
        sys.exit(1)

    src = Path(args[0])
    dst = Path(args[1])

    if not src.exists():
        print(f'错误: 文件不存在 {src}')
        sys.exit(1)

    dst.parent.mkdir(parents=True, exist_ok=True)

    raw_lines = src.read_text(encoding='utf-8').splitlines(keepends=False)
    print(f'读取 {len(raw_lines)} 行')

    cleaned = clean_noise(raw_lines)
    print(f'清洗后 {len(cleaned)} 行（删除 {len(raw_lines) - len(cleaned)} 行噪音）')

    # 始终收集规则数据（用于摘要中区分 level-1 匹配 vs 真正未匹配）
    rewritten, report_data = rewrite_headings(cleaned, collect_report=True)
    merged = merge_continuation_headings(rewritten)

    # 构建"真正未匹配"的行号集合（rule:未匹配 且最终仍是 # 的标题）
    unmatched_linenos: set[int] = set()
    for lineno, title, level, rule in report_data:
        if rule == 'rule:未匹配':
            unmatched_linenos.add(lineno)

    # 统计层级分布，区分"level-1 匹配"和"未匹配"
    level_count = {1: 0, 2: 0, 3: 0, 4: 0, 'other': 0}
    unmatched_h1: list[tuple[int, str]] = []   # 真正未匹配的 # 标题
    matched_h1: list[tuple[int, str]] = []     # 正确分类为 level-1 的 # 标题

    # 重建行号映射（merged 行号与 report_data 行号对应 cleaned 阶段）
    # 简单方案：扫描 merged，对所有 # 行查 unmatched_linenos
    # 注意：merged 行号基本与 cleaned 行号一致（merge_continuation 只合并，不插入）
    cur_lineno = 0
    for line in merged:
        cur_lineno += 1
        mm = HEADING_RE.match(line)
        if mm:
            n = len(mm.group(1))
            if n in level_count:
                level_count[n] += 1
            else:
                level_count['other'] += 1
            if n == 1:
                if cur_lineno in unmatched_linenos:
                    unmatched_h1.append((cur_lineno, line[:80]))
                else:
                    matched_h1.append((cur_lineno, line[:80]))

    dst.write_text('\n'.join(merged) + '\n', encoding='utf-8')
    print(f'输出到 {dst}')
    print(f'标题层级分布: #={level_count[1]}  ##={level_count[2]}  ###={level_count[3]}  ####={level_count[4]}')
    if matched_h1:
        print(f'  其中 level-1（书/部级）: {len(matched_h1)} 个  未匹配: {len(unmatched_h1)} 个')

    if unmatched_h1:
        print(f'\n⚠️  未分类的 # 标题（共 {len(unmatched_h1)} 个，需人工或 AI 复查）：')
        for lineno, h in unmatched_h1:
            print(f'  行{lineno:>5}: {h}')
    else:
        print('\n✓ 所有标题均已分类（# 仅用于 level-1 书/部级标题）。')

    # ── --report 模式 ─────────────────────────────────────────────────────────
    if report_mode and report_data:
        print('\n' + '═' * 72)
        print('=== 标题规则对照表 ===')
        print(f'{"行号":>6}  {"层级":<8}  {"规则":<28}  标题')
        print('─' * 72)
        for lineno, title, level, rule in report_data:
            level_str = '#' * level if 1 <= level <= 6 else '#(未匹配)'
            flag = ' ⚠️' if rule == 'rule:未匹配' else ''
            print(f'{lineno:>6}  {level_str:<8}  {rule:<28}  {title}{flag}')

        print('\n' + '═' * 72)
        print('=== 异常检测 ===')
        anomalies = []

        # 异常1：层级跳跃（前后两标题层级差 ≥ 2，且向下跳）
        prev_level = 0
        prev_title = ''
        prev_lineno = 0
        for lineno, title, level, rule in report_data:
            if level < 1:
                continue
            if prev_level > 0 and level - prev_level >= 2:
                anomalies.append(
                    f'  [层级跳跃] 行{prev_lineno}→行{lineno}: '
                    f'{"#"*prev_level} → {"#"*level}  '
                    f'"{prev_title[:30]}" → "{title[:30]}"'
                )
            prev_level = level
            prev_title = title
            prev_lineno = lineno

        # 异常2：连续 5 个以上 #### 堆积
        streak = 0
        streak_start_line = None
        streak_start_title = None
        for lineno, title, level, rule in report_data:
            if level == 4:
                streak += 1
                if streak == 1:
                    streak_start_line = lineno
                    streak_start_title = title
            else:
                if streak >= 5:
                    anomalies.append(
                        f'  [####堆积] 行{streak_start_line}起连续{streak}个####，'
                        f'首个标题："{streak_start_title[:40]}"（可能漏判了###）'
                    )
                streak = 0
                streak_start_line = None
        if streak >= 5:
            anomalies.append(
                f'  [####堆积] 行{streak_start_line}起连续{streak}个####，'
                f'首个标题："{streak_start_title[:40]}"'
            )

        if anomalies:
            for a in anomalies:
                print(a)
        else:
            print('  无异常。')


if __name__ == '__main__':
    main()
