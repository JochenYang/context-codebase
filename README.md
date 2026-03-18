# miloya-codebase

Professional context engine for fast project handoff between models and sessions.

`miloya-codebase` generates a reusable JSON snapshot so a new model can understand a codebase without rescanning everything from scratch.

## What It Produces

The snapshot is stored at `repo/progress/miloya-codebase.json` and includes:
- `summary`: project type, README-derived description, dominant languages, important paths
- `workspace`: root manifests, package/workspace layout, monorepo hints
- `contextHints`: suggested read order and high-signal areas
- `fileTree`: normalized project tree with root files under `./`
- `modules`: top-level responsibility summaries
- `dependencies`: root manifest dependencies
- `importantFiles`: ranked high-signal files for a model to inspect first
- `representativeSnippets`: short anchor snippets from those files
- `apiRoutes`, `dataModels`, `keyFunctions`, `architecture`
- `sourceFingerprint`, `freshness`, `git`

## Why This Is Better Than A Plain File Tree

A good context engine should answer:
- What kind of project is this?
- Where should a model start reading?
- Which files carry the most architectural signal?
- Is the snapshot still fresh?

This tool now targets those questions directly instead of only dumping folders and symbols.

## Usage

```bash
python miloya-codebase/scripts/generate.py <project_path>
python miloya-codebase/scripts/generate.py <project_path> --force
```

Skill commands:

```text
/miloya-codebase
/miloya-codebase refresh
/miloya-codebase read
```

## Core Behaviors

- **Self-reference exclusion**: `repo/progress/` is explicitly excluded to prevent snapshot from including itself
- **Comment-aware parsing**: Removes `//`, `/* */`, and `#` comments before regex extraction to avoid false-positive routes (e.g., `@app.get('/path')` in comments)
- **Smart caching**: Compares SHA256 fingerprint of all source files; skips regeneration if unchanged
- **Freshness detection**: `freshness.stale` flag tells consumers if the snapshot is current or outdated
- **Path normalization**: All paths use POSIX-style forward slashes for cross-platform portability
- **File size limits**: Skips files over 512KB to avoid bloating the snapshot
- **Monorepo detection**: Recognizes `pnpm-workspace.yaml`, `turbo.json`, `nx.json`, `apps/`, `packages/` layouts

## File Scoring

`importantFiles` are ranked by a multi-signal scoring system:

| Signal | Score Impact | Reason |
|--------|-------------|--------|
| Entry point (index.ts, main.ts, App.tsx) | +110 | Primary application entry |
| Root/config manifest | +90 | Essential project metadata |
| Has API routes | +60 + 5/route | API surface |
| Has data models | +45 + 4/model | Domain entities |
| Has exports | +30 + 2/export | Public API |
| Test files | -40 | Lower priority for context |

## Architecture Inference

Detects architecture style by checking all directory levels:

| Pattern | Architecture |
|---------|--------------|
| `controllers/` + `routes/` | MVC / Controller-based |
| `store/` or `state/` or `redux/` | Flux / State management |
| `services/` + `repositories/` | Layered / Repository |
| `middleware/` | Middleware-based |
| Otherwise | Modular |

## Example Snapshot Outline

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
  "summary": {
    "name": "example",
    "type": "Backend Service",
    "description": "Short README-derived project summary",
    "importantPaths": ["package.json", "src/index.ts"]
  },
  "workspace": {
    "isMonorepo": false,
    "rootManifests": ["package.json"],
    "packages": []
  },
  "contextHints": {
    "readOrder": ["package.json", "src/index.ts"],
    "recommendedStart": "package.json"
  },
  "importantFiles": [
    {
      "path": "src/index.ts",
      "role": "API surface",
      "score": 152
    }
  ]
}
```

## Development

Run tests:

```bash
python -m unittest miloya-codebase.tests.test_generate
```

## Status

Current implementation is optimized for practical context transfer:
- correctness fixes for self-reference and false-positive routes
- richer schema for large-project navigation
- cache freshness detection via source fingerprint
- regression tests for freshness and schema output
