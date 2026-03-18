# miloya-codebase

`miloya-codebase` 是一个面向大型仓库的专业 Context Engine。

它会在项目内生成 `repo/progress/miloya-codebase.json` 快照，让新的模型、
新的 IDE 会话或其他工具无需重新全量扫描仓库，也能快速建立项目上下文。

它不是简单的文件树导出器。它的目标是回答模型交接时真正需要的问题：

- 这是什么类型的项目？
- 应该先读哪些文件？
- 哪些模块承载了最高价值的架构信号？
- 当前快照是否仍然足够新鲜，可以直接复用？

## 定位

很多仓库分析工具只给出文件树、符号列表或语言统计。这对于真实项目中的
模型切换和上下文交接并不够。

`miloya-codebase` 在结构扫描之上增加了一层“导航语义”：

- 项目摘要与技术栈识别
- workspace / monorepo 结构提示
- 高信号文件阅读顺序
- 代表性代码片段
- 快照新鲜度判断
- 基于内容指纹的缓存复用

目标是“高效上下文迁移”，而不是“编译器级绝对静态分析”。

## 安装

最小可运行结构：

```text
miloya-codebase/
  SKILL.md
  scripts/
    generate.py
```

推荐开发结构：

```text
miloya-codebase/
  SKILL.md
  scripts/
    generate.py
  tests/
    test_generate.py
  README.md
  README_zh.md
```

不要带入：

- `repo/progress/`
- `__pycache__/`
- `*.pyc`

## Skill 用法

这个实现刻意保持为单 skill。

使用方式：

```text
/miloya-codebase
/miloya-codebase refresh
/miloya-codebase read
```

### `/miloya-codebase`

默认模式。

行为：

- 如果快照不存在，则新生成一份
- 如果源码指纹未变化，则直接复用已有快照
- 返回适合模型快速理解项目的上下文结果

适用场景：

- 第一次进入项目
- 切换模型或切换 IDE
- 想快速恢复对仓库的整体认知

### `/miloya-codebase refresh`

强制刷新模式。

行为：

- 不复用缓存
- 重新扫描项目
- 覆盖已有快照

适用场景：

- 代码发生了明显变化
- 你不希望继续使用旧快照
- 你怀疑当前快照已经过时或信息不足

### `/miloya-codebase read`

只读模式。

行为：

- 直接读取已有快照
- 跳过强制重建逻辑

适用场景：

- 快照已经存在
- 只想最快速度把上下文加载回来
- 切换了工具或会话，但仓库并没有变化

## 脚本直接使用

```bash
python miloya-codebase/scripts/generate.py <项目路径>
python miloya-codebase/scripts/generate.py <项目路径> --force
```

生成物写入：

```text
<project>/repo/progress/miloya-codebase.json
```

## 快照包含什么

这份快照是给模型消费的，不只是给人看。

主要字段包括：

- `summary`：项目身份、类型、主语言、重要路径、入口点
- `workspace`：monorepo 检测、根清单文件、包布局
- `analysis`：本次用了哪些分析器、是否发生回退、有哪些分析警告
- `index`：本地索引状态、chunk 数量以及本次增量变化
- `chunkCatalog`：可检索的高价值 chunk 锚点目录
- `contextHints`：推荐起始文件、阅读顺序、高信号区域
- `fileTree`：规范化文件树，根目录文件放在 `./`
- `modules`：顶层模块职责摘要
- `dependencies`：根清单依赖
- `importantFiles`：优先阅读的高价值文件列表
- `graph`：文件依赖图、模块关系、symbol 索引、热点文件
- `retrieval`：可用检索任务、检索策略与查询提示
- `contextPacks`：按任务预构建的上下文包
- `externalContext`：最近提交、变更文件、文档与团队约定
- `representativeSnippets`：重要文件中的代表性片段
- `apiRoutes`：提取出的路由定义
- `dataModels`：提取出的数据模型与类型定义
- `keyFunctions`：关键函数及其文件、行号锚点
- `architecture`：推断出的架构风格
- `sourceFingerprint`：用于缓存复用的源码内容指纹
- `freshness`：快照是否过期
- `git`：当前分支、提交和工作区状态

## 示例快照结构

```json
{
  "version": "3.0",
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
    "description": "项目简短摘要",
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
  "analysis": {
    "engines": {
      "Python": "python-ast",
      "TypeScript": "typescript-regex-fallback"
    },
    "filesByEngine": {
      "python-ast": 3,
      "typescript-regex-fallback": 6
    },
    "warnings": ["typescript compiler unavailable; used regex fallback"]
  },
  "index": {
    "stateVersion": "1.0",
    "statePath": "repo/progress/miloya-codebase.index.json",
    "fileCount": 234,
    "chunkCount": 980,
    "reusedSnapshot": false,
    "delta": {
      "newFiles": 2,
      "changedFiles": 4,
      "removedFiles": 0,
      "unchangedFiles": 228
    }
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
  "chunkCatalog": [
    {
      "id": "src/index.ts#function:10-32:abc123",
      "path": "src/index.ts",
      "kind": "function",
      "language": "TypeScript",
      "startLine": 10,
      "endLine": 32,
      "signals": ["bootstrap"],
      "preview": "export async function bootstrap() { ... }"
    }
  ],
  "graph": {
    "stats": {
      "files": 234,
      "symbols": 540,
      "dependencyEdges": 620
    }
  },
  "retrieval": {
    "defaultTask": "understand-project",
    "availableTasks": ["understand-project", "feature-delivery", "bugfix-investigation", "code-review", "onboarding"]
  },
  "contextPacks": {
    "understand-project": {
      "task": "understand-project",
      "files": ["README.md", "src/index.ts"]
    }
  },
  "externalContext": {
    "recentCommits": [],
    "documentationSources": ["README.md"]
  },
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
    "src/": "主要应用源码；200 个文件；routes: 15；models: 30",
    "src/routes/": "HTTP 或应用路由定义；15 个文件"
  },
  "apiRoutes": [],
  "dataModels": [],
  "keyFunctions": [],
  "architecture": "MVC / Controller-based"
}
```

## 为什么它比普通文件树更有用

普通文件树只能回答“文件在哪里”。

真正有价值的 Context Engine 还应该回答：

- 模型应该从哪里开始读
- 哪些文件最值得消耗 token
- 哪些区域最能代表项目结构
- 当前上下文是否可以安全复用

这正是这个 skill 重点优化的方向。

## 重要文件排序

`importantFiles` 使用多信号启发式排序。高分通常来自：

- 入口文件和启动文件
- 根清单文件和关键配置
- 带有路由、模型、导出和集成边界的文件
- 很可能定义了 API 表面或核心领域流程的文件

较低分通常来自：

- 测试文件
- 仅支持性用途的文件
- 信号较低的末端工具文件

这也是它相比单纯文件树更实用的关键原因。

## 检测覆盖范围

当前支持检测：

- JavaScript / TypeScript 生态识别：React、Next.js、Vue、NestJS、Express、Angular、Svelte
- Python 生态识别：FastAPI、Flask、Django、Pydantic、SQLAlchemy
- Go：Gin
- Java：Spring Boot
- 其他生态标记：Maven、Gradle、Cargo

当前语义提取深度最强的是：

- Python：基于 AST 的 imports、models、routes、key functions
- JavaScript / TypeScript：有 TypeScript 编译器时走 AST；否则回退到 regex，
  并在 `analysis` 字段中显式标注

## 准确性边界

这个工具优化的是“实际可用的上下文迁移效率”。

它擅长：

- 快速建立仓库认知
- 给出阅读顺序
- 在模型、会话、IDE 之间做上下文交接
- 为大型项目提供导航层

它目前还不是完整的跨语言 AST-first 语义索引器。部分提取仍然使用 regex 和
启发式，尤其是 JS/TS 项目缺少 TypeScript 编译器时，因此在复杂语法或边缘
工程结构下，仍可能出现漏报或局部误判。

这个取舍是有意的：优先速度、可移植性和实际使用价值。

## 开发与验证

运行测试：

```bash
python -m unittest miloya-codebase.tests.test_generate
```

当前测试覆盖：

- 排除对 `repo/progress` 的自引用扫描
- 避免注释里的伪路由误报
- Python AST 提取 async function 与 dataclass
- JS/TS 在无 TypeScript 编译器时显式报告 fallback
- 本地 index state 与 chunk catalog 生成
- 面向任务的 context pack 检索
- 路径统一为相对路径
- richer schema 字段存在
- 源指纹不变时复用缓存
- 源文件变化后重新生成快照

## 当前状态

当前实现已经适合真实项目中的 context-engine 场景：

- 修正了原始扫描器的关键正确性问题
- 增加了快照新鲜度与源码指纹
- 增加了面向大型项目导航的 schema
- 增加了本地索引状态、chunk、依赖图、检索元数据和 context packs
- 增加了核心行为回归测试

## 已知限制

- 某些语言的路由、模型和函数提取仍然带有启发式成分
- `read` 是 skill 使用模式，不是脚本子命令
- 当前 retrieval 仍是 hybrid + graph aware，不是 embedding 语义检索
- 设计目标不是绝对精确，而是高效、可靠、可复用的项目理解

## 许可

请遵循宿主仓库的许可证与内部发布规范使用。
