"""Report rendering must preserve evidence without executing document content."""

from html import escape
import unittest

from runbook_lens.checker import Finding, ScanResult
from runbook_lens.reporting import render_html, render_text


class ReportingTests(unittest.TestCase):
    def test_html_escapes_untrusted_finding_content_and_paths(self):
        finding = Finding(
            path="docs/<script>alert('path')</script>.md",
            line=7,
            code="<img src=x onerror=alert('code')>",
            severity="<svg onload=alert('severity')>",
            message="Review <script>alert('message')</script> & confirm rollback.",
        )
        result = ScanResult(files_scanned=1, findings=[finding])

        report = render_html(result)

        self.assertIsInstance(report, str)
        self.assertNotIn("<script>", report)
        self.assertNotIn("<img src=x", report)
        self.assertNotIn("<svg onload=", report)
        for value in (finding.path, finding.code, finding.severity, finding.message):
            with self.subTest(field=value):
                self.assertIn(escape(value), report)

    def test_text_report_includes_source_location_and_actionable_message(self):
        finding = Finding(
            path="services/restart.md",
            line=12,
            code="OPEN_TASK",
            severity="warning",
            message="Complete the rollback rehearsal.",
        )
        result = ScanResult(files_scanned=3, findings=[finding])

        report = render_text(result)

        self.assertIsInstance(report, str)
        self.assertIn("services/restart.md", report)
        self.assertIn("12", report)
        self.assertIn("OPEN_TASK", report)
        self.assertIn("Complete the rollback rehearsal.", report)

    def test_empty_results_render_without_errors(self):
        result = ScanResult(files_scanned=0, findings=[])

        self.assertTrue(render_text(result).strip())
        self.assertTrue(render_html(result).strip())


if __name__ == "__main__":
    unittest.main()
