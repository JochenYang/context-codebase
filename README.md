# miloya-codebase

**Context Engine for AI Model Switching** — Generate project snapshots so new models can understand a codebase instantly without rescanning.

---

## Concept

**Problem**: When switching between AI models or starting a new session, each model must rescan the entire codebase to understand the project. For large projects (100k+ lines), this wastes time and tokens.

**Solution**: miloya-codebase generates a structured JSON snapshot of the project once. New models read this snapshot and immediately understand:
- What the project is (tech stack, type)
- How it's organized (file tree, modules)
- Where key things are (API routes, data models, functions)

**Core Idea**: One model analyzes, all models benefit. The snapshot is stored in the project and persists across sessions.

---

## How It Works

```
Project Files
    ↓
[ generate.py Script ]
    ↓
┌─────────────────────────────────────┐
│ 1. Scan: Recursive file traversal   │
│    (exclude node_modules/.git/dist) │
│                                     │
│ 2. Detect: Match patterns           │
│    - package.json → tech stack      │
│    - File names → entry points      │
│    - Decorators/regex → routes      │
│                                     │
│ 3. Extract: Parse code              │
│    - interfaces/types/classes       │
│    - API route definitions          │
│    - Exported functions             │
│                                     │
│ 4. Infer: Architecture type         │
│    (MVC / Flux / Layered / Modular) │
└─────────────────────────────────────┘
    ↓
repo/progress/miloya-codebase.json
```

---

## Script Logic (generate.py)

### File Scanning
- Recursive `os.walk()` traversal
- Excludes: `node_modules`, `.git`, `dist`, `venv`, `__pycache__`, `.cache`, etc.
- Counts total files and lines of code

### Framework Detection
**From package.json dependencies:**
| Dependency | Framework |
|------------|-----------|
| react, react-dom | React |
| next | Next.js |
| vue | Vue |
| @nestjs/core | NestJS |
| express | Express |
| fastapi | FastAPI |
| flask | Flask |

**From file indicators:**
| File | Framework |
|------|-----------|
| manage.py | Django |
| go.mod | Go |
| Cargo.toml | Rust |
| pom.xml | Maven |

### API Route Extraction
Uses regex to match route patterns:

| Framework | Pattern Example |
|-----------|-----------------|
| Express | `router.get('/users', ...)` |
| NestJS | `@Get('users')` |
| FastAPI | `@app.get('/items')` |

### Data Model Extraction
| Language | Patterns |
|----------|----------|
| TypeScript | `interface X`, `type X`, `class X` |
| Python | `class X(BaseModel)`, `class X(models.Model)` |

### Architecture Inference
Based on directory structure:
- `controllers/` + `routes/` → **MVC / Controller-based**
- `store/` + `state/` → **Flux / State management**
- `services/` + `repositories/` → **Layered / Repository**
- Otherwise → **Modular**

---

## Output Format

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

## Use Cases

| Scenario | Without Snapshot | With Snapshot |
|----------|-----------------|---------------|
| Model switch mid-project | Rescan entire codebase (10+ min) | Read snapshot (seconds) |
| Onboarding new developer | Hours to understand structure | Minutes with structured overview |
| Quick architecture review | Manual file hunting | JSON + visual summary |
| Cross-model context sharing | Each model rescans | Share same snapshot file |

---

## Usage

```
/miloya-codebase          # Generate new snapshot
/miloya-codebase refresh  # Force regenerate (overwrite)
/miloya-codebase read     # Read existing snapshot
```

### Manual Script Usage

```bash
# Generate snapshot
python miloya-codebase/scripts/generate.py <project_path>

# Force refresh
python miloya-codebase/scripts/generate.py <project_path> --force
```

---

## Installation

Copy `miloya-codebase/` folder to your Claude skills directory:
```
~/.claude/skills/miloya-codebase/
```

---

## Features

- **Fast**: Scans 600+ files in ~45 seconds
- **Structured Output**: JSON format, easy for models to parse
- **Cross-Model Sharing**: Snapshot persists in `repo/progress/`
- **Multi-Framework**: Supports React, Next.js, Vue, NestJS, Express, FastAPI, Django, Go, Rust, and more
- **Auto-Deduplication**: API routes and models are deduplicated
- **Architecture Inference**: Automatically infers MVC/Flux/Layered/Modular

---

## Storage

**Snapshot Location**: `{project}/repo/progress/miloya-codebase.json`

This file is meant to be committed to version control so the entire team (and all AI models) benefit from the analysis.
