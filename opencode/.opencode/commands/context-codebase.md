---
description: Generate or reuse a context-codebase project snapshot
---

Load the `context-codebase` skill and use it for the current project.

Requirements:

- Treat the current workspace root as the project path.
- Do not guess another repository path, parent directory, home directory, or
  skill installation path.
- If the current workspace is not a single project root, say so before running.
- Generate a snapshot if one does not exist yet.
- Reuse the existing snapshot if it is already valid.
- Return a concise project overview based on the skill output.
- Do not claim the repository was rescanned unless it actually was.
- Treat this mode as project orientation, not deep analysis.

Enhanced modes (v2.0):
- `--semantic` - AST-based semantic chunking for better code partitioning
- `--incremental` - Chunk-level change tracking for faster updates
- `--sqlite` - SQLite index for fast KV queries
