---
name: find-and-download-references
description: >
  搜索、评估和下载学术参考文献。当用户说「找文献」「收集参考资料」「文献综述」
  「找论文」「推荐著作」「参考书目」「collect references」「bibliography」
  「有哪些相关文献」「推荐阅读」「下载文献」「找原文」「下载论文」
  「download references」「获取全文」「下载PDF」「帮我找到这篇论文」
  「把文献下载下来」，或讨论某个学术主题需要哪些文献支撑时触发。
argument-hint: "[主题关键词或文献标题] [--type monograph|paper|all] [--download-only]"
---

# 文献搜索、评估与下载指引

帮助用户搜索学术文献、评估文献质量、整理下载链接，并在用户手动下载后完成文件重命名与索引更新。

**核心原则：**
- 推荐的文献必须是真实存在的，不可编造
- 如果无法确认某文献是否真实存在，标注 `[待核实]`
- 不突破付费墙：遇到付费文献只记录链接，提示用户自行获取
- 诚实报告每篇文献的搜索结果
- **不自动下载文件**：AI 负责整理下载链接，由用户在浏览器中手动下载

---

## 工作流程

### Step 1: 明确搜索范围

确认用户需要的文献类型和主题方向：
- 主题关键词（如"康德法权学说"、"独立命题 categorical imperative"）
- 文献类型偏好：专著、期刊论文、译著、或全部
- 语言偏好：中文为主，是否需要外文文献
- 如果用户使用了 `--download-only`，直接跳到 Step 5

### Step 2: 多源搜索

读取 `${CLAUDE_PLUGIN_ROOT}/references/api-endpoints.md` 获取 API 查询方式。

**Tier 1：学术 API 结构化搜索（优先）**

使用 WebFetch 调用以下 API，按用户提供的关键词搜索：

1. **Semantic Scholar API** — 搜索论文，获取标题、作者、年份、被引次数、OA PDF 链接
   ```
   WebFetch: https://api.semanticscholar.org/graph/v1/paper/search?query={关键词}&fields=title,authors,year,abstract,externalIds,openAccessPdf,url,citationCount&limit=10
   ```

2. **CrossRef API** — 验证文献真实性，获取 DOI 和出版元数据
   ```
   WebFetch: https://api.crossref.org/works?query={关键词}&rows=5&select=DOI,title,author,published-print,container-title,publisher,type
   ```

3. **OpenAlex API** — 查询开放获取状态
   ```
   WebFetch: https://api.openalex.org/works?search={关键词}&per_page=10&select=id,doi,title,authorships,publication_year,cited_by_count,open_access,primary_location
   ```

对于每篇 API 返回的论文，提取：
- 标题、作者、年份
- DOI（如有）
- 被引次数（`citationCount` 或 `cited_by_count`）
- OA PDF 链接（`openAccessPdf.url` 或 `open_access.oa_url`）
- 期刊/出版社名称

**Tier 2：WebSearch 补充搜索**

API 覆盖不足的领域，使用 WebSearch 补充：
- **中文文献**：搜索百度学术（`site:xueshu.baidu.com "论文标题"`）、知网开放获取
- **哲学专业文献**：搜索 PhilPapers（`site:philpapers.org {关键词}`）
- **Google Scholar**：`site:scholar.google.com "{论文标题}"`

**Tier 3：核心学者参考**

读取 `${CLAUDE_PLUGIN_ROOT}/skills/find-and-download-references/references/source-databases.md`，
交叉验证搜索结果是否覆盖了该主题的核心学者和重要文献。

### Step 3: 整理候选列表并评估质量

**去重：** 根据 DOI 或精确标题去重，合并来自不同来源的信息。

**检查已有文献：** 读取 `library/index.md` 和 `sources/index.md`，标注哪些文献已经获取或入库。

为每篇候选文献整理以下信息：

#### 3.1 基本引用信息
- 完整引用（GB/T 7714 格式）
- DOI（如有）

#### 3.2 学术质量说明（必须提供）

为每篇文献提供质量评估，帮助用户判断是否值得引用：

**期刊/出版社级别：**
- 中文期刊：是否被 CSSCI（南大核心）或北大核心收录。参考 source-databases.md 中的核心期刊列表
- 外文期刊：是否被 A&HCI、SSCI 收录；是否为学科公认重要期刊（如 *Kant-Studien*、*International Journal of Philosophical Studies*）
- 专著出版社：是否为学术权威出版社（如 Cambridge UP、Oxford UP、Harvard UP、De Gruyter、商务印书馆、中国人民大学出版社、法律出版社等）

**被引次数：**
- 从 Semantic Scholar 或 OpenAlex 获取的被引数
- 注明数据来源（如"据 Semantic Scholar 数据"）
- 中文文献在国际数据库中被引数据可能不完整，需注明

**作者资质：**
- 是否为 source-databases.md 中列出的核心学者
- 作者的主要学术机构和研究方向（如已知）

**一句话质量定性判断：** 例如：
- "本文发表于 A&HCI 收录期刊 *Kant-Studien*，作者为该领域活跃研究者，被引 45 次，在毕业论文中引用符合学术规范"
- "本书由 Cambridge University Press 出版，作者 Ripstein 是当代康德法权理论最重要的研究者之一，被引 380 次，属于核心参考文献"
- "本文发表于 CSSCI 核心期刊《伦理学研究》，在毕业论文中引用符合学术规范"

#### 3.3 获取状态
- 是否有免费下载版本（标注 OA PDF URL）
- 如需付费，建议获取途径（学校 VPN、图书馆、馆际互借等）

#### 3.4 与论文的关联
- 推荐理由（2-3 句，说明与论文的关联）
- 建议用于论文哪个部分
- 重要程度：核心文献 / 重要参考 / 扩展阅读

### Step 4: 展示结果，等待用户审批

将候选列表展示给用户，**明确询问**：
> 以上是搜索到的候选文献。请告诉我：
> 1. 哪些文献需要下载？（输入编号）
> 2. 是否需要继续搜索其他方向的文献？
> 3. 是否需要将推荐列表保存到 `research/` 目录？

**必须等用户回复后才进入 Step 5。不要自动开始下载。**

### Step 5: 整理下载指引

对用户批准的每篇文献，查找最佳下载链接并整理成下载指引，由用户手动下载。

#### 5.1 查找下载链接

**如果 Step 3 已有 OA PDF URL：** 直接使用。

**如果没有，按以下顺序查找：**

1. **有 DOI 的文献 — API 查找 OA 版本：**
   - Unpaywall：`WebFetch: https://api.unpaywall.org/v2/{doi}?email=thesis-assistant@example.com`
     → 检查 `best_oa_location.url_for_pdf`
   - Semantic Scholar：`WebFetch: https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=openAccessPdf`
     → 检查 `openAccessPdf.url`
   - OpenAlex：`WebFetch: https://api.openalex.org/works/doi:{doi}`
     → 检查 `open_access.oa_url`

2. **无 DOI 或 API 无结果 — WebSearch 搜索：**
   - 外文：`"{论文完整标题}" filetype:pdf`，以及作者主页、大学仓库
   - 中文：百度学术搜索标题，检查是否有免费下载

#### 5.1b 格式偏好与查找策略

按以下优先级寻找最佳格式，每级找不到再降级：

**书籍类文献（按优先级）：**

1. **EPUB（首选）**  
   - 在 Z-Library 用 ISBN 搜索，筛选 EPUB 格式
   - 若无结果，去掉格式过滤再搜一次确认 Z-Library 是否收录该书（可能只有 PDF）
   - 补充检查：Project Gutenberg、Open Library（主要覆盖公版书）

2. **HTML 全文（次选）**  
   - 用 DOI 查出版商页面（Harvard UP → De Gruyter、Oxford UP → Oxford Academic、Cambridge UP → Cambridge Core 等）
   - ⚠️ 注意：主流学术出版社的 HTML 全文**几乎均需机构认证**，不可直接下载
   - 如果用户有学校 VPN / 图书馆账号可访问，HTML 是最佳格式；否则跳过
   - 在下载指引中注明 HTML 链接及"需机构访问"

3. **PDF（回退）**  
   - Z-Library ISBN 搜索（无格式过滤）
   - OA PDF（Unpaywall / Semantic Scholar / OpenAlex）
   - 如果 sources/ 里已有 PDF，**无需重复下载**，直接保留并在 index 中标注 `PDF（无EPUB版）`

**期刊论文（按优先级）：**

1. **HTML 全文（首选）**：检查出版商是否提供 HTML 全文页面（Springer、Wiley、Cambridge UP、De Gruyter 等大多数出版商都有）；OA 期刊可直接访问
2. **PDF（回退）**：OA PDF 链接（Unpaywall / Semantic Scholar）

**为什么优先 EPUB/HTML：** 这些格式保留语义结构（标题层级、脚注），后续 `/process-reference` 处理时无需清洗和标题修复，节省约 70% 的 token 消耗。

**现实说明：** Harvard UP、Oxford UP、Cambridge UP 等主流学术出版社的专著，Z-Library 通常只收录 PDF 而无 EPUB；HTML 版本也均在付费墙后。遇到此类情况时，应在下载指引中**直接标注「无可用 EPUB/HTML，保留现有 PDF」**，不必让用户反复搜索。

#### 5.2 生成下载指引

将所有需要下载的文献整理成表格，展示给用户：

> 请在浏览器中按以下信息下载文献，下载后将文件存入 `sources/` 目录（文件名随意，AI 会在下一步帮你重命名）：
>
> | # | 文献 | 建议格式 | 下载链接 / 搜索建议 |
> |---|------|---------|-------------------|
> | 1 | ... | EPUB | [链接](...) |
> | 2 | ... | PDF | Z-Library 搜索："{标题}" |
>
> 下载完成后，请告诉我每个文件下载到 `sources/` 的实际文件名（或直接说"都下好了"，我会扫描目录）。

**如果某文献无法找到免费链接：**
- 标注 `🔗 需付费/登录`，提供最佳 URL（如 Z-Library 搜索链接、出版商页面）
- 建议获取途径：学校 VPN 访问数据库、图书馆电子资源、馆际互借

#### 5.3 等待用户确认下载完成

**必须等用户确认后才进入 5.4。**

当用户告知文件已下载（或提供文件名）后，读取 `sources/` 目录扫描新增文件：
```
ls sources/
```

#### 5.4 重命名文件

按以下命名规则将用户下载的文件重命名：

**命名格式：** `完整书名-作者/译者/编者/注者.{epub|html|pdf}`

**规则：**
- **命名语言服从原语言**：中文书用中文，英文书用英文，不强制转拼音
- 书名取完整标题；若含副标题且文件名超过 80 字符，可省略副标题
- 作者/译者等角色之间用空格分隔；译者、编者、注者在姓名后标注角色，如 `李秋零（译）`、`张荣 李秋零（译注）`
- 文件名中避免以下特殊字符：`/ \ : * ? " < > |`（冒号用全角 `：` 代替）

**示例：**
- `Force and Freedom-Arthur Ripstein.epub`
- `Kant's Doctrine of Right-B. Sharon Byrd Joachim Hruschka.pdf`
- `道德形而上学-康德 张荣 李秋零（译注）.epub`
- `道德形而上学的奠基-康德 李秋零（译）.pdf`
- `法、自由与强制力-吴彦.epub`
- `道德与法权的关系-叶会成.pdf`

执行重命名：
```bash
mv "sources/{原文件名}" "sources/{新文件名}"
```

#### 5.5 更新追踪索引

在 `sources/index.md` 的表格中追加或更新记录：

| 文献 | 文件名 | 年代 | 来源 | 格式 | 已下载 | 已处理 |
|------|--------|------|------|------|--------|--------|

**字段说明：**
- `文献`：作者、书/文名（简写即可）
- `文件名`：重命名后的文件名（含扩展名）
- `年代`：出版年份（4 位数字）
- `来源`：下载来源，如 `Z-Library`、`OA PDF`、`知网`、`作者主页`、`手动`
- `格式`：`EPUB` / `PDF` / `HTML` / `DOC`
- `已下载`：`✅` / `❌ 待下载`
- `已处理`：`✅` / `否`（是否已 `/process-reference` 入库）

### Step 6: 结果报告

向用户展示结果汇总：

**已完成重命名的文献：** 列出新文件名和存储位置。

**待用户手动下载的文献（付费/需登录）：**
- 提供找到的最佳 URL
- 建议获取途径

**未找到的文献：** 确认文献信息是否准确，建议替代版本或相关文献。

**后续步骤提醒：**
> 文件已整理到 `sources/` 目录。要让 AI 能在写作时引用这些文献：
> 1. 将文件（EPUB/HTML/MD）放入 `inbox/pending/` 目录
> 2. 运行 `/process-reference` 进行切分和索引
> 3. **EPUB 和 HTML 文件可直接处理**，无需外部转换！
> 4. PDF 文件仍需先用 MinerU 转为 MD，或优先查找 EPUB/HTML 版本

如果用户希望保存推荐列表，写入 `research/` 目录。

---

## 注意事项

- 推荐的文献必须是真实存在的，不可编造
- 如果无法确认某文献是否真实存在，标注 `[待核实]`
- 优先推荐 CSSCI 来源期刊的论文和权威出版社的专著
- 对于康德原著，注明推荐的中文译本版本
- 绝不尝试绕过付费墙或访问限制
- 不读取或解析下载的 PDF 内容
- 优先查找开放获取版本，即使存在付费的正式出版版本
- API 调用注意速率限制：Semantic Scholar 每 5 分钟 100 次，避免短时间内大量请求
