# miloya-codebase

**AI 模型切换的 Context Engine** — 生成项目快照，让新模型无需重新扫描即可快速理解代码库。

---

## 概念

**问题**：在 AI 模型切换或开启新会话时，每个模型都需要重新扫描整个代码库来理解项目。对于大型项目（10万行以上），这浪费时间和 token。

**解决方案**：miloya-codebase 一次生成项目的结构化 JSON 快照。新模型读取快照后立即理解：
- 项目是什么（技术栈、类型）
- 如何组织（文件树、模块）
- 关键内容在哪（API 路由、数据模型、函数）

**核心思想**：一个模型分析，所有模型受益。快照保存在项目中，跨会话持久化。

---

## 工作原理

```
项目文件
    ↓
[ generate.py 脚本 ]
    ↓
┌─────────────────────────────────────┐
│ 1. 扫描：递归遍历文件               │
│    （排除 node_modules/.git/dist）    │
│                                      │
│ 2. 检测：匹配模式                   │
│    - package.json → 技术栈           │
│    - 文件名 → 入口点                 │
│    - 装饰器/regex → 路由            │
│                                      │
│ 3. 提取：解析代码                   │
│    - interfaces/types/classes        │
│    - API 路由定义                   │
│    - 导出函数                       │
│                                      │
│ 4. 推断：架构类型                   │
│    (MVC / Flux / Layered / Modular) │
└─────────────────────────────────────┘
    ↓
repo/progress/miloya-codebase.json
```

---

## 脚本逻辑 (generate.py)

### 文件扫描
- 递归 `os.walk()` 遍历
- 排除：`node_modules`、`.git`、`dist`、`venv`、`__pycache__`、`.cache` 等
- 统计总文件数和代码行数

### 框架检测
**从 package.json 依赖检测：**
| 依赖 | 框架 |
|------|------|
| react, react-dom | React |
| next | Next.js |
| vue | Vue |
| @nestjs/core | NestJS |
| express | Express |
| fastapi | FastAPI |
| flask | Flask |

**从文件标识检测：**
| 文件 | 框架 |
|------|------|
| manage.py | Django |
| go.mod | Go |
| Cargo.toml | Rust |
| pom.xml | Maven |

### API 路由提取
使用正则匹配路由模式：

| 框架 | 模式示例 |
|------|----------|
| Express | `router.get('/users', ...)` |
| NestJS | `@Get('users')` |
| FastAPI | `@app.get('/items')` |

### 数据模型提取
| 语言 | 模式 |
|------|------|
| TypeScript | `interface X`, `type X`, `class X` |
| Python | `class X(BaseModel)`, `class X(models.Model)` |

### 架构推断
基于目录结构：
- `controllers/` + `routes/` → **MVC / 基于控制器**
- `store/` + `state/` → **Flux / 状态管理**
- `services/` + `repositories/` → **分层 / 仓库模式**
- 其他 → **模块化**

---

## 输出格式

```json
{
  "version": "1.0",
  "generatedAt": "2026-03-18T21:36:58",
  "projectPath": "D:\\codes\\LobsterAI",
  "summary": {
    "name": "lobsterai",
    "type": "React (Electron 桌面应用)",
    "techStack": ["React", "Electron", "Redux Toolkit", "TypeScript"],
    "entryPoints": ["vite.config.ts", "electron/main.ts"],
    "totalFiles": 632,
    "totalLines": 251998
  },
  "fileTree": {
    "src/": ["main/", "renderer/"],
    "src/main/": ["im/", "libs/"]
  },
  "apiRoutes": [],
  "dataModels": [
    { "name": "IMConfig", "type": "interface", "file": "src/main/im/types.ts" }
  ],
  "keyFunctions": [
    { "name": "coworkRunner", "file": "src/main/libs/coworkRunner.ts", "line": 42 }
  ],
  "architecture": "Modular"
}
```

---

## 使用场景

| 场景 | 无快照 | 有快照 |
|------|--------|--------|
| 模型切换中途 | 重新扫描整个代码库（10+ 分钟） | 读取快照（秒级） |
| 新人上手 | 数小时理解结构 | 分钟级结构化概览 |
| 快速架构审查 | 手动文件查找 | JSON + 可视化摘要 |
| 跨模型上下文共享 | 每个模型重新扫描 | 共享相同快照文件 |

---

## 使用方式

```
/miloya-codebase          # 生成新快照
/miloya-codebase refresh  # 强制重新生成（覆盖）
/miloya-codebase read     # 读取已有快照
```

### 手动脚本使用

```bash
# 生成快照
python miloya-codebase/scripts/generate.py <项目路径>

# 强制刷新
python miloya-codebase/scripts/generate.py <项目路径> --force
```

---

## 安装

将 `miloya-codebase/` 文件夹复制到 Claude skills 目录：
```
~/.claude/skills/miloya-codebase/
```

---

## 功能特性

- **快速**：约 45 秒扫描 600+ 文件
- **结构化输出**：JSON 格式，模型易解析
- **跨模型共享**：快照保存在 `repo/progress/`
- **多框架支持**：React、Next.js、Vue、NestJS、Express、FastAPI、Django、Go、Rust 等
- **自动去重**：API 路由和数据模型去重
- **架构推断**：自动推断 MVC/Flux/Layered/Modular

---

## 存储位置

**快照路径**：`{project}/repo/progress/miloya-codebase.json`

建议将此文件提交到版本控制，让整个团队（和所有 AI 模型）都能受益于分析结果。
