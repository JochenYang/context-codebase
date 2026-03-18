from __future__ import annotations

import re
from collections import Counter


STOPWORDS = {
    'the', 'and', 'for', 'with', 'from', 'that', 'this', 'into', 'when', 'want',
    'your', 'have', 'what', 'where', 'which', 'does', 'read', 'code', 'file',
    'files', 'repo', 'project', 'understand', 'task', 'mode', 'need', 'use',
}


TASK_BLUEPRINTS = {
    'understand-project': {
        'query': 'project overview architecture entry points important files modules dependencies',
        'description': 'Orient a new model to the project quickly.',
    },
    'feature-delivery': {
        'query': 'entry points routes services models integration config implementation pattern',
        'description': 'Add or extend behavior using existing project structure.',
    },
    'bugfix-investigation': {
        'query': 'recent changes error handling validation tests routes services config',
        'description': 'Trace failure paths and relevant surrounding code.',
    },
    'code-review': {
        'query': 'recent changes critical paths dependencies tests configuration edge cases',
        'description': 'Review touched areas and their immediate risk surface.',
    },
    'onboarding': {
        'query': 'readme architecture important files conventions packages modules',
        'description': 'Help a new engineer or model build a working mental map.',
    },
}


def build_retrieval_artifacts(
    chunks: list[dict],
    important_files: list[dict],
    graph: dict,
    external_context: dict,
) -> tuple[dict, dict]:
    important_ranks = {item['path']: index for index, item in enumerate(important_files)}
    recent_changed = set(external_context.get('recentChangedFiles', []))
    file_dependency_map = {
        item['path']: item['dependsOn']
        for item in graph.get('fileDependencies', [])
    }

    retrieval = {
        'defaultTask': 'understand-project',
        'availableTasks': list(TASK_BLUEPRINTS.keys()),
        'strategies': ['keyword', 'graph-expansion', 'importance-boost', 'recent-change-boost'],
        'keywordVocabularySize': estimate_vocabulary(chunks),
        'chunkCount': len(chunks),
        'sampleQueries': [
            blueprint['query']
            for blueprint in TASK_BLUEPRINTS.values()
        ],
    }

    context_packs = {}
    for task, blueprint in TASK_BLUEPRINTS.items():
        context_packs[task] = build_context_pack(
            task,
            blueprint['query'],
            blueprint['description'],
            chunks,
            important_ranks,
            recent_changed,
            file_dependency_map,
        )

    return retrieval, context_packs


def build_context_pack(
    task: str,
    query: str,
    description: str,
    chunks: list[dict],
    important_ranks: dict[str, int],
    recent_changed: set[str],
    file_dependency_map: dict[str, list[str]],
) -> dict:
    ranked = retrieve_chunks(
        query,
        chunks,
        important_ranks,
        recent_changed,
        file_dependency_map,
        task=task,
        limit=10,
    )
    related_files = []
    for item in ranked:
        related_files.append(item['path'])
        related_files.extend(file_dependency_map.get(item['path'], []))

    return {
        'task': task,
        'description': description,
        'query': query,
        'chunks': ranked,
        'files': sorted(dict.fromkeys(related_files))[:12],
    }


def retrieve_chunks(
    query: str,
    chunks: list[dict],
    important_ranks: dict[str, int],
    recent_changed: set[str],
    file_dependency_map: dict[str, list[str]],
    task: str,
    limit: int,
) -> list[dict]:
    query_tokens = tokenize(query)
    scored = []

    for chunk in chunks:
        score, reasons = score_chunk(
            chunk,
            query_tokens,
            important_ranks,
            recent_changed,
            task,
        )
        if score <= 0:
            continue
        scored.append((score, reasons, chunk))

    scored.sort(key=lambda item: (-item[0], item[2]['path'], item[2]['startLine']))
    selected = []
    seen_ids = set()
    selected_files = set()

    for score, reasons, chunk in scored:
        if chunk['id'] in seen_ids:
            continue
        seen_ids.add(chunk['id'])
        selected_files.add(chunk['path'])
        selected.append(format_chunk_match(chunk, score, reasons))
        if len(selected) >= limit:
            break

    if task in {'bugfix-investigation', 'code-review'}:
        for chunk in chunks:
            if chunk['path'] not in recent_changed or chunk['id'] in seen_ids:
                continue
            selected.append(format_chunk_match(chunk, 10, ['recently changed file']))
            seen_ids.add(chunk['id'])
            selected_files.add(chunk['path'])
            if len(selected) >= limit:
                break

    if task in {'feature-delivery', 'bugfix-investigation'}:
        dependency_expansions = []
        for path in list(selected_files):
            for dependency in file_dependency_map.get(path, []):
                dependency_expansions.append(dependency)

        for dependency in dependency_expansions:
            for chunk in chunks:
                if chunk['path'] != dependency or chunk['id'] in seen_ids:
                    continue
                selected.append(format_chunk_match(chunk, 8, ['graph expansion']))
                seen_ids.add(chunk['id'])
                if len(selected) >= limit:
                    break
            if len(selected) >= limit:
                break

    return selected[:limit]


def score_chunk(
    chunk: dict,
    query_tokens: set[str],
    important_ranks: dict[str, int],
    recent_changed: set[str],
    task: str,
) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    haystack = ' '.join([
        chunk['path'],
        chunk.get('kind', ''),
        ' '.join(chunk.get('signals', [])),
        chunk.get('preview', ''),
    ]).lower()

    overlap = sorted(token for token in query_tokens if token in haystack)
    if overlap:
        score += len(overlap) * 12
        reasons.append(f'keyword overlap: {", ".join(overlap[:4])}')

    path_rank = important_ranks.get(chunk['path'])
    if path_rank is not None:
        score += max(0, 30 - path_rank * 3)
        reasons.append('important file')

    if chunk['path'] in recent_changed:
        boost = 18 if task in {'bugfix-investigation', 'code-review'} else 8
        score += boost
        reasons.append('recently changed')

    if task == 'understand-project' and chunk['kind'] in {'section', 'model', 'function'}:
        score += 10
        reasons.append('orientation chunk')
    if task == 'feature-delivery' and chunk['kind'] in {'route', 'function', 'model'}:
        score += 12
        reasons.append('implementation anchor')
    if task == 'bugfix-investigation' and chunk['kind'] in {'route', 'function'}:
        score += 10
        reasons.append('execution path')
    if task == 'code-review' and chunk['kind'] in {'function', 'model', 'route'}:
        score += 8
        reasons.append('review hotspot')

    return score, reasons


def format_chunk_match(chunk: dict, score: int, reasons: list[str]) -> dict:
    return {
        'id': chunk['id'],
        'path': chunk['path'],
        'kind': chunk['kind'],
        'language': chunk['language'],
        'startLine': chunk['startLine'],
        'endLine': chunk['endLine'],
        'signals': chunk.get('signals', []),
        'preview': chunk.get('preview', ''),
        'score': score,
        'reasons': reasons,
    }


def estimate_vocabulary(chunks: list[dict]) -> int:
    tokens = Counter()
    for chunk in chunks:
        for token in tokenize(' '.join([chunk['path'], *chunk.get('signals', []), chunk.get('preview', '')])):
            tokens[token] += 1
    return len(tokens)


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r'[a-zA-Z0-9_./-]+', text.lower())
        if len(token) >= 3 and token not in STOPWORDS
    }
