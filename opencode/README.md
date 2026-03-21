# `miloya-codebase` 的 OpenCode 接入骨架

这个目录是一份可直接复制的 OpenCode 最小接入骨架，用来把
`miloya-codebase` 接到其他项目里。

这里的定位是纯 context engine 接入层：

- `miloya-codebase` 负责生成或复用项目快照，并提供 `files`、`snippets`、
  `flowAnchors`、`nextHops`、`searchScope` 等候选上下文材料。
- 宿主模型负责理解用户问题，并基于这些材料决定先读哪些文件、是否需要继续
  定点搜索。
- 它不是语义问答器，也不是通过反复重跑 `read` 来扩大搜索范围的工具。

## 目录结构

```text
opencode/
  .opencode/
    commands/
      miloya-codebase.md
      miloya-codebase-read.md
      miloya-codebase-report.md
    skills/
      miloya-codebase/
        README.md
```

## 使用方式

1. 把 `opencode/.opencode/` 整个复制到目标项目根目录。
2. 如果你希望 skill 跟项目一起分发，就把真实的 `miloya-codebase`
   skill 文件放到 `.opencode/skills/miloya-codebase/`。
3. 如果你已经全局安装了 `miloya-codebase`，可以删除本地占位目录
   `.opencode/skills/miloya-codebase/`，只保留命令文件即可。

## 可用命令

- `/miloya-codebase`
- `/miloya-codebase-read <问题>`
- `/miloya-codebase-report <问题>`

这些命令只是快捷入口，真正的能力来自 `miloya-codebase` skill 本体。

## 宿主行为约束

对 `read` 模式，推荐遵守下面的使用方式：

1. 先消费已有 payload 中的 `files`、`snippets`、`flowAnchors`、
   `nextHops`、`searchScope`。
2. 如果 payload 不足，直接在 `searchScope` 指示的范围内做定点 repo
   search，而不是再次运行 `miloya-codebase --read` 试图“扩大搜索范围”。
3. 不要通过切换 `--task`、重复调用 `--read`、或改写问题问法，来把
   `read` 当成语义检索扩展器使用。

`read` 的职责是返回候选上下文包，不是替宿主完成多轮搜索规划。

## 中文查询注意事项

如果问题里包含中文、日文或其他非 ASCII 字符，推荐让宿主优先通过
`--query-file` 或 `--query-stdin` 传递原始问题文本，不要先转成拼音、
英文近似词或随意拼装的 `\\uXXXX` 字符串。

只有在能够确保转义内容与原问题逐字一致时，才使用 `--query-escaped`。
否则很容易出现：

- 原始问题是 `WhatsApp 的接入是如何实现的？`
- 实际传给脚本的却变成 `WhatsAppisuojieruheshixiande`

这种情况不是 `miloya-codebase` 检索逻辑本身失效，而是查询在进入脚本之前就已被破坏。

## 可选项

如果你的 OpenCode 环境启用了 skill 权限控制，再额外在项目的
`opencode.json` 中显式允许 `miloya-codebase` 即可；这不是最小骨架的必需项。
