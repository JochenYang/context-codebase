# context-codebase

Place the `context-codebase` skill files in this directory to ship the skill
with the target OpenCode project.

Expected minimum layout:

```text
.opencode/skills/context-codebase/
  SKILL.md
  scripts/
    generate.py
```

If the skill is installed globally instead, you can remove this placeholder
directory and keep only the command files plus `opencode.json` permission
config.
