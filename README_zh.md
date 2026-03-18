# miloya-codebase

**AI 模型切换的 Context Engine** — 生成项目快照，让新模型无需重新扫描即可快速理解代码库。

`miloya-codebase` 生成可复用的 JSON 快照，新模型可以直接理解代码库而无需从头扫描。

## 输出内容

快照保存在 `repo/progress/miloya-codebase.json`，包含：
- `summary`：项目类型、README 描述、主要语言、重要路径
- `workspace`：根清单文件、monorepo 布局
- `contextHints`：建议阅读顺序和高信号区域
- `fileTree`：规范化的项目树，根目录文件在 `./` 下
- `modules`：顶层模块职责摘要
- `dependencies`：根清单依赖
- `importantFiles`：按重要性排序的高价值文件列表
- `representativeSnippets`：来自重要文件的锚点代码片段
- `apiRoutes`、`dataModels`、`keyFunctions`、`architecture`
- `sourceFingerprint`、`freshness`、`git`

## 为什么比普通文件树更好

一个好的 Context Engine 应该回答：
- 这是什么类型的项目？
- 模型应该从哪开始读？
- 哪些文件承载最多的架构信号？
- 快照是否还是新鲜的？

这个工具现在直接瞄准这些问题，而不是仅仅转储文件夹和符号。

## 使用方式

```bash
python miloya-codebase/scripts/generate.py <项目路径>
python miloya-codebase/scripts/generate.py <项目路径> --force
```

Skill 命令：

```text
/miloya-codebase
/miloya-codebase refresh
/miloya-codebase read
```

## 核心行为

- **自引用排除**：`repo/progress/` 被明确排除，防止快照包含自身
- **注释感知解析**：提取路由和模型前先移除 `//`、`/* */`、`#` 注释，避免误匹配（如注释中的 `@app.get('/path')`）
- **智能缓存**：比较所有源文件的 SHA256 指纹；若无变化则跳过重新生成
- **新鲜度检测**：`freshness.stale` 标志告诉使用者快照是否最新
- **路径规范化**：所有路径使用 POSIX 风格正斜杠，跨平台可移植
- **文件大小限制**：跳过超过 512KB 的文件，避免快照膨胀
- **Monorepo 检测**：识别 `pnpm-workspace.yaml`、`turbo.json`、`nx.json`、`apps/`、`packages/` 布局

## 文件评分

`importantFiles` 通过多信号评分系统排序：

| 信号 | 分数影响 | 原因 |
|------|----------|------|
| 入口文件 (index.ts, main.ts, App.tsx) | +110 | 主要应用入口 |
| 根/配置文件 | +90 | 重要的项目元数据 |
| 有 API 路由 | +60 + 5/路由 | API 表面 |
| 有数据模型 | +45 + 4/模型 | 领域实体 |
| 有导出 | +30 + 2/导出 | 公共 API |
| 测试文件 | -40 | 上下文优先级较低 |

## 架构推断

通过检查所有目录层级来检测架构风格：

| 模式 | 架构 |
|------|------|
| `controllers/` + `routes/` | MVC / 基于控制器 |
| `store/` 或 `state/` 或 `redux/` | Flux / 状态管理 |
| `services/` + `repositories/` | 分层 / 仓库模式 |
| `middleware/` | 中间件模式 |
| 其他 | 模块化 |

## 示例快照结构

```json
{
  "version": "2.0",
  "generatedAt": "2026-03-18T14:09:58+00:00",
  "projectPath": "D:/codes/example",
  "sourceFingerprint": "sha256...",
  "freshness": {
    "stale": false,
    "reason": "source fingerprint unchanged",
    "newestSourceMtime": "2026-03-18T14:09:36+00:00",
    "snapshotPath": "repo/progress/miloya-codebase.json"
  },
  "git": {
    "branch": "main",
    "commit": "abc123",
    "status": "clean"
  },
  "summary": {
    "name": "example",
    "type": "Backend Service",
    "description": "项目简短描述",
    "techStack": ["Express", "TypeScript"],
    "entryPoints": ["src/index.ts"],
    "totalFiles": 234,
    "totalLines": 12840,
    "dominantLanguages": [{"language": "TypeScript", "files": 180}],
    "importantPaths": ["package.json", "src/index.ts"]
  },
  "workspace": {
    "isMonorepo": false,
    "rootManifests": ["package.json"],
    "packages": []
  },
  "contextHints": {
    "readOrder": ["package.json", "src/index.ts"],
    "recommendedStart": "package.json",
    "highSignalAreas": ["src/", "src/routes/"],
    "monorepo": false
  },
  "importantFiles": [
    {
      "path": "src/index.ts",
      "role": "API surface",
      "language": "TypeScript",
      "lines": 150,
      "imports": ["express", "router"],
      "exports": ["app", "router"],
      "score": 152,
      "whyImportant": "entry point, API surface"
    }
  ],
  "representativeSnippets": [
    {
      "path": "src/index.ts",
      "reason": "route definition",
      "startLine": 1,
      "endLine": 12,
      "snippet": "import express from 'express'..."
    }
  ],
  "modules": {
    "src/": "Primary application source code; 200 files; routes: 15; models: 30",
    "src/routes/": "HTTP or application routing definitions; 15 files"
  },
  "apiRoutes": [],
  "dataModels": [],
  "keyFunctions": [],
  "architecture": "MVC / Controller-based"
}
```

## 开发

运行测试：

```bash
python -m unittest miloya-codebase.tests.test_generate
```

## 状态

当前实现针对实际上下文传递进行了优化：
- 修复了自引用和误报路由的正确性问题
- 为大项目导航提供更丰富的 schema
- 通过源指纹检测实现缓存新鲜度
- 用于新鲜度和 schema 输出的回归测试
