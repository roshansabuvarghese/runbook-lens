"""Exercise the public command entry point and reports together."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from runbook_lens.__main__ import main

from tests.test_checker import COMPLETE_RUNBOOK


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.baseline = self.workspace / "before"
        self.current = self.workspace / "after"
        self.baseline.mkdir()
        self.current.mkdir()
        for root in (self.baseline, self.current):
            (root / "overview.md").write_text(
                COMPLETE_RUNBOOK + "\n[Dependency](dependency.md)\n", encoding="utf-8"
            )
        (self.baseline / "dependency.md").write_text(COMPLETE_RUNBOOK, encoding="utf-8")
        (self.current / "dependency.md").write_text(
            COMPLETE_RUNBOOK + "\nRevised synthetic configuration.\n", encoding="utf-8"
        )

    def run_cli(self, *arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main([str(argument) for argument in arguments])
        return status, stdout.getvalue(), stderr.getvalue()

    def test_scan_only_json_retains_existing_schema(self):
        status, output, errors = self.run_cli(self.current, "--format", "json")

        payload = json.loads(output)
        self.assertEqual(status, 0)
        self.assertEqual(errors, "")
        self.assertEqual(payload["files_scanned"], 2)
        self.assertEqual(payload["findings"], [])
        self.assertNotIn("comparison", payload)

    def test_baseline_json_combines_quality_findings_with_change_impact(self):
        status, output, errors = self.run_cli(
            self.current, "--baseline", self.baseline, "--format", "json"
        )

        payload = json.loads(output)
        self.assertEqual(status, 0)
        self.assertEqual(errors, "")
        self.assertEqual(payload["files_scanned"], 2)
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["comparison"]["changed"], ["dependency.md"])
        self.assertEqual(payload["comparison"]["affected"][0]["path"], "overview.md")

    def test_comparison_supports_readable_text_and_html_reports(self):
        for report_format in ("text", "html"):
            with self.subTest(report_format=report_format):
                status, output, errors = self.run_cli(
                    self.current, "--baseline", self.baseline, "--format", report_format
                )

                self.assertEqual(status, 0)
                self.assertEqual(errors, "")
                self.assertIn("dependency.md", output)
                self.assertIn("overview.md", output)
                self.assertNotIn("Revised synthetic configuration.", output)

    def test_comparison_html_escapes_changed_paths_and_dependency_chains(self):
        target_name = "target<script>.md"
        for root in (self.baseline, self.current):
            (root / "reference.md").write_text(
                COMPLETE_RUNBOOK + "\n[Target](target%3Cscript%3E.md)\n", encoding="utf-8"
            )
            (root / target_name).write_text(COMPLETE_RUNBOOK, encoding="utf-8")
        (self.current / target_name).write_text(
            COMPLETE_RUNBOOK + "\nPrivate synthetic body text.\n", encoding="utf-8"
        )

        status, output, errors = self.run_cli(
            self.current, "--baseline", self.baseline, "--format", "html"
        )

        self.assertEqual(status, 0)
        self.assertEqual(errors, "")
        self.assertIn("target&lt;script&gt;.md", output)
        self.assertNotIn("target<script>.md", output)
        self.assertNotIn("Private synthetic body text.", output)

    def test_output_file_contains_report_instead_of_stdout(self):
        target = self.workspace / "reports" / "impact.json"

        status, output, errors = self.run_cli(
            self.current, "--baseline", self.baseline, "--format", "json", "--output", target
        )

        self.assertEqual(status, 0)
        self.assertEqual(output, "")
        self.assertEqual(errors, "")
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))
                         ["comparison"]["changed"], ["dependency.md"])

    def test_invalid_baseline_reports_input_error(self):
        status, output, errors = self.run_cli(
            self.current, "--baseline", self.workspace / "not-found"
        )

        self.assertEqual(status, 2)
        self.assertEqual(output, "")
        self.assertTrue(errors.strip())

    def test_quality_findings_still_control_exit_code_with_comparison(self):
        path = self.current / "dependency.md"
        path.write_text(COMPLETE_RUNBOOK + "\n- [ ] Rehearse rollback\n", encoding="utf-8")

        for fail_on, expected_status in (("error", 0), ("warning", 1), ("none", 0)):
            with self.subTest(fail_on=fail_on):
                status, output, errors = self.run_cli(
                    self.current, "--baseline", self.baseline, "--format", "json",
                    "--fail-on", fail_on,
                )

                self.assertEqual(status, expected_status)
                self.assertEqual(errors, "")
                payload = json.loads(output)
                self.assertEqual(payload["findings"][0]["code"], "OPEN_TASK")
                self.assertIn("comparison", payload)


if __name__ == "__main__":
    unittest.main()
