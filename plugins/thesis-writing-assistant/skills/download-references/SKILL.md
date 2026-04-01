---
name: download-references
description: >
  搜索并下载学术参考文献原文，支持直接下载和浏览器自动下载两种模式。
  直接下载模式：通过 Google Scholar、PhilPapers、CORE 等平台获取开放获取 PDF。
  浏览器模式（--browser）：通过 Chrome 自动操作用户已登录的平台（Z-Library、LibGen、
  Sci-Hub、知网、JSTOR 等），处理需要登录的资源。当用户说「下载文献」「找原文」
  「下载论文」「download references」「获取全文」「下载PDF」「帮我找到这篇论文」
  「把文献下载下来」，或用户希望获取 collect-references 推荐的文献原文时触发。
argument-hint: "[文献标题或引用信息] [--from scholar|cnki|zlib|auto] [--list] [--browser]"
allowed-tools: [Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, Bash, mcp__Claude_in_Chrome__computer, mcp__Claude_in_Chrome__find, mcp__Claude_in_Chrome__form_input, mcp__Claude_in_Chrome__get_page_text, mcp__Claude_in_Chrome__navigate, mcp__Claude_in_Chrome__read_page, mcp__Claude_in_Chrome__read_network_requests, mcp__Claude_in_Chrome__tabs_context_mcp, mcp__Claude_in_Chrome__tabs_create_mcp, mcp__Claude_in_Chrome__tabs_close_mcp, mcp__Claude_in_Chrome__javascript_tool]
---

# 文献搜索与下载

自动搜索学术文献的可下载版本，通过直接下载或浏览器自动化操作获取 PDF 等原始文件，存入 `sources/` 目录。

## 核心原则

- **合法使用用户账号**：通过浏览器操作时，利用的是用户自己已登录的账号和机构权限，属于合法使用
- **不自动读取 sources/**：下载的文件仅存储，不纳入 AI 的文献检索流程
- **诚实报告**：如实汇报每篇文献的下载结果，不伪造下载状态
- **用户确认优先**：首次使用浏览器模式时，向用户确认已登录相关平台

---

## 下载模式

本技能支持两种下载模式，可组合使用：

### 模式 A：直接下载（默认）
通过 WebSearch + curl 下载开放获取的文献。适用于免费 PDF。

### 模式 B：浏览器自动下载
通过 Chrome 浏览器自动操作，在用户已登录的数据库/平台中搜索和下载文献。适用于需要登录或付费的资源（用户有合法访问权限）。

**触发条件：**
- 用户使用 `--browser` 参数
- 模式 A 无法下载时自动提示切换
- 用户主动要求通过浏览器下载

---

## 工作流程

### Step 1: 确定目标文献

解析用户的下载请求：

- **用户指定文献**：直接使用用户提供的标题、作者、引用信息
- **`--list` 模式**：读取 `research/` 目录下 collect-references 保存的推荐列表，提取其中的文献条目
- **交互确认**：如果信息不足以精确定位文献，询问用户补充

**去重检查**：读取 `sources/index.md`，跳过已下载的文献（除非用户明确要求重新下载）。

### Step 2: 搜索下载源（模式 A — 直接下载）

对每篇目标文献，使用 WebSearch 搜索可下载版本。

**搜索策略（按优先级）：**

**外文文献：**
1. Google Scholar — 搜索标题 + 作者，寻找 [PDF] 标记的直接链接
2. ResearchGate / Academia.edu — 作者自行上传的全文
3. PhilPapers — 哲学类文献专用（康德研究重点来源）
4. 大学机构仓库 — 开放获取的学位论文和预印本
5. CORE / Unpaywall — 开放获取聚合平台
6. arXiv / PhilSci-Archive — 预印本
7. 出版商网站 — 可能需要付费

**中文文献：**
1. 百度学术 — 搜索标题，寻找免费下载链接
2. 知网开放获取 — CNKI 部分免费论文
3. 万方数据 — 部分免费获取
4. 国家哲学社会科学文献中心 — 免费学术资源
5. 各大学机构仓库 — 学位论文

**搜索关键词构造：**
- 优先使用 DOI（如有）：直接搜索 `doi:10.xxxx/xxxxx filetype:pdf`
- 使用精确标题搜索：`"论文完整标题" filetype:pdf`
- 补充作者名：`作者姓名 "论文标题" pdf`
- 如果 collect-references 提供了下载线索（DOI/URL），优先使用

找到直接下载链接后，使用 Bash `curl -L -o` 下载。

### Step 3: 浏览器自动下载（模式 B）

当模式 A 无法获取文献，且用户同意使用浏览器模式时，执行以下流程：

#### 3.0 初始化浏览器

1. 调用 `tabs_context_mcp`（设置 `createIfEmpty: true`）获取当前标签页组
2. 如需新标签页，调用 `tabs_create_mcp`
3. 首次使用时提醒用户确认已在 Chrome 中登录相关平台

#### 3.1 选择平台并导航

根据文献类型和用户指定的 `--from` 参数，按以下优先级选择平台：

**电子书/专著类：**
1. **Z-Library** — 搜索书名 + 作者，下载 PDF/EPUB
2. **Library Genesis (LibGen)** — 搜索书名，下载 PDF
3. **Anna's Archive** — 综合聚合搜索
4. **Open Library (Internet Archive)** — 公版书和可借阅电子书

**外文期刊论文：**
1. **Sci-Hub** — 通过 DOI 或标题直接获取
2. **Z-Library** — 也收录大量期刊论文
3. **Google Scholar** — 浏览器中可能触发机构访问
4. **用户已登录的数据库** — JSTOR、Cambridge Core、Springer 等

**中文文献：**
1. **知网 (CNKI)** — 需学校 VPN/已登录
2. **万方数据** — 需登录
3. **超星/读秀** — 电子书
4. **微信读书** — 部分学术书可用
5. **全国图书馆参考咨询联盟** — 文献传递

#### 3.2 搜索文献

在目标平台上执行搜索：

1. 用 `navigate` 打开平台首页
2. 用 `find` 或 `read_page` 定位搜索框
3. 用 `form_input` 输入搜索关键词（标题/作者/DOI）
4. 用 `computer`（`left_click`）点击搜索按钮
5. 等待搜索结果加载（`computer` 的 `wait` + `screenshot`）
6. 用 `read_page` 或 `get_page_text` 解析搜索结果
7. 识别最匹配的结果条目

#### 3.3 下载文献

在搜索结果页面或详情页面：

1. 用 `find` 定位下载按钮/链接（如 "Download PDF"、"下载"、"获取全文"）
2. 用 `computer`（`left_click`）点击下载
3. 如果需要选择格式，优先选择 PDF
4. 用 `computer`（`wait`）等待下载完成（3-5 秒）
5. 下载的文件会进入系统默认下载目录

#### 3.4 移动文件到 sources/

下载完成后，将文件从系统下载目录移到项目的 `sources/`：

```bash
# 查找最新下载的文件
ls -t ~/Downloads/*.pdf | head -1

# 按命名规则重命名并移动
mv ~/Downloads/<原文件名>.pdf "sources/<规范文件名>.pdf"
```

#### 3.5 处理异常情况

- **需要验证码/人机验证**：截图展示给用户，请用户手动完成验证后继续
- **页面加载失败**：重试一次，仍然失败则跳过并记录
- **下载链接不可用**：尝试平台优先级中的下一个平台
- **文件格式非 PDF**：接受 EPUB/DJVU 等格式，在 index.md 中注明

### Step 4: 验证文件

对每个下载的文件进行验证：

```bash
file "sources/<文件名>"
ls -la "sources/<文件名>"
```

- `PDF document`：下载成功
- `HTML document` / `ASCII text`：可能下载了登录页面，删除并标记失败
- 文件大小为 0：删除并标记失败
- 文件大小合理范围：学术 PDF 通常 100KB - 50MB

### Step 5: 更新追踪索引

在 `sources/index.md` 的表格中追加记录：

| 文献 | 文件名 | 状态 | 下载日期 | 来源 | 已处理 |
|------|--------|------|----------|------|--------|
| 完整引用（GB/T 7714） | 文件名.pdf | ✅ 已下载 | 2026-04-02 | 来源平台 | 否 |

**状态值：**
- `✅ 已下载` — 文件已成功保存到 sources/
- `❌ 需获取` — 所有自动途径均失败，需用户手动获取
- `⏳ 待重试` — 临时失败（如网络问题），可稍后重试

### Step 6: 结果报告

向用户展示下载结果汇总：

**成功下载的文献：**
列出文件名、页数/大小、存储位置。

**未能下载的文献：**
- 说明失败原因（付费、未找到、网络问题等）
- 提供已知的最佳获取途径
- 如果尚未使用浏览器模式，建议切换到 `--browser` 模式重试

**后续步骤提醒：**
> 下载的文件存放在 `sources/` 目录。要让 AI 能使用这些文献：
> 1. 将 PDF 转换为 Markdown 格式
> 2. 放入 `inbox/` 目录
> 3. 运行 `/process-reference` 进行切分和索引

---

## 文件命名规则

- 英文：`作者姓-年份-简短标题.pdf`（如 `ripstein-2009-force-freedom.pdf`）
- 中文：`作者拼音-年份-简短标题.pdf`（如 `deng-xiaomang-2004-chunli-pipan.pdf`）
- 简短标题取 2-4 个关键词，用连字符连接，全小写
- 避免特殊字符，只使用字母、数字和连字符
- 非 PDF 格式保留原扩展名（.epub、.djvu 等）

## 注意事项

- 浏览器模式利用的是用户自己的合法账号权限
- 同一平台连续操作间隔 2-3 秒，避免触发反爬机制
- 遇到验证码时暂停并请用户协助
- 不读取或解析下载的文件内容 — 此目录不属于 AI 的文献检索范围
- 如果单个文件超过 50MB，先告知用户再下载
- 下载完成后及时关闭不再需要的浏览器标签页（`tabs_close_mcp`）
