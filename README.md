# thesis-writing-assistant

法学毕业论文写作 AI 助手 — Claude Code Plugin

## 功能

一套覆盖论文写作全流程的 Claude Code 插件，包含 5 个 skill：

| Skill | 功能 | 触发方式 |
|-------|------|----------|
| **process-reference** | 自动切分参考文献、生成描述索引 | `/process-reference` |
| **collect-references** | 搜索和推荐学术文献 | `/collect-references` |
| **thesis-outline** | 制定和调整论文大纲 | `/thesis-outline` |
| **write-chapter** | 撰写论文章节 | `/write-chapter` |
| **format-check** | 格式校对和引用检查 | `/format-check` |

## 核心机制：文献自动切分与按需检索

解决 AI 无法一次性读取大量参考文献的问题：

```
用户将完整文献放入 inbox/
        ↓
/process-reference 自动切分成小块（每块 500-1500 字）
        ↓
每块生成一句描述，汇总到 library/index.md
        ↓
写作或讨论时，AI 读取索引 → 按描述选择相关小块 → 只读取需要的部分
```

本质上是一个**文件系统版 RAG**：用 Claude 的判断力替代向量搜索，用文件目录替代向量数据库。

## 安装

### 方式一：通过 GitHub 安装（推荐）

在 Claude Code 设置中添加本仓库作为 plugin 源。

### 方式二：本地安装

将本仓库克隆到本地，在 Claude Code 的 `settings.json` 中注册：

```json
{
  "enabledPlugins": {
    "thesis-writing-assistant@local": true
  }
}
```

## 使用流程

### 1. 导入参考文献
将文献的 MD 文件放入 `inbox/` 目录，然后：
```
/process-reference
```

### 2. 制定大纲
```
/thesis-outline new
```

### 3. 撰写章节
```
/write-chapter 第一章
```

### 4. 格式校对
```
/format-check chapter1.md
```

## 目录结构

```
├── skills/                  # 5 个 skill 定义
├── library/                 # 文献库（切分后的小块 + 索引）
│   ├── index.md            # 全局索引
│   └── <文献名>/           # 每篇文献一个目录
├── inbox/                   # 放入原始文献的入口
├── thesis/                  # 论文输出
└── research/                # 个人研究笔记
```

## 适用场景

本插件为法学毕业论文设计，但核心的文献切分-索引-检索机制适用于任何需要大量参考文献的学术写作场景。
