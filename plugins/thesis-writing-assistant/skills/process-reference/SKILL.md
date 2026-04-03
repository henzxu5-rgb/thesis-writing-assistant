---
name: process-reference
description: >
  处理和切分参考文献。当用户说「处理文献」「切分文献」「导入文献」
  「process reference」「处理这本书」「处理这篇论文」「把这个放入文献库」
  「index this」，或用户提到已将文件放入 inbox/pending/ 目录时触发。
  当用户上传或提供一篇完整的学术文献（书籍、论文）并希望 AI 能够
  理解和记忆其内容时，也应触发此技能。
argument-hint: "[文献文件名或路径] [--name 文献简称]"
---

# 文献处理与切分

将用户提供的完整文献（整本书或论文的 MD 文件）自动切分成小块，
为每块生成描述摘要，并更新全局索引，以便后续按需检索。

## 工作流程

### Step 1: 定位原始文献

扫描 `inbox/pending/` 目录，列出所有待处理的 MD 文件。
如果用户指定了具体文件名，直接使用该文件。

如果 `inbox/pending/` 为空，检查 `library/` 根目录是否有待处理的 MD 文件（用户有时会直接放在 library/ 而非 inbox/pending/），如果发现则正常处理，并提示用户下次放入 inbox/pending/。

如果以上均为空且用户提供了文件路径，从该路径读取。

### Step 2: 分析文献结构（不读全文）

用以下三个轻量操作完成分析，**禁止全量读取原始文献**：

1. **读引用信息**：`Read` 文件前 20 行，获取作者、书名、出版信息及文献类型（M/J/D 等）
2. **估算规模**：`Bash: wc -l <文件路径>`，得到总行数
3. **检测是否平铺型**：并行运行三条 Grep（只统计行数，不返回内容）：
   - `Grep ^# `（所有标题总数）
   - `Grep ^## `（二级标题数）
   - `Grep ^### `（三级标题数）
   若 `##` 与 `###` 之和少于全部 `#` 标题数的 10%，判定为"平铺型文件"，需执行 Step 2.5。

向用户简要报告（文献名、总行数、是否平铺型、预计块数），确认后继续。

### Step 2.5: 噪音清洗与标题层级修复（仅平铺型文件）

分两个阶段处理：

#### 阶段一：通用噪音清洗

```
python3 ${CLAUDE_PLUGIN_ROOT}/tools/clean-mineru.py <原文件路径> library/<name>/source-cleaned.md
```

输出 `source-cleaned.md`。标题层级保持原样，由阶段二处理。

#### 阶段二：Per-book 标题层级修复

每本书的标题结构不同，使用 per-book 脚本处理。

**若 `library/<name>/fix-headings.py` 已存在**，直接运行：
```
python3 library/<name>/fix-headings.py library/<name>/source-cleaned.md library/<name>/source-fixed.md
```

**若不存在**，AI 按以下目录阅读协议分析文献结构，然后编写 `fix-headings.py`：

> **PDF 源文件定位**：优先检查 `inbox/pending/` 或 `library/<name>/` 目录下是否存在同名 PDF 文件。
> 若不存在，询问用户提供 PDF 路径。若用户无法提供 PDF，退回纯 MD 模式（仅执行下方 A 部分）。

> **目录阅读协议**（以目录为主要信息源，不读正文）：
>
> **A. 标题清单 + 目录页**：
> 1. **提取标题清单**：用 Grep 搜索所有 `^#` 行及行号
> 2. **读取 MD 目录页**：读取文件开头 300 行，定位目录节，理解目录的章节名称与层次
>
> **B. PDF 目录页**（1-2 页，不超过 2 页）：
> 3. **读 PDF 目录页**：通过视觉缩进/编号直接确认哪些标题属于 `##`、`###`、`####`
> 4. **确认脚注格式**：目录页附近通常有脚注样例，确认脚注编号风格（上标、方括号、圆括号、数字+空格等）
>
> **C. 总量控制**：MD ≤ 300 行（仅目录部分）+ PDF ≤ 2 页

分析完成后，编写 `library/<name>/fix-headings.py`，脚本只需包含：
- `H2_TITLES`、`H3_TITLES`、`H4_TITLES` 三个集合，从目录直接抄写对应层级的标题
- 需要删除的行（如 "This page intentionally left blank"、出版商信息伪标题）
- 少量 OCR 修复（如字母间距、`I`→`1` 等字体混淆）
- **跨行标题合并**：OCR 导出的书籍标题常被拆成多行（章号行、副标题行各自成一个 `#`），且行间可能夹有空行或页码行（如 `[446]`）。合并逻辑的循环**必须 skip 空行和页码行继续查找**，不能遇空行即 break；直到遇到非 `#` 标题的实质内容行才停止收集。
- **脚注段落标记**：检测脚注段落（通常为空行后以数字编号开头的段落），在其前插入 `<!-- footnote N -->` 标记行。**注意短引用脚注**：Ibid.、See、Cf.、Id. 等常不足 5 词，需单独使用更宽松正则（如 `^\d{1,3}\s+(?:Ibid\.|See\s|Cf\.\s|Id\.,)`，无词数下限）。
- **脚注阻断段落合并**：标记脚注后，运行一遍合并传递（`merge_around_footnotes`）。检测模式：line_A 不以句末标点结尾 → 空行 → `<!-- footnote -->` + 脚注内容 → 空行 → line_B 以小写字母或 `(` 开头，将 line_A 与 line_B 合并，脚注标记保留原位。

体内子节标记（`(1)(2)(3)`、`(a)(b)(c)` 等）在 Step 3.5 草案审查时作为候选拆分点使用，不在此处转为标题。

**验证**：运行脚本后只需确认：
- `##` 数量 ≈ 目录中章/部数（误差 ±2 以内）
- `###` 数量 ≈ 目录中节数
- 若书有脚注，脚注标记数 > 0

通常不需要调试循环。修复完成后告知用户 source-fixed.md 已生成，可打开检查；如有误判，用户可手动调整后告知继续。

### Step 3.5: 生成切分草案并审查

```
python3 ${CLAUDE_PLUGIN_ROOT}/tools/plan-chunks.py library/<name>/source-fixed.md
```

脚本输出 `library/<name>/draft-chunks.md`。读取草案后审查：
- `⚠️` 标注的大块：判断是否需要拆，选择候选拆分点或指定其他位置；如果书中该节有体内子节标记（`(1)(2)(3)`、`(a)(b)(c)` 等），可将其行号作为拆分点
- `↑` 标注的小块：判断与哪个相邻块合并更合逻辑（同章优先）
- 根据标题文字推断论证连贯性，判断相邻小块是否应合并

**⚠️ 超大块处理协议**（字数 > FORCE）：

plan-chunks.py 已给出 N 个均匀分布的候选拆分点（N ≈ 块字数 / target_max）。处理步骤：

1. **确认候选数量足够**：候选点数应 ≈ 需拆次数。若明显不足（段落空行稀疏），则参考体内子节标记（`(1)(2)(3)`、`(a)(b)(c)`）补充拆分点。
2. **抽样读取，不线性读全文**：对每个候选行，**并行**执行 `Read source-fixed.md offset=<候选行-3> limit=8`，读候选点上下各 3-4 行，判断是否为语义边界（段落结束 vs. 句中断开）。
3. **一次确认所有拆分点**：基于抽样结果一次性形成完整拆分方案，再修改 draft-chunks.md。

> **禁止**：不得从头线性读取超大块的完整正文。单块 Read 调用数 ≤ 候选点数，且每次 `limit ≤ 10`。

**草案审查强制要求**：
- `↑ 不足字数` 的**每一个** chunk 都必须明确处理——合并入相邻 chunk，或保留并记录原因
- **禁止**存在未处理的不足字数 warning 的 chunk 进入 Step 4

调整后形成最终切分方案，再执行 Step 4。

### Step 4: 执行切分并保存

1. 为该文献创建目录：`library/<文献简称>/`
   - 文献简称使用英文 kebab-case，如 `kant-metaphysics-morals`、`zhang-rechtstaat-2020`
   - 如果用户通过 `--name` 指定了简称，使用用户指定的

2. 生成 `meta.md`：
```markdown
# <文献标题>

## 引用信息
<GB/T 7714 格式的完整引用>

## 全书/全文概述（200-300字）
<概括文献的核心论点、研究方法、主要结论>

## 与论文的关联
<简述该文献对论文写作的价值和可能的用途>

## 小块清单
共 N 个小块，详见 library/<name>/index.md
```

3. 运行插件内置脚本自动写出所有 chunk 文件：
   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/tools/write-chunks.py \
     library/<name>/source-fixed.md \
     library/<name>/draft-chunks.md \
     library/<name>/ \
     --label "<文献标题>"
   ```

### Step 5: 为每块生成描述（子 agent 模式）

使用 **Agent 工具**委托子 agent（`model: "haiku"`）生成描述，避免主上下文积压 chunk 内容。

**分批**：单个子 agent 最多处理 35 个 chunk；多个子 agent 可**并行启动**。

| 总 chunk 数 | 子 agent 数 |
|------------|------------|
| ≤ 35 | 1 |
| 36-70 | 2（前半 + 后半）|
| 71-105 | 3（均分）|

**调用方式**：向每个子 agent 传入如下任务说明（替换编号范围和批次编号 N）：

> 读取 `library/<name>/` 目录下的 chunk-XX.md 到 chunk-YY.md（**全量读取**每个 chunk 的完整内容）。
> 对每个 chunk 生成：
> 1. **主描述**（一行）：节号范围 + 至少1个论证骨架动词 + 2-4个关键术语（附原文术语，如德文原词）
>    - 论证骨架动词示例："演绎/推导出/证明……"、"区分……与……"、"论证……根据"、"拒绝……而主张……"
> 2. **子话题列表**（2-4条）：每条 ≤ 20字，标识 chunk 内的独立论证步骤或论题转换。
>    子话题必须包含动词，能回答"这个 chunk 论证了什么"——而不仅仅是话题词。
> 3. **Tags 行**：3-6 个关键术语，用逗号分隔。注意识别并保留德文、拉丁文等外文关键术语原词（如 Recht、Zwangsbefugnis、kategorischer Imperativ）。
>
> 好的主描述示例："法权论导论·§2——区分法权（Recht）概念与道德概念；论证外在强制与普遍自由法则相一致的可能性根据"
> 好的子话题示例：
>   - "法权普遍原则与定言命令的区别"（含"区别"动词）
>   - "分析性判断为何仍需演绎"（含"需演绎"动词）
>   - "自由概念的实践实在性如何证明"（含"证明"动词）
> 差的描述/子话题（禁止）：
>   - "第一章的内容"（无节号无动词）
>   - "关于国际法权的讨论"（纯主题词，无动词）
>   - "自由概念"、"第一命令"（词组，不是论点）
>   - "第一部分"（纯位置信息）
>   - "一些论证"（无信息量）
>
> 生成完毕后，将所有描述**直接写入文件** `library/<name>/index-part-N.md`，格式如下（无需任何前缀或说明文字）：
> chunk-XX.md: <主描述>
>   - <子话题1>
>   - <子话题2>
>   Tags: term1, term2, Recht, ...
> chunk-XX+1.md: <主描述>
>   ...
>
> 写入完成后，**只向主上下文回复**："已写入 index-part-N.md，共处理 chunk-XX~YY"。不要将描述内容返回给主上下文。

**主上下文**收到所有子 agent 的状态确认后：
1. 运行 `cat library/<name>/index-part-*.md` 确认所有批次文件已生成
2. 如某批次有遗漏，通过 `SendMessage` 继续该 agent 补全
3. 将所有 index-part 文件的内容合并，交由 Step 6.1 写入最终 index.md

### Step 6: 更新两级索引

**6.1 新建/更新局部索引** `library/<name>/index.md`

创建该文献的局部索引，按 Part/Chapter（篇/章）分组，包含所有 chunk 的描述、子话题和关键术语标签：

```markdown
# <文献标题>局部索引

## 引用
<GB/T 7714 格式的简要引用>

## 块描述

共 N 个小块。

### <Part/篇/章标题> (chunk-01 ~ chunk-NN)
<一句话概括该部分主题>

- **chunk-01.md**: <主描述>
  - <子话题1>
  - <子话题2>
  Tags: term1, term2, Recht, ...
- **chunk-02.md**: <主描述>
  - <子话题1>
  - <子话题2>
  - <子话题3>
  Tags: term1, term2, ...

### <下一个 Part/篇/章标题> (chunk-NN ~ chunk-MM)
<一句话概括>

- ...
```

分组依据：根据 chunk 标题中的 Part/Chapter/篇/章 信息推断。若文献无明显分部结构（如单篇论文），则不分组，直接平铺列出。

**6.2 更新全局索引** `library/index.md`

在 `library/index.md` 末尾追加：

```markdown
## <文献标题>（`<目录名>/`）

[文献类型标记] <简要引用>。<全文一句话概述>。
共 N 个小块 → 详见 `<目录名>/index.md`
```

文献类型标记：`[M]` 专著、`[J]` 期刊论文、`[D]` 学位论文、`[C]` 会议论文、`[N]` 报纸

### Step 7: 清理

将处理完的原始文件从 `inbox/pending/` 移到 `inbox/processed/`。
如果原文件在 `library/` 根目录，同样移动到 `inbox/processed/`。

向用户报告处理结果：文献名称、切分块数、索引已更新。

## 批量处理

如果 `inbox/pending/` 中有多个文件，**先向用户说明处理计划，询问确认后再执行**，不要默默逐个处理。

### 告知用户的信息
列出检测到的所有文件及其大致规模（行数），说明预计的处理方式：

> 检测到 inbox/pending/ 中有 N 个待处理文件：
> 1. `文件名A.md`（约 X 行）
> 2. `文件名B.md`（约 X 行）
>
> 建议按以下流水线批量处理，以缩短总耗时：
> - **阶段一（可并行）**：对所有文件同时运行 clean-mineru.py 清洗脚本
> - **阶段二（需逐个）**：为每本书分析结构、编写 fix-headings.py（需要 AI 判断，无法并行）
> - **阶段三（可并行）**：所有书的 plan-chunks + write-chunks + 描述生成同时运行
>
> 是否按此顺序开始？还是优先处理某一本？

### 阶段一：并行清洗

获得用户确认后，对所有文件**同时**（在同一条消息中）发出 Bash 调用，运行 clean-mineru.py：

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/tools/clean-mineru.py inbox/pending/文件A.md library/name-a/source-cleaned.md
python3 ${CLAUDE_PLUGIN_ROOT}/tools/clean-mineru.py inbox/pending/文件B.md library/name-b/source-cleaned.md
```

### 阶段二：逐本分析结构、生成 fix-headings.py

每本书的目录结构不同，必须逐本进行（AI 读目录 → 编写简化脚本 → 运行 → 验证），**通常无需调试循环**。完成一本后向用户简报，再处理下一本。

### 阶段三：并行切分与描述生成

所有书的 fix-headings.py 都完成后（或每本完成后立即加入），对已就绪的书**同时**运行切分和描述生成：

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/tools/plan-chunks.py library/name-a/source-fixed.md
python3 ${CLAUDE_PLUGIN_ROOT}/tools/plan-chunks.py library/name-b/source-fixed.md
```

描述生成（Step 5）的子 agent 也可以跨书并行启动。

## 特殊情况

- **用户已按章分好多个 MD**：视为同一文献的多个部分，放入同一个 `library/<name>/` 目录，chunk 编号连续
- **文献缺少引用信息**：询问用户补充，或标注 `[引用信息待补充]`
- **文献内容过短**（不足 400 字）：不切分，整体作为一个 chunk，仍然生成 meta.md 和索引条目
- **用户手动修改了 source-fixed.md**：从修改后的文件重新执行 Step 3 起的流程
