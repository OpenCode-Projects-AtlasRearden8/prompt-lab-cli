import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import promptlab.report as report
import promptlab.runner as runner

from helpers import EndpointMixin, requests_pool


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tests = [
            {"name": "first", "input": "in one"},
            {"name": "second", "input": "in two"},
        ]
        self.results = [
            {"ok": True, "content": "out one", "latency": 0.123},
            {"ok": False, "error": "endpoint down", "latency": 1.5},
        ]
        self.meta = {"prompt": "demo", "prompt_version": 2,
                     "base_url": "http://localhost:11434/v1", "model": "m"}

    def test_entries_and_aggregate(self):
        entries = report.build_entries(self.results, self.tests)
        summary = report.aggregate(entries)
        self.assertEqual(summary, {"total": 2, "ok": 1, "error": 1,
                                   "latency_average_seconds": 0.123})

    def test_markdown_report_contents(self):
        md = report.build_markdown(self.meta, report.build_entries(self.results, self.tests))
        self.assertIn("# Prompt Lab Run Report", md)
        self.assertIn("demo (version 2)", md)
        self.assertIn("Asdale Dynamics, LLC", md)
        self.assertIn("endpoint down", md)
        self.assertIn("out one", md)

    def test_json_report_contents(self):
        data = json.loads(report.build_json(self.meta, report.build_entries(self.results, self.tests)))
        self.assertEqual(data["prompt"], "demo")
        self.assertEqual(data["summary"]["ok"], 1)
        self.assertEqual(data["tests"][1]["status"], "error")

    def test_all_failed_average_is_none(self):
        entries = report.build_entries(
            [{"ok": False, "error": "x", "latency": 0.0}], [{"name": "a", "input": "b"}]
        )
        self.assertIsNone(report.aggregate(entries)["latency_average_seconds"])

    def test_render_placeholder(self):
        rendered, used = runner.render("q: {{input}}", "hi")
        self.assertEqual((rendered, used), ("q: hi", True))


def run_cli(*argv):
    """Run the CLI in-process; return (returncode, stdout, stderr)."""
    from promptlab.cli import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class CliRunOfflineTests(EndpointMixin):
    """End-to-end CLI runs against the local fake endpoint (localhost only)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "lib"
        self._tmp2 = tempfile.TemporaryDirectory()
        run_cli("--library", str(self.root), "init")
        prompt_file = Path(self._tmp2.name) / "demo.md"
        prompt_file.write_text("Say {{input}} nicely.", encoding="utf-8")
        tests_file = Path(self._tmp2.name) / "tests.json"
        tests_file.write_text(
            json.dumps([{"name": "one", "input": "A"}, {"name": "two", "input": "B"}]),
            encoding="utf-8",
        )
        rc, _, err = run_cli(
            "--library", str(self.root), "add", "demo prompt",
            "--file", str(prompt_file),
            "--notes", "first",
            "--tags", "demo,writing",
            "--description", "demo prompt for tests",
            "--save-tests", str(tests_file),
        )
        self.assertEqual(rc, 0, err)

    def tearDown(self):
        self._tmp.cleanup()
        self._tmp2.cleanup()

    def _env(self):
        return mock.patch.dict(
            os.environ,
            {"PROMPTLAB_BASE_URL": self.base_url, "PROMPTLAB_MODEL": "fake-small"},
        )

    def _run(self, *extra):
        return run_cli("--library", str(self.root), "run", "demo-prompt", *extra)

    def test_dry_run_touches_no_endpoint(self):
        self.clear_requests()
        with self._env():
            rc, out, err = self._run("--dry-run")
        self.assertEqual(rc, 0, err)
        self.assertEqual(len(requests_pool), 0)
        self.assertIn("Say A nicely.", out)

    def test_run_one_input_against_fake_endpoint(self):
        self.clear_requests()
        with self._env():
            rc, out, err = self._run("--input", "hello world")
        self.assertEqual(rc, 0, err)
        payload = self.last_request_payload()
        self.assertEqual(payload["messages"][-1]["content"], "Say hello world nicely.")
        headers = self.last_request_headers()
        self.assertNotIn("Authorization", headers)
        self.assertNotIn("Api-Key", headers)
        self.assertIn("hello world", out)

    def test_run_saved_tests_and_markdown_report(self):
        self.clear_requests()
        report_path = Path(self._tmp2.name) / "report.md"
        with self._env():
            rc, out, err = self._run("--report", str(report_path))
        self.assertEqual(rc, 0, err)
        text = report_path.read_text(encoding="utf-8")
        self.assertIn("# Prompt Lab Run Report", text)
        self.assertIn("demo-prompt (version 1)", text)
        self.assertIn("one — ok", text)
        self.assertIn("echo: Say A nicely.", text)
        self.assertIn("Asdale Dynamics, LLC", text)
        self.assertEqual(self.last_request_payload()["messages"][-1]["content"], "Say B nicely.")

    def test_run_json_report(self):
        report_path = Path(self._tmp2.name) / "report.json"
        with self._env():
            rc, _, err = self._run("--report", str(report_path), "--report-format", "json")
        self.assertEqual(rc, 0, err)
        data = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(data["summary"]["ok"], 2)
        self.assertEqual(data["summary"]["error"], 0)

    def test_run_reports_failures_and_exit_code(self):
        self.clear_requests()
        report_path = Path(self._tmp2.name) / "report.md"
        with mock.patch.dict(os.environ, {"PROMPTLAB_BASE_URL": self.base_url}):
            with mock.patch.object(
                runner, "send_json", side_effect=ConnectionError("refused")
            ):
                rc, out, err = self._run("--report", str(report_path))
        self.assertEqual(rc, 1)
        self.assertIn("FAILED", out)
        text = report_path.read_text(encoding="utf-8")
        self.assertIn("error", text)

    def test_run_fails_helpfully_without_tests_or_input(self):
        run_cli("--library", str(self.root), "init")
        second = Path(self._tmp2.name) / "lib2"
        rc, _, _ = run_cli("--library", str(second), "init")
        self.assertEqual(rc, 0)
        second_prompt = Path(self._tmp2.name) / "l.md"
        second_prompt.write_text("no tests here {{input}}", encoding="utf-8")
        rc, _, err = run_cli(
            "--library", str(second), "add", "lonely", "--file", str(second_prompt)
        )
        self.assertEqual(rc, 0)
        rc, out, err = run_cli("--library", str(second), "run", "lonely")
        self.assertEqual(rc, 1)
        self.assertIn("No test inputs found", err)

    def test_missing_library_command(self):
        rc, out, err = run_cli("--library", str(Path(self._tmp2.name) / "nothing"), "list")
        self.assertEqual(rc, 1)
        self.assertIn("promptlab init", err)


class CliLibraryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "lib"

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *argv):
        return run_cli("--library", str(self.root), *argv)

    def _prompt_file(self, text):
        path = Path(self._tmp.name) / "prompt.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def test_commands_fail_helpfully_without_library(self):
        rc, out, err = self._run("list")
        self.assertEqual(rc, 1)
        self.assertIn("promptlab init", err)

    def test_full_lifecycle(self):
        rc, out, err = self._run("init")
        self.assertEqual(rc, 0, err)
        self.assertIn("Created library at", out)

        rc, out, err = self._run(
            "add", "friend explainer", "--file", str(self._prompt_file("Explain {{input}} like a friend.")),
            "--notes", "v1", "--tags", "writing,beginner", "--description", "friendly explanations",
        )
        self.assertEqual(rc, 0, err)
        self.assertIn("as version 1", out)

        rc, out, err = self._run(
            "update", "friend-explainer", "--file", str(self._prompt_file("Explain {{input}} like a very patient friend.")),
            "--notes", "warmer",
        )
        self.assertEqual(rc, 0, err)

        rc, out, err = self._run("list")
        self.assertEqual(rc, 0)
        self.assertIn("friend-explainer", out)
        self.assertIn("friendly explanations", out)

        rc, out, err = self._run("list", "--tag", "beginner")
        self.assertIn("friend-explainer", out)
        rc, out, err = self._run("list", "--tag", "nonexistent")
        self.assertIn("No prompts tagged", out)

        rc, out, err = self._run("versions", "friend explainer")
        self.assertEqual(rc, 0)
        self.assertIn("v1", out)
        self.assertIn("v2", out)
        self.assertIn("warmer", out)

        rc, out, err = self._run("show", "friend-explainer", "1")
        self.assertIn("like a friend.", out)

        rc, out, err = self._run("diff", "friend-explainer")
        self.assertEqual(rc, 0)
        self.assertIn("+Explain {{input}} like a very patient friend.", out)

        rc, out, err = self._run("diff", "friend-explainer", "1", "2")
        self.assertIn("---", out)
        self.assertIn("+++", out)

        rc, out, err = self._run("meta", "friend-explainer", "--add-tag", "education")
        self.assertIn("education", out)
        rc, out, err = self._run("meta", "friend-explainer", "--remove-tag", "writing")
        self.assertIn("education", out)
        self.assertNotIn("writing", out)

        rc, out, err = self._run("meta", "friend-explainer", "--save-tests",
                                 str(self._tests_file([{"name": "t1", "input": "AI"}])))
        self.assertEqual(rc, 0)
        rc, out, err = self._run("run", "friend-explainer", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("Explain AI like a", out)

    def _tests_file(self, data):
        path = Path(self._tmp.name) / "tests.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_add_duplicate_errors(self):
        self.assertEqual(self._run("init")[0], 0)
        prompt_file = self._prompt_file("content {{input}}")
        self.assertEqual(self._run("add", "dup", "--file", str(prompt_file))[0], 0)
        rc, out, err = self._run("add", "dup", "--file", str(prompt_file))
        self.assertEqual(rc, 1)
        self.assertIn("already exists", err)

    def test_show_missing_version(self):
        self.assertEqual(self._run("init")[0], 0)
        self.assertEqual(
            self._run("add", "solo", "--file", str(self._prompt_file("one {{input}}")))[0], 0
        )
        rc, out, err = self._run("show", "solo", "99")
        self.assertEqual(rc, 1)
        self.assertIn("no version 99", err)

    def test_config_command(self):
        self.assertEqual(self._run("init")[0], 0)
        rc, out, err = self._run("config")
        self.assertEqual(rc, 0)
        cfg = json.loads(out)
        self.assertEqual(cfg["base_url"], "http://localhost:11434/v1")
        self.assertEqual(cfg["model"], "llama3.2")

    def test_slug_names_consistent(self):
        self.assertEqual(self._run("init")[0], 0)
        rc, out, err = self._run("add", "  Mixed CASE name!! ", "--file", str(self._prompt_file("hello {{input}}")))
        self.assertEqual(rc, 0, err)
        self.assertIn("mixed-case-name", out)
        rc, out, err = self._run("versions", "mixed-case-name")
        self.assertEqual(rc, 0)

    def test_version_flag_and_help(self):
        rc, out, _ = run_cli("--version")
        self.assertEqual(rc, 0)
        self.assertIn("promptlab", out)
        rc, out, _ = run_cli()
        self.assertEqual(rc, 2)
        self.assertIn("usage:", out)

    def test_diff_single_version_needs_two(self):
        self.assertEqual(self._run("init")[0], 0)
        self.assertEqual(
            self._run("add", "single", "--file", str(self._prompt_file("only {{input}}")))[0], 0
        )
        rc, out, err = self._run("diff", "single")
        self.assertEqual(rc, 1)
        self.assertIn("A diff needs two", err)


if __name__ == "__main__":
    unittest.main()
