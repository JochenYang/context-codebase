#!/usr/bin/env python3
"""
miloya-codebase: Generate project snapshot JSON
Usage: python generate.py <project_path> [--force]
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

EXCLUDE_DIRS = {
    'node_modules', '.git', 'dist', 'build', 'venv', '__pycache__',
    '.venv', 'env', '.env', 'coverage', '.next', '.nuxt', '.cache',
    '.svn', '.hg', 'vendor', 'target', 'out', '.idea', '.vscode'
}

ENTRY_PATTERNS = [
    'index.ts', 'index.js', 'main.ts', 'main.js', 'app.ts', 'app.js',
    'App.tsx', 'App.ts', 'App.jsx', 'main.go', 'main.py', 'manage.py',
    'index.html', 'main.go', 'main.rs', 'Cargo.toml', 'go.mod'
]

FRAMEWORK_DEPS = {
    'react': 'React', 'react-dom': 'React',
    'next': 'Next.js',
    'vue': 'Vue',
    '@nestjs/core': 'NestJS',
    'express': 'Express',
    'fastapi': 'FastAPI',
    'flask': 'Flask',
    '@angular/core': 'Angular',
    'svelte': 'Svelte',
    'django': 'Django',
    'spring-boot-starter-web': 'Spring Boot',
    'gin-gonic/gin': 'Gin',
}

ARCHITECTURE_PATTERNS = [
    (['controllers', 'routes'], 'MVC / Controller-based'),
    (['store', 'state', 'redux', 'zustand'], 'Flux / State management'),
    (['services', 'repositories'], 'Layered / Repository'),
    (['middleware'], 'Middleware-based'),
]


def scan_files(project_path: str) -> list[str]:
    """Recursively scan project files, excluding defined directories."""
    files = []
    base = Path(project_path)

    for root, dirs, filenames in os.walk(base):
        # Filter out excluded directories in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]

        for filename in filenames:
            if filename.startswith('.'):
                continue
            full_path = os.path.join(root, filename)
            files.append(full_path)

    return files


def detect_framework(files: list[str], project_path: str) -> list[str]:
    """Detect frameworks from package.json and file indicators."""
    frameworks = []
    base = Path(project_path)

    # Check package.json
    pkg_path = base / 'package.json'
    if pkg_path.exists():
        try:
            import json
            with open(pkg_path, 'r', encoding='utf-8') as f:
                pkg = json.load(f)
            deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
            for dep, name in FRAMEWORK_DEPS.items():
                if dep in deps and name not in frameworks:
                    frameworks.append(name)
        except Exception:
            pass

    # Check other files
    for f in files:
        fname = os.path.basename(f)
        if fname == 'manage.py' and 'Django' not in frameworks:
            frameworks.append('Django')
        elif fname == 'go.mod' and 'Go' not in frameworks:
            frameworks.append('Go')
        elif fname == 'Cargo.toml' and 'Rust' not in frameworks:
            frameworks.append('Rust')
        elif fname == 'pom.xml' and 'Maven' not in frameworks:
            frameworks.append('Maven')
        elif fname == 'build.gradle' and 'Gradle' not in frameworks:
            frameworks.append('Gradle')

    return frameworks


def find_entry_points(files: list[str], project_path: str) -> list[str]:
    """Find entry point files."""
    base = Path(project_path)
    entry_points = []

    for pattern in ENTRY_PATTERNS:
        for f in files:
            if os.path.basename(f) == pattern:
                rel = os.path.relpath(f, base)
                if rel not in entry_points:
                    entry_points.append(rel)

    return entry_points


def extract_api_routes(content: str, filename: str) -> list[dict]:
    """Extract API routes from file content."""
    routes = []
    ext = os.path.splitext(filename)[1]

    if ext in ['.ts', '.js', '.tsx', '.jsx']:
        # Express routes: router.get('/path', handler)
        express_pattern = r'router\.(get|post|put|delete|patch|head|options)\s*\(\s*[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(express_pattern, content, re.IGNORECASE):
            routes.append({
                'method': match.group(1).upper(),
                'path': match.group(2)
            })

        # NestJS decorators: @Get('path'), @Post('path')
        nestjs_pattern = r'@(Get|Post|Put|Delete|Patch|Head|Options)\s*\(\s*[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(nestjs_pattern, content, re.IGNORECASE):
            routes.append({
                'method': match.group(1).upper(),
                'path': match.group(2)
            })

        # FastAPI: @app.get('/path')
        fastapi_pattern = r'@(app|router)\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(fastapi_pattern, content, re.IGNORECASE):
            routes.append({
                'method': match.group(2).upper(),
                'path': match.group(3)
            })

    elif ext == '.py':
        # FastAPI/Python decorators
        fastapi_pattern = r'@(app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']'
        for match in re.finditer(fastapi_pattern, content):
            routes.append({
                'method': match.group(2).upper(),
                'path': match.group(3)
            })

        # Flask routes
        flask_pattern = r'@(app|blueprint)\.route\(\s*["\']([^"\']+)["\']'
        for match in re.finditer(flask_pattern, content):
            routes.append({
                'method': 'GET',
                'path': match.group(2)
            })

    return routes


def extract_data_models(content: str, filename: str) -> list[dict]:
    """Extract data models from file content."""
    models = []
    ext = os.path.splitext(filename)[1]

    if ext in ['.ts', '.tsx', '.js', '.jsx']:
        # TypeScript interfaces
        for match in re.finditer(r'(?:export\s+)?interface\s+(\w+)', content):
            models.append({'name': match.group(1), 'type': 'interface'})

        # TypeScript types
        for match in re.finditer(r'(?:export\s+)?type\s+(\w+)\s*=', content):
            models.append({'name': match.group(1), 'type': 'type'})

        # TypeScript classes
        for match in re.finditer(r'(?:export\s+)?class\s+(\w+)', content):
            models.append({'name': match.group(1), 'type': 'class'})

    elif ext == '.py':
        # Pydantic models
        for match in re.finditer(r'class\s+(\w+)\s*\(\s*BaseModel', content):
            models.append({'name': match.group(1), 'type': 'pydantic'})

        # Django models
        for match in re.finditer(r'class\s+(\w+)\s*\(\s*models\.Model', content):
            models.append({'name': match.group(1), 'type': 'django-model'})

        # SQLAlchemy models
        for match in re.finditer(r'class\s+(\w+)\s*\(\s*Base', content):
            models.append({'name': match.group(1), 'type': 'sqlalchemy'})

    return models


def extract_key_functions(content: str, filename: str) -> list[dict]:
    """Extract exported functions and classes."""
    functions = []
    ext = os.path.splitext(filename)[1]
    lines = content.split('\n')

    if ext in ['.ts', '.tsx', '.js', '.jsx']:
        # Function declarations
        for i, line in enumerate(lines):
            # export function name()
            match = re.search(r'export\s+(?:async\s+)?function\s+(\w+)', line)
            if match:
                functions.append({'name': match.group(1), 'file': filename, 'line': i + 1})
                continue

            # const/let name = async () => {} or const/let name = () => {}
            match = re.search(r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(', line)
            if match:
                name = match.group(1)
                if name not in ['if', 'for', 'while', 'switch', 'catch']:
                    functions.append({'name': name, 'file': filename, 'line': i + 1})

    elif ext == '.py':
        # def function_name
        for i, line in enumerate(lines):
            match = re.search(r'def\s+(\w+)\s*\(', line)
            if match:
                name = match.group(1)
                if not name.startswith('_'):
                    functions.append({'name': name, 'file': filename, 'line': i + 1})

    return functions


def infer_architecture(files: list[str], project_path: str) -> str:
    """Infer architecture from directory structure."""
    dirs = set()
    base = Path(project_path)

    for f in files:
        rel = os.path.relpath(f, base)
        parts = Path(rel).parts
        if len(parts) > 1:
            dirs.add(parts[0])

    dir_str = ' '.join(dirs)

    for patterns, arch in ARCHITECTURE_PATTERNS:
        if any(p in dir_str for p in patterns):
            return arch

    return 'Modular'


def build_file_tree(files: list[str], project_path: str) -> dict[str, list[str]]:
    """Build hierarchical file tree."""
    tree = {}
    base = Path(project_path)

    for f in files:
        rel = os.path.relpath(f, base)
        parts = Path(rel).parts

        if len(parts) == 1:
            continue

        dir_path = '/'.join(parts[:-1]) + '/'
        filename = parts[-1]

        if dir_path not in tree:
            tree[dir_path] = []
        tree[dir_path].append(filename)

    return tree


def generate_snapshot(project_path: str, force: bool = False) -> dict:
    """Generate complete project snapshot."""
    base = Path(project_path)
    output_dir = base / 'repo' / 'progress'
    output_file = output_dir / 'miloya-codebase.json'

    # Check if snapshot exists and not forcing
    if output_file.exists() and not force:
        with open(output_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    # Scan files
    files = scan_files(project_path)

    # Get relative paths for analysis
    rel_files = [os.path.relpath(f, base) for f in files]

    # Detect framework
    frameworks = detect_framework(files, project_path)

    # Find entry points
    entry_points = find_entry_points(files, project_path)

    # Count lines
    total_lines = 0
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8', errors='ignore') as fp:
                total_lines += len(fp.readlines())
        except Exception:
            pass

    # Extract API routes, data models, functions
    api_routes = []
    data_models = []
    key_functions = []

    for f in files:
        try:
            with open(f, 'r', encoding='utf-8', errors='ignore') as fp:
                content = fp.read()

            rel_path = os.path.relpath(f, base)
            for route in extract_api_routes(content, f):
                route['handler'] = rel_path
                api_routes.append(route)

            for model in extract_data_models(content, f):
                model['file'] = rel_path
                data_models.append(model)

            for func in extract_key_functions(content, f):
                key_functions.append(func)

        except Exception:
            pass

    # Deduplicate
    seen_routes = set()
    unique_routes = []
    for r in api_routes:
        key = f"{r['method']}:{r['path']}"
        if key not in seen_routes:
            seen_routes.add(key)
            unique_routes.append(r)

    seen_models = set()
    unique_models = []
    for m in data_models:
        key = f"{m['name']}:{m['type']}"
        if key not in seen_models:
            seen_models.add(key)
            unique_models.append(m)

    # Limit key functions
    key_functions = key_functions[:50]

    # Infer architecture
    architecture = infer_architecture(files, project_path)

    # Get project name
    pkg_path = base / 'package.json'
    if pkg_path.exists():
        try:
            with open(pkg_path, 'r', encoding='utf-8') as f:
                pkg = json.load(f)
            project_name = pkg.get('name', base.name)
        except Exception:
            project_name = base.name
    else:
        project_name = base.name

    # Build snapshot
    snapshot = {
        'version': '1.0',
        'generatedAt': datetime.now().isoformat(),
        'projectPath': str(base.resolve()),
        'summary': {
            'name': project_name,
            'type': ' + '.join(frameworks) if frameworks else 'unknown',
            'techStack': frameworks,
            'entryPoints': entry_points,
            'totalFiles': len(files),
            'totalLines': total_lines
        },
        'fileTree': build_file_tree(files, project_path),
        'modules': {},
        'dependencies': {},
        'apiRoutes': unique_routes,
        'dataModels': unique_models,
        'keyFunctions': key_functions,
        'architecture': architecture
    }

    # Save to file
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    print(f"Snapshot saved to: {output_file}", file=sys.stderr)
    return snapshot


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate.py <project_path> [--force]", file=sys.stderr)
        sys.exit(1)

    project_path = sys.argv[1]
    force = '--force' in sys.argv or '--refresh' in sys.argv

    if not os.path.isdir(project_path):
        print(f"Error: {project_path} is not a valid directory", file=sys.stderr)
        sys.exit(1)

    snapshot = generate_snapshot(project_path, force)

    # Output JSON to stdout
    print(json.dumps(snapshot, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
