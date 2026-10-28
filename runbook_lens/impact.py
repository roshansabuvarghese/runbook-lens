"""Compare Markdown folders and trace which unchanged documents need review.

Links describe dependency, not proof of a defect: if A links to B and B changes,
A is a review candidate. Parsing uses the checker's documented Markdown subset.
Only filenames, change categories and dependency chains leave this module;
document bodies are never included in its result.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .checker import _IGNORED_DIRECTORIES, _INLINE_LINK, _link_issue, _mask_code


@dataclass(frozen=True)
class DocumentLink:
    """One unique directed local Markdown dependency, using relative paths."""

    source: str
    target: str


@dataclass(frozen=True)
class AffectedDocument:
    """An unchanged document and its shortest chain to a changed/removed target."""

    path: str
    trigger: str
    chain: list[str]


@dataclass
class ComparisonResult:
    """Deterministic change inventory and review candidates for two snapshots."""

    added: list[str]
    removed: list[str]
    changed: list[str]
    unchanged_count: int
    affected: list[AffectedDocument]
    links: list[DocumentLink]
    baseline_count: int
    current_count: int

    def to_dict(self) -> dict:
        """Return JSON-ready values without document contents or absolute paths."""

        return asdict(self)


def _snapshot(directory: Path) -> tuple[Path, dict[str, bytes]]:
    """Read real UTF-8 Markdown files, excluding ignored dirs and symlinks.

    An incomplete snapshot must not silently look like document removal, so any
    unreadable directory/file or non-UTF-8 Markdown file aborts the comparison.
    """

    try:
        candidate = Path(directory).expanduser()
        if candidate.is_symlink() or not candidate.is_dir():
            raise ValueError("Choose an existing directory that is not a symbolic link.")
        root = Path(os.path.abspath(candidate))
    except (TypeError, OSError, RuntimeError) as exc:
        raise ValueError("Choose readable local directories to compare.") from exc

    contents: dict[str, bytes] = {}

    def directory_error(error: OSError) -> None:
        raise ValueError("A comparison directory could not be read.") from error

    for directory_name, subdirectories, filenames in os.walk(
        root, topdown=True, followlinks=False, onerror=directory_error
    ):
        parent = Path(directory_name)
        subdirectories[:] = sorted(
            name for name in subdirectories
            if not name.startswith(".")
            and name not in _IGNORED_DIRECTORIES
            and not (parent / name).is_symlink()
        )
        for name in sorted(filenames):
            source = parent / name
            if source.suffix.lower() != ".md" or source.is_symlink():
                continue
            relative = source.relative_to(root).as_posix()
            try:
                if not source.is_file():
                    continue
                data = source.read_bytes()
                data.decode("utf-8-sig")
            except (OSError, UnicodeError) as exc:
                raise ValueError(f"Markdown file could not be read as UTF-8: {relative}") from exc
            contents[relative] = data
    return root, contents


def _target_path(root: Path, source: Path, destination: str) -> str | None:
    """Return a safe Markdown destination, including nonexistent local targets."""

    if not destination or destination.startswith("#"):
        return None
    try:
        parsed = urlsplit(destination)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    issue = _link_issue(root, source, destination)
    if issue and issue[0] == "UNSAFE_LINK":
        return None
    target = Path(os.path.abspath(source.parent / unquote(parsed.path)))
    if target.suffix.lower() != ".md":
        return None
    try:
        return target.relative_to(root).as_posix()
    except ValueError:
        return None


def _document_links(root: Path, contents: dict[str, bytes]) -> list[DocumentLink]:
    """Build unique current links without reading linked targets or using a network."""

    links: set[tuple[str, str]] = set()
    for relative in sorted(contents):
        source = root / relative
        text = _mask_code(contents[relative].decode("utf-8-sig"))
        for line in text.splitlines():
            for match in _INLINE_LINK.finditer(line):
                destination = match.group(1) if match.group(1) is not None else match.group(2)
                target = _target_path(root, source, destination)
                if target is not None:
                    links.add((relative, target))
    return [DocumentLink(source, target) for source, target in sorted(links)]


def _shortest_chain(
    source: str, graph: dict[str, list[str]], triggers: set[str]
) -> list[str] | None:
    """Choose the shortest dependency chain, breaking ties lexicographically."""

    queue = deque([(source, [source])])
    visited = {source}
    while queue:
        node, chain = queue.popleft()
        if node in triggers:
            return chain
        for target in graph.get(node, []):
            if target not in visited:
                visited.add(target)
                queue.append((target, chain + [target]))
    return None


def compare_directories(baseline: Path, current: Path) -> ComparisonResult:
    """Compare two local folders and identify unchanged documents needing review.

    Added/removed/changed categories use relative filenames and exact file bytes.
    Affected documents are unchanged current files that link, directly or
    transitively, to a changed or removed Markdown file. They are review
    candidates rather than claims that their text is stale. Cycles are safe,
    and shortest-path ties are settled by sorted path names.
    """

    _, before = _snapshot(baseline)
    current_root, after = _snapshot(current)
    before_names = set(before)
    after_names = set(after)
    added = sorted(after_names - before_names)
    removed = sorted(before_names - after_names)
    shared = before_names & after_names
    changed = sorted(name for name in shared if before[name] != after[name])
    unchanged = sorted(name for name in shared if before[name] == after[name])
    triggers = set(changed) | set(removed)

    links = _document_links(current_root, after)
    graph: dict[str, list[str]] = {}
    for link in links:
        graph.setdefault(link.source, []).append(link.target)

    affected: list[AffectedDocument] = []
    for source in unchanged:
        chain = _shortest_chain(source, graph, triggers)
        if chain is not None:
            affected.append(AffectedDocument(path=source, trigger=chain[-1], chain=chain))

    return ComparisonResult(
        added=added,
        removed=removed,
        changed=changed,
        unchanged_count=len(unchanged),
        affected=affected,
        links=links,
        baseline_count=len(before),
        current_count=len(after),
    )
