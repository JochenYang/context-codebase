---
description: Prepare deep analysis context with miloya-codebase
---

Load the `miloya-codebase` skill and use report mode for the current project.

Question: $ARGUMENTS

Requirements:

- Treat report mode as consuming the existing snapshot and index.
- Generate a deep-pack style result for deeper analysis.
- Do not expand into a full long report unless delegation is unavailable.
- Keep the parent thread lightweight.
- Mention snapshot generation only if the snapshot was actually missing.
