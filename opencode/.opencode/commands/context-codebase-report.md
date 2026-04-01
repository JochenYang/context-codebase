---
description: Prepare deep analysis context with context-codebase
---

Load the `context-codebase` skill and use report mode for the current project.

Question: $ARGUMENTS

Requirements:

- Treat the current workspace root as the project path.
- Do not guess another repository path, parent directory, home directory, or
  skill installation path.
- If the current workspace is not a single project root, stop and say so.
- Treat report mode as consuming the existing snapshot and index.
- Generate a deep-pack style result for deeper analysis.
- Do not expand into a full long report unless delegation is unavailable.
- Keep the parent thread lightweight.
- Mention snapshot generation only if the snapshot was actually missing.
- Treat report mode as context preparation, not semantic repository reasoning.
- Use the pack to prepare downstream analysis; do not keep rerunning report/read
  variants to simulate wider search.
- Preserve the user's question exactly. Do not transliterate, paraphrase, or
  convert Chinese text into pinyin-like ASCII.
- When the question contains non-ASCII text, prefer `--query-file` with a UTF-8
  temp file. If that is not practical, use `--query-stdin`.
- Use `--query-escaped` only if you can produce exact Unicode escapes from the
  original question text. Never invent an escaped string from transliteration.
