"""Dependency-free, escaped reports. Reports never embed document contents."""

from collections import Counter
from html import escape

from .checker import ScanResult


def render_text(result: ScanResult, comparison=None) -> str:
    counts = Counter(f.severity for f in result.findings)
    lines = [
        "Runbook Lens",
        f"{result.files_scanned} Markdown files scanned | "
        f"{counts['error']} errors | {counts['warning']} warnings",
    ]
    if comparison is not None:
        lines.append(
            f"Compared with baseline | {len(comparison.added)} added | "
            f"{len(comparison.changed)} changed | {len(comparison.removed)} removed | "
            f"{len(comparison.affected)} other documents need review"
        )
        for status in ("added", "changed", "removed"):
            for path in getattr(comparison, status):
                lines.append(f"{status.upper()}: {path}")
        for document in comparison.affected:
            lines.append(f"REVIEW: {document.path} | {' -> '.join(document.chain)}")
    if not result.findings:
        lines.append("No findings from the enabled checks.")
    for finding in result.findings:
        lines.append(
            f"{finding.path}:{finding.line}: {finding.severity.upper()} "
            f"{finding.code} — {finding.message}"
        )
    return "\n".join(lines) + "\n"


def _impact_html(comparison) -> str:
    if comparison is None:
        return ""
    change_cards = []
    for status in ("added", "changed", "removed"):
        paths = getattr(comparison, status)
        files = "".join(f"<li><code>{escape(path)}</code></li>" for path in paths)
        change_cards.append(
            f'<div class="stat"><b>{len(paths)}</b><span>{status.title()}</span>'
            f'<ul>{files}</ul></div>'
        )
    affected_rows = "".join(
        f'<tr><td><code>{escape(doc.path)}</code></td><td>'
        f'<span class="badge warning">Review suggested</span>'
        f'<p>{escape(" → ".join(doc.chain))}</p></td></tr>'
        for doc in comparison.affected
    ) or '<tr><td colspan="2" class="empty">No unchanged document links to a changed or removed document.</td></tr>'
    graph_rows = "".join(
        f'<li><code>{escape(link.source)}</code> → <code>{escape(link.target)}</code></li>'
        for link in comparison.links
    ) or "<li>No eligible Markdown links found.</li>"
    return (
        '<section class="impact"><div class="eyebrow">Change impact</div>'
        '<h2>What changed, and what depends on it?</h2>'
        f'<p class="intro">{comparison.baseline_count} baseline files · '
        f'{comparison.current_count} current files · '
        f'{comparison.unchanged_count} unchanged files</p>'
        '<div class="stats">' + "".join(change_cards) + '</div>'
        '<section class="panel"><div class="panelhead">'
        f'<h2>{len(comparison.affected)} linked guides to review</h2>'
        '<p class="intro">A link establishes a reference, not proof the guide is incorrect. '
        'Follow each dependency chain and decide whether an update is needed.</p></div>'
        '<div class="tablewrap"><table><thead><tr><th>Document</th><th>Reason</th></tr></thead>'
        '<tbody>' + affected_rows + '</tbody></table></div></section>'
        '<details><summary>Inspect the current reference graph</summary><ul>'
        + graph_rows + '</ul></details></section>'
    )


def render_html(result: ScanResult, comparison=None) -> str:
    counts = Counter(f.severity for f in result.findings)
    rows = []
    for finding in result.findings:
        label = "error" if finding.severity == "error" else "warning"
        rows.append(
            f'<tr><td><span class="badge {label}">{escape(finding.severity)}</span></td>'
            f'<td><code>{escape(finding.path)}:{finding.line}</code></td>'
            f'<td><strong>{escape(finding.code)}</strong>'
            f'<p>{escape(finding.message)}</p></td></tr>'
        )
    body = "\n".join(rows) if rows else (
        '<tr><td colspan="3" class="empty">No findings from the enabled checks.</td></tr>'
    )
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>Runbook Lens · Documentation report</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f3f6fa;color:#182b42;font:16px/1.6 system-ui,-apple-system,sans-serif}
main{max-width:1040px;margin:56px auto;padding:0 24px}.eyebrow{color:#256b67;text-transform:uppercase;letter-spacing:.16em;font-size:12px;font-weight:750}
h1{font-size:44px;letter-spacing:-.045em;line-height:1.1;margin:12px 0}h2{font-size:22px;margin:0}.intro{color:#53657a;max-width:720px}.impact{margin:36px 0}.impact .stats{margin:20px 0}.stat ul{padding-left:16px;margin-bottom:0}details{margin:20px 0}summary{cursor:pointer;font-weight:650;color:#256b67}.impact h2{margin-top:8px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:32px 0}.stat{background:#fff;border:1px solid #dce4ed;border-radius:14px;padding:20px}
.stat b{display:block;font-size:32px;line-height:1.2}.stat span{color:#53657a}.panel{background:#fff;border:1px solid #dce4ed;border-radius:16px;overflow:hidden}
.panelhead{padding:22px 24px;border-bottom:1px solid #e3e9f0}.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;text-align:left}th{background:#f8fafc;font-size:12px;color:#53657a;text-transform:uppercase;letter-spacing:.07em}
th,td{padding:16px 24px;vertical-align:top;border-bottom:1px solid #e8edf3}tr:last-child td{border-bottom:0}td p{margin:4px 0;color:#53657a}code{font-size:13px;overflow-wrap:anywhere}
.badge{display:inline-block;border-radius:6px;padding:2px 9px;font-size:12px;font-weight:700}.error{background:#fff0ed;color:#a63c2c}.warning{background:#fff6dc;color:#806000}
.empty{color:#256b67}.foot{color:#53657a;font-size:13px;margin:20px 0 48px}.note{border-left:3px solid #4d8f89;padding:2px 0 2px 14px}
@media(max-width:600px){main{margin:28px auto;padding:0 16px}h1{font-size:36px}.stats{gap:8px}.stat{padding:12px}.stat b{font-size:26px}th,td{padding:12px}}
</style></head><body><main>
<div class="eyebrow">Local documentation quality</div><h1>Runbook Lens</h1>
<p class="intro">Understand how changes ripple through your documentation, then check the instructions people will follow.</p>
""" + _impact_html(comparison) + """
<div class="eyebrow">Current document checks</div><div class="stats">
""" + (
        f'<div class="stat"><b>{result.files_scanned}</b><span>Markdown files</span></div>'
        f'<div class="stat"><b>{counts["error"]}</b><span>Errors</span></div>'
        f'<div class="stat"><b>{counts["warning"]}</b><span>Warnings</span></div>'
    ) + """</div><section class="panel"><div class="panelhead"><h2>Findings</h2></div>
<div class="tablewrap"><table><thead><tr><th>Severity</th><th>Location</th><th>What to check</th></tr></thead>
<tbody>""" + body + """</tbody></table></div></section>
<div class="foot"><p class="note">This report checks document structure and local references. It does not execute instructions or establish that a procedure is correct or safe.</p>
<p>Generated locally · No network requests · No document body included in this report</p></div>
</main></body></html>
"""
