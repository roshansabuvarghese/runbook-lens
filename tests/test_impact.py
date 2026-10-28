"""Compare documentation snapshots and trace actual local dependencies."""

import json
from pathlib import Path
import tempfile
import unittest

from runbook_lens.impact import compare_directories


class ImpactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.baseline = self.workspace / "before"
        self.current = self.workspace / "after"
        self.baseline.mkdir()
        self.current.mkdir()

    def write(self, root, relative, content):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def both(self, relative, content):
        self.write(self.baseline, relative, content)
        self.write(self.current, relative, content)

    def compare(self):
        return compare_directories(self.baseline, self.current)

    def test_empty_snapshots_have_no_changes(self):
        result = self.compare()

        self.assertEqual(result.added, [])
        self.assertEqual(result.removed, [])
        self.assertEqual(result.changed, [])
        self.assertEqual(result.affected, [])
        self.assertEqual(result.links, [])
        self.assertEqual(result.unchanged_count, 0)
        self.assertEqual(result.baseline_count, 0)
        self.assertEqual(result.current_count, 0)

    def test_added_removed_changed_and_unchanged_documents_are_distinct(self):
        self.both("same.md", "# Same\n")
        self.write(self.baseline, "changed.md", "# Before\n")
        self.write(self.current, "changed.md", "# After\n")
        self.write(self.baseline, "removed.md", "# Removed\n")
        self.write(self.current, "added.md", "# Added\n")

        result = self.compare()

        self.assertEqual(result.added, ["added.md"])
        self.assertEqual(result.removed, ["removed.md"])
        self.assertEqual(result.changed, ["changed.md"])
        self.assertEqual(result.unchanged_count, 1)
        self.assertEqual(result.baseline_count, 3)
        self.assertEqual(result.current_count, 3)
        self.assertEqual(result.affected, [])

    def test_unchanged_documents_transitively_depend_on_a_changed_target(self):
        self.both("overview.md", "[Restart procedure](ops/restart.md)\n")
        self.both("ops/restart.md", "[Service configuration](../service.md)\n")
        self.write(self.baseline, "service.md", "# Version one\n")
        self.write(self.current, "service.md", "# Version two\n")

        result = self.compare()
        affected = {item.path: item for item in result.affected}

        self.assertEqual(set(affected), {"overview.md", "ops/restart.md"})
        self.assertEqual(affected["overview.md"].trigger, "service.md")
        self.assertEqual(affected["overview.md"].chain,
                         ["overview.md", "ops/restart.md", "service.md"])
        self.assertEqual(affected["ops/restart.md"].chain,
                         ["ops/restart.md", "service.md"])
        self.assertNotIn("service.md", affected)

    def test_links_to_removed_documents_still_explain_review_impact(self):
        self.both("restart.md", "[Rollback](rollback.md)\n")
        self.write(self.baseline, "rollback.md", "# Old rollback instructions\n")

        result = self.compare()

        self.assertEqual(result.removed, ["rollback.md"])
        self.assertEqual([(link.source, link.target) for link in result.links],
                         [("restart.md", "rollback.md")])
        self.assertEqual(len(result.affected), 1)
        self.assertEqual(result.affected[0].path, "restart.md")
        self.assertEqual(result.affected[0].trigger, "rollback.md")
        self.assertEqual(result.affected[0].chain, ["restart.md", "rollback.md"])

    def test_only_unchanged_documents_are_marked_for_dependent_review(self):
        self.both("unchanged.md", "[Target](target.md)\n")
        self.write(self.baseline, "edited.md", "[Target](target.md)\nOld wording\n")
        self.write(self.current, "edited.md", "[Target](target.md)\nNew wording\n")
        self.write(self.current, "new.md", "[Target](target.md)\n")
        self.write(self.baseline, "target.md", "# Old target\n")
        self.write(self.current, "target.md", "# New target\n")

        result = self.compare()

        self.assertEqual([item.path for item in result.affected], ["unchanged.md"])

    def test_cycles_terminate_and_keep_shortest_dependency_chains(self):
        self.both("a.md", "[B](b.md)\n")
        self.both("b.md", "[A](a.md)\n[Target](target.md)\n")
        self.write(self.baseline, "target.md", "# Old\n")
        self.write(self.current, "target.md", "# New\n")

        result = self.compare()
        affected = {item.path: item for item in result.affected}

        self.assertEqual(set(affected), {"a.md", "b.md"})
        self.assertEqual(affected["a.md"].chain, ["a.md", "b.md", "target.md"])
        self.assertEqual(affected["b.md"].chain, ["b.md", "target.md"])

    def test_shortest_chain_wins_over_a_longer_alternative(self):
        self.both("overview.md", "[Via](intermediate.md)\n[Direct](target.md)\n")
        self.both("intermediate.md", "[Target](target.md)\n")
        self.write(self.baseline, "target.md", "# Old\n")
        self.write(self.current, "target.md", "# New\n")

        affected = {item.path: item for item in self.compare().affected}

        self.assertEqual(affected["overview.md"].chain, ["overview.md", "target.md"])

    def test_equal_length_paths_choose_a_deterministic_chain(self):
        self.both("overview.md", "[Z](z.md)\n[A](a.md)\n")
        self.both("z.md", "[Target](target.md)\n")
        self.both("a.md", "[Target](target.md)\n")
        self.write(self.baseline, "target.md", "# Old\n")
        self.write(self.current, "target.md", "# New\n")

        result = self.compare()
        overview = next(item for item in result.affected if item.path == "overview.md")

        self.assertEqual(overview.chain, ["overview.md", "a.md", "target.md"])
        self.assertEqual([item.path for item in result.affected],
                         sorted(item.path for item in result.affected))

    def test_only_current_document_links_determine_impact(self):
        self.write(self.baseline, "overview.md", "[Retired dependency](target.md)\n")
        self.write(self.current, "overview.md", "# Dependency removed\n")
        self.write(self.baseline, "target.md", "# Old\n")
        self.write(self.current, "target.md", "# New\n")

        result = self.compare()

        self.assertEqual(result.links, [])
        self.assertEqual(result.affected, [])

    def test_decoded_relative_markdown_links_are_normalized(self):
        self.both("ops/restart.md", "[Reference](../docs/service%20guide.md?view=1#steps)\n")
        self.write(self.baseline, "docs/service guide.md", "# Old\n")
        self.write(self.current, "docs/service guide.md", "# New\n")

        result = self.compare()

        self.assertEqual([(link.source, link.target) for link in result.links],
                         [("ops/restart.md", "docs/service guide.md")])
        self.assertEqual(result.affected[0].chain,
                         ["ops/restart.md", "docs/service guide.md"])

    def test_external_code_nonmarkdown_and_outside_links_are_not_dependencies(self):
        self.both("overview.md", """# References
[Web](https://example.invalid/target.md)
[Mail](mailto:person@example.invalid)
[Local anchor](#steps)
[Outside](../outside.md)
[Text asset](reference.txt)
`[Inline example](target.md)`
```markdown
[Fenced example](target.md)
```
~~~markdown
[Another example](target.md)
~~~
""")
        self.write(self.baseline, "target.md", "# Old\n")
        self.write(self.current, "target.md", "# New\n")

        result = self.compare()

        self.assertEqual(result.links, [])
        self.assertEqual(result.affected, [])

    def test_symlink_documents_directories_and_targets_are_excluded(self):
        outside = self.workspace / "outside"
        outside.mkdir()
        outside_doc = outside / "external.md"
        outside_doc.write_text("# Outside\n", encoding="utf-8")
        for root in (self.baseline, self.current):
            (root / "linked.md").symlink_to(outside_doc)
            (root / "linked-dir").symlink_to(outside, target_is_directory=True)
        self.both("overview.md", "[Alias](linked.md)\n[Alias folder](linked-dir/external.md)\n")

        result = self.compare()

        self.assertEqual(result.baseline_count, 1)
        self.assertEqual(result.current_count, 1)
        self.assertEqual(result.links, [])
        self.assertEqual(result.affected, [])

    def test_generated_and_hidden_folders_do_not_create_changes(self):
        self.both("overview.md", "# Stable\n")
        for ignored in (".git", ".private", "node_modules", ".venv", "__pycache__", "build"):
            self.write(self.current, f"nested/{ignored}/new.md", "# Ignored\n")

        result = self.compare()

        self.assertEqual(result.current_count, 1)
        self.assertEqual(result.added, [])

    def test_serialization_exposes_relative_metadata_without_document_bodies(self):
        secret = "SYNTHETIC_DOCUMENT_BODY_MUST_NOT_BE_IN_REPORT"
        self.both("ops/restart.md", f"[Target](../target.md)\n{secret}\n")
        self.write(self.baseline, "target.md", "# Old\n")
        self.write(self.current, "target.md", "# New\n")

        encoded = json.dumps(self.compare().to_dict())
        payload = json.loads(encoded)

        self.assertNotIn(secret, encoded)
        self.assertNotIn(str(self.baseline), encoded)
        self.assertNotIn(str(self.current), encoded)
        self.assertEqual(payload["changed"], ["target.md"])
        self.assertEqual(payload["affected"][0]["path"], "ops/restart.md")
        self.assertEqual(payload["affected"][0]["chain"], ["ops/restart.md", "target.md"])

    def test_each_snapshot_root_must_be_an_existing_directory(self):
        missing = self.workspace / "missing"
        regular_file = self.workspace / "file.txt"
        regular_file.write_text("Not a directory\n", encoding="utf-8")
        for bad_root in (missing, regular_file):
            for position in ("baseline", "current"):
                with self.subTest(root=bad_root, position=position):
                    with self.assertRaises(ValueError):
                        if position == "baseline":
                            compare_directories(bad_root, self.current)
                        else:
                            compare_directories(self.baseline, bad_root)


if __name__ == "__main__":
    unittest.main()
