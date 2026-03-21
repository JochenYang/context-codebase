---
description: Query focused implementation details with miloya-codebase
---

Load the `miloya-codebase` skill and use read mode for the current project.

Question: $ARGUMENTS

Requirements:

- Treat read mode as consuming the existing snapshot and index.
- Do not imply a full repo rescan.
- Start from `files`, `snippets`, `flowAnchors`, `nextHops`, and `searchScope`.
- Only widen to repo search if the payload is insufficient.
- Return a quick implementation summary, not a long report.
- Prioritize entry points and execution flow before broad explanations.
