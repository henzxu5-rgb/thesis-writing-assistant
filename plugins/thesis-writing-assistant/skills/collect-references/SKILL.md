---
name: collect-references
description: >
  搜索和收集学术参考文献。当用户说「找文献」「收集参考资料」「文献综述」
  「找论文」「推荐著作」「参考书目」「collect references」「bibliography」
  「有哪些相关文献」「推荐阅读」，或讨论某个学术主题需要哪些文献支撑时触发。
argument-hint: "[主题或关键词] [--type monograph|paper|all]"
allowed-tools: [Read, Write, Edit, Glob, Grep, WebSearch, WebFetch]
---

# 文献搜集与推荐

帮助用户搜索、发现和整理与论文相关的高质量学术文献。

## 工作流程

### Step 1: 明确搜索范围

确认用户需要的文献类型和主题方向：
- 主题关键词（如"康德法权学说"、"德国法治国家历史"）
- 文献类型偏好：专著、期刊论文、译著、或全部
- 语言偏好：中文为主，是否需要外文文献

### Step 2: 搜索策略

利用 WebSearch 搜索学术资源，优先以下来源：
- 中国知网 (CNKI) / 万方数据 / 中国社会科学引文索引 (CSSCI)
- Google Scholar / JSTOR（外文文献）
- 各大学图书馆目录

读取 `${CLAUDE_PLUGIN_ROOT}/skills/collect-references/references/source-databases.md`
获取该论文主题的核心学者和关键词建议。

### Step 3: 整理推荐列表

为每条推荐的文献提供：
1. **完整引用信息**（GB/T 7714 格式）
2. **推荐理由**（2-3 句，说明与论文的关联）
3. **重要程度**：核心文献 / 重要参考 / 扩展阅读
4. **建议用于论文哪个部分**
5. **下载线索**：已知的 DOI、URL、或获取途径（供 `/download-references` 使用）

### Step 4: 检查文献库

读取 `library/index.md`，标注哪些推荐文献已在文献库中，
哪些需要用户获取后通过 `/process-reference` 导入。

### Step 5: 输出

将推荐列表展示给用户。如果用户希望保存，写入 `research/` 目录。

## 注意事项

- 推荐的文献必须是真实存在的，不可编造
- 如果无法确认某文献是否真实存在，标注 `[待核实]`
- 优先推荐 CSSCI 来源期刊的论文和权威出版社的专著
- 对于康德原著，注明推荐的中文译本版本
