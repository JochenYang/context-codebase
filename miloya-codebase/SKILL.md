---
name: miloya-codebase
description: Professional project context engine. Usage: /miloya-codebase [refresh|read]
---

# miloya-codebase

Generate a professional project context snapshot for fast model switching, IDE
handoff, and large-repo understanding. The snapshot is stored at
`{project}/repo/progress/miloya-codebase.json`.

## Positioning

This skill is not just a file tree dumper. It is a context engine designed to
help a new model answer these questions quickly:

- What kind of project is this?
- Where should I start reading?
- Which files carry the most architectural signal?
- Is the existing snapshot still fresh and safe to reuse?

## Usage

Single skill, three modes:

### `/miloya-codebase`

Default entry.

Behavior:

- Generate a new snapshot when no snapshot exists
- Reuse the cached snapshot when the source fingerprint is unchanged
- Return the current project context in a format optimized for fast model understanding

Recommended use:

- First time entering a project
- Switching to a new model or IDE and wanting the latest reusable context
- General "understand this repo quickly" workflow

### `/miloya-codebase refresh`

Force regenerate the snapshot.

Behavior:

- Ignore cache reuse
- Re-scan the project and overwrite the existing snapshot

Recommended use:

- The codebase changed significantly
- You do not want cache reuse
- You suspect the current snapshot is stale or insufficient

### `/miloya-codebase read`

Read the existing snapshot directly from `{project}/repo/progress/miloya-codebase.json`.

Behavior:

- Use the already generated snapshot and index as-is
- Skip forced regeneration logic
- Return a retrieval-oriented payload with:
  - high-value files
  - code snippets with line ranges
  - task-oriented reading packs
  - graph hotspots and external context
- When the user asks a focused question, prefer running read mode with
  `--task` plus a UTF-8 safe query channel so the output contains direct code
  anchors instead of only a project summary
- On Windows or any environment where non-ASCII query text may be mojibake,
  prefer `--query-escaped <ascii_only_query>` first, then `--query-file
  <utf8_file>` or `--query-stdin`, instead of raw `--query`
- In read mode, prefer this workflow:
  1. inspect `files`, `snippets`, `nextHops`, and `searchScope`
  2. read the suggested files directly when possible
  3. only widen to repo search if the read payload is insufficient
  4. when widening search, explicitly exclude `repo/progress/`, `node_modules/`,
     `dist/`, `build/`, and `__pycache__/`

Recommended use:

- The snapshot already exists
- You are switching models/tools and only want to load the saved context quickly
- You want a stable handoff artifact without rescanning
- You want fast file and snippet retrieval for a concrete task without rescanning

## How It Works

This skill uses `scripts/generate.py` to:

1. Scan the project while excluding generated/vendor noise
2. Detect frameworks, manifests, entry points, and architecture hints
3. Run language analyzers, preferring AST-backed extraction when available
4. Extract routes, models, imports, exports, and named functions
5. Record analyzer engines and fallback warnings in the snapshot
6. Rank high-signal files for reading order
7. Produce a reusable JSON snapshot for future sessions and tools

## Core Behaviors

- Excludes generated/vendor noise such as `.git`, `node_modules`, `dist`,
  `build`, `__pycache__`, and `repo/progress`
- Avoids self-referential snapshots by not rescanning its own output
- Uses Python AST for Python semantic extraction
- Uses the TypeScript compiler AST for JS/TS when available in the analyzed
  project
- Records explicit fallback warnings when JS/TS must fall back to regex extraction
- Reuses the cached snapshot automatically when the `sourceFingerprint` is unchanged
- Falls back to regeneration when source files or schema version change
- Normalizes all output paths to relative POSIX-style paths
- Detects common monorepo layouts such as `apps/`, `packages/`,
  `pnpm-workspace.yaml`, `turbo.json`, and `nx.json`

## Manual Script Usage

```bash
python {skill_dir}/scripts/generate.py <project_path>
python {skill_dir}/scripts/generate.py <project_path> --force
python {skill_dir}/scripts/generate.py <project_path> --read
python {skill_dir}/scripts/generate.py <project_path> --read --task feature-delivery --query "skill lifecycle runtime"
python {skill_dir}/scripts/generate.py <project_path> --read --task feature-delivery --query-escaped "\\u6280\\u80fd\\u7ba1\\u7406\\u5668\\u5982\\u4f55\\u5b9e\\u73b0"
python {skill_dir}/scripts/generate.py <project_path> --read --task feature-delivery --query-file query.txt
cat query.txt | python {skill_dir}/scripts/generate.py <project_path> --read --task feature-delivery --query-stdin
cat {project}/repo/progress/miloya-codebase.json
```

Windows-safe example:

```powershell
python {skill_dir}/scripts/generate.py <project_path> --read --task feature-delivery --query-escaped "\\u6280\\u80fd\\u7ba1\\u7406\\u5668\\u5982\\u4f55\\u5b9e\\u73b0"
```

When `--read` returns a payload with `searchScope`, `files`, `snippets`, and
`nextHops`, treat those as the first-class search plan. Do not start with
repo-wide search unless those hints are insufficient.

## Snapshot Output Schema

```json
{
  "version": "3.0",
  "generatedAt": "2026-03-18T...",
  "projectPath": "/path/to/project",
  "sourceFingerprint": "sha256...",
  "freshness": {
    "stale": false,
    "reason": "source fingerprint unchanged",
    "newestSourceMtime": "2026-03-18T...",
    "snapshotPath": "repo/progress/miloya-codebase.json"
  },
  "git": {
    "branch": "main",
    "commit": "abc123",
    "status": "clean"
  },
  "summary": {
    "name": "project-name",
    "type": "web-api | frontend | monorepo | cli | ...",
    "description": "Short README-derived project summary",
    "techStack": ["React", "Node.js"],
    "entryPoints": ["src/index.ts"],
    "totalFiles": 234,
    "totalLines": 12840,
    "dominantLanguages": [{ "language": "TypeScript", "files": 120 }],
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
    "reusedSnapshot": false
  },
  "contextHints": {
    "readOrder": ["package.json", "src/index.ts"],
    "recommendedStart": "package.json",
    "highSignalAreas": ["./", "src/"],
    "monorepo": false,
    "description": "Short README-derived project summary"
  },
  "fileTree": {
    "./": ["README.md", "package.json"],
    "src/": ["components/", "hooks/", "utils/"]
  },
  "modules": {
    "./": "Project root metadata and entry files; 4 files",
    "src/": "Primary application source code; 42 files; notable areas: api, components, hooks"
  },
  "dependencies": {
    "package.json": ["react", "typescript", "vite"]
  },
  "importantFiles": [
    {
      "path": "src/index.ts",
      "role": "API surface",
      "language": "TypeScript",
      "lines": 180,
      "imports": ["express"],
      "exports": ["bootstrap"],
      "score": 152,
      "whyImportant": "entry point, 4 API routes, 3 exports"
    }
  ],
  "chunkCatalog": [
    {
      "id": "src/index.ts#function:10-32:abc123",
      "path": "src/index.ts",
      "kind": "function",
      "language": "TypeScript",
      "startLine": 10,
      "endLine": 32
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
      "startLine": 10,
      "endLine": 20,
      "snippet": "..."
    }
  ],
  "apiRoutes": [
    { "method": "GET", "path": "/api/users", "handler": "src/api/users.ts" }
  ],
  "dataModels": [
    { "name": "User", "type": "interface", "file": "src/models/user.ts" }
  ],
  "keyFunctions": [
    { "name": "fetchUser", "file": "src/api/users.ts", "line": 42 }
  ],
  "architecture": "MVC | Flux | Layered | Modular"
}
```

## Why This Is Better Than A Plain File Tree

A plain file tree tells a model where files exist. A context engine should also
tell the model:

- which files are worth reading first
- which modules define the project shape
- whether the current snapshot is reusable
- where the highest-value architectural signals live

This skill is designed around those higher-value questions.

## Important File Prioritization

`importantFiles` are ranked using multiple signals, including:

- entry points and startup files
- root manifests and config files
- files with routes, models, exports, and integration edges
- lower priority for test/support files

This makes the output much more useful than a plain project tree when a model
needs a fast reading order.

## Output Notes

- Root-level files are stored under `fileTree["./"]`
- `modules` contains top-level responsibility summaries
- `dependencies` contains root-level manifest dependencies when detectable
- `analysis` reports which analyzers were used and whether any language fell back
- `index` and `chunkCatalog` support incremental indexing and retrieval
- `graph`, `retrieval`, `contextPacks`, and `externalContext` support task-aware context assembly
- `freshness` and `sourceFingerprint` determine whether a cached snapshot can be reused safely
- `workspace` and `contextHints` improve navigation for large repos and monorepos
- `importantFiles` ranks the highest-signal files for model reading order
- `representativeSnippets` provides short anchor snippets from those files

## Snapshot Consumption Order

When reading an existing snapshot or presenting a freshly generated one, consume
the fields in this order:

1. `summary`, `workspace`, `analysis`, `freshness`, `git`
2. `contextHints`, `importantFiles`, `modules`
3. `graph`, especially `stats`, `moduleDependencies`, `hotspots`, `packages`
4. `contextPacks` and `retrieval`
5. `externalContext`
6. `representativeSnippets`, `apiRoutes`, `dataModels`, `keyFunctions`

Do not stop after the overview layer. The engine is only useful when graph,
task packs, and external context are surfaced to the user.

## Response Contract

When summarizing the snapshot for the user, always produce a Chinese report that
uses the snapshot as evidence instead of improvising from file names alone.

Minimum required sections:

1. `项目定位`
   - State the project type, main stack, repo/workspace shape, and whether the
     conclusion is fact or inference.
2. `架构边界`
   - Explain the major runtime or package boundaries using `summary`,
     `workspace`, `modules`, and `graph`.
   - For Electron-style apps, explicitly call out `main` / `renderer` /
     preload or extension boundaries when supported by the snapshot.
3. `核心关系`
   - Use `graph.moduleDependencies`, `graph.hotspots`, `importantFiles`, and
     `entryPoints` to describe how the important modules connect.
4. `任务入口`
   - Surface at least 3 task-oriented reading paths from `contextPacks`.
   - Preferred tasks: `understand-project`, `feature-delivery`,
     `bugfix-investigation`, `code-review`, `onboarding`.
5. `置信度与回退项`
   - Report analyzer engines from `analysis.engines`
   - Quote fallback reasons from `analysis.warnings`
   - Distinguish high-confidence facts from heuristic inferences
6. `补充上下文`
   - Use `externalContext` to mention recent changes, docs, decisions, or team
     conventions when available

## Facts, Inference, and Fallback Rules

- Label direct snapshot facts as `事实`
- Label architecture or role judgments as `推断`
- Label analyzer limitations as `回退`
- Never invent reasons that are not supported by the snapshot
- If TypeScript analysis falls back, do not say `缺少 tsconfig` unless the
  snapshot explicitly proves that; prefer the exact warning from `analysis`
- If the repo is dirty, mention it briefly but do not let it dominate the
  summary unless the task is bugfix or review

## Task-Oriented Presentation Rules

When `contextPacks` are present, do not only list important files. Convert them
into actionable reading guides:

- `understand-project`: where a new model should start and why
- `feature-delivery`: which files are likely to contain implementation patterns
- `bugfix-investigation`: which files are close to recent changes or execution paths
- `code-review`: which files form the immediate risk surface
- `onboarding`: which files best explain conventions and structure

Each task entry should include:

- 1 sentence goal
- 3-6 files
- a brief `why these files` explanation using pack reasons, hotspots, or graph links

## Output Quality Bar

Avoid stopping at:

- project name
- tech stack
- file count
- a flat list of important files

The final answer should help the next model understand:

- where the architectural boundaries are
- which modules are central
- how to start reading for a specific task
- which parts of the snapshot are high-confidence versus heuristic

## Storage

**Path:** `{project}/repo/progress/miloya-codebase.json`

This file is the reusable handoff artifact for other models and tools.

## Framework Detection

The script detects:

- JavaScript/TypeScript: React, Next.js, Vue, NestJS, Express, Angular, Svelte
- Python: FastAPI, Flask, Django, Pydantic, SQLAlchemy
- Go: Gin
- Java: Spring Boot
- Other: Maven, Gradle, Rust (Cargo)

Extraction depth is strongest for Python and for JS/TS projects that have a
TypeScript compiler available locally. When JS/TS AST analysis is unavailable,
the snapshot records a fallback warning in `analysis`.
