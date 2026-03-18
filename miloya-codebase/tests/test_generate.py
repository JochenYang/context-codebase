import importlib.util
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate.py"
SPEC = importlib.util.spec_from_file_location("miloya_generate", MODULE_PATH)
GENERATE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(GENERATE)


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
                    "def list_items():",
                    "    return []",
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

        self.assertEqual(snapshot["version"], "2.0")
        self.assertIn("sourceFingerprint", snapshot)
        self.assertIn("freshness", snapshot)
        self.assertIn("workspace", snapshot)
        self.assertIn("importantFiles", snapshot)
        self.assertIn("representativeSnippets", snapshot)
        self.assertIn("contextHints", snapshot)
        self.assertIsInstance(snapshot["importantFiles"], list)
        self.assertTrue(snapshot["importantFiles"])
        self.assertEqual(snapshot["freshness"]["stale"], False)
        self.assertEqual(snapshot["workspace"]["rootManifests"], ["package.json"])
        self.assertIn("package.json", [item["path"] for item in snapshot["importantFiles"]])

    def test_snapshot_reuses_cached_result_when_sources_are_unchanged(self) -> None:
        first = GENERATE.generate_snapshot(str(self.temp_dir), force=True)
        second = GENERATE.generate_snapshot(str(self.temp_dir), force=False)

        self.assertEqual(first["sourceFingerprint"], second["sourceFingerprint"])
        self.assertEqual(first["generatedAt"], second["generatedAt"])
        self.assertEqual(second["freshness"]["reason"], "source fingerprint unchanged")

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
                    "def list_items():",
                    "    return []",
                    "",
                    "@app.post('/real')",
                    "def create_item():",
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


if __name__ == "__main__":
    unittest.main()
