import tempfile
import unittest
from pathlib import Path
from unittest import mock

import promptlab.storage as storage

from helpers import make_library


class StorageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = make_library(Path(self._tmp.name))
        self.lib = storage.Library(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def add_sample(self):
        return self.lib.add_prompt(
            "Everyday Explainer",
            "Explain {{input}} plainly.",
            notes="first draft",
            tags=["writing", "beginner"],
            description="plain explanations",
        )

    def test_slugify(self):
        self.assertEqual(storage.slugify("Everyday Explainer!"), "everyday-explainer")
        with self.assertRaises(ValueError):
            storage.slugify("###")

    def test_add_prompt_roundtrip(self):
        slug = self.add_sample()
        self.assertEqual(slug, "everyday-explainer")
        meta = self.lib.load_meta("everyday-explainer")
        self.assertEqual(meta["tags"], ["writing", "beginner"])
        self.assertEqual(meta["versions"][0]["id"], 1)
        content = self.lib.read_version("everyday-explainer", 1)
        self.assertIn("{{input}}", content)
        self.assertEqual(content, self.lib.read_version("everyday-explainer", "v1"))

    def test_add_duplicate_fails(self):
        self.add_sample()
        with self.assertRaises(storage.StorageError):
            self.lib.add_prompt("everyday explainer", "again")

    def test_version_progression_and_latest(self):
        self.add_sample()
        vid = self.lib.add_version("everyday-explainer", "Improved {{input}} draft.", notes="v2")
        self.assertEqual(vid, 2)
        meta = self.lib.load_meta("everyday-explainer")
        self.assertEqual(self.lib.latest_version_id(meta), 2)
        self.assertEqual(self.lib.read_version("everyday-explainer", "latest"), "Improved {{input}} draft.")
        self.assertEqual(self.lib.read_version("everyday-explainer", 1), "Explain {{input}} plainly.")

    def test_read_missing_prompt(self):
        with self.assertRaises(storage.StorageError):
            self.lib.load_meta("nope")

    def test_resolve_bad_version(self):
        self.add_sample()
        meta = self.lib.load_meta("everyday-explainer")
        with self.assertRaises(storage.StorageError):
            self.lib.resolve_version(meta, "9")
        with self.assertRaises(storage.StorageError):
            self.lib.resolve_version(meta, "banana")

    def test_list_and_tags(self):
        self.add_sample()
        self.lib.add_prompt("chess tester", "Board: {{input}}", tags=["chess"])
        self.assertEqual(self.lib.prompt_names(), ["chess-tester", "everyday-explainer"])

    def test_tests_roundtrip_and_validation(self):
        self.add_sample()
        self.lib.write_tests("everyday-explainer", ["hello", {"name": "second", "input": "hi"}])
        tests = self.lib.read_tests("everyday-explainer")
        self.assertEqual(tests[0]["name"], "test-1")
        self.assertEqual(tests[1]["name"], "second")
        with self.assertRaises(storage.StorageError):
            storage.normalize_test_inputs([{"input": "   "}])
        with self.assertRaises(storage.StorageError):
            storage.normalize_test_inputs("not a list")

    def test_diff_variants(self):
        self.add_sample()
        self.lib.add_version("everyday-explainer", "Better {{input}} draft.")
        a, b, text_a, text_b = self.lib.diff("everyday-explainer", None, None)
        self.assertEqual((a, b), (1, 2))
        self.assertIn("plainly", text_a)
        self.assertIn("Better", text_b)
        with self.assertRaises(storage.StorageError):
            self.lib.diff("everyday-explainer", "1", "1")

    def test_populate_from_copies_samples(self):
        src = Path(self._tmp.name) / "samples"
        (src / "prompts" / "demo" / "versions").mkdir(parents=True)
        (src / "config.json").write_text("{}", encoding="utf-8")
        (src / "prompts" / "demo" / "meta.json").write_text("{}", encoding="utf-8")
        self.lib.populate_from(src)
        self.assertTrue((self.root / "prompts" / "demo" / "meta.json").is_file())

    def test_meta_update(self):
        self.add_sample()
        meta = self.lib.load_meta("everyday-explainer")
        meta["tags"] = ["updated"]
        self.lib.save_meta("everyday-explainer", meta)
        self.assertEqual(self.lib.load_meta("everyday-explainer")["tags"], ["updated"])


if __name__ == "__main__":
    unittest.main()
