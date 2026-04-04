#!/usr/bin/env python3
"""
extract-html.py — 从学术 HTML 页面提取结构化 Markdown

用法: python3 tools/extract-html.py <input.html> <output.md>

功能：
- 从出版商 HTML 全文页面提取正文内容
- 使用 readability-lxml 去除导航、��边栏、广告
- 保留标题层级，检测并标记脚注
- 输出与 plan-chunks.py / write-chunks.py 兼容的 source-fixed.md
"""

from __future__ import annotations

import re
import sys
import argparse
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup, NavigableString
from readability import Document
import markdownify

# ---------------------------------------------------------------------------
# Heading level offset: HTML <h1> → ## (# is reserved for document title)
# ---------------------------------------------------------------------------
HEADING_OFFSET = 1

# ---------------------------------------------------------------------------
# Footnote detection patterns
# ---------------------------------------------------------------------------
_FN_HREF_RE = re.compile(r'#(?:fn|note|endnote|ftn|sdfootnote)[_-]?(\w+)', re.I)
_FN_ID_RE = re.compile(r'^(?:fn|note|endnote|ftn|sdfootnote)[_-]?(\w+)', re.I)


def detect_encoding(raw_bytes: bytes) -> str:
    """Detect HTML encoding from BOM, meta charset, or fallback to utf-8."""
    # BOM detection
    if raw_bytes.startswith(b'\xef\xbb\xbf'):
        return 'utf-8'
    if raw_bytes.startswith(b'\xff\xfe'):
        return 'utf-16-le'

    # Quick meta charset scan (first 4KB)
    head = raw_bytes[:4096].decode('ascii', errors='replace')
    m = re.search(r'charset=["\']?([^"\'\s;>]+)', head, re.I)
    if m:
        return m.group(1).strip()

    # Try utf-8, fallback to gb18030 (covers most Chinese pages)
    try:
        raw_bytes.decode('utf-8')
        return 'utf-8'
    except UnicodeDecodeError:
        return 'gb18030'


def extract_metadata(soup: BeautifulSoup) -> dict[str, str]:
    """Extract document metadata from <meta> tags."""
    meta = {}
    for tag in soup.find_all('meta'):
        name = tag.get('name', '') or tag.get('property', '')
        content = tag.get('content', '')
        name_lower = name.lower()
        if 'title' in name_lower or name_lower == 'dc.title' or name_lower == 'citation_title':
            meta['title'] = content
        elif 'author' in name_lower or name_lower == 'dc.creator' or name_lower == 'citation_author':
            meta.setdefault('authors', []).append(content)
        elif name_lower in ('dc.date', 'citation_publication_date', 'citation_date'):
            meta['date'] = content
        elif name_lower in ('dc.source', 'citation_journal_title'):
            meta['journal'] = content
        elif name_lower in ('citation_doi', 'dc.identifier'):
            if 'doi' in content.lower() or '10.' in content:
                meta['doi'] = content

    # Fallback: try <title> tag
    if 'title' not in meta:
        title_tag = soup.find('title')
        if title_tag:
            meta['title'] = title_tag.get_text(strip=True)

    return meta


def extract_footnotes_from_html(soup: BeautifulSoup) -> dict[str, str]:
    """
    Extract footnotes from HTML. Looks for common patterns:
    - <div class="footnotes"> / <section class="footnotes">
    - <ol> containing <li id="fn-...">
    - Individual <div id="fn1"> or <p id="note-1">
    """
    footnotes = {}

    # Pattern 1: Footnote container (div/section/ol with footnote class or id)
    for container_tag in ('div', 'section', 'aside', 'ol'):
        for container in soup.find_all(container_tag,
                id=lambda x: x and re.search(r'foot|note|endnote|fn', x, re.I) if x else False):
            _extract_fn_from_container(container, footnotes)
        for container in soup.find_all(container_tag,
                class_=lambda x: x and any(re.search(r'foot|note|endnote|fn', c, re.I) for c in (x if isinstance(x, list) else [x])) if x else False):
            _extract_fn_from_container(container, footnotes)

    # Pattern 2: Individual elements with footnote IDs
    if not footnotes:
        for tag in soup.find_all(id=_FN_ID_RE):
            fn_id = tag.get('id', '')
            text = tag.get_text(strip=True)
            # Remove leading number
            text = re.sub(r'^\d+\.?\s*', '', text)
            text = re.sub(r'^↩\s*', '', text)  # Remove back-link arrow
            if text and len(text) > 5:
                footnotes[fn_id] = text

    return footnotes


def _extract_fn_from_container(container, footnotes: dict):
    """Extract individual footnotes from a container element."""
    # Try <li> items first (ordered list of footnotes)
    for li in container.find_all('li', id=True):
        fn_id = li.get('id', '')
        text = li.get_text(strip=True)
        # Remove back-link arrows and leading numbers
        text = re.sub(r'↩\s*$', '', text)
        text = re.sub(r'^\d+\.?\s*', '', text)
        if text:
            footnotes[fn_id] = text

    # Try <p> or <div> items if no <li> found
    if not any(fn_id for fn_id in footnotes if container.find(id=fn_id)):
        for child in container.find_all(['p', 'div'], id=True):
            fn_id = child.get('id', '')
            if _FN_ID_RE.match(fn_id):
                text = child.get_text(strip=True)
                text = re.sub(r'^\d+\.?\s*', '', text)
                if text:
                    footnotes[fn_id] = text


class AcademicMarkdownConverter(markdownify.MarkdownConverter):
    """Custom markdown converter for academic HTML."""

    def __init__(self, footnotes: dict[str, str], **kwargs):
        super().__init__(**kwargs)
        self.footnotes = footnotes
        self.fn_counter = 0

    def convert_hn(self, n, el, text, convert_as_inline):
        """Convert heading with level offset."""
        level = n + HEADING_OFFSET
        text = text.strip()
        if not text:
            return ''
        # Remove footnote markers from heading text
        text = re.sub(r'\[\d+\]', '', text).strip()
        return f'\n\n{"#" * level} {text}\n\n'

    def convert_sup(self, el, text, convert_as_inline):
        """Handle superscript - check for footnote references."""
        a = el.find('a', href=True)
        if a:
            return self._try_footnote_ref(a, text)
        # Check if parent is a footnote link
        if el.parent and el.parent.name == 'a' and el.parent.get('href'):
            return ''  # Will be handled by parent <a>
        return text

    def convert_a(self, el, text, convert_as_inline):
        """Handle links - check for footnote references."""
        href = el.get('href', '')
        result = self._try_footnote_ref(el, text)
        if result is not None:
            return result
        # Regular link: just return text (no markdown links in academic text)
        return text

    def _try_footnote_ref(self, a_el, text) -> Optional[str]:
        """Try to resolve a footnote reference from an <a> element."""
        href = a_el.get('href', '')
        m = _FN_HREF_RE.search(href)
        if not m:
            return None

        # Try to find footnote by various ID patterns
        fn_key = m.group(0).lstrip('#')
        fn_text = self.footnotes.get(fn_key)

        if not fn_text:
            # Try matching just the numeric part
            for fid, ftext in self.footnotes.items():
                if fid.endswith(m.group(1)):
                    fn_text = ftext
                    break

        if fn_text:
            self.fn_counter += 1
            fn_num = self.fn_counter
            return f'\n\n<!-- footnote {fn_num} -->\n{fn_num} {fn_text}\n\n'

        return None

    def convert_blockquote(self, el, text, convert_as_inline):
        """Convert blockquote."""
        text = text.strip()
        lines = text.split('\n')
        return '\n\n' + '\n'.join(f'> {line}' for line in lines) + '\n\n'

    def convert_img(self, el, text, convert_as_inline):
        """Skip images."""
        return ''


def process_html(html_path: str, output_path: str) -> dict:
    """Main processing function."""
    raw_bytes = Path(html_path).read_bytes()
    encoding = detect_encoding(raw_bytes)
    html_text = raw_bytes.decode(encoding, errors='replace')

    # Parse full HTML for metadata and footnotes
    full_soup = BeautifulSoup(html_text, 'lxml')
    metadata = extract_metadata(full_soup)
    footnotes = extract_footnotes_from_html(full_soup)

    # Use readability to extract main content
    doc = Document(html_text)
    title = metadata.get('title', doc.title() or 'Untitled')
    content_html = doc.summary()

    # Convert to Markdown using custom converter
    converter = AcademicMarkdownConverter(
        footnotes=footnotes,
        heading_style='ATX',
        bullets='-',
        strong_em_symbol='*',
    )
    md_body = converter.convert(content_html)

    # Build full document
    parts = [f'# {title}\n']

    # Add metadata block if available
    meta_lines = []
    if 'authors' in metadata:
        meta_lines.append(f'作者: {", ".join(metadata["authors"])}')
    if 'journal' in metadata:
        meta_lines.append(f'期刊: {metadata["journal"]}')
    if 'date' in metadata:
        meta_lines.append(f'日期: {metadata["date"]}')
    if 'doi' in metadata:
        meta_lines.append(f'DOI: {metadata["doi"]}')

    if meta_lines:
        parts.append('\n'.join(meta_lines) + '\n')

    parts.append(md_body)

    full_md = '\n'.join(parts)

    # Clean up
    full_md = re.sub(r'\n{4,}', '\n\n\n', full_md)
    lines = full_md.split('\n')
    lines = [line.rstrip() for line in lines]
    full_md = '\n'.join(lines).strip() + '\n'

    # Write output
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(full_md, encoding='utf-8')

    # Stats
    h2_count = full_md.count('\n## ')
    h3_count = full_md.count('\n### ')
    h4_count = full_md.count('\n#### ')
    line_count = len(full_md.split('\n'))

    return {
        'title': title,
        'lines': line_count,
        'h2': h2_count,
        'h3': h3_count,
        'h4': h4_count,
        'footnotes': converter.fn_counter,
    }


def main():
    parser = argparse.ArgumentParser(
        description='从学术 HTML 页面提取结构化 Markdown'
    )
    parser.add_argument('input', help='输入 HTML 文件路径')
    parser.add_argument('output', help='输出 Markdown 文件路径')
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f'错误: 文件不存在 {args.input}')
        sys.exit(1)

    stats = process_html(args.input, args.output)

    print(f'TITLE: {stats["title"]}')
    print(f'FORMAT: html')
    print(f'OUTPUT: {args.output}')
    print(f'LINES: {stats["lines"]}')
    print(f'H2_COUNT: {stats["h2"]}')
    print(f'H3_COUNT: {stats["h3"]}')
    print(f'H4_COUNT: {stats["h4"]}')
    print(f'FOOTNOTES: {stats["footnotes"]}')
    print(f'SKIP_CLEANING: true')


if __name__ == '__main__':
    main()
