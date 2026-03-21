# `miloya-codebase` 的 OpenCode 接入骨架

这个目录是一份可直接复制的 OpenCode 最小接入骨架，用来把
`miloya-codebase` 接到其他项目里。

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

## 可选项

如果你的 OpenCode 环境启用了 skill 权限控制，再额外在项目的
`opencode.json` 中显式允许 `miloya-codebase` 即可；这不是最小骨架的必需项。
