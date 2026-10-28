"""Exercise checks against small, real documentation trees."""

import json
from pathlib import Path
import tempfile
import unittest

from runbook_lens.checker import REQUIRED_SECTIONS, scan_directory


COMPLETE_RUNBOOK = """# Restart a sample service

## Purpose
Restore the synthetic example service.

## Prerequisites
Use the local demonstration environment.

## Steps
- Stop the sample service.
- Start the sample service.

## Verification
Confirm that the sample health check passes.

## Rollback
Restore the preceding demonstration configuration.
"""


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.root = self.workspace / "runbooks"
        self.root.mkdir()

    def write(self, relative_path, contents):
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        return path

    def findings_for(self, code):
        return [finding for finding in scan_directory(self.root).findings
                if finding.code == code]

    def test_complete_runbook_has_no_findings(self):
        self.write("restart.md", COMPLETE_RUNBOOK)

        result = scan_directory(self.root)

        self.assertEqual(result.files_scanned, 1)
        self.assertEqual(result.findings, [])

    def test_empty_directory_is_a_valid_scan(self):
        result = scan_directory(self.root)

        self.assertEqual(result.files_scanned, 0)
        self.assertEqual(result.findings, [])

    def test_nonexistent_root_is_rejected(self):
        with self.assertRaises(ValueError):
            scan_directory(self.workspace / "does-not-exist")

    def test_file_cannot_be_used_as_root(self):
        file_path = self.write("runbook.md", COMPLETE_RUNBOOK)

        with self.assertRaises(ValueError):
            scan_directory(file_path)

    def test_required_sections_are_case_insensitive(self):
        self.write("restart.md", COMPLETE_RUNBOOK.swapcase())

        self.assertEqual(scan_directory(self.root).findings, [])

    def test_missing_section_is_reported_at_start_of_file(self):
        self.write("restart.md", COMPLETE_RUNBOOK.replace("## Rollback", "## Notes"))

        findings = self.findings_for("MISSING_SECTION")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "restart.md")
        self.assertEqual(findings[0].line, 1)
        self.assertEqual(findings[0].severity, "error")
        self.assertIn("rollback", findings[0].message.lower())

    def test_normal_prose_does_not_replace_section_headings(self):
        self.write("notes.md", "Purpose, Prerequisites, Steps, Verification, Rollback.\n")

        findings = self.findings_for("MISSING_SECTION")

        self.assertEqual(len(findings), len(REQUIRED_SECTIONS))
        for section in REQUIRED_SECTIONS:
            self.assertTrue(any(section.lower() in finding.message.lower()
                                for finding in findings))

    def test_fenced_examples_do_not_supply_required_sections(self):
        for fence in ("```", "~~~"):
            with self.subTest(fence=fence):
                self.write("example.md", f"{fence}markdown\n{COMPLETE_RUNBOOK}{fence}\n")

                findings = self.findings_for("MISSING_SECTION")

                self.assertEqual(len(findings), len(REQUIRED_SECTIONS))

    def test_open_task_reports_its_source_line(self):
        document = COMPLETE_RUNBOOK + "\n- [x] Completed review\n- [ ] Confirm rollback\n"
        self.write("restart.md", document)

        findings = self.findings_for("OPEN_TASK")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "restart.md")
        self.assertEqual(findings[0].line,
                         document.splitlines().index("- [ ] Confirm rollback") + 1)
        self.assertEqual(findings[0].severity, "warning")

    def test_fenced_tasks_and_links_are_examples_not_findings(self):
        for fence in ("```", "~~~"):
            with self.subTest(fence=fence):
                self.write("restart.md", COMPLETE_RUNBOOK +
                           f"\n{fence}markdown\n- [ ] Example task\n"
                           f"[example](missing.txt)\n{fence}\n")

                self.assertEqual(scan_directory(self.root).findings, [])

    def test_checks_resume_after_a_code_fence(self):
        document = COMPLETE_RUNBOOK + (
            "\n```markdown\n- [ ] Example only\n```\n- [ ] Real follow-up\n"
        )
        self.write("restart.md", document)

        findings = self.findings_for("OPEN_TASK")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].line,
                         document.splitlines().index("- [ ] Real follow-up") + 1)

    def test_existing_relative_link_decodes_spaces_and_strips_query_fragment(self):
        self.write("assets/guide one.txt", "Synthetic reference text.\n")
        self.write("services/restart.md", COMPLETE_RUNBOOK +
                   "\n[Reference](../assets/guide%20one.txt?download=1#example)\n")

        self.assertEqual(scan_directory(self.root).findings, [])

    def test_web_email_and_fragment_links_are_not_local_files(self):
        self.write("restart.md", COMPLETE_RUNBOOK + """
[Secure reference](https://example.invalid/guide)
[Reference](http://example.invalid/guide)
[Contact](mailto:example@example.invalid)
[Steps](#steps)
""")

        self.assertEqual(scan_directory(self.root).findings, [])

    def test_missing_file_and_image_links_are_reported(self):
        document = COMPLETE_RUNBOOK + (
            "\n[Reference](missing.txt)\n![Diagram](images/missing.png)\n"
        )
        self.write("restart.md", document)

        findings = self.findings_for("BROKEN_LINK")

        self.assertEqual(len(findings), 2)
        expected_lines = [document.splitlines().index("[Reference](missing.txt)") + 1,
                          document.splitlines().index("![Diagram](images/missing.png)") + 1]
        self.assertEqual([finding.line for finding in findings], expected_lines)

    def test_parent_traversal_outside_root_is_unsafe_even_when_target_exists(self):
        (self.workspace / "outside.txt").write_text("Outside the scan.\n", encoding="utf-8")
        self.write("restart.md", COMPLETE_RUNBOOK + "\n[Outside](../outside.txt)\n")

        findings = self.findings_for("UNSAFE_LINK")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "restart.md")
        self.assertFalse(self.findings_for("BROKEN_LINK"))

    def test_encoded_parent_traversal_cannot_escape_root(self):
        (self.workspace / "outside.txt").write_text("Outside the scan.\n", encoding="utf-8")
        self.write("restart.md", COMPLETE_RUNBOOK + "\n[Outside](%2e%2e/outside.txt)\n")

        self.assertEqual(len(self.findings_for("UNSAFE_LINK")), 1)

    def test_symlink_link_target_outside_root_is_unsafe(self):
        outside = self.workspace / "outside.txt"
        outside.write_text("Outside the scan.\n", encoding="utf-8")
        (self.root / "shortcut.txt").symlink_to(outside)
        self.write("restart.md", COMPLETE_RUNBOOK + "\n[Reference](shortcut.txt)\n")

        self.assertEqual(len(self.findings_for("UNSAFE_LINK")), 1)

    def test_symlink_documents_and_directories_are_not_scanned(self):
        outside = self.workspace / "outside"
        outside.mkdir()
        (outside / "incomplete.md").write_text("# Not a runbook\n", encoding="utf-8")
        (self.root / "linked.md").symlink_to(outside / "incomplete.md")
        (self.root / "linked-directory").symlink_to(outside, target_is_directory=True)
        self.write("restart.md", COMPLETE_RUNBOOK)

        result = scan_directory(self.root)

        self.assertEqual(result.files_scanned, 1)
        self.assertEqual(result.findings, [])

    def test_generated_and_hidden_directories_are_excluded(self):
        ignored = (".git", "node_modules", ".venv", "__pycache__", "build", ".private")
        for directory in ignored:
            self.write(f"{directory}/bad.md", "# Intentionally incomplete\n")
            self.write(f"nested/{directory}/bad.md", "# Intentionally incomplete\n")
        self.write("services/restart.md", COMPLETE_RUNBOOK)
        self.write("notes.txt", "Non-Markdown text is not a runbook.\n")

        result = scan_directory(self.root)

        self.assertEqual(result.files_scanned, 1)
        self.assertEqual(result.findings, [])

    def test_findings_use_sorted_posix_relative_paths(self):
        self.write("z-last.md", COMPLETE_RUNBOOK + "\n- [ ] Follow up\n")
        self.write("a-first/nested.md", COMPLETE_RUNBOOK + "\n- [ ] Follow up\n")

        result = scan_directory(self.root)

        self.assertEqual(result.files_scanned, 2)
        self.assertEqual([finding.path for finding in result.findings],
                         ["a-first/nested.md", "z-last.md"])

    def test_result_dictionary_is_json_serializable_and_preserves_findings(self):
        self.write("restart.md", COMPLETE_RUNBOOK + "\n- [ ] Follow up\n")
        result = scan_directory(self.root)

        payload = json.loads(json.dumps(result.to_dict()))

        self.assertEqual(payload["files_scanned"], 1)
        self.assertEqual(len(payload["findings"]), 1)
        self.assertEqual(payload["findings"][0]["path"], "restart.md")
        self.assertEqual(payload["findings"][0]["code"], "OPEN_TASK")


if __name__ == "__main__":
    unittest.main()
