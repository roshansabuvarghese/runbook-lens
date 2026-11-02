# Runbook Lens

A local documentation change-impact tool for Markdown SOPs and runbooks. Compare
an earlier folder with the current version, trace which linked guides need
review, and check for missing sections, unfinished steps and broken references.
Results are available as text, JSON or a standalone HTML report.

**Status:** working starter, version 0.1.0. This is a newly started personal
project, developed with AI assistance. It is not an established product, and no
external adoption or performance claim is made.

## Why build it?

A build guide changes from one output format to two. The release guide links to
it, and the onboarding guide links to the release guide. Which guides should be
reviewed? Runbook Lens traces those references, shows the dependency chain and
adds basic document-quality checks. It is intended for original personal-project
documentation and synthetic examples, with a person deciding what needs updating.

## Run it in a minute

Requires **Python 3.9+** and Git. There are no third-party runtime dependencies,
accounts, AI model calls or API keys. Run commands from the repository root:

```sh
python3 -m runbook_lens examples/simple --fail-on none
python3 -m runbook_lens examples/simple --format html --output build/report.html --fail-on none
python3 -m runbook_lens examples/simple --format json --output build/report.json --fail-on none
```

Open `build/report.html` in a browser. The second sample deliberately produces
errors and warnings, so you can see a useful report immediately.

For the change-impact demo:

```sh
python3 -m runbook_lens examples/change/current --baseline examples/change/baseline --format html --output build/impact-report.html --fail-on none
```

Open `build/impact-report.html`. The fictional demo has one added document, one
changed document and one removed document. The unchanged release and onboarding
guides depend on the changed build guide; another unchanged checklist still
links to the removed guide. The report explains each suggested review with a
shortest reference chain. It does not automatically rewrite any instructions.

To check your own folder:

```sh
python3 -m runbook_lens /path/to/your/runbooks
```

The scanner never changes source files, follows symlinks or makes network
requests. Reports contain filenames, line numbers and findings, not document
bodies. Use documents you own and are permitted to process; filenames and
finding messages can still disclose information if a report is shared.

## Current checks

### Change comparison

With `--baseline`, the tool compares Markdown file bytes, classifies additions,
changes and removals, and builds a directed graph of current local Markdown
references. It finds unchanged documents that link, directly or transitively,
to changed or removed files. Cycles terminate safely; one shortest deterministic
chain is shown per affected document. A reference suggests a review, not proof
of incorrect content. Renames currently appear as an addition plus removal.

JSON adds a `comparison` object when `--baseline` is supplied. Change-impact
suggestions alone do not cause a failing exit code; document findings use the
threshold below. A baseline read failure returns exit code 2 rather than a
misleading comparison.

### Document quality

| Code | Severity | Behavior |
| --- | --- | --- |
| `MISSING_SECTION` | Error | Requires Purpose, Prerequisites, Steps, Verification and Rollback headings, without regard to case. A missing section points to line 1. |
| `BROKEN_LINK` | Error | Checks basic inline local file/image links; ignores external web/mail links and same-document anchors. |
| `UNSAFE_LINK` | Error | Flags links outside the scanned folder or through symlinks instead of accessing the target. |
| `OPEN_TASK` | Warning | Finds unfinished Markdown task-list items outside code blocks. |
| `READ_ERROR` | Error | Reports a document that could not be read. |

Fenced examples and inline code are excluded from document checks. Findings use
paths relative to the scanned folder. Hidden folders, `.git`, `.venv`,
`node_modules`, `__pycache__` and `build` are skipped.

Exit codes: **0** means no findings at the requested failure threshold,
**1** means findings met that threshold, and **2** means invalid input or report
output failure. `--fail-on warning` also fails on warnings; `--fail-on none`
always succeeds after a completed scan. An empty folder reports zero files; it
does not prove the documentation is complete.

## Test

```sh
python3 -m unittest discover -s tests -v
```

## Limits of this version

- This is a focused Markdown subset, not a complete CommonMark parser. Reference
  links, nested link labels and complex destinations need future work.
- It checks file existence, not headings inside linked files or external URLs.
- It does not validate that shell commands, rollback procedures or business
  processes are correct, safe or appropriate. Human review remains necessary.
- Required headings are currently fixed. See the development roadmap for plans.
- The graph follows explicit local Markdown links, not implicit references in
  prose. A changed file can affect a document even when no link exists.
- The two folders are read during the scan, not captured as atomic snapshots;
  keep them unchanged while generating a comparison.

## Next development

See [the roadmap](docs/ROADMAP.md) for small, useful next steps and acceptance
criteria. The starter deliberately leaves configuration, richer parsing and
incremental scans for subsequent development.

## Project provenance

The initial implementation and synthetic sample documents were created from
scratch with AI assistance. No employer/client repository, document, meeting
notes or personal data was used as an input. Development history starts with
this starter; no earlier use or authorship history is implied.

This project is a documentation utility. It is not an AI-model training,
evaluation or benchmarking system. No third-party project approval is claimed.

## License

Licensed under the [MIT License](LICENSE).
