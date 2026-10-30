#!/usr/bin/env python3
"""Behavior tests for deeptutor-book-lint (stdlib only, offline)."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "bin" / "deeptutor-book-lint"
EXAMPLES = ROOT / "examples" / "in"


def run(*args):
    proc = subprocess.run(
        [sys.executable, str(TOOL), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


class ExampleTests(unittest.TestCase):
    def test_valid_workspace_exits_zero(self):
        code, out, _ = run(EXAMPLES / "workspace")
        self.assertEqual(code, 0)
        self.assertIn("0 error(s)", out)

    def test_broken_book_exits_one(self):
        code, out, _ = run(EXAMPLES / "broken")
        self.assertEqual(code, 1)
        self.assertIn("BLK003", out)
        self.assertIn("CHP008", out)

    def test_json_output_is_parseable(self):
        code, out, _ = run(EXAMPLES / "broken", "--json")
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertFalse(data["ok"])
        self.assertEqual(data["summary"]["books"], 1)
        self.assertGreaterEqual(data["summary"]["errors"], 5)

    def test_json_valid_book_is_ok(self):
        code, out, _ = run(EXAMPLES / "workspace", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertEqual(data["books"][0]["findings"], [])

    def test_expected_output_matches_checked_in_snapshot(self):
        code, out, _ = run(EXAMPLES / "broken", "--json")
        self.assertEqual(code, 1)
        expected = json.loads((ROOT / "examples" / "out" / "broken.json").read_text())
        self.assertEqual(json.loads(out)["summary"], expected["summary"])
        self.assertEqual(
            [f["code"] for f in json.loads(out)["books"][0]["findings"]],
            [f["code"] for f in expected["books"][0]["findings"]],
        )


class InputErrorTests(unittest.TestCase):
    def test_missing_path_is_usage_error(self):
        code, _, err = run("/nonexistent/book/path")
        self.assertEqual(code, 2)
        self.assertIn("does not exist", err)

    def test_directory_without_books_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = run(tmp)
            self.assertEqual(code, 2)
            self.assertIn("no book_*/manifest.json", err)

    def test_unknown_flag_is_usage_error(self):
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--nope"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(proc.returncode, 2)


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.book = Path(self.tmp.name) / "book_bk_x"
        (self.book / "pages").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, obj):
        path = self.book / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj))

    def base(self):
        self.write("manifest.json", {
            "id": "bk_x", "title": "T", "status": "ready",
            "page_count": 1, "chapter_count": 1,
        })
        self.write("spine.json", {"book_id": "bk_x", "chapters": [
            {"id": "ch_a", "title": "A", "page_ids": ["pg_a"]},
        ]})
        self.write("pages/pg_a.json", {
            "id": "pg_a", "book_id": "bk_x", "chapter_id": "ch_a",
            "status": "ready", "order": 0,
            "blocks": [{"id": "b1", "type": "text", "status": "ready",
                        "payload": {"body": "hello"}}],
        })

    def test_baseline_is_clean(self):
        self.base()
        code, out, _ = run(self.book, "--json")
        self.assertEqual(code, 0, out)

    def test_missing_manifest(self):
        self.write("spine.json", {"book_id": "bk_x", "chapters": []})
        code, out, _ = run(self.book, "--json")
        self.assertEqual(code, 1)
        codes = [f["code"] for f in json.loads(out)["books"][0]["findings"]]
        self.assertIn("BOOK001", codes)

    def test_invalid_json_is_reported_not_crash(self):
        self.base()
        (self.book / "pages" / "pg_a.json").write_text("{not json")
        code, out, _ = run(self.book, "--json")
        self.assertEqual(code, 1)
        self.assertIn("JSON001", out)

    def test_ready_quiz_without_questions(self):
        self.base()
        self.write("pages/pg_a.json", {
            "id": "pg_a", "book_id": "bk_x", "chapter_id": "ch_a",
            "status": "ready", "order": 0,
            "blocks": [{"id": "b1", "type": "quiz", "status": "ready",
                        "payload": {"questions": []}}],
        })
        code, out, _ = run(self.book, "--json")
        self.assertEqual(code, 1)
        self.assertIn("BLK007", out)

    def test_duplicate_chapter_ids(self):
        self.base()
        self.write("spine.json", {"book_id": "bk_x", "chapters": [
            {"id": "ch_a", "title": "A", "page_ids": ["pg_a"]},
            {"id": "ch_a", "title": "A again", "page_ids": []},
        ]})
        code, out, _ = run(self.book, "--json")
        self.assertEqual(code, 1)
        self.assertIn("CHP003", out)

    def test_warning_only_exits_zero_but_strict_fails(self):
        self.base()
        manifest = json.loads((self.book / "manifest.json").read_text())
        manifest["page_count"] = 9
        self.write("manifest.json", manifest)
        code, _, _ = run(self.book, "--json")
        self.assertEqual(code, 0)
        code, out, _ = run(self.book, "--json", "--strict")
        self.assertEqual(code, 1)
        self.assertIn("CNT001", out)

    def test_unreferenced_page_warning(self):
        self.base()
        self.write("pages/pg_extra.json", {
            "id": "pg_extra", "book_id": "bk_x", "chapter_id": "ch_a",
            "status": "ready", "order": 5, "blocks": [],
        })
        code, out, _ = run(self.book, "--json")
        self.assertEqual(code, 0)
        self.assertIn("PAGE006", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
