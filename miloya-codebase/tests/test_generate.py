import importlib.util
import io
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate.py"
SPEC = importlib.util.spec_from_file_location("miloya_generate", MODULE_PATH)
GENERATE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(GENERATE)

EXTERNAL_CONTEXT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "context_engine" / "external_context.py"
EXTERNAL_CONTEXT_SPEC = importlib.util.spec_from_file_location("miloya_external_context", EXTERNAL_CONTEXT_PATH)
EXTERNAL_CONTEXT = importlib.util.module_from_spec(EXTERNAL_CONTEXT_SPEC)
assert EXTERNAL_CONTEXT_SPEC.loader is not None
EXTERNAL_CONTEXT_SPEC.loader.exec_module(EXTERNAL_CONTEXT)

GRAPH_PATH = Path(__file__).resolve().parents[1] / "scripts" / "context_engine" / "graph.py"
GRAPH_SPEC = importlib.util.spec_from_file_location("miloya_graph", GRAPH_PATH)
GRAPH = importlib.util.module_from_spec(GRAPH_SPEC)
assert GRAPH_SPEC.loader is not None
GRAPH_SPEC.loader.exec_module(GRAPH)


class FailingStdout:
    def __init__(self) -> None:
        self.buffer = io.BytesIO()

    def write(self, text: str) -> int:
        raise UnicodeEncodeError("gbk", text, 0, 1, "illegal multibyte sequence")


class GenerateSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="miloya-codebase-"))
        (self.temp_dir / "src").mkdir(parents=True)
        (self.temp_dir / "repo" / "progress").mkdir(parents=True)

        (self.temp_dir / "README.md").write_text("# demo\n", encoding="utf-8")
        (self.temp_dir / "package.json").write_text(
            json.dumps(
                {
                    "name": "demo-project",
                    "dependencies": {"express": "^4.0.0"},
                }
            ),
            encoding="utf-8",
        )
        (self.temp_dir / "src" / "app.py").write_text(
            "\n".join(
                [
                    "# @app.get('/fake-from-comment')",
                    "from fastapi import FastAPI",
                    "",
                    "app = FastAPI()",
                    "",
                    "@app.get('/real')",
                    "async def list_items():",
                    "    return []",
                ]
            ),
            encoding="utf-8",
        )
        (self.temp_dir / "src" / "models.py").write_text(
            "\n".join(
                [
                    "from dataclasses import dataclass",
                    "",
                    "@dataclass",
                    "class Settings:",
                    "    enabled: bool = True",
                ]
            ),
            encoding="utf-8",
        )
        (self.temp_dir / "src" / "web.ts").write_text(
            "\n".join(
                [
                    "import express from 'express';",
                    "const router = express.Router();",
                    "",
                    "export const loadUsers = async () => [];",
                    "router.get('/users', loadUsers);",
                ]
            ),
            encoding="utf-8",
        )
        (self.temp_dir / "repo" / "progress" / "miloya-codebase.json").write_text(
            '{"stale": true}',
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_snapshot_excludes_generated_progress_and_keeps_root_files(self) -> None:
        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)

        self.assertNotIn("repo/progress/", snapshot["fileTree"])
        self.assertIn("./", snapshot["fileTree"])
        self.assertIn("README.md", snapshot["fileTree"]["./"])
        self.assertIn("package.json", snapshot["fileTree"]["./"])

    def test_route_extraction_ignores_comments(self) -> None:
        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)

        routes = {(item["method"], item["path"]) for item in snapshot["apiRoutes"]}
        self.assertIn(("GET", "/real"), routes)
        self.assertNotIn(("GET", "/fake-from-comment"), routes)

    def test_key_function_paths_are_relative(self) -> None:
        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)

        key_functions = snapshot["keyFunctions"]
        self.assertTrue(key_functions)
        self.assertTrue(all(not Path(item["file"]).is_absolute() for item in key_functions))

    def test_snapshot_includes_context_engine_fields(self) -> None:
        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)

        self.assertEqual(snapshot["version"], "3.0")
        self.assertIn("sourceFingerprint", snapshot)
        self.assertIn("freshness", snapshot)
        self.assertIn("workspace", snapshot)
        self.assertIn("analysis", snapshot)
        self.assertIn("index", snapshot)
        self.assertIn("chunkCatalog", snapshot)
        self.assertIn("graph", snapshot)
        self.assertIn("retrieval", snapshot)

    def test_read_query_input_prefers_utf8_query_file(self) -> None:
        query_file = self.temp_dir / "query.txt"
        query_file.write_text("技能管理器如何实现", encoding="utf-8")

        value = GENERATE.read_query_input(None, None, str(query_file), False)

        self.assertEqual(value, "技能管理器如何实现")

    def test_read_query_input_can_read_stdin(self) -> None:
        with patch("sys.stdin", io.StringIO("中文查询\n")):
            value = GENERATE.read_query_input(None, None, None, True)

        self.assertEqual(value, "中文查询")

    def test_snapshot_writes_index_state_with_chunks(self) -> None:
        GENERATE.generate_snapshot(str(self.temp_dir), force=True)

        index_state_path = self.temp_dir / "repo" / "progress" / "miloya-codebase.index.json"
        self.assertTrue(index_state_path.exists())
        index_state = json.loads(index_state_path.read_text(encoding="utf-8"))

        self.assertEqual(index_state["version"], "1.0")
        self.assertIn("src/app.py", index_state["files"])
        self.assertTrue(index_state["chunks"])
        self.assertTrue(any(chunk["path"] == "src/app.py" for chunk in index_state["chunks"]))

    def test_context_pack_query_returns_focused_matches(self) -> None:
        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)
        index_state = GENERATE.load_existing_index_state(
            self.temp_dir / "repo" / "progress" / "miloya-codebase.index.json"
        )

        pack = GENERATE.build_focus_context_pack(
            query="fastapi routes users",
            task="feature-delivery",
            snapshot=snapshot,
            index_state=index_state,
        )

        self.assertIsNotNone(pack)
        self.assertEqual(pack["task"], "feature-delivery")
        self.assertTrue(pack["matches"])
        self.assertIn("src/app.py", pack["files"])

    def test_read_payload_uses_snapshot_and_returns_file_guides(self) -> None:
        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)
        index_state = GENERATE.load_existing_index_state(
            self.temp_dir / "repo" / "progress" / "miloya-codebase.index.json"
        )

        payload = GENERATE.build_read_payload(
            snapshot=snapshot,
            index_state=index_state,
            task="understand-project",
            query=None,
        )

        self.assertEqual(payload["mode"], "read")
        self.assertEqual(payload["responseMode"], "lightweight")
        self.assertEqual(payload["packVersion"], "1.0")
        self.assertEqual(payload["queryProfile"], "generic")
        self.assertEqual(payload["task"], "understand-project")
        self.assertTrue(payload["files"])
        self.assertTrue(payload["snippets"])
        self.assertIn("availableTasks", payload)
        self.assertIn("recommendedStart", payload["quickStart"])
        self.assertTrue(any(item["path"] == "README.md" for item in payload["files"]))
        self.assertTrue(payload["constraints"]["preferLightweightAnswer"])
        self.assertTrue(payload["constraints"]["avoidLongReport"])
        self.assertTrue(payload["constraints"]["preferBriefImplementationSummary"])
        self.assertEqual(payload["constraints"]["primaryGoal"], "locate-code-and-briefly-explain")
        self.assertLessEqual(payload["constraints"]["maxFiles"], 5)
        self.assertLessEqual(payload["constraints"]["maxSnippets"], 4)
        self.assertIn("recommendedAnswerShape", payload)
        self.assertEqual(payload["recommendedAnswerShape"]["style"], "brief-technical-answer")
        self.assertIn("brief-flow", payload["recommendedAnswerShape"]["sections"])
        self.assertEqual(payload["hostHints"]["outputStyle"], "lightweight-answer")
        self.assertEqual(payload["hostHints"]["parentThreadAction"], "answer-from-pack")
        self.assertEqual(payload["hostHints"]["preferredNarrative"], "locate-and-briefly-explain")

    def test_read_payload_query_returns_snippets_with_line_ranges(self) -> None:
        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)
        index_state = GENERATE.load_existing_index_state(
            self.temp_dir / "repo" / "progress" / "miloya-codebase.index.json"
        )

        payload = GENERATE.build_read_payload(
            snapshot=snapshot,
            index_state=index_state,
            task="feature-delivery",
            query="fastapi real route",
        )

        self.assertEqual(payload["mode"], "read")
        self.assertEqual(payload["task"], "feature-delivery")
        self.assertEqual(payload["query"], "fastapi real route")
        self.assertTrue(payload["snippets"])
        self.assertTrue(any(item["path"] == "src/app.py" for item in payload["files"]))
        self.assertTrue(any(item["startLine"] <= item["endLine"] for item in payload["snippets"]))

    def test_read_payload_query_includes_scope_and_next_hops(self) -> None:
        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)
        index_state = GENERATE.load_existing_index_state(
            self.temp_dir / "repo" / "progress" / "miloya-codebase.index.json"
        )

        payload = GENERATE.build_read_payload(
            snapshot=snapshot,
            index_state=index_state,
            task="feature-delivery",
            query="config guide type",
        )

        self.assertIn("queryIntent", payload)
        self.assertIn("configuration", payload["queryIntent"]["labels"])
        self.assertIn("documentation-link", payload["queryIntent"]["labels"])
        self.assertIn("type-definition", payload["queryIntent"]["labels"])
        self.assertIn("searchScope", payload)
        self.assertIn("repo/progress/", payload["searchScope"]["excludePaths"])
        self.assertIn("nextHops", payload)
        self.assertTrue(isinstance(payload["nextHops"], list))

    def test_report_payload_returns_deep_pack_structure(self) -> None:
        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)
        index_state = GENERATE.load_existing_index_state(
            self.temp_dir / "repo" / "progress" / "miloya-codebase.index.json"
        )

        payload = GENERATE.build_report_payload(
            snapshot=snapshot,
            index_state=index_state,
            task="feature-delivery",
            query="skill download flow",
        )

        self.assertEqual(payload["mode"], "report")
        self.assertEqual(payload["reportMode"], "deep-pack")
        self.assertEqual(payload["reportPackVersion"], "1.0")
        self.assertIn("coreFiles", payload)
        self.assertIn("snippets", payload)
        self.assertIn("flowAnchors", payload)
        self.assertIn("constraints", payload)
        self.assertTrue(payload["constraints"]["preferSubagent"])
        self.assertTrue(payload["constraints"]["fallbackToMainThread"])
        self.assertTrue(payload["constraints"]["delegationRequiredIfAvailable"])
        self.assertFalse(payload["constraints"]["allowParentThreadExpansion"])
        self.assertEqual(payload["constraints"]["parentThreadAction"], "stop-after-pack")
        self.assertEqual(payload["hostHints"]["preferredExecution"], "subagent")
        self.assertEqual(payload["hostHints"]["outputStyle"], "pack-only")
        self.assertEqual(payload["hostHints"]["parentThreadAction"], "stop-after-pack")
        self.assertTrue(payload["hostHints"]["delegationRequiredIfAvailable"])
        self.assertFalse(payload["hostHints"]["allowParentThreadExpansion"])

    def test_report_payload_recommends_sections_and_focus_modules(self) -> None:
        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)
        index_state = GENERATE.load_existing_index_state(
            self.temp_dir / "repo" / "progress" / "miloya-codebase.index.json"
        )

        payload = GENERATE.build_report_payload(
            snapshot=snapshot,
            index_state=index_state,
            task="bugfix-investigation",
            query="IM gateway delivery route",
        )

        self.assertIn("recommendedReportShape", payload)
        self.assertIn("sections", payload["recommendedReportShape"])
        self.assertIn("facts-vs-inference", payload["recommendedReportShape"]["sections"])
        self.assertIn("call-chain", payload["recommendedReportShape"]["sections"])
        self.assertTrue(isinstance(payload["focusModules"], list))

    def test_query_intent_recognizes_generic_flow_intents_even_with_mojibake_noise(self) -> None:
        intent = GENERATE.infer_query_intent("IM gateway im���� ��ϢͶ�� ·�� delivery route")

        self.assertIn("integration-flow", intent["labels"])
        self.assertIn("routing-flow", intent["labels"])
        self.assertIn("gateway", intent["keywords"])
        self.assertIn("delivery", intent["keywords"])

    def test_query_intent_expands_mixed_language_flow_terms(self) -> None:
        intent = GENERATE.infer_query_intent("skill\u4e0b\u8f7d\u6d41\u7a0b\u600e\u4e48\u5b9e\u73b0")

        self.assertIn("runtime-flow", intent["labels"])
        self.assertIn("skill", intent["keywords"])
        self.assertIn("下载", intent["keywords"])
        self.assertIn("download", intent["keywords"])
        self.assertIn("流程", intent["terms"])

    def test_read_payload_query_can_hit_config_links_and_persist_flows(self) -> None:
        (self.temp_dir / "src" / "IMSettings.tsx").write_text(
            "\n".join(
                [
                    "const IM_GUIDE_URLS = {",
                    "  feishu: 'https://example.com/feishu-guide',",
                    "};",
                    "",
                    "async function handleSaveFeishuConfig() {",
                    "  await imService.persistConfig({ feishu: { enabled: true } });",
                    "}",
                    "",
                    "export function IMSettings() {",
                    "  return <GuideCard guideUrl={IM_GUIDE_URLS.feishu} />;",
                    "}",
                ]
            ),
            encoding="utf-8",
        )

        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)
        index_state = GENERATE.load_existing_index_state(
            self.temp_dir / "repo" / "progress" / "miloya-codebase.index.json"
        )

        payload = GENERATE.build_read_payload(
            snapshot=snapshot,
            index_state=index_state,
            task="feature-delivery",
            query="feishu config guide link",
        )

        self.assertTrue(any(item["path"] == "src/IMSettings.tsx" for item in payload["files"]))
        self.assertTrue(any(item["path"] == "src/IMSettings.tsx" for item in payload["snippets"]))
        matched_file = next(item for item in payload["files"] if item["path"] == "src/IMSettings.tsx")
        self.assertEqual(matched_file["language"], "TypeScript")
        self.assertEqual(matched_file["lines"], 11)
        self.assertEqual(matched_file["role"], "UI component")
        self.assertTrue(isinstance(matched_file["whyImportant"], str))

    def test_gateway_query_returns_compact_payload_with_flow_anchors(self) -> None:
        (self.temp_dir / "src" / "imGatewayManager.ts").write_text(
            "\n".join(
                [
                    "export function routeChannelMessage() {",
                    "  return 'gateway';",
                    "}",
                ]
            ),
            encoding="utf-8",
        )
        (self.temp_dir / "src" / "imDeliveryRoute.ts").write_text(
            "\n".join(
                [
                    "export function resolveDeliveryRoute() {",
                    "  return 'route';",
                    "}",
                ]
            ),
            encoding="utf-8",
        )
        (self.temp_dir / "src" / "imChatHandler.ts").write_text(
            "\n".join(
                [
                    "export function handleGatewayMessage() {",
                    "  return 'chat';",
                    "}",
                ]
            ),
            encoding="utf-8",
        )

        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)
        index_state = GENERATE.load_existing_index_state(
            self.temp_dir / "repo" / "progress" / "miloya-codebase.index.json"
        )

        payload = GENERATE.build_read_payload(
            snapshot=snapshot,
            index_state=index_state,
            task="feature-delivery",
            query="IM gateway delivery route",
        )

        self.assertIn("integration-flow", payload["queryIntent"]["labels"])
        self.assertIn("routing-flow", payload["queryIntent"]["labels"])
        self.assertLessEqual(len(payload["files"]), 8)
        self.assertLessEqual(len(payload["snippets"]), 6)
        self.assertIn("flowAnchors", payload)
        self.assertTrue(payload["flowAnchors"])
        self.assertTrue(any(item["path"] == "src/imGatewayManager.ts" for item in payload["files"]))
        self.assertTrue(any(item["type"] in {"manager", "routing", "handler", "integration"} for item in payload["flowAnchors"]))

    def test_action_flow_query_prefers_operation_anchor(self) -> None:
        (self.temp_dir / "src" / "skillManager.ts").write_text(
            "\n".join(
                [
                    "export async function downloadSkill(source: string) {",
                    "  return source;",
                    "}",
                    "",
                    "export function listSkills() {",
                    "  return [];",
                    "}",
                ]
            ),
            encoding="utf-8",
        )
        (self.temp_dir / "src" / "runtimeAdapter.ts").write_text(
            "\n".join(
                [
                    "export function startRuntime() {",
                    "  return 'runtime';",
                    "}",
                ]
            ),
            encoding="utf-8",
        )

        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)
        index_state = GENERATE.load_existing_index_state(
            self.temp_dir / "repo" / "progress" / "miloya-codebase.index.json"
        )

        payload = GENERATE.build_read_payload(
            snapshot=snapshot,
            index_state=index_state,
            task="feature-delivery",
            query="skill download flow",
        )

        self.assertEqual(payload["files"][0]["path"], "src/skillManager.ts")
        self.assertEqual(payload["queryProfile"], "skill-runtime")
        self.assertEqual(payload["snippets"][0]["path"], "src/skillManager.ts")
        self.assertIn(payload["snippets"][0]["kind"], {"action-flow", "function"})
        self.assertTrue(any(anchor["type"] == "operation" for anchor in payload["flowAnchors"]))

    def test_select_read_profile_defaults_to_generic(self) -> None:
        profile = GENERATE.select_read_profile(
            GENERATE.infer_query_intent("how does config persistence work")
        )

        self.assertEqual(profile["name"], "generic")

    def test_select_read_profile_uses_skill_runtime_strategy(self) -> None:
        profile = GENERATE.select_read_profile(
            GENERATE.infer_query_intent("skill download flow")
        )

        self.assertEqual(profile["name"], "skill-runtime")
        self.assertIn("skillmanager", profile["focusManagerTokens"])

    def test_read_payload_skill_download_prefers_exact_anchor_and_core_chain(self) -> None:
        (self.temp_dir / "src" / "main").mkdir(parents=True, exist_ok=True)
        (self.temp_dir / "src" / "main" / "libs").mkdir(parents=True, exist_ok=True)
        (self.temp_dir / "scripts").mkdir(parents=True, exist_ok=True)
        (self.temp_dir / "src" / "main" / "skillManager.ts").write_text(
            "\n".join(
                [
                    "export async function installSkill(source: string) {",
                    "  return source;",
                    "}",
                    "",
                    "export async function downloadSkill(source: string) {",
                    "  return installSkill(source);",
                    "}",
                ]
            ),
            encoding="utf-8",
        )
        (self.temp_dir / "src" / "main" / "main.ts").write_text(
            "\n".join(
                [
                    "import { downloadSkill } from './skillManager';",
                    "export async function registerSkillHandlers() {",
                    "  return downloadSkill('demo');",
                    "}",
                ]
            ),
            encoding="utf-8",
        )
        (self.temp_dir / "src" / "main" / "preload.ts").write_text(
            "\n".join(
                [
                    "export const skillBridge = {",
                    "  downloadSkill: (source: string) => source,",
                    "};",
                ]
            ),
            encoding="utf-8",
        )
        (self.temp_dir / "src" / "main" / "libs" / "pythonRuntime.ts").write_text(
            "\n".join(
                [
                    "export async function setupPythonRuntime() {",
                    "  return 'runtime';",
                    "}",
                ]
            ),
            encoding="utf-8",
        )
        (self.temp_dir / "scripts" / "setup-python-runtime.js").write_text(
            "\n".join(
                [
                    "function setupPythonRuntime() {",
                    "  return 'setup';",
                    "}",
                ]
            ),
            encoding="utf-8",
        )

        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)
        index_state = GENERATE.load_existing_index_state(
            self.temp_dir / "repo" / "progress" / "miloya-codebase.index.json"
        )

        payload = GENERATE.build_read_payload(
            snapshot=snapshot,
            index_state=index_state,
            task="feature-delivery",
            query="skill download flow",
        )

        self.assertEqual(payload["files"][0]["path"], "src/main/skillManager.ts")
        self.assertTrue(any(item["path"] == "src/main/main.ts" for item in payload["files"]))
        self.assertTrue(any(item["path"] == "src/main/preload.ts" for item in payload["files"]))
        self.assertFalse(any(item["path"] == "src/main/libs/pythonRuntime.ts" for item in payload["files"]))
        self.assertFalse(any(item["path"] == "scripts/setup-python-runtime.js" for item in payload["files"]))
        self.assertEqual(payload["snippets"][0]["path"], "src/main/skillManager.ts")
        self.assertIn("downloadSkill", payload["snippets"][0]["preview"])
        self.assertNotIn("installSkill", payload["snippets"][0]["preview"].splitlines()[0])
        self.assertLessEqual(len(payload["files"]), 4)
        self.assertLessEqual(len(payload["snippets"]), 3)
        self.assertLessEqual(len(payload["nextHops"]), 2)

    def test_runtime_query_returns_follow_up_paths(self) -> None:
        snapshot = {
            "summary": {
                "entryPoints": [
                    "src/main/main.ts",
                    "src/main/preload.ts",
                    "src/main/libs/agentEngine/index.ts",
                ]
            },
            "importantFiles": [
                {
                    "path": "src/main/skillManager.ts",
                    "role": "Runtime / integration",
                    "whyImportant": "coordinates skill lifecycle",
                },
                {
                    "path": "src/main/libs/openclawConfigSync.ts",
                    "role": "Runtime / integration",
                    "whyImportant": "syncs runtime config",
                },
            ],
            "graph": {
                "fileDependencies": [],
                "pathIndex": [
                    {
                        "module": "src/",
                        "files": [
                            {"path": "src/main/main.ts"},
                            {"path": "src/main/preload.ts"},
                            {"path": "src/main/skillManager.ts"},
                            {"path": "src/main/libs/openclawConfigSync.ts"},
                        ],
                    }
                ],
            },
        }

        next_hops = GENERATE.build_read_next_hops(
            snapshot=snapshot,
            file_paths=[
                "src/main/libs/agentEngine/openclawRuntimeAdapter.ts",
                "src/main/skillManager.ts",
            ],
            snippet_items=[
                {"path": "src/main/libs/agentEngine/openclawRuntimeAdapter.ts"},
            ],
            query_intent=GENERATE.infer_query_intent("skill lifecycle runtime"),
        )

        self.assertTrue(next_hops)
        self.assertTrue(any(item["reason"] == "runtime flow follow-up" for item in next_hops))

    def test_graph_resolves_tsconfig_path_aliases(self) -> None:
        (self.temp_dir / "tsconfig.json").write_text(
            json.dumps(
                {
                    "compilerOptions": {
                        "baseUrl": ".",
                        "paths": {
                            "@/*": ["src/*"],
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        (self.temp_dir / "src" / "shared").mkdir(parents=True, exist_ok=True)
        (self.temp_dir / "src" / "main").mkdir(parents=True, exist_ok=True)
        (self.temp_dir / "src" / "shared" / "util.ts").write_text(
            "export const util = () => 'ok';",
            encoding="utf-8",
        )
        (self.temp_dir / "src" / "main" / "feature.ts").write_text(
            "\n".join(
                [
                    "import React from 'react';",
                    "import express from 'express';",
                    "import fs from 'fs';",
                    "import path from 'path';",
                    "import os from 'os';",
                    "import http from 'http';",
                    "import yaml from 'js-yaml';",
                    "import lodash from 'lodash';",
                    "import { util } from '@/shared/util';",
                    "export const runFeature = () => util();",
                ]
            ),
            encoding="utf-8",
        )

        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)

        dependency_map = {
            item["path"]: item["dependsOn"]
            for item in snapshot["graph"]["fileDependencies"]
        }
        self.assertIn("src/main/feature.ts", dependency_map)
        self.assertIn("src/shared/util.ts", dependency_map["src/main/feature.ts"])
        self.assertTrue(
            any(
                edge["source"] == "src/main/" and edge["target"] == "src/shared/"
                for edge in snapshot["graph"]["moduleDependencies"]
            )
        )

    def test_next_hops_infers_role_for_non_important_files(self) -> None:
        snapshot = {
            "summary": {
                "entryPoints": [
                    "src/main/main.ts",
                ]
            },
            "importantFiles": [],
            "graph": {
                "fileDependencies": [],
                "hotspots": [
                    {
                        "path": "src/main/services/pluginManager.ts",
                        "inbound": 2,
                        "outbound": 1,
                        "signals": 3,
                    }
                ],
                "pathIndex": [
                    {
                        "module": "src/main/",
                        "files": [
                            {"path": "src/main/services/pluginManager.ts"},
                        ],
                    }
                ],
            },
        }

        next_hops = GENERATE.build_read_next_hops(
            snapshot=snapshot,
            file_paths=["src/main/runtime.ts"],
            snippet_items=[],
            query_intent=GENERATE.infer_query_intent("runtime lifecycle manager"),
        )

        self.assertTrue(next_hops)
        plugin_manager = next(item for item in next_hops if item["path"] == "src/main/services/pluginManager.ts")
        self.assertEqual(plugin_manager["role"], "Runtime / integration")
        self.assertTrue(isinstance(plugin_manager["whyImportant"], str))

    def test_external_context_handles_non_utf8_git_output(self) -> None:
        commit_stdout = "abc123\x1f2026-03-18T12:00:00+08:00\x1ffeature ".encode("gb18030") + b"\xae\n"
        changed_stdout = "src\\app.py\nREADME.md\n".encode("utf-8")

        with patch.object(
            EXTERNAL_CONTEXT.subprocess,
            "run",
            side_effect=[
                SimpleNamespace(returncode=0, stdout=commit_stdout, stderr=b""),
                SimpleNamespace(returncode=0, stdout=changed_stdout, stderr=b""),
            ],
        ):
            context = EXTERNAL_CONTEXT.collect_external_context(
                str(self.temp_dir),
                [
                    {"path": "README.md", "language": "Markdown"},
                    {"path": "src/app.py", "language": "Python"},
                ],
            )

        self.assertEqual(context["recentCommits"][0]["hash"], "abc123")
        self.assertEqual(context["recentChangedFiles"], ["src/app.py", "README.md"])
        self.assertTrue(isinstance(context["recentCommits"][0]["summary"], str))

    def test_decode_subprocess_output_accepts_memoryview_payload(self) -> None:
        payload = memoryview("技能管理器".encode("utf-8"))

        decoded = EXTERNAL_CONTEXT.decode_subprocess_output(payload)

        self.assertEqual(decoded, "技能管理器")

    def test_graph_module_for_path_handles_empty_string(self) -> None:
        self.assertEqual(GRAPH.module_for_path(""), "./")

    def test_ast_analysis_detects_async_python_functions_and_dataclasses(self) -> None:
        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)

        key_functions = {(item["file"], item["name"]) for item in snapshot["keyFunctions"]}
        data_models = {(item["file"], item["name"], item["type"]) for item in snapshot["dataModels"]}

        self.assertIn(("src/app.py", "list_items"), key_functions)
        self.assertIn(("src/models.py", "Settings", "dataclass"), data_models)

    def test_typescript_analysis_reports_fallback_when_compiler_is_unavailable(self) -> None:
        snapshot = GENERATE.generate_snapshot(str(self.temp_dir), force=True)

        self.assertEqual(snapshot["analysis"]["engines"]["TypeScript"], "typescript-regex-fallback")
        self.assertIn(
            "typescript compiler unavailable; used regex fallback",
            snapshot["analysis"]["warnings"],
        )
        routes = {(item["method"], item["path"]) for item in snapshot["apiRoutes"]}
        self.assertIn(("GET", "/users"), routes)

    def test_stdout_writer_falls_back_when_console_cannot_encode(self) -> None:
        fake_stdout = FailingStdout()

        with patch.object(GENERATE.sys, "stdout", fake_stdout):
            GENERATE.write_json_stdout({"warning": "⚠️", "status": "ok"})

        rendered = fake_stdout.buffer.getvalue().decode("utf-8")
        self.assertIn('"warning": "⚠️"', rendered)
        self.assertIn('"status": "ok"', rendered)

    def test_snapshot_reuses_cached_result_when_sources_are_unchanged(self) -> None:
        first = GENERATE.generate_snapshot(str(self.temp_dir), force=True)
        second = GENERATE.generate_snapshot(str(self.temp_dir), force=False)

        self.assertEqual(first["sourceFingerprint"], second["sourceFingerprint"])
        self.assertEqual(first["generatedAt"], second["generatedAt"])
        self.assertEqual(second["freshness"]["reason"], "source fingerprint unchanged")
        self.assertEqual(second["index"]["delta"]["unchangedFiles"], second["index"]["fileCount"])
        self.assertEqual(second["index"]["delta"]["changedFiles"], 0)
        self.assertEqual(second["index"]["delta"]["newFiles"], 0)
        self.assertTrue(second["index"]["reusedSnapshot"])

    def test_snapshot_regenerates_when_sources_change(self) -> None:
        first = GENERATE.generate_snapshot(str(self.temp_dir), force=True)

        time.sleep(1.1)
        (self.temp_dir / "src" / "app.py").write_text(
            "\n".join(
                [
                    "from fastapi import FastAPI",
                    "",
                    "app = FastAPI()",
                    "",
                    "@app.get('/real')",
                    "async def list_items():",
                    "    return []",
                    "",
                    "@app.post('/real')",
                    "async def create_item():",
                    "    return {}",
                ]
            ),
            encoding="utf-8",
        )

        second = GENERATE.generate_snapshot(str(self.temp_dir), force=False)

        self.assertNotEqual(first["sourceFingerprint"], second["sourceFingerprint"])
        self.assertNotEqual(first["generatedAt"], second["generatedAt"])
        self.assertEqual(second["freshness"]["reason"], "regenerated because sources changed")
        self.assertIn(("POST", "/real"), {(item["method"], item["path"]) for item in second["apiRoutes"]})
        self.assertEqual(second["index"]["delta"]["changedFiles"], 1)
        self.assertFalse(second["index"]["reusedSnapshot"])

    def test_read_query_input_can_decode_escaped_query(self) -> None:
        value = GENERATE.read_query_input(None, "\\u6280\\u80fd\\u4e0b\\u8f7d\\u6d41\\u7a0b", None, False)

        self.assertEqual(value, "技能下载流程")


if __name__ == "__main__":
    unittest.main()
