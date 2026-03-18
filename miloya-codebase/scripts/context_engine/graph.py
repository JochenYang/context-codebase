from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path


LOCAL_CODE_EXTENSIONS = ['.ts', '.tsx', '.js', '.jsx', '.py']


def build_code_graph(
    file_records: list[dict],
    unique_routes: list[dict],
    unique_models: list[dict],
    key_functions: list[dict],
    workspace: dict,
) -> dict:
    file_paths = {record['path'] for record in file_records}
    path_to_record = {record['path']: record for record in file_records}
    file_dependencies = {}
    dependency_edges = []
    module_edge_counts = Counter()
    symbol_index = []

    for record in file_records:
        resolved_dependencies = resolve_local_dependencies(record, file_paths)
        file_dependencies[record['path']] = resolved_dependencies
        source_module = module_for_path(record['path'])

        for target_path in resolved_dependencies:
            dependency_edges.append({
                'source': record['path'],
                'target': target_path,
                'type': 'imports',
            })
            target_module = module_for_path(target_path)
            if source_module != target_module:
                module_edge_counts[(source_module, target_module)] += 1

        for route in record.get('apiRoutes', []):
            symbol_index.append({
                'kind': 'route',
                'name': f'{route.get("method", "GET")} {route.get("path", "")}',
                'file': record['path'],
                'line': route.get('line'),
                'confidence': record.get('analysisConfidence', 'none'),
            })

        for model in record.get('dataModels', []):
            symbol_index.append({
                'kind': 'model',
                'name': model['name'],
                'file': record['path'],
                'line': model.get('line'),
                'type': model.get('type'),
                'confidence': record.get('analysisConfidence', 'none'),
            })

        for func in record.get('keyFunctions', []):
            symbol_index.append({
                'kind': 'function',
                'name': func['name'],
                'file': record['path'],
                'line': func['line'],
                'confidence': record.get('analysisConfidence', 'none'),
            })

    inbound_counts = Counter()
    outbound_counts = Counter()
    for edge in dependency_edges:
        outbound_counts[edge['source']] += 1
        inbound_counts[edge['target']] += 1

    hotspots = []
    for record in file_records:
        path = record['path']
        hotspots.append({
            'path': path,
            'language': record['language'],
            'inbound': inbound_counts[path],
            'outbound': outbound_counts[path],
            'signals': len(record.get('apiRoutes', [])) + len(record.get('dataModels', [])) + len(record.get('keyFunctions', [])),
        })

    hotspots.sort(key=lambda item: (-item['inbound'], -item['signals'], item['path']))

    route_to_handler = [
        {
            'method': route['method'],
            'path': route['path'],
            'handler': route['handler'],
        }
        for route in unique_routes
    ]

    packages = []
    for package in workspace.get('packages', []):
        packages.append({
            'name': package['name'],
            'path': package['path'],
            'role': package['role'],
            'entryPoints': package['entryPoints'],
            'fileCount': package['fileCount'],
        })

    return {
        'stats': {
            'files': len(file_records),
            'symbols': len(symbol_index),
            'dependencyEdges': len(dependency_edges),
            'routeCount': len(unique_routes),
            'modelCount': len(unique_models),
            'functionCount': len(key_functions),
        },
        'packages': packages,
        'moduleDependencies': [
            {'source': source, 'target': target, 'count': count}
            for (source, target), count in sorted(module_edge_counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
        ][:80],
        'fileDependencies': [
            {'path': path, 'dependsOn': targets}
            for path, targets in sorted(file_dependencies.items())
            if targets
        ][:120],
        'routeToHandler': route_to_handler[:120],
        'symbolIndex': sorted(symbol_index, key=lambda item: (item['file'], item.get('line') or 0, item['kind'], item['name']))[:240],
        'hotspots': hotspots[:30],
        'pathIndex': build_path_index(path_to_record),
    }


def build_path_index(path_to_record: dict[str, dict]) -> list[dict]:
    module_to_paths = defaultdict(list)
    for path, record in path_to_record.items():
        module_to_paths[module_for_path(path)].append({
            'path': path,
            'language': record.get('language'),
            'lineCount': record.get('lineCount'),
        })

    return [
        {
            'module': module,
            'files': sorted(items, key=lambda item: item['path'])[:40],
        }
        for module, items in sorted(module_to_paths.items())
    ]


def module_for_path(path: str) -> str:
    parts = Path(path).parts
    return './' if len(parts) == 1 else f'{parts[0]}/'


def resolve_local_dependencies(record: dict, file_paths: set[str]) -> list[str]:
    resolved = []
    current_path = Path(record['path'])
    language = record.get('language')

    for import_path in record.get('imports', []):
        candidate_paths = []

        if language in {'TypeScript', 'JavaScript'} and import_path.startswith('.'):
            base_path = normalize_posix_path(current_path.parent.joinpath(import_path))
            candidate_paths.extend(expand_code_candidates(base_path))
        elif language == 'Python':
            if import_path.startswith('.'):
                trimmed = import_path.lstrip('.')
                if trimmed:
                    base_path = normalize_posix_path(current_path.parent.joinpath(trimmed.replace('.', '/')))
                    candidate_paths.extend(expand_code_candidates(base_path))
            else:
                base_path = import_path.replace('.', '/')
                candidate_paths.extend(expand_code_candidates(base_path))
                if '/' in record['path']:
                    local_base = normalize_posix_path(Path(record['path']).parent.joinpath(import_path.replace('.', '/')))
                    candidate_paths.extend(expand_code_candidates(local_base))

        for candidate in candidate_paths:
            if candidate in file_paths and candidate != record['path']:
                resolved.append(candidate)
                break

    return sorted(dict.fromkeys(resolved))


def expand_code_candidates(base_path: str) -> list[str]:
    candidates = [base_path]
    for ext in LOCAL_CODE_EXTENSIONS:
        candidates.append(f'{base_path}{ext}')
        candidates.append(f'{base_path}/index{ext}')
    return candidates


def normalize_posix_path(path_like: Path) -> str:
    return str(path_like).replace('\\', '/').replace('//', '/')

