# Build a local documentation report

This is a fictional example supplied with Runbook Lens. It uses no employer,
client or personal information.

## Purpose
Generate a documentation check report for a personal project.

## Prerequisites
- Python 3.9 or later.
- A local copy of this repository.

## Steps
1. Open a terminal in the repository root.
2. Generate an HTML report:

```sh
python3 -m runbook_lens examples/simple --format html --output build/report.html --fail-on none
```

## Verification
Open the report and confirm it includes both example Markdown files. The
[incomplete example](needs-attention.md) intentionally contains findings.

## Rollback
Delete the generated report if it is no longer needed. The scanner does not
change the source documents.
