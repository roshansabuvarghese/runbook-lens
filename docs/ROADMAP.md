# Development roadmap

These are proposed features, not completed work. Choose useful tasks based on
actual needs rather than promising a fixed number of development hours.

## 1. Configurable document profiles

Support different required sections for a personal setup guide, a release
runbook and an incident checklist. Load an explicit JSON config without adding
dependencies. Reject malformed configuration with a useful error.

Acceptance: existing behavior stays the default; tests cover optional headings,
invalid configs and duplicate section names.

## 2. Markdown parsing improvements

Support reference-style links, escaped brackets and nested parentheses without
reading outside the selected folder. Evaluate whether a maintained Markdown
parser is preferable to extending the small current parser.

Acceptance: add representative fixtures; preserve fence and symlink boundaries;
document any remaining unsupported syntax.

## 3. Linked-heading validation

For an eligible local Markdown target, check a link's heading fragment and
report a missing destination heading with the original source line number.

Acceptance: account for duplicate headings, Unicode and URL encoding; do not
request web resources.

## 4. Report filtering and grouping

Group the HTML report by document and filter errors/warnings. Preserve readable
results when JavaScript is disabled and keep all document-derived text escaped.

Acceptance: keyboard-accessible controls, useful empty state and stable JSON.

Also offer a visual dependency explorer with selectable nodes and the full set
of change-trigger paths, while preserving the static shortest-chain report.

## 5. Changed-file scans

Offer an explicit mode for checking only changed Markdown files in a personal
Git repository, without running hooks or altering the working tree.

Acceptance: cover renamed/deleted/untracked paths and clearly state which files
were included. Keep full-folder scans available.

## 6. Comparison refinements

Add rename detection, a user-managed review baseline and per-profile exceptions
so known documentation debt does not hide a new regression. Keep every
suppression explicit and reversible.

Acceptance: demonstrate renamed linked targets, multiple simultaneous triggers,
removed documents and stale exceptions with synthetic fixtures.
