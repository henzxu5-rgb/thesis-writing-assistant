# 免费学术 API 端点

以下 API 均免费、无需认证（或仅需邮箱），可通过 WebFetch 直接调用。
返回格式均为 JSON。

---

## 1. Semantic Scholar API

覆盖约 2 亿篇学术论文，支持开放获取 PDF 链接查询。

**按关键词搜索：**
```
GET https://api.semanticscholar.org/graph/v1/paper/search?query={query}&fields=title,authors,year,abstract,externalIds,openAccessPdf,url,citationCount&limit=10
```

**按 DOI 精确查找：**
```
GET https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=title,authors,year,abstract,openAccessPdf,url,citationCount
```

**关键返回字段：**
- `title` — 论文标题
- `authors[].name` — 作者列表
- `year` — 发表年份
- `citationCount` — 被引次数
- `externalIds.DOI` — DOI 编号
- `openAccessPdf.url` — 开放获取 PDF 的直接下载链接（如有）
- `url` — Semantic Scholar 页面链接

**速率限制：** 100 次/5 分钟（无 API key）

---

## 2. CrossRef API

全球最大的 DOI 注册机构，可验证文献真实性并获取精确元数据。

**按关键词搜索：**
```
GET https://api.crossref.org/works?query={query}&rows=5&select=DOI,title,author,published-print,container-title,publisher,type
```

**按 DOI 精确查找：**
```
GET https://api.crossref.org/works/{doi}
```

**关键返回字段（在 `message` 或 `message.items[]` 下）：**
- `DOI` — DOI 编号
- `title[0]` — 论文标题
- `author[].given`, `author[].family` — 作者姓名
- `container-title[0]` — 期刊/书名
- `publisher` — 出版社
- `published-print.date-parts[0]` — 出版日期 [年, 月, 日]
- `type` — 文献类型（journal-article, book, book-chapter 等）

**速率限制：** 无硬性限制（建议在 URL 中添加 `&mailto=user@example.com` 以获得更高优先级）

---

## 3. OpenAlex API

免费开放的学术元数据库，特别擅长标注开放获取状态。

**按关键词搜索：**
```
GET https://api.openalex.org/works?search={query}&per_page=10&select=id,doi,title,authorships,publication_year,cited_by_count,open_access,primary_location,biblio
```

**按 DOI 精确查找：**
```
GET https://api.openalex.org/works/doi:{doi}
```

**关键返回字段（在 `results[]` 下）：**
- `title` — 标题
- `doi` — DOI（完整 URL 格式如 `https://doi.org/10.xxxx/xxxxx`）
- `authorships[].author.display_name` — 作者
- `publication_year` — 发表年份
- `cited_by_count` — 被引次数
- `open_access.is_oa` — 是否开放获取（true/false）
- `open_access.oa_url` — 开放获取版本的 URL
- `primary_location.source.display_name` — 期刊/出版物名称
- `primary_location.source.type` — 来源类型（journal, book 等）

**速率限制：** 无限制（建议添加 `&mailto=user@example.com`）

---

## 4. Unpaywall API

专门用于查找已知 DOI 论文的开放获取版本，覆盖率最高的 OA 发现工具。

**按 DOI 查找（必须已知 DOI）：**
```
GET https://api.unpaywall.org/v2/{doi}?email=thesis-assistant@example.com
```

**关键返回字段：**
- `best_oa_location.url_for_pdf` — 最佳 OA PDF 直接链接
- `best_oa_location.url` — OA 版本页面链接
- `best_oa_location.host_type` — 来源类型（publisher, repository）
- `is_oa` — 是否有任何 OA 版本
- `oa_locations[]` — 所有已知 OA 版本列表（可在首选失败时尝试其他）

**速率限制：** 100,000 次/天

---

## API 查询策略

### 场景 A：已知 DOI
1. **Unpaywall** — 最直接，专门查 OA PDF
2. **Semantic Scholar** — `openAccessPdf` 字段
3. **OpenAlex** — `open_access.oa_url` 字段

### 场景 B：仅知标题和/或作者
1. **CrossRef 搜索** — 获取精确 DOI 和出版元数据
2. 拿到 DOI 后走场景 A 流程
3. 如 CrossRef 无结果，用 **Semantic Scholar 搜索**（标题关键词）

### 场景 C：按主题探索
1. **Semantic Scholar 搜索** — 用主题关键词搜索相关论文
2. **OpenAlex 搜索** — 补充搜索，侧重 OA 状态
3. 对感兴趣的结果，用 CrossRef 验证并补全元数据

### 中文文献特别说明
- CrossRef 对中文文献覆盖有限，但越来越多 CSSCI 期刊已注册 DOI
- Semantic Scholar 对中文文献有一定覆盖（尤其是有英文摘要的论文）
- 中文文献仍建议辅以 **WebSearch 搜索百度学术**（`site:xueshu.baidu.com "论文标题"`）
- CNKI 和万方没有免费公开 API，只能通过 WebSearch 间接搜索
