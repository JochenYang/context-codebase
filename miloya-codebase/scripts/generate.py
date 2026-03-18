#!/usr/bin/env python3
"""
miloya-codebase: Generate project snapshot JSON
Usage: python generate.py <project_path> [--force]
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from context_engine.analyzers import AnalyzerRegistry
from context_engine.external_context import collect_external_context
from context_engine.graph import build_code_graph
from context_engine.retrieval import build_retrieval_artifacts, retrieve_chunks

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


SNAPSHOT_VERSION = '3.0'
INDEX_STATE_VERSION = '1.0'
MAX_TEXT_FILE_BYTES = 512 * 1024
MAX_IMPORTANT_FILES = 15
MAX_REPRESENTATIVE_SNIPPETS = 5
MAX_SNIPPET_LINES = 12
MAX_CHUNK_LINES = 60
MAX_CHUNK_PREVIEW_LINES = 16
MAX_CHUNK_CATALOG_ITEMS = 40

EXCLUDE_DIRS = {
    'node_modules', '.git', 'dist', 'build', 'venv', '__pycache__',
    '.venv', 'env', '.env', 'coverage', '.next', '.nuxt', '.cache',
    '.svn', '.hg', 'vendor', 'target', 'out', '.idea', '.vscode'
}

EXCLUDE_PATH_PREFIXES = {
    'repo/progress',
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

ARCHITECTURE_RULES = [
    ('all', ['controllers', 'routes'], 'MVC / Controller-based'),
    ('any', ['store', 'state', 'redux', 'zustand'], 'Flux / State management'),
    ('all', ['services', 'repositories'], 'Layered / Repository'),
    ('any', ['middleware'], 'Middleware-based'),
]

DEPENDENCY_FILES = {
    'package.json',
    'requirements.txt',
    'pyproject.toml',
    'go.mod',
    'Cargo.toml',
    'pom.xml',
}

MODULE_ROLE_HINTS = {
    'src': 'Primary application source code',
    'app': 'Application runtime and entry modules',
    'apps': 'Workspace applications in a monorepo',
    'packages': 'Shared packages in a monorepo',
    'components': 'UI components and presentation logic',
    'pages': 'Routable views or pages',
    'routes': 'HTTP or application routing definitions',
    'controllers': 'Request handlers and controller layer',
    'services': 'Business logic and orchestration',
    'repositories': 'Persistence and repository abstractions',
    'models': 'Data models and domain entities',
    'schemas': 'Schema definitions and validation',
    'store': 'State management',
    'state': 'State containers and reducers',
    'hooks': 'Reusable hooks and composition helpers',
    'utils': 'Utility helpers and shared functions',
    'lib': 'Reusable library code',
    'libs': 'Reusable library code',
    'api': 'API handlers and integration points',
    'scripts': 'Automation and maintenance scripts',
    'tests': 'Automated tests and fixtures',
    'docs': 'Project documentation and design notes',
    'config': 'Configuration files',
}

SOURCE_EXTENSIONS = {'.py', '.js', '.jsx', '.ts', '.tsx'}
MONOREPO_MARKERS = {'pnpm-workspace.yaml', 'turbo.json', 'nx.json'}
IMPORTANT_FILE_NAMES = {
    'package.json', 'pyproject.toml', 'requirements.txt', 'go.mod',
    'Cargo.toml', 'pom.xml', 'README.md', 'README_zh.md', 'tsconfig.json',
    'vite.config.ts', 'vite.config.js', 'next.config.js', 'next.config.mjs',
}
ANALYZER_REGISTRY = AnalyzerRegistry(SCRIPT_DIR / 'context_engine' / 'ts_ast_bridge.js')


def normalize_rel_path(path: str) -> str:
    return path.replace('\\', '/')


def is_excluded_path(rel_path: str) -> bool:
    normalized = normalize_rel_path(rel_path).strip('./')
    if not normalized:
        return False

    return any(
        normalized == prefix or normalized.startswith(prefix + '/')
        for prefix in EXCLUDE_PATH_PREFIXES
    )


def clean_content_for_parsing(content: str, ext: str) -> str:
    """Remove common comments to reduce regex false positives."""
    if ext == '.py':
        return re.sub(r'^\s*#.*$', '', content, flags=re.MULTILINE)

    if ext in ['.ts', '.tsx', '.js', '.jsx']:
        without_blocks = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        return re.sub(r'^\s*//.*$', '', without_blocks, flags=re.MULTILINE)

    return content


def extract_dependencies(project_path: str) -> dict[str, list[str]]:
    """Extract root-level dependency manifests for quick project understanding."""
    dependencies: dict[str, list[str]] = {}
    base = Path(project_path)

    pkg_path = base / 'package.json'
    if pkg_path.exists():
        try:
            with open(pkg_path, 'r', encoding='utf-8') as f:
                pkg = json.load(f)
            deps = {
                **pkg.get('dependencies', {}),
                **pkg.get('devDependencies', {}),
                **pkg.get('peerDependencies', {}),
            }
            if deps:
                dependencies['package.json'] = sorted(deps.keys())
        except Exception:
            pass

    requirements_path = base / 'requirements.txt'
    if requirements_path.exists():
        try:
            lines = []
            with open(requirements_path, 'r', encoding='utf-8') as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith('#'):
                        continue
                    name = re.split(r'[<>=!~\[]', line, maxsplit=1)[0].strip()
                    if name:
                        lines.append(name)
            if lines:
                dependencies['requirements.txt'] = sorted(set(lines))
        except Exception:
            pass

    pyproject_path = base / 'pyproject.toml'
    if pyproject_path.exists():
        try:
            if tomllib is not None:
                data = tomllib.loads(pyproject_path.read_text(encoding='utf-8'))
                names = []
                for item in data.get('project', {}).get('dependencies', []):
                    name = re.split(r'[<>=!~\[]', item, maxsplit=1)[0].strip()
                    if name:
                        names.append(name)
                names.extend(
                    key for key in data.get('tool', {}).get('poetry', {}).get('dependencies', {}).keys()
                    if key != 'python'
                )
            else:
                content = pyproject_path.read_text(encoding='utf-8')
                names = re.findall(r'^\s*["\']?([A-Za-z0-9_.-]+)\s*[<>=!~]', content, flags=re.MULTILINE)
            if names:
                dependencies['pyproject.toml'] = sorted(set(names))
        except Exception:
            pass

    go_mod_path = base / 'go.mod'
    if go_mod_path.exists():
        try:
            content = go_mod_path.read_text(encoding='utf-8')
            names = re.findall(r'^\s*(?:require\s+)?([A-Za-z0-9_.\-/]+)\s+v', content, flags=re.MULTILINE)
            if names:
                dependencies['go.mod'] = sorted(set(names))
        except Exception:
            pass

    cargo_path = base / 'Cargo.toml'
    if cargo_path.exists():
        try:
            content = cargo_path.read_text(encoding='utf-8')
            section_match = re.search(r'\[dependencies\](.*?)(?:\n\[|$)', content, flags=re.DOTALL)
            if section_match:
                names = re.findall(r'^\s*([A-Za-z0-9_-]+)\s*=', section_match.group(1), flags=re.MULTILINE)
                if names:
                    dependencies['Cargo.toml'] = sorted(set(names))
        except Exception:
            pass

    pom_path = base / 'pom.xml'
    if pom_path.exists():
        try:
            content = pom_path.read_text(encoding='utf-8')
            names = re.findall(r'<artifactId>([^<]+)</artifactId>', content)
            if names:
                dependencies['pom.xml'] = sorted(set(names))
        except Exception:
            pass

    return dependencies


def summarize_modules(files: list[str], project_path: str) -> dict[str, str]:
    """Summarize top-level modules to provide higher-signal context."""
    module_files: dict[str, list[str]] = {}
    base = Path(project_path)

    for file_path in files:
        rel = normalize_rel_path(os.path.relpath(file_path, base))
        parts = Path(rel).parts
        module_key = './' if len(parts) == 1 else f'{parts[0]}/'
        module_files.setdefault(module_key, []).append(rel)

    summaries: dict[str, str] = {}
    for module_key, rel_paths in sorted(module_files.items()):
        if module_key == './':
            summaries[module_key] = (
                f'Project root metadata and entry files; {len(rel_paths)} files'
            )
            continue

        module_name = module_key.rstrip('/').split('/')[-1].lower()
        role = MODULE_ROLE_HINTS.get(module_name, 'Project module')
        notable_areas = sorted({
            part
            for rel_path in rel_paths
            for part in Path(rel_path).parts[1:3]
            if part and '.' not in part
        })[:3]

        summary = f'{role}; {len(rel_paths)} files'
        if notable_areas:
            summary += f'; notable areas: {", ".join(notable_areas)}'
        summaries[module_key] = summary

    return summaries


def rank_key_function(func: dict, entry_points: list[str]) -> tuple[int, int, str, int]:
    """Prioritize functions near important files for downstream consumers."""
    file_path = normalize_rel_path(func['file'])
    file_name = Path(file_path).name.lower()
    path_score = 0

    if file_path in entry_points:
        path_score -= 40
    if any(token in file_path.lower() for token in ['route', 'controller', 'service', 'api']):
        path_score -= 20
    if file_name.startswith(('main', 'app', 'index')):
        path_score -= 10
    if '/tests/' in file_path.lower() or file_name.startswith('test_') or file_name.endswith('_test.py'):
        path_score += 40
    if file_path.lower().endswith('.md'):
        path_score += 20

    return (path_score, func['line'], file_path, len(func['name']))


def infer_project_type(files: list[str], project_path: str, frameworks: list[str]) -> str:
    """Infer a readable project type for the summary."""
    base = Path(project_path)
    file_names = {Path(file_path).name for file_path in files}

    if any(marker in file_names for marker in MONOREPO_MARKERS):
        return 'Monorepo'
    if 'package.json' in file_names and any(name in frameworks for name in ['React', 'Next.js', 'Vue', 'Angular', 'Svelte']):
        return 'Frontend Application'
    if any(name in frameworks for name in ['Express', 'NestJS', 'FastAPI', 'Flask', 'Django', 'Spring Boot', 'Gin']):
        return 'Backend Service'
    if 'scripts' in {part for file_path in files for part in Path(normalize_rel_path(os.path.relpath(file_path, base))).parts[:-1]}:
        return 'Tooling / Automation'
    if (base / 'package.json').exists():
        return 'Node.js Project'
    if (base / 'pyproject.toml').exists() or (base / 'requirements.txt').exists():
        return 'Python Project'
    return 'unknown'


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def detect_language(path: str) -> str | None:
    return LANGUAGE_BY_EXTENSION.get(Path(path).suffix.lower())


LANGUAGE_BY_EXTENSION = {
    '.py': 'Python',
    '.js': 'JavaScript',
    '.jsx': 'JavaScript',
    '.ts': 'TypeScript',
    '.tsx': 'TypeScript',
    '.go': 'Go',
    '.rs': 'Rust',
    '.java': 'Java',
    '.json': 'JSON',
    '.md': 'Markdown',
    '.toml': 'TOML',
    '.yaml': 'YAML',
    '.yml': 'YAML',
    '.xml': 'XML',
}

TEXT_EXTENSIONS = set(LANGUAGE_BY_EXTENSION) | {'.txt', '.ini', '.cfg', '.conf', '.sh', '.ps1'}


def read_text_file(path: Path) -> str | None:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return None
    if path.stat().st_size > MAX_TEXT_FILE_BYTES:
        return None

    try:
        return path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return None
    except Exception:
        return None


def build_source_fingerprint(files: list[str], project_path: str) -> str:
    base = Path(project_path)
    digest = hashlib.sha256()

    for file_path in files:
        path_obj = Path(file_path)
        rel_path = normalize_rel_path(os.path.relpath(file_path, base))
        stat = path_obj.stat()
        digest.update(f'{rel_path}:{stat.st_size}:{stat.st_mtime_ns}\n'.encode('utf-8'))

    return digest.hexdigest()


def build_file_signatures(files: list[str], project_path: str) -> dict[str, dict]:
    base = Path(project_path)
    signatures = {}

    for file_path in files:
        path_obj = Path(file_path)
        rel_path = normalize_rel_path(os.path.relpath(file_path, base))
        stat = path_obj.stat()
        signatures[rel_path] = {
            'sizeBytes': stat.st_size,
            'mtimeNs': stat.st_mtime_ns,
        }

    return signatures


def get_newest_source_mtime(files: list[str]) -> str | None:
    if not files:
        return None

    newest = max(Path(file_path).stat().st_mtime for file_path in files)
    return datetime.fromtimestamp(newest, tz=timezone.utc).replace(microsecond=0).isoformat()


def load_readme_summary(project_path: str) -> str | None:
    for file_name in ['README.md', 'README_zh.md']:
        path = Path(project_path) / file_name
        if not path.exists():
            continue

        content = read_text_file(path)
        if not content:
            continue

        for line in content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                return stripped[:240]

    return None


def run_git_command(project_path: str, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ['git', *args],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return None

    return completed.stdout.strip() or None


def collect_git_context(project_path: str) -> dict[str, str | None]:
    return {
        'branch': run_git_command(project_path, ['rev-parse', '--abbrev-ref', 'HEAD']),
        'commit': run_git_command(project_path, ['rev-parse', 'HEAD']),
        'status': 'dirty' if run_git_command(project_path, ['status', '--porcelain']) else 'clean',
    }


def extract_imports(content: str, language: str | None) -> list[str]:
    imports = []

    if language in ['TypeScript', 'JavaScript']:
        imports.extend(re.findall(r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]', content))
        imports.extend(re.findall(r'require\(\s*[\'"]([^\'"]+)[\'"]\s*\)', content))
    elif language == 'Python':
        imports.extend(re.findall(r'^\s*from\s+([A-Za-z0-9_\.]+)\s+import', content, flags=re.MULTILINE))
        imports.extend(re.findall(r'^\s*import\s+([A-Za-z0-9_\.]+)', content, flags=re.MULTILINE))

    return sorted(set(imports))[:8]


def extract_exports(content: str, language: str | None) -> list[str]:
    exports = []

    if language in ['TypeScript', 'JavaScript']:
        exports.extend(re.findall(r'export\s+(?:async\s+)?function\s+(\w+)', content))
        exports.extend(re.findall(r'export\s+class\s+(\w+)', content))
        exports.extend(re.findall(r'export\s+(?:const|let|var)\s+(\w+)', content))
        exports.extend(re.findall(r'export\s+interface\s+(\w+)', content))
        exports.extend(re.findall(r'export\s+type\s+(\w+)', content))
    elif language == 'Python':
        exports.extend(re.findall(r'^\s*def\s+([A-Za-z_]\w*)\s*\(', content, flags=re.MULTILINE))
        exports.extend(re.findall(r'^\s*class\s+([A-Za-z_]\w*)', content, flags=re.MULTILINE))

    return sorted(set(name for name in exports if not name.startswith('_')))[:8]


def collect_file_records(files: list[str], project_path: str) -> tuple[list[dict], int]:
    base = Path(project_path)
    records = []
    total_lines = 0

    for file_path in files:
        path_obj = Path(file_path)
        rel_path = normalize_rel_path(os.path.relpath(file_path, base))
        language = detect_language(rel_path)
        content = read_text_file(path_obj)
        line_count = len(content.splitlines()) if content is not None else 0
        total_lines += line_count
        analysis = ANALYZER_REGISTRY.analyze_file(content, rel_path, project_path)

        records.append({
            'path': rel_path,
            'fileName': path_obj.name,
            'language': language,
            'lineCount': line_count,
            'sizeBytes': path_obj.stat().st_size,
            'content': content,
            'imports': analysis.imports,
            'exports': analysis.exports,
            'apiRoutes': analysis.api_routes,
            'dataModels': analysis.data_models,
            'keyFunctions': analysis.key_functions,
            'frameworkHints': analysis.framework_hints,
            'analysisEngine': analysis.engine,
            'analysisConfidence': analysis.confidence,
            'analysisWarnings': analysis.warnings,
        })

    return records, total_lines


def detect_workspace(file_records: list[dict], project_path: str, dependencies: dict[str, list[str]]) -> dict:
    project_name = Path(project_path).name
    packages = []

    manifest_records = [record for record in file_records if record['fileName'] in DEPENDENCY_FILES]
    for record in sorted(manifest_records, key=lambda item: item['path']):
        package_path = './' if '/' not in record['path'] else normalize_rel_path(str(Path(record['path']).parent)) + '/'
        role = 'root'
        for candidate in ['apps', 'packages', 'services', 'libs']:
            if package_path.startswith(candidate + '/'):
                role = candidate[:-1] if candidate.endswith('s') else candidate
                break

        package_name = project_name if package_path == './' else Path(package_path.rstrip('/')).name
        if record['fileName'] == 'package.json':
            try:
                pkg = json.loads((Path(project_path) / record['path']).read_text(encoding='utf-8'))
                package_name = pkg.get('name', package_name)
            except Exception:
                pass

        package_records = [
            item for item in file_records
            if item['path'] == record['path'] or package_path == './' or item['path'].startswith(package_path)
        ]
        entry_points = [
            item['path'] for item in package_records
            if item['fileName'] in ENTRY_PATTERNS
        ][:5]

        packages.append({
            'name': package_name,
            'path': package_path,
            'manifest': record['path'],
            'role': role,
            'entryPoints': entry_points,
            'dependencyCount': len(dependencies.get(record['path'], [])),
            'fileCount': len(package_records),
        })

    root_manifests = sorted([
        record['path'] for record in manifest_records
        if '/' not in record['path']
    ])
    is_monorepo = any(package['path'].startswith(('apps/', 'packages/')) for package in packages)

    return {
        'isMonorepo': is_monorepo,
        'rootManifests': root_manifests,
        'packages': packages,
    }


def infer_file_role(record: dict) -> str:
    path = record['path'].lower()
    file_name = record['fileName'].lower()

    if file_name in ['readme.md', 'readme_zh.md']:
        return 'Project overview'
    if file_name in DEPENDENCY_FILES:
        return 'Dependency manifest'
    if 'route' in path or 'controller' in path or record['apiRoutes']:
        return 'API surface'
    if 'service' in path:
        return 'Business logic'
    if 'model' in path or 'schema' in path or record['dataModels']:
        return 'Data model'
    if 'config' in path or file_name.endswith(('.json', '.toml')):
        return 'Configuration'
    if 'test' in path:
        return 'Test/support'
    if 'script' in path:
        return 'Automation'
    return 'Implementation'


def score_file(record: dict, entry_points: list[str], root_manifests: set[str]) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    path = record['path']
    lower_path = path.lower()

    if path in entry_points:
        score += 110
        reasons.append('entry point')
    if record['fileName'] in IMPORTANT_FILE_NAMES:
        score += 90
        reasons.append('root/config manifest')
    if path in root_manifests:
        score += 80
        reasons.append('dependency manifest')
    if record['apiRoutes']:
        score += 60 + len(record['apiRoutes']) * 5
        reasons.append(f'{len(record["apiRoutes"])} API routes')
    if record['dataModels']:
        score += 45 + len(record['dataModels']) * 4
        reasons.append(f'{len(record["dataModels"])} data models')
    if record['exports']:
        score += 30 + len(record['exports']) * 2
        reasons.append(f'{len(record["exports"])} exports')
    if len(record['imports']) > 3:
        score += 10
        reasons.append('integration-heavy file')
    if record['keyFunctions']:
        score += min(30, len(record['keyFunctions']) * 2)
        reasons.append(f'{len(record["keyFunctions"])} named functions')
    if record['lineCount']:
        score += min(20, record['lineCount'] // 50)

    if any(token in lower_path for token in ['route', 'controller', 'service', 'model', 'schema', 'config', 'main', 'app', 'index']):
        score += 8

    if '/tests/' in lower_path or record['fileName'].startswith('test_') or record['fileName'].endswith('_test.py'):
        score -= 40
        reasons.append('test/support file')
    if lower_path.endswith('.md') and record['fileName'] not in ['README.md', 'README_zh.md']:
        score -= 15
        reasons.append('documentation file')

    return score, reasons


def build_important_files(file_records: list[dict], entry_points: list[str], workspace: dict) -> list[dict]:
    root_manifest_set = set(workspace.get('rootManifests', []))
    scored_files = []

    for record in file_records:
        score, reasons = score_file(record, entry_points, root_manifest_set)
        if score <= 0:
            continue
        scored_files.append((score, record, reasons))

    scored_files.sort(key=lambda item: (-item[0], item[1]['path']))
    important_files = []

    for score, record, reasons in scored_files[:MAX_IMPORTANT_FILES]:
        important_files.append({
            'path': record['path'],
            'role': infer_file_role(record),
            'language': record['language'],
            'lines': record['lineCount'],
            'imports': record['imports'],
            'exports': record['exports'],
            'score': score,
            'whyImportant': ', '.join(dict.fromkeys(reasons))[:220] or 'high-signal project file',
        })

    return important_files


def choose_anchor_line(record: dict) -> tuple[int, str]:
    content = record.get('content') or ''
    lines = content.splitlines()

    if record.get('language') == 'Markdown':
        for line_number, line in enumerate(lines, start=1):
            if line.strip() and not line.strip().startswith('#'):
                return line_number, 'document summary'
        return 1, 'document summary'

    patterns = [
        (r'router\.(get|post|put|delete|patch|head|options)\s*\(', 'route definition'),
        (r'^\s*@(Get|Post|Put|Delete|Patch|Head|Options)\s*\(', 'route decorator'),
        (r'^\s*@(app|router)\.(get|post|put|delete|patch)\s*\(', 'route decorator'),
        (r'(?:export\s+)?interface\s+\w+', 'data model'),
        (r'(?:export\s+)?class\s+\w+', 'class definition'),
        (r'export\s+(?:async\s+)?function\s+\w+', 'exported function'),
        (r'^\s*def\s+\w+\s*\(', 'function definition'),
        (r'^\s*class\s+\w+', 'class definition'),
    ]

    for line_number, line in enumerate(lines, start=1):
        for pattern, reason in patterns:
            if re.search(pattern, line):
                return line_number, reason

    for line_number, line in enumerate(lines, start=1):
        if line.strip():
            return line_number, 'file opening'

    return 1, 'file opening'


def build_representative_snippets(file_records: list[dict], important_files: list[dict]) -> list[dict]:
    record_map = {record['path']: record for record in file_records}
    snippets = []

    for important in important_files:
        record = record_map.get(important['path'])
        if not record or not record.get('content'):
            continue

        lines = record['content'].splitlines()
        if not lines:
            continue

        anchor_line, reason = choose_anchor_line(record)
        start = max(1, anchor_line - 2)
        end = min(len(lines), start + MAX_SNIPPET_LINES - 1)
        snippet = '\n'.join(lines[start - 1:end]).strip()
        if not snippet:
            continue

        snippets.append({
            'path': record['path'],
            'reason': reason,
            'startLine': start,
            'endLine': end,
            'snippet': snippet,
        })

        if len(snippets) >= MAX_REPRESENTATIVE_SNIPPETS:
            break

    return snippets


def build_context_hints(summary: dict, workspace: dict, important_files: list[dict], modules: dict[str, str]) -> dict:
    read_order = [item['path'] for item in important_files[:8]]

    return {
        'readOrder': read_order,
        'recommendedStart': read_order[0] if read_order else None,
        'highSignalAreas': list(modules.keys())[:5],
        'monorepo': workspace.get('isMonorepo', False),
        'description': summary.get('description'),
    }


def build_analysis_metadata(file_records: list[dict]) -> dict:
    engines_by_language = {}
    file_counts_by_engine = Counter()
    warnings = []

    for record in file_records:
        engine = record.get('analysisEngine') or 'none'
        file_counts_by_engine[engine] += 1
        language = record.get('language')
        if language and language not in engines_by_language and engine != 'none':
            engines_by_language[language] = engine
        warnings.extend(record.get('analysisWarnings', []))

    return {
        'engines': engines_by_language,
        'filesByEngine': dict(sorted(file_counts_by_engine.items())),
        'warnings': sorted(set(warnings)),
    }


def make_chunk_id(path: str, kind: str, start_line: int, end_line: int) -> str:
    digest = hashlib.sha1(f'{path}:{kind}:{start_line}:{end_line}'.encode('utf-8')).hexdigest()[:12]
    return f'{path}#{kind}:{start_line}-{end_line}:{digest}'


def clip_chunk_preview(lines: list[str], start_line: int, end_line: int) -> str:
    preview_end = min(end_line, start_line + MAX_CHUNK_PREVIEW_LINES - 1)
    return '\n'.join(lines[start_line - 1:preview_end]).strip()


def build_chunks(file_records: list[dict]) -> list[dict]:
    chunks = []

    for record in file_records:
        content = record.get('content')
        if not content:
            continue

        lines = content.splitlines()
        if not lines:
            continue

        if record['language'] == 'Markdown':
            chunks.extend(build_markdown_chunks(record, lines))
            continue

        anchor_lines: list[tuple[int, str, list[str]]] = []
        for route in record.get('apiRoutes', []):
            line_no = route.get('line')
            if line_no:
                anchor_lines.append((line_no, 'route', [route.get('method', ''), route.get('path', '')]))
        for model in record.get('dataModels', []):
            line_no = model.get('line')
            if line_no:
                anchor_lines.append((line_no, 'model', [model.get('type', ''), model.get('name', '')]))
        for func in record.get('keyFunctions', []):
            anchor_lines.append((func['line'], 'function', [func['name']]))

        if anchor_lines:
            seen_ranges = set()
            for line_no, kind, signals in sorted(anchor_lines, key=lambda item: item[0]):
                start_line = max(1, line_no - 3)
                end_line = min(len(lines), start_line + MAX_CHUNK_LINES - 1)
                range_key = (start_line, end_line)
                if range_key in seen_ranges:
                    continue
                seen_ranges.add(range_key)
                chunks.append({
                    'id': make_chunk_id(record['path'], kind, start_line, end_line),
                    'path': record['path'],
                    'kind': kind,
                    'language': record['language'],
                    'startLine': start_line,
                    'endLine': end_line,
                    'signals': [signal for signal in signals if signal],
                    'preview': clip_chunk_preview(lines, start_line, end_line),
                    'analysisEngine': record.get('analysisEngine'),
                    'analysisConfidence': record.get('analysisConfidence'),
                })
            continue

        window_start = 1
        window_index = 0
        while window_start <= len(lines):
            window_end = min(len(lines), window_start + MAX_CHUNK_LINES - 1)
            chunks.append({
                'id': make_chunk_id(record['path'], f'window-{window_index}', window_start, window_end),
                'path': record['path'],
                'kind': 'window',
                'language': record['language'],
                'startLine': window_start,
                'endLine': window_end,
                'signals': [],
                'preview': clip_chunk_preview(lines, window_start, window_end),
                'analysisEngine': record.get('analysisEngine'),
                'analysisConfidence': record.get('analysisConfidence'),
            })
            window_index += 1
            window_start = window_end + 1

    return chunks


def build_markdown_chunks(record: dict, lines: list[str]) -> list[dict]:
    chunks = []
    heading_indexes = [
        index + 1
        for index, line in enumerate(lines)
        if line.strip().startswith('#')
    ]

    if not heading_indexes:
        return [{
            'id': make_chunk_id(record['path'], 'document', 1, min(len(lines), MAX_CHUNK_LINES)),
            'path': record['path'],
            'kind': 'document',
            'language': record['language'],
            'startLine': 1,
            'endLine': min(len(lines), MAX_CHUNK_LINES),
            'signals': ['documentation'],
            'preview': clip_chunk_preview(lines, 1, min(len(lines), MAX_CHUNK_LINES)),
            'analysisEngine': record.get('analysisEngine'),
            'analysisConfidence': record.get('analysisConfidence'),
        }]

    for index, start_line in enumerate(heading_indexes):
        next_heading = heading_indexes[index + 1] - 1 if index + 1 < len(heading_indexes) else len(lines)
        end_line = min(next_heading, start_line + MAX_CHUNK_LINES - 1)
        heading = lines[start_line - 1].strip().lstrip('#').strip()
        chunks.append({
            'id': make_chunk_id(record['path'], 'section', start_line, end_line),
            'path': record['path'],
            'kind': 'section',
            'language': record['language'],
            'startLine': start_line,
            'endLine': end_line,
            'signals': [heading] if heading else ['documentation'],
            'preview': clip_chunk_preview(lines, start_line, end_line),
            'analysisEngine': record.get('analysisEngine'),
            'analysisConfidence': record.get('analysisConfidence'),
        })

    return chunks


def load_existing_index_state(index_state_file: Path) -> dict | None:
    if not index_state_file.exists():
        return None

    try:
        return json.loads(index_state_file.read_text(encoding='utf-8'))
    except Exception:
        return None


def diff_index_state(previous_state: dict | None, current_signatures: dict[str, dict]) -> dict:
    previous_files = (previous_state or {}).get('files', {})
    previous_paths = set(previous_files.keys())
    current_paths = set(current_signatures.keys())

    new_paths = current_paths - previous_paths
    removed_paths = previous_paths - current_paths
    shared_paths = current_paths & previous_paths
    changed_paths = {
        path for path in shared_paths
        if {
            'sizeBytes': previous_files.get(path, {}).get('sizeBytes'),
            'mtimeNs': previous_files.get(path, {}).get('mtimeNs'),
        } != current_signatures.get(path, {})
    }
    unchanged_paths = shared_paths - changed_paths

    return {
        'newFiles': len(new_paths),
        'changedFiles': len(changed_paths),
        'removedFiles': len(removed_paths),
        'unchangedFiles': len(unchanged_paths),
    }


def build_chunk_catalog(chunks: list[dict], important_files: list[dict]) -> list[dict]:
    important_paths = {item['path']: index for index, item in enumerate(important_files)}

    ranked_chunks = sorted(
        chunks,
        key=lambda item: (
            important_paths.get(item['path'], 999),
            0 if item['kind'] in {'route', 'model', 'function', 'section'} else 1,
            item['path'],
            item['startLine'],
        ),
    )

    catalog = []
    for chunk in ranked_chunks[:MAX_CHUNK_CATALOG_ITEMS]:
        catalog.append({
            'id': chunk['id'],
            'path': chunk['path'],
            'kind': chunk['kind'],
            'language': chunk['language'],
            'startLine': chunk['startLine'],
            'endLine': chunk['endLine'],
            'signals': chunk['signals'],
            'preview': chunk['preview'],
        })
    return catalog


def build_index_metadata(
    base: Path,
    index_state_file: Path,
    previous_state: dict | None,
    current_signatures: dict[str, dict],
    chunks: list[dict],
    reusing_snapshot: bool,
) -> dict:
    delta = diff_index_state(previous_state, current_signatures)
    return {
        'stateVersion': INDEX_STATE_VERSION,
        'statePath': normalize_rel_path(str(index_state_file.relative_to(base))),
        'fileCount': len(current_signatures),
        'chunkCount': len(chunks),
        'reusedSnapshot': reusing_snapshot,
        'delta': delta,
    }


def save_index_state(
    index_state_file: Path,
    current_signatures: dict[str, dict],
    chunks: list[dict],
    file_records: list[dict],
    source_fingerprint: str,
) -> None:
    chunk_ids_by_path: dict[str, list[str]] = {}
    for chunk in chunks:
        chunk_ids_by_path.setdefault(chunk['path'], []).append(chunk['id'])

    files_payload = {}
    for record in file_records:
        files_payload[record['path']] = {
            **current_signatures.get(record['path'], {}),
            'language': record['language'],
            'lineCount': record['lineCount'],
            'analysisEngine': record.get('analysisEngine'),
            'analysisConfidence': record.get('analysisConfidence'),
            'chunkIds': chunk_ids_by_path.get(record['path'], []),
        }

    payload = {
        'version': INDEX_STATE_VERSION,
        'generatedAt': utc_now_iso(),
        'sourceFingerprint': source_fingerprint,
        'files': files_payload,
        'chunks': chunks,
    }

    index_state_file.parent.mkdir(parents=True, exist_ok=True)
    index_state_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')


def load_existing_snapshot(output_file: Path) -> dict | None:
    if not output_file.exists():
        return None

    try:
        return json.loads(output_file.read_text(encoding='utf-8'))
    except Exception:
        return None


def summarize_modules_from_records(file_records: list[dict]) -> dict[str, str]:
    module_stats = {}

    for record in file_records:
        parts = Path(record['path']).parts
        module_key = './' if len(parts) == 1 else f'{parts[0]}/'
        stats = module_stats.setdefault(module_key, {
            'files': 0,
            'lines': 0,
            'routes': 0,
            'models': 0,
            'functions': 0,
            'languages': Counter(),
            'areas': set(),
        })

        stats['files'] += 1
        stats['lines'] += record['lineCount']
        stats['routes'] += len(record['apiRoutes'])
        stats['models'] += len(record['dataModels'])
        stats['functions'] += len(record['keyFunctions'])
        if record['language']:
            stats['languages'][record['language']] += 1
        for part in parts[1:3]:
            if '.' not in part:
                stats['areas'].add(part)

    summaries = {}
    for module_key, stats in sorted(module_stats.items()):
        if module_key == './':
            summaries[module_key] = (
                f'Project root metadata and entry files; {stats["files"]} files; '
                f'{stats["lines"]} lines'
            )
            continue

        module_name = module_key.rstrip('/').split('/')[-1].lower()
        role = MODULE_ROLE_HINTS.get(module_name, 'Project module')
        primary_language = stats['languages'].most_common(1)[0][0] if stats['languages'] else 'mixed'
        summary = (
            f'{role}; {stats["files"]} files; {stats["lines"]} lines; '
            f'primary language: {primary_language}'
        )
        if stats['routes']:
            summary += f'; routes: {stats["routes"]}'
        if stats['models']:
            summary += f'; models: {stats["models"]}'
        if stats['functions']:
            summary += f'; functions: {stats["functions"]}'
        if stats['areas']:
            summary += f'; notable areas: {", ".join(sorted(stats["areas"])[:3])}'
        summaries[module_key] = summary

    return summaries


def build_summary(
    project_path: str,
    files: list[str],
    frameworks: list[str],
    entry_points: list[str],
    total_lines: int,
    file_records: list[dict],
    important_files: list[dict],
) -> dict:
    pkg_path = Path(project_path) / 'package.json'
    if pkg_path.exists():
        try:
            pkg = json.loads(pkg_path.read_text(encoding='utf-8'))
            project_name = pkg.get('name', Path(project_path).name)
        except Exception:
            project_name = Path(project_path).name
    else:
        project_name = Path(project_path).name

    language_counter = Counter(record['language'] for record in file_records if record['language'])
    dominant_languages = [
        {'language': language, 'files': count}
        for language, count in language_counter.most_common(5)
    ]

    return {
        'name': project_name,
        'type': infer_project_type(files, project_path, frameworks),
        'description': load_readme_summary(project_path),
        'techStack': frameworks,
        'entryPoints': entry_points,
        'totalFiles': len(files),
        'totalLines': total_lines,
        'dominantLanguages': dominant_languages,
        'importantPaths': [item['path'] for item in important_files[:8]],
    }


def build_focus_context_pack(
    query: str,
    task: str,
    snapshot: dict,
    index_state: dict | None,
) -> dict | None:
    if not query or not index_state:
        return None

    chunks = index_state.get('chunks', [])
    if not chunks:
        return None

    graph = snapshot.get('graph', {})
    important_files = snapshot.get('importantFiles', [])
    external_context = snapshot.get('externalContext', {})
    important_ranks = {item['path']: index for index, item in enumerate(important_files)}
    recent_changed = set(external_context.get('recentChangedFiles', []))
    file_dependency_map = {
        item['path']: item['dependsOn']
        for item in graph.get('fileDependencies', [])
    }
    matches = retrieve_chunks(
        query=query,
        chunks=chunks,
        important_ranks=important_ranks,
        recent_changed=recent_changed,
        file_dependency_map=file_dependency_map,
        task=task,
        limit=12,
    )
    return {
        'task': task,
        'query': query,
        'matches': matches,
        'files': sorted(dict.fromkeys(match['path'] for match in matches)),
    }


def scan_files(project_path: str) -> list[str]:
    """Recursively scan project files, excluding defined directories."""
    files = []
    base = Path(project_path)

    for root, dirs, filenames in os.walk(base):
        rel_root = os.path.relpath(root, base)
        rel_root = '' if rel_root == '.' else normalize_rel_path(rel_root)

        # Filter out excluded directories in-place
        filtered_dirs = []
        for dir_name in dirs:
            if dir_name in EXCLUDE_DIRS or dir_name.startswith('.'):
                continue
            rel_dir = dir_name if not rel_root else f'{rel_root}/{dir_name}'
            if is_excluded_path(rel_dir):
                continue
            filtered_dirs.append(dir_name)
        dirs[:] = filtered_dirs

        for filename in filenames:
            if filename.startswith('.'):
                continue
            full_path = os.path.join(root, filename)
            rel_path = normalize_rel_path(os.path.relpath(full_path, base))
            if is_excluded_path(rel_path):
                continue
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
    cleaned = clean_content_for_parsing(content, ext)

    if ext in ['.ts', '.js', '.tsx', '.jsx']:
        # Express routes: router.get('/path', handler)
        express_pattern = r'router\.(get|post|put|delete|patch|head|options)\s*\(\s*[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(express_pattern, cleaned, re.IGNORECASE):
            routes.append({
                'method': match.group(1).upper(),
                'path': match.group(2)
            })

        # NestJS decorators: @Get('path'), @Post('path')
        nestjs_pattern = r'^\s*@(Get|Post|Put|Delete|Patch|Head|Options)\s*\(\s*[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(nestjs_pattern, cleaned, re.IGNORECASE | re.MULTILINE):
            routes.append({
                'method': match.group(1).upper(),
                'path': match.group(2)
            })

        # FastAPI: @app.get('/path')
        fastapi_pattern = r'^\s*@(app|router)\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(fastapi_pattern, cleaned, re.IGNORECASE | re.MULTILINE):
            routes.append({
                'method': match.group(2).upper(),
                'path': match.group(3)
            })

    elif ext == '.py':
        # FastAPI/Python decorators
        fastapi_pattern = r'^\s*@(app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']'
        for match in re.finditer(fastapi_pattern, cleaned, flags=re.MULTILINE):
            routes.append({
                'method': match.group(2).upper(),
                'path': match.group(3)
            })

        # Flask routes
        flask_pattern = (
            r'^\s*@(app|blueprint)\.route\(\s*["\']([^"\']+)["\']'
            r'(?P<args>[^)]*)\)'
        )
        for match in re.finditer(flask_pattern, cleaned, flags=re.MULTILINE):
            methods = re.search(r'methods\s*=\s*\[([^\]]+)\]', match.group('args'))
            if not methods:
                routes.append({
                    'method': 'GET',
                    'path': match.group(2)
                })
                continue

            for raw_method in re.findall(r'["\']([A-Za-z]+)["\']', methods.group(1)):
                routes.append({
                    'method': raw_method.upper(),
                    'path': match.group(2)
                })

    return routes


def extract_data_models(content: str, filename: str) -> list[dict]:
    """Extract data models from file content."""
    models = []
    ext = os.path.splitext(filename)[1]
    cleaned = clean_content_for_parsing(content, ext)

    if ext in ['.ts', '.tsx', '.js', '.jsx']:
        # TypeScript interfaces
        for match in re.finditer(r'(?:export\s+)?interface\s+(\w+)', cleaned):
            models.append({'name': match.group(1), 'type': 'interface'})

        # TypeScript types
        for match in re.finditer(r'(?:export\s+)?type\s+(\w+)\s*=', cleaned):
            models.append({'name': match.group(1), 'type': 'type'})

        # TypeScript classes
        for match in re.finditer(r'(?:export\s+)?class\s+(\w+)', cleaned):
            models.append({'name': match.group(1), 'type': 'class'})

    elif ext == '.py':
        # Pydantic models
        for match in re.finditer(r'class\s+(\w+)\s*\(\s*BaseModel', cleaned):
            models.append({'name': match.group(1), 'type': 'pydantic'})

        # Django models
        for match in re.finditer(r'class\s+(\w+)\s*\(\s*models\.Model', cleaned):
            models.append({'name': match.group(1), 'type': 'django-model'})

        # SQLAlchemy models
        for match in re.finditer(r'class\s+(\w+)\s*\(\s*Base', cleaned):
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
        rel = normalize_rel_path(os.path.relpath(f, base))
        parts = Path(rel).parts
        for part in parts[:-1]:
            dirs.add(part.lower())

    for mode, patterns, arch in ARCHITECTURE_RULES:
        if mode == 'all' and all(pattern in dirs for pattern in patterns):
            return arch
        if mode == 'any' and any(pattern in dirs for pattern in patterns):
            return arch

    return 'Modular'


def build_file_tree(files: list[str], project_path: str) -> dict[str, list[str]]:
    """Build hierarchical file tree."""
    tree = {}
    base = Path(project_path)

    for f in files:
        rel = normalize_rel_path(os.path.relpath(f, base))
        parts = Path(rel).parts

        if len(parts) == 1:
            tree.setdefault('./', []).append(parts[0])
            continue

        dir_path = '/'.join(parts[:-1]) + '/'
        filename = parts[-1]

        if dir_path not in tree:
            tree[dir_path] = []
        tree[dir_path].append(filename)

    return {
        dir_path: sorted(filenames)
        for dir_path, filenames in sorted(tree.items())
    }


def generate_snapshot(project_path: str, force: bool = False) -> dict:
    """Generate complete project snapshot."""
    base = Path(project_path)
    output_dir = base / 'repo' / 'progress'
    output_file = output_dir / 'miloya-codebase.json'
    index_state_file = output_dir / 'miloya-codebase.index.json'

    # Scan files
    files = scan_files(project_path)
    source_fingerprint = build_source_fingerprint(files, project_path)
    current_signatures = build_file_signatures(files, project_path)
    newest_source_mtime = get_newest_source_mtime(files)
    existing_snapshot = load_existing_snapshot(output_file)
    existing_index_state = load_existing_index_state(index_state_file)

    if (
        existing_snapshot
        and not force
        and existing_snapshot.get('version') == SNAPSHOT_VERSION
        and existing_snapshot.get('sourceFingerprint') == source_fingerprint
    ):
        freshness = existing_snapshot.setdefault('freshness', {})
        freshness['stale'] = False
        freshness['reason'] = 'source fingerprint unchanged'
        freshness['newestSourceMtime'] = newest_source_mtime
        existing_snapshot['index'] = build_index_metadata(
            base,
            index_state_file,
            existing_index_state,
            current_signatures,
            (existing_index_state or {}).get('chunks', []),
            reusing_snapshot=True,
        )
        existing_snapshot['chunkCatalog'] = build_chunk_catalog(
            (existing_index_state or {}).get('chunks', []),
            existing_snapshot.get('importantFiles', []),
        )
        return existing_snapshot

    file_records, total_lines = collect_file_records(files, project_path)
    # Detect framework
    frameworks = detect_framework(files, project_path)

    for record in file_records:
        for framework_hint in record.get('frameworkHints', []):
            if framework_hint not in frameworks:
                frameworks.append(framework_hint)

    # Find entry points
    entry_points = find_entry_points(files, project_path)
    dependencies = extract_dependencies(project_path)
    workspace = detect_workspace(file_records, project_path, dependencies)
    important_files = build_important_files(file_records, entry_points, workspace)
    modules = summarize_modules_from_records(file_records)
    analysis = build_analysis_metadata(file_records)
    chunks = build_chunks(file_records)
    chunk_catalog = build_chunk_catalog(chunks, important_files)
    index_metadata = build_index_metadata(
        base,
        index_state_file,
        existing_index_state,
        current_signatures,
        chunks,
        reusing_snapshot=False,
    )

    # Expand framework hints from dependency manifests
    for manifest_path, manifest_dependencies in dependencies.items():
        if manifest_path.endswith(('requirements.txt', 'pyproject.toml')):
            python_frameworks = {
                'fastapi': 'FastAPI',
                'flask': 'Flask',
                'django': 'Django',
                'pydantic': 'Pydantic',
                'sqlalchemy': 'SQLAlchemy',
            }
            for dependency_name, framework_name in python_frameworks.items():
                if dependency_name in manifest_dependencies and framework_name not in frameworks:
                    frameworks.append(framework_name)
    frameworks = sorted(set(frameworks))
    summary = build_summary(
        project_path,
        files,
        frameworks,
        entry_points,
        total_lines,
        file_records,
        important_files,
    )
    context_hints = build_context_hints(summary, workspace, important_files, modules)

    # Extract API routes, data models, functions
    api_routes = []
    data_models = []
    key_functions = []

    for record in file_records:
        for route in record['apiRoutes']:
            api_routes.append({
                'method': route['method'],
                'path': route['path'],
                'handler': record['path'],
                'line': route.get('line'),
                'source': record.get('analysisEngine'),
                'confidence': record.get('analysisConfidence'),
            })

        for model in record['dataModels']:
            data_models.append({
                'name': model['name'],
                'type': model['type'],
                'file': record['path'],
                'line': model.get('line'),
                'source': record.get('analysisEngine'),
                'confidence': record.get('analysisConfidence'),
            })

        for func in record['keyFunctions']:
            key_functions.append(func)

    # Deduplicate
    seen_routes = set()
    unique_routes = []
    for r in api_routes:
        key = f"{r['method']}:{r['path']}:{r['handler']}"
        if key not in seen_routes:
            seen_routes.add(key)
            unique_routes.append(r)

    seen_models = set()
    unique_models = []
    for m in data_models:
        key = f"{m['name']}:{m['type']}:{m['file']}"
        if key not in seen_models:
            seen_models.add(key)
            unique_models.append(m)

    seen_functions = set()
    unique_functions = []
    for func in key_functions:
        key = f"{func['file']}:{func['name']}:{func['line']}"
        if key not in seen_functions:
            seen_functions.add(key)
            unique_functions.append(func)

    # Limit key functions after ranking important areas first
    key_functions = sorted(unique_functions, key=lambda item: rank_key_function(item, entry_points))[:80]

    # Infer architecture
    architecture = infer_architecture(files, project_path)
    graph = build_code_graph(file_records, unique_routes, unique_models, key_functions, workspace)
    external_context = collect_external_context(project_path, file_records)
    retrieval, context_packs = build_retrieval_artifacts(chunks, important_files, graph, external_context)

    # Build snapshot
    snapshot = {
        'version': SNAPSHOT_VERSION,
        'generatedAt': utc_now_iso(),
        'projectPath': str(base.resolve()),
        'sourceFingerprint': source_fingerprint,
        'freshness': {
            'stale': False,
            'reason': 'forced regeneration' if force else ('regenerated because sources changed' if existing_snapshot else 'initial generation'),
            'newestSourceMtime': newest_source_mtime,
            'snapshotPath': normalize_rel_path(str(output_file.relative_to(base))),
        },
        'git': collect_git_context(project_path),
        'summary': summary,
        'workspace': workspace,
        'analysis': analysis,
        'index': index_metadata,
        'contextHints': context_hints,
        'fileTree': build_file_tree(files, project_path),
        'modules': modules,
        'dependencies': dependencies,
        'importantFiles': important_files,
        'chunkCatalog': chunk_catalog,
        'graph': graph,
        'retrieval': retrieval,
        'contextPacks': context_packs,
        'externalContext': external_context,
        'representativeSnippets': build_representative_snippets(file_records, important_files),
        'apiRoutes': sorted(unique_routes, key=lambda item: (item['handler'], item['path'], item['method'])),
        'dataModels': sorted(unique_models, key=lambda item: (item['file'], item['type'], item['name'])),
        'keyFunctions': key_functions,
        'architecture': architecture
    }

    # Save to file
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    save_index_state(index_state_file, current_signatures, chunks, file_records, source_fingerprint)

    print(f"Snapshot saved to: {output_file}", file=sys.stderr)
    return snapshot


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate.py <project_path> [--force] [--task <task>] [--query <query>]", file=sys.stderr)
        sys.exit(1)

    project_path = sys.argv[1]
    force = '--force' in sys.argv or '--refresh' in sys.argv
    task = 'understand-project'
    query = None

    if '--task' in sys.argv:
        task_index = sys.argv.index('--task')
        if task_index + 1 < len(sys.argv):
            task = sys.argv[task_index + 1]

    if '--query' in sys.argv:
        query_index = sys.argv.index('--query')
        if query_index + 1 < len(sys.argv):
            query = sys.argv[query_index + 1]

    if not os.path.isdir(project_path):
        print(f"Error: {project_path} is not a valid directory", file=sys.stderr)
        sys.exit(1)

    snapshot = generate_snapshot(project_path, force)

    if query:
        index_state = load_existing_index_state(Path(project_path) / 'repo' / 'progress' / 'miloya-codebase.index.json')
        focus_pack = build_focus_context_pack(query, task, snapshot, index_state)
        write_json_stdout(focus_pack or snapshot)
        return

    write_json_stdout(snapshot)


def write_json_stdout(payload: dict) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + '\n'
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        buffer = getattr(sys.stdout, 'buffer', None)
        if buffer is not None:
            buffer.write(text.encode('utf-8', errors='replace'))
            buffer.flush()
            return

        safe_text = text.encode('ascii', errors='backslashreplace').decode('ascii')
        sys.stdout.write(safe_text)


if __name__ == '__main__':
    main()
