# thesis-writing-assistant

法学毕业论文写作 AI 助手 — Claude Code Plugin Marketplace

## 安装

在 Claude Code `~/.claude/settings.json` 中添加：

```json
{
  "extraKnownMarketplaces": {
    "thesis-writing-assistant": {
      "source": {
        "source": "git",
        "url": "https://github.com/henzxu5-rgb/thesis-writing-assistant.git"
      }
    }
  },
  "enabledPlugins": {
    "thesis-writing-assistant@thesis-writing-assistant": true
  }
}
```

然后重启 Claude Code，在论文工作目录下启动新会话即可。

## 工作目录结构

在你的论文工作目录下需要准备以下目录：

```
你的论文目录/
├── library/
│   └── index.md          # 自动生成，文献索引
├── inbox/                # 文献入口
│   ├── pending/          # 将原始文献 MD 放在这里
│   └── processed/        # 处理完成后自动移入
├── thesis/               # 论文输出目录
└── research/             # 个人研究笔记（可选）
```

## 功能

| Skill | 功能 | 触发方式 |
|-------|------|----------|
| **process-reference** | 自动切分参考文献、生成描述索引 | `/process-reference` |
| **collect-references** | 搜索和推荐学术文献 | `/collect-references` |
| **thesis-outline** | 制定和调整论文大纲 | `/thesis-outline` |
| **write-chapter** | 撰写论文章节 | `/write-chapter` |
| **format-check** | 格式校对和引用检查 | `/format-check` |

## 核心机制

文件系统版 RAG：将参考文献自动切分成 500-1500 字的小块，每块生成一句描述，汇总到 `library/index.md`。写作和讨论时 AI 读取索引，按描述判断相关性，只读取需要的小块。
