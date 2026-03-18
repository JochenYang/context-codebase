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
        self.assertIn("contextPacks", snapshot)
        self.assertIn("externalContext", snapshot)
        self.assertIn("importantFiles", snapshot)
        self.assertIn("representativeSnippets", snapshot)
        self.assertIn("contextHints", snapshot)
        self.assertIsInstance(snapshot["importantFiles"], list)
        self.assertTrue(snapshot["importantFiles"])
        self.assertTrue(snapshot["chunkCatalog"])
        self.assertEqual(snapshot["freshness"]["stale"], False)
        self.assertEqual(snapshot["workspace"]["rootManifests"], ["package.json"])
        self.assertIn("package.json", [item["path"] for item in snapshot["importantFiles"]])
        self.assertEqual(snapshot["analysis"]["engines"]["Python"], "python-ast")
        self.assertEqual(snapshot["index"]["fileCount"], 5)
        self.assertGreater(snapshot["index"]["chunkCount"], 0)
        self.assertIn("understand-project", snapshot["contextPacks"])
        self.assertTrue(snapshot["graph"]["stats"]["symbols"] > 0)
        self.assertIn("understand-project", snapshot["retrieval"]["availableTasks"])
        self.assertIn("README.md", snapshot["externalContext"]["documentationSources"])

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


if __name__ == "__main__":
    unittest.main()
