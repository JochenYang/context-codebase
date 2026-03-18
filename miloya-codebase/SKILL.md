---
name: miloya-codebase
description: Generate a complete project snapshot (file tree, tech stack, API routes, data models, key functions) as JSON. Use when you need to quickly understand a project structure or when switching between models.
---

# miloya-codebase

Generate a complete project snapshot for quick understanding across model switches. Uses a Python script to analyze the project and outputs JSON to `{project}/repo/progress/miloya-codebase.json`.

## Commands

### `/miloya-codebase`
Generate a new project snapshot. Outputs JSON to conversation and saves to `{project}/repo/progress/miloya-codebase.json`.

### `/miloya-codebase refresh`
Force regenerate the snapshot, overwriting the existing file.

### `/miloya-codebase read`
Read and display the existing snapshot from `{project}/repo/progress/miloya-codebase.json`.

## How It Works

This skill uses `scripts/generate.py` to perform the analysis. The model should:

1. Locate the skill directory
2. Run the script with the current project path
3. Output the resulting JSON in the conversation

## Running the Script

### Step 1: Find the script

The script is located at: `{skill_dir}/scripts/generate.py`

### Step 2: Run the script

```bash
python {skill_dir}/scripts/generate.py <project_path>
```

For refresh mode:
```bash
python {skill_dir}/scripts/generate.py <project_path> --force
```

### Step 3: Read the output

The script outputs JSON to stdout. Read it and display in the conversation.

### Step 4: Read existing snapshot

To read an existing snapshot without regenerating:
```bash
cat {project}/repo/progress/miloya-codebase.json
```

## Snapshot Output Schema

```json
{
  "version": "1.0",
  "generatedAt": "2026-03-18T...",
  "projectPath": "/path/to/project",
  "summary": {
    "name": "项目名",
    "type": "web-api | frontend | monorepo | cli | ...",
    "techStack": ["React", "Node.js"],
    "entryPoints": ["src/index.ts"],
    "totalFiles": 234,
    "totalLines": 12840
  },
  "fileTree": {
    "src/": ["components/", "hooks/", "utils/"],
    "src/components/": ["Button.tsx", "Modal.tsx"]
  },
  "modules": {},
  "dependencies": {},
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

## Storage

**Path:** `{project}/repo/progress/miloya-codebase.json`

This file can be read by other models/tools to quickly understand the project without rescanning.

## Framework Detection

The script detects:
- **JavaScript/TypeScript**: React, Next.js, Vue, NestJS, Express, Angular, Svelte
- **Python**: FastAPI, Flask, Django
- **Go**: Gin
- **Java**: Spring Boot
- **Other**: Maven, Gradle, Rust (Cargo)
