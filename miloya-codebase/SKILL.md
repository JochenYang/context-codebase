---
name: miloya-codebase
description: Generate a professional project context snapshot with file tree, workspace layout, important files, representative snippets, routes, models, and key functions. Use when you need fast project understanding or model handoff context.
---

# miloya-codebase

Generate a complete project context snapshot for fast model switching and large-repo understanding. The snapshot is saved to `{project}/repo/progress/miloya-codebase.json`.

Key behavior:
- Excludes its own generated cache under `repo/progress/`
- Tracks a `sourceFingerprint` and `freshness` block
- Reuses the cached snapshot automatically when sources have not changed
- Produces high-signal navigation fields such as `workspace`, `contextHints`, `importantFiles`, and `representativeSnippets`

## Commands

### `/miloya-codebase`
Generate a new project snapshot. If a compatible snapshot already exists and the source fingerprint is unchanged, the script returns the cached snapshot instead of rebuilding it.

### `/miloya-codebase refresh`
Force regenerate the snapshot, overwriting the existing file.

### `/miloya-codebase read`
Read and display the existing snapshot from `{project}/repo/progress/miloya-codebase.json`.

## How It Works

This skill uses `scripts/generate.py` to:
1. Scan the project while excluding generated/vendor noise
2. Detect frameworks, manifests, entry points, and architecture hints
3. Extract routes, models, imports, exports, and named functions
4. Rank high-signal files for reading order
5. Save a reusable JSON snapshot for later sessions or other models

## Running The Script

```bash
python {skill_dir}/scripts/generate.py <project_path>
```

For refresh mode:

```bash
python {skill_dir}/scripts/generate.py <project_path> --force
```

To read an existing snapshot without regenerating:

```bash
cat {project}/repo/progress/miloya-codebase.json
```

## Snapshot Output Schema

```json
{
  "version": "2.0",
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

## Output Notes

- Root-level files are stored under `fileTree["./"]` so models can see project entry metadata immediately.
- `modules` contains top-level responsibility summaries.
- `dependencies` contains root-level manifest dependencies when detectable.
- `freshness` and `sourceFingerprint` determine whether the cached snapshot can be reused safely.
- `workspace` and `contextHints` improve navigation for large repos and monorepos.
- `importantFiles` ranks the highest-signal files for model reading order.
- `representativeSnippets` exposes short anchor snippets from those files.
- Route extraction ignores common source-code comments to reduce false positives.

## Storage

**Path:** `{project}/repo/progress/miloya-codebase.json`

This file can be read by other models/tools to quickly understand the project without rescanning.

## Framework Detection

The script detects:
- JavaScript/TypeScript: React, Next.js, Vue, NestJS, Express, Angular, Svelte
- Python: FastAPI, Flask, Django, Pydantic, SQLAlchemy
- Go: Gin
- Java: Spring Boot
- Other: Maven, Gradle, Rust (Cargo)
