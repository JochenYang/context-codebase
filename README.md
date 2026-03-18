# miloya-codebase

`miloya-codebase` is a professional project context engine for large repositories.

It generates a reusable snapshot at `repo/progress/miloya-codebase.json` so a new
model, a new IDE session, or another tool can understand a codebase quickly
without rescanning the entire repository from scratch.

This is not a plain file-tree exporter. It is designed to answer the questions a
model actually needs at handoff time:

- What kind of project is this?
- Which files should be read first?
- Which modules carry the highest architectural signal?
- Is the existing snapshot still fresh enough to reuse?

## Positioning

Most repository summary tools stop at file trees, symbol lists, or simple
language counts. That is not enough for fast model onboarding in a real project.

`miloya-codebase` adds a navigation layer on top of structural scanning:

- project summary and technology stack detection
- workspace and monorepo hints
- read-order guidance for high-signal files
- representative snippets for quick anchoring
- snapshot freshness and source fingerprinting
- cache reuse for faster follow-up sessions

The goal is practical context transfer, not compiler-grade static analysis.

## Installation

Minimum required files:

```text
miloya-codebase/
  SKILL.md
  scripts/
    generate.py
```

Recommended development layout:

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

Do not include:

- `repo/progress/`
- `__pycache__/`
- `*.pyc`

## Skill Usage

This is intentionally a single-skill design.

Use:

```text
/miloya-codebase
/miloya-codebase refresh
/miloya-codebase read
```

### `/miloya-codebase`

Default mode.

Behavior:

- generates a new snapshot if one does not exist
- reuses the existing snapshot if the source fingerprint is unchanged
- returns project context optimized for fast model understanding

Recommended when:

- entering a project for the first time
- switching to another model or IDE
- refreshing your mental map of the repository

### `/miloya-codebase refresh`

Force regeneration mode.

Behavior:

- ignores cache reuse
- rescans the project
- overwrites the existing snapshot

Recommended when:

- the codebase changed materially
- you want to avoid stale context
- you suspect the current snapshot is insufficient

### `/miloya-codebase read`

Read-only mode.

Behavior:

- loads the existing snapshot directly
- skips forced regeneration

Recommended when:

- the snapshot already exists
- you want the fastest possible handoff
- you changed tools or sessions but not the repository

## Manual Script Usage

```bash
python miloya-codebase/scripts/generate.py <project_path>
python miloya-codebase/scripts/generate.py <project_path> --force
```

The generated artifact is written to:

```text
<project>/repo/progress/miloya-codebase.json
```

## What The Snapshot Contains

The snapshot is built for model consumption, not just human inspection.

Primary sections:

- `summary`: project identity, type, dominant languages, important paths, entry points
- `workspace`: monorepo detection, root manifests, package layout
- `analysis`: analyzer engines used, fallback usage, analysis warnings
- `index`: local index-state metadata, chunk counts, and change delta
- `chunkCatalog`: top chunk anchors for retrieval and context packing
- `contextHints`: recommended start file, read order, high-signal areas
- `fileTree`: normalized project tree, including root files under `./`
- `modules`: top-level responsibility summaries
- `dependencies`: root manifest dependencies when detectable
- `importantFiles`: ranked files that are worth reading first
- `graph`: file dependency graph, module relationships, symbol index, hotspots
- `retrieval`: available retrieval tasks, strategies, and query hints
- `contextPacks`: prebuilt task-focused context bundles
- `externalContext`: recent commits, changed files, documentation, conventions
- `representativeSnippets`: short anchor snippets from those files
- `apiRoutes`: extracted route definitions
- `dataModels`: extracted models and type definitions
- `keyFunctions`: important named functions with file and line anchors
- `architecture`: inferred architecture style
- `sourceFingerprint`: content fingerprint used for cache reuse
- `freshness`: whether the snapshot is stale
- `git`: current branch, commit, and working tree status when available

## Example Snapshot Outline

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
    "description": "Short README-derived project summary",
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
    "src/": "Primary application source code; 200 files; routes: 15; models: 30",
    "src/routes/": "HTTP or application routing definitions; 15 files"
  },
  "apiRoutes": [],
  "dataModels": [],
  "keyFunctions": [],
  "architecture": "MVC / Controller-based"
}
```

## Why This Is Better Than A Plain File Tree

A plain file tree answers where files exist.

A context engine should answer:

- where a model should start
- which files are worth the tokens
- which areas define the application shape
- whether the existing context can be trusted

That difference is what this skill is optimized for.

## Core Behaviors

- excludes generated and vendor noise such as `.git`, `node_modules`, `dist`,
  `build`, `__pycache__`, and `repo/progress`
- avoids self-referential snapshots by excluding its own output directory
- uses Python AST for Python semantic extraction
- uses the TypeScript compiler AST for JS/TS when available in the analyzed
  project, otherwise records an explicit regex fallback warning
- maintains a local index-state file and chunk catalog for incremental reuse
- builds a dependency graph, retrieval metadata, and task-oriented context packs
- captures recent git history and documentation sources as external context
- removes common source-code comments before fallback extraction to reduce
  false positives
- normalizes all paths to relative POSIX-style paths
- skips oversized files to control snapshot size
- detects common monorepo signals such as `apps/`, `packages/`,
  `pnpm-workspace.yaml`, `turbo.json`, and `nx.json`
- reuses an existing snapshot when the content fingerprint is unchanged
- invalidates the cache when source files or schema version change

## Important File Ranking

`importantFiles` are ranked with a multi-signal heuristic. Higher scores are
assigned to:

- entry points and startup files
- root manifests and major configuration files
- files with routes, models, exports, and integration boundaries
- files likely to define API surface or core domain flow

Lower scores are assigned to:

- test files
- support-only files
- low-signal leaf utilities

This is what makes the output materially more useful than a tree dump.

## Detection Coverage

Current detection includes:

- JavaScript and TypeScript ecosystem detection: React, Next.js, Vue, NestJS,
  Express, Angular, Svelte
- Python ecosystem detection: FastAPI, Flask, Django, Pydantic, SQLAlchemy
- Go: Gin
- Java: Spring Boot
- Other ecosystem markers: Maven, Gradle, Cargo

Semantic extraction depth is currently strongest for:

- Python: AST-backed imports, models, routes, and key functions
- JavaScript / TypeScript: TypeScript-compiler AST when available, otherwise
  regex fallback with explicit warning in `analysis`

## Accuracy Boundary

This tool is optimized for practical context transfer.

It is strong at:

- fast repository orientation
- read-order suggestion
- handoff between models, sessions, and IDEs
- large-project navigation

It is not yet a full cross-language AST-first semantic indexer. Some extraction
still relies on regex and heuristics, especially when a JS/TS AST compiler is
not available in the analyzed project, which means edge cases can still produce
misses or partial misclassification.

That tradeoff is intentional for speed and portability.

## Development And Validation

Run tests:

```bash
python -m unittest miloya-codebase.tests.test_generate
```

Current validation covers:

- self-reference exclusion
- comment-based false-positive route prevention
- Python AST extraction for async functions and dataclasses
- explicit JS/TS fallback reporting when no TypeScript compiler is available
- local index-state and chunk catalog generation
- task-focused context-pack retrieval
- relative-path normalization
- richer schema presence
- cache reuse when source fingerprint is unchanged
- regeneration when source files change

## Status

Current implementation is suitable for real context-engine usage in active
projects:

- corrected major correctness issues from the original scanner
- added snapshot freshness and source fingerprinting
- added navigation-focused schema for large-project understanding
- added local index-state, chunking, dependency graph, retrieval metadata, and context packs
- added regression tests for core behavior

## Limitations

- route, model, and function extraction are still heuristic in some languages
- `read` is a skill usage mode, not a standalone script subcommand
- retrieval is hybrid and graph-aware, but not embedding-backed semantic search yet
- absolute precision is not the design goal; usable project understanding is
  the design goal

## License

Use according to the host repository's license and internal distribution rules.
