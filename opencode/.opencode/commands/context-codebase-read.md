---
description: Query focused implementation details with context-codebase
---

Load the `context-codebase` skill and use read mode for the current project.

Question: $ARGUMENTS

Requirements:

- Treat the current workspace root as the project path.
- Do not guess another repository path, parent directory, home directory, or
  skill installation path.
- If the current workspace is not a single project root, stop and say so.
- Treat read mode as consuming the existing snapshot and index.
- If the snapshot is missing, do not pretend read mode can use cached context;
  run the default `/context-codebase` flow first.
- Do not imply a full repo rescan.
- Start from `files`, `snippets`, `flowAnchors`, `nextHops`, and `searchScope`.
- Only widen to repo search if the payload is insufficient.
- Return a quick implementation summary, not a long report.
- Prioritize entry points and execution flow before broad explanations.
- Treat the payload as candidate context, not as a semantic answer engine.
- Use the payload to decide what to read next; the host model is responsible for
  understanding the question and choosing the path.
- Preserve the user's question exactly. Do not transliterate, paraphrase, or
  convert Chinese text into pinyin-like ASCII.
- When the question contains non-ASCII text, prefer `--query-file` with a UTF-8
  temp file. If that is not practical, use `--query-stdin`.
- Use `--query-escaped` only if you can produce exact Unicode escapes from the
  original question text. Never invent an escaped string from transliteration.
- If the read payload is weak because the query was mangled, fix the query input
  method first before widening to repo search.
- Do not rerun `context-codebase --read` with a different `--task`, alternate
  flags, or a lightly rewritten query just to widen search.
- If the first read payload is weak but valid, keep that payload and move to
  direct repo search within the suggested `searchScope`.
