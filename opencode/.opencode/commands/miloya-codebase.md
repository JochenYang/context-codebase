---
description: Generate or reuse a miloya-codebase project snapshot
---

Load the `miloya-codebase` skill and use it for the current project.

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
