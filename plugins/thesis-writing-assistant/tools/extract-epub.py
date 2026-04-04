#!/usr/bin/env python3
"""
extract-epub.py — 从 EPUB 文件提取结构化 Markdown

用法: python3 tools/extract-epub.py <input.epub> <output.md>

功能：
- 保留 EPUB 原生标题层级（h1→##, h2→###, h3→####）
- 检测并回填尾注/脚注，插入 <!-- footnote N --> 标记
- 输出与 plan-chunks.py / write-chunks.py 兼容的 source-fixed.md
"""

from __future__ import annotations

import re
import sys
import argparse
from pathlib import Path
from collections import OrderedDict
from typing import Optional

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, NavigableString, XMLParsedAsHTMLWarning
import warnings

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# ---------------------------------------------------------------------------
# Heading level offset: EPUB <h1> → ## (# is reserved for book title)
# ---------------------------------------------------------------------------
HEADING_OFFSET = 1

# ---------------------------------------------------------------------------
# Endnote detection patterns
# ---------------------------------------------------------------------------
# Pattern for footnote reference links: <a href="...#zw1">注1</a>
# or <a href="...#fn1">1</a>, etc.
_FN_REF_PATTERNS = [
    re.compile(r'#(zw\w+)'),       # Chinese: zw1, zw4a
    re.compile(r'#(fn_?\w+)'),     # fn1, fn_1
    re.compile(r'#(note[_-]?\w+)'),# note1, note-1
    re.compile(r'#(endnote\w*)'),  # endnote1
]

# Pattern to detect endnote anchor IDs
_FN_ANCHOR_PATTERNS = [
    re.compile(r'^zw'),
    re.compile(r'^fn'),
    re.compile(r'^note'),
    re.compile(r'^endnote'),
]

# Metadata pages to skip (copyright, title page, etc.)
_SKIP_CLASSES = {'sgc-toc-title', 'sgc-toc-level', 'sgc-toc-level1'}


def is_toc_page(soup: BeautifulSoup) -> bool:
    """Detect if an HTML document is a table of contents page."""
    body = soup.find('body')
    if not body:
        return False
    toc_divs = body.find_all('div', class_=lambda c: c and 'toc' in c.lower() if c else False)
    if len(toc_divs) > 3:
        return True
    toc_title = body.find(class_=lambda c: c and 'toc-title' in c.lower() if c else False)
    if toc_title:
        return True
    return False


def is_metadata_page(soup: BeautifulSoup) -> bool:
    """Detect cover, title page, copyright page, etc."""
    body = soup.find('body')
    if not body:
        return True
    text = body.get_text(strip=True)
    # Very short pages with only images are likely cover/title pages
    if len(text) < 50:
        imgs = body.find_all('img')
        if imgs:
            return True
    # Copyright indicators
    copyright_keywords = ['ISBN', '版权所有', 'Copyright', 'All rights reserved',
                          '出版社', 'Publishing', '印刷', '字数', '开本']
    matches = sum(1 for kw in copyright_keywords if kw in text)
    if matches >= 3:
        return True
    return False


def find_endnote_files(book) -> set[str]:
    """
    Identify endnote collection files by analyzing cross-file link targets.
    Strategy: count how many spine files link to each target file.
    The endnote file is the one that many different content files link to.
    """
    from collections import Counter

    # Count: for each target file, how many different source files link to it
    target_source_count: dict[str, set[str]] = {}

    for item_id, linear in book.spine:
        item = book.get_item_with_id(item_id)
        if not item:
            continue
        content = item.get_content().decode('utf-8', errors='replace')
        soup = BeautifulSoup(content, 'lxml')
        source_name = item.get_name()

        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            if '#' in href and not href.startswith('#'):
                target_file = href.split('#')[0]
                if target_file != source_name:
                    if target_file not in target_source_count:
                        target_source_count[target_file] = set()
                    target_source_count[target_file].add(source_name)

    # An endnote file is linked to by many different content files (>5)
    endnote_files = set()
    for target, sources in target_source_count.items():
        if len(sources) >= 5:
            endnote_files.add(target)

    return endnote_files


def extract_endnotes(soup: BeautifulSoup) -> dict[str, str]:
    """
    Extract endnotes from an endnote collection page.
    Returns {anchor_id: footnote_text}.
    """
    endnotes = OrderedDict()
    body = soup.find('body')
    if not body:
        return endnotes

    for p in body.find_all(['p', 'div', 'li']):
        a = p.find('a', id=True)
        if not a:
            continue
        aid = a.get('id', '')
        if not any(pat.match(aid) for pat in _FN_ANCHOR_PATTERNS):
            continue
        # Get the full text of the footnote entry.
        # Use get_text() (not strip=True) to preserve whitespace between
        # the "注N" link and the actual footnote content, preventing them
        # from being concatenated (e.g., "注2Hannah" → would lose "H").
        text = p.get_text()
        # Remove leading whitespace, then "注N" / "注4a" prefix or bare number
        text = text.strip()
        text = re.sub(r'^注\d+[a-zA-Z]?\s*', '', text)
        text = re.sub(r'^\d+[a-zA-Z]?\s+', '', text)
        text = text.strip()
        # Collapse internal whitespace (newlines from HTML formatting)
        text = re.sub(r'\s+', ' ', text)
        if text:
            endnotes[aid] = text

    return endnotes


def resolve_fn_ref(href: str) -> str | None:
    """Extract footnote anchor ID from a href like 'text00051.html#zw1'."""
    if not href:
        return None
    for pattern in _FN_REF_PATTERNS:
        m = pattern.search(href)
        if m:
            return m.group(1)
    return None


def element_to_markdown(element, endnotes: dict[str, str],
                        fn_counter: list[int]) -> str:
    """
    Convert a single HTML element to Markdown text.
    Handles inline formatting, blockquotes, lists, and footnote references.
    """
    if isinstance(element, NavigableString):
        text = str(element)
        # Collapse whitespace but preserve newlines
        text = re.sub(r'[ \t]+', ' ', text)
        return text

    tag = element.name
    if tag is None:
        return ''

    # Skip images
    if tag == 'img':
        return ''

    # Skip <br> — just add a newline
    if tag == 'br':
        return '\n'

    # Headings
    if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
        level = int(tag[1]) + HEADING_OFFSET
        prefix = '#' * level
        # Extract heading text, skipping footnote ref elements (<sup>, <a>)
        text_parts = []
        for child in element.descendants:
            if isinstance(child, NavigableString):
                parent = child.parent
                # Skip text inside <sup> or footnote <a> tags
                if parent.name == 'sup':
                    continue
                if parent.name == 'a' and parent.find('sup'):
                    continue
                text_parts.append(str(child))
        text = ''.join(text_parts).strip()
        text = re.sub(r'\s+', ' ', text)
        return f'\n{prefix} {text}\n'

    # Footnote reference link: <a href="...#zwN"><sup>注N</sup></a>
    # or <sup><a href="...#zwN">注N</a></sup>
    # Both patterns: an <a> with a footnote href, possibly wrapping or inside <sup>
    if tag == 'a' and element.get('href'):
        fn_id = resolve_fn_ref(element.get('href', ''))
        if fn_id and fn_id in endnotes:
            fn_counter[0] += 1
            fn_num = fn_counter[0]
            fn_text = endnotes[fn_id]
            return f'\n\n<!-- footnote {fn_num} -->\n{fn_num} {fn_text}\n'

    if tag == 'sup':
        # Check if parent <a> already handled footnote
        parent_a = element.find_parent('a')
        if parent_a:
            fn_id = resolve_fn_ref(parent_a.get('href', ''))
            if fn_id and fn_id in endnotes:
                # Already handled by the <a> tag processing above
                return ''
        # Check if <sup> contains <a> (alternative pattern)
        a = element.find('a', href=True)
        if a:
            fn_id = resolve_fn_ref(a.get('href', ''))
            if fn_id and fn_id in endnotes:
                fn_counter[0] += 1
                fn_num = fn_counter[0]
                fn_text = endnotes[fn_id]
                return f'\n\n<!-- footnote {fn_num} -->\n{fn_num} {fn_text}\n'
        # Plain superscript text
        return element.get_text()

    # Blockquote
    if tag == 'blockquote':
        inner = children_to_markdown(element, endnotes, fn_counter)
        inner = inner.strip()
        # Prefix each line with >
        lines = inner.split('\n')
        quoted = '\n'.join(f'> {line}' for line in lines)
        return f'\n\n{quoted}\n'

    # Emphasis
    if tag in ('em', 'i'):
        inner = children_to_markdown(element, endnotes, fn_counter)
        inner = inner.strip()
        if inner:
            return f'*{inner}*'
        return ''

    # Strong
    if tag in ('strong', 'b'):
        inner = children_to_markdown(element, endnotes, fn_counter)
        inner = inner.strip()
        if inner:
            return f'**{inner}**'
        return ''

    # Lists
    if tag == 'ul':
        items = []
        for li in element.find_all('li', recursive=False):
            text = children_to_markdown(li, endnotes, fn_counter).strip()
            items.append(f'- {text}')
        return '\n' + '\n'.join(items) + '\n'

    if tag == 'ol':
        items = []
        for i, li in enumerate(element.find_all('li', recursive=False), 1):
            text = children_to_markdown(li, endnotes, fn_counter).strip()
            items.append(f'{i}. {text}')
        return '\n' + '\n'.join(items) + '\n'

    # Paragraph
    if tag == 'p':
        inner = children_to_markdown(element, endnotes, fn_counter)
        inner = inner.strip()
        if inner:
            return f'\n\n{inner}\n'
        return ''

    # Generic block elements
    if tag in ('div', 'section', 'article', 'main', 'body'):
        return children_to_markdown(element, endnotes, fn_counter)

    # Span and other inline elements
    return children_to_markdown(element, endnotes, fn_counter)


def children_to_markdown(element, endnotes: dict[str, str],
                         fn_counter: list[int]) -> str:
    """Convert all children of an element to Markdown."""
    parts = []
    for child in element.children:
        parts.append(element_to_markdown(child, endnotes, fn_counter))
    return ''.join(parts)


def process_epub(epub_path: str, output_path: str) -> dict:
    """
    Main processing function.
    Returns stats dict with line_count, h2_count, h3_count, footnote_count.
    """
    book = epub.read_epub(epub_path, options={"ignore_ncx": False})

    # Extract book title from metadata
    titles = book.get_metadata('DC', 'title')
    book_title = titles[0][0] if titles else 'Untitled'

    # First pass: identify endnote collection files by cross-file link analysis
    endnote_files = find_endnote_files(book)
    endnotes = OrderedDict()

    for item_id, linear in book.spine:
        item = book.get_item_with_id(item_id)
        if not item:
            continue
        if item.get_name() not in endnote_files:
            continue
        content = item.get_content().decode('utf-8', errors='replace')
        soup = BeautifulSoup(content, 'lxml')
        page_notes = extract_endnotes(soup)
        endnotes.update(page_notes)

    # Second pass: convert content pages to Markdown
    md_parts = [f'# {book_title}\n']
    fn_counter = [0]  # mutable counter for footnote numbering

    for item_id, linear in book.spine:
        item = book.get_item_with_id(item_id)
        if not item:
            continue

        # Skip endnote pages (already processed)
        if item.get_name() in endnote_files:
            continue

        content = item.get_content().decode('utf-8', errors='replace')
        soup = BeautifulSoup(content, 'lxml')

        # Skip non-content pages
        if is_toc_page(soup):
            continue
        if is_metadata_page(soup):
            continue

        body = soup.find('body')
        if not body:
            continue

        page_md = children_to_markdown(body, endnotes, fn_counter)
        if page_md.strip():
            md_parts.append(page_md)

    # Join and clean up
    full_md = '\n'.join(md_parts)

    # Normalize blank lines (max 2 consecutive)
    full_md = re.sub(r'\n{4,}', '\n\n\n', full_md)

    # Remove trailing whitespace on lines
    lines = full_md.split('\n')
    lines = [line.rstrip() for line in lines]
    full_md = '\n'.join(lines)

    # Ensure file ends with single newline
    full_md = full_md.strip() + '\n'

    # Write output
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(full_md, encoding='utf-8')

    # Compute stats
    h2_count = full_md.count('\n## ')
    h3_count = full_md.count('\n### ')
    h4_count = full_md.count('\n#### ')
    fn_count = fn_counter[0]
    line_count = len(full_md.split('\n'))

    return {
        'title': book_title,
        'lines': line_count,
        'h2': h2_count,
        'h3': h3_count,
        'h4': h4_count,
        'footnotes': fn_count,
    }


def main():
    parser = argparse.ArgumentParser(
        description='从 EPUB 文件提取结构化 Markdown'
    )
    parser.add_argument('input', help='输入 EPUB 文件路径')
    parser.add_argument('output', help='输出 Markdown 文件路径')
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f'错误: 文件不存在 {args.input}')
        sys.exit(1)

    stats = process_epub(args.input, args.output)

    print(f'TITLE: {stats["title"]}')
    print(f'FORMAT: epub')
    print(f'OUTPUT: {args.output}')
    print(f'LINES: {stats["lines"]}')
    print(f'H2_COUNT: {stats["h2"]}')
    print(f'H3_COUNT: {stats["h3"]}')
    print(f'H4_COUNT: {stats["h4"]}')
    print(f'FOOTNOTES: {stats["footnotes"]}')
    print(f'SKIP_CLEANING: true')


if __name__ == '__main__':
    main()
