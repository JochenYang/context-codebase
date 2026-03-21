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
- Treat report mode as context preparation, not semantic repository reasoning.
- Use the pack to prepare downstream analysis; do not keep rerunning report/read
  variants to simulate wider search.
- Preserve the user's question exactly. Do not transliterate, paraphrase, or
  convert Chinese text into pinyin-like ASCII.
- When the question contains non-ASCII text, prefer `--query-file` with a UTF-8
  temp file. If that is not practical, use `--query-stdin`.
- Use `--query-escaped` only if you can produce exact Unicode escapes from the
  original question text. Never invent an escaped string from transliteration.
