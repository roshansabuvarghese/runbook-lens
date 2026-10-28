"""Check local Markdown runbooks without executing commands or fetching URLs.

The parser intentionally supports a small Markdown subset: ATX and setext
headings, list checkboxes, and inline links/images with plain or angle-bracketed
destinations and optional quoted titles. Reference-style links and nested link
labels are not parsed. Fenced examples and inline code are excluded from checks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import re
import stat
from urllib.parse import unquote, urlsplit


REQUIRED_SECTIONS = ("Purpose", "Prerequisites", "Steps", "Verification", "Rollback")
_IGNORED_DIRECTORIES = {".git", "node_modules", ".venv", "__pycache__", "build"}
_FENCE_START = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_ATX_HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+|$)(.*)$")
_SETEXT_UNDERLINE = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
_OPEN_TASK = re.compile(r"^\s*(?:[-+*]|\d+[.)])[ \t]+\[ \](?:[ \t]+|$)")
_INLINE_LINK = re.compile(
    r"!?\[[^\]\n]*\]\([ \t]*(?:<([^>\n]*)>|([^\s)]+))"
    r"(?:[ \t]+(?:\"[^\"\n]*\"|'[^'\n]*'|\([^\)\n]*\)))?[ \t]*\)"
)
_BACKTICKS = re.compile(r"`+")
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[/\\]")


@dataclass(frozen=True)
class Finding:
    """One actionable issue, with a one-based source line and relative path."""

    path: str
    line: int
    code: str
    severity: str
    message: str


@dataclass
class ScanResult:
    """The result of one deterministic directory scan."""

    files_scanned: int
    findings: list[Finding]

    def to_dict(self) -> dict:
        """Return ordinary JSON-serializable values, preserving finding order."""

        return {
            "files_scanned": self.files_scanned,
            "findings": [asdict(finding) for finding in self.findings],
        }


def _mask_code(text: str) -> str:
    """Replace fenced blocks and matched inline code with line-preserving spaces."""

    output: list[str] = []
    fence_character = ""
    fence_length = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        match = _FENCE_START.match(content)
        if fence_character:
            close = re.fullmatch(
                r" {0,3}" + re.escape(fence_character) + "{" + str(fence_length) + r",}[ \t]*",
                content,
            )
            output.append("".join("\n" if char == "\n" else " " for char in line))
            if close:
                fence_character = ""
                fence_length = 0
        elif match:
            marker, info = match.groups()
            # A backtick fence's info string may not itself contain backticks.
            if marker[0] == "`" and "`" in info:
                output.append(line)
                continue
            fence_character = marker[0]
            fence_length = len(marker)
            output.append("".join("\n" if char == "\n" else " " for char in line))
        else:
            output.append(line)

    unfenced = "".join(output)
    masked = list(unfenced)
    runs = list(_BACKTICKS.finditer(unfenced))
    cursor = 0
    while cursor < len(runs):
        opening = runs[cursor]
        closing_index = next(
            (index for index in range(cursor + 1, len(runs))
             if len(runs[index].group()) == len(opening.group())),
            None,
        )
        if closing_index is None:
            cursor += 1
            continue
        closing = runs[closing_index]
        for offset in range(opening.start(), closing.end()):
            if masked[offset] != "\n":
                masked[offset] = " "
        cursor = closing_index + 1
    return "".join(masked)


def _link_issue(root: Path, source: Path, destination: str) -> tuple[str, str] | None:
    """Validate a local destination without following symlinks or reading targets."""

    if not destination or destination.startswith("#"):
        return None
    try:
        parsed = urlsplit(destination)
    except ValueError:
        return "UNSAFE_LINK", "Link destination is not a valid local path."
    if parsed.scheme.lower() in {"http", "https", "mailto"}:
        return None
    if parsed.scheme or parsed.netloc:
        return "UNSAFE_LINK", "Link destination must be a relative local path."

    target_text = unquote(parsed.path)
    if not target_text:
        return None
    if "\x00" in target_text or Path(target_text).is_absolute() or _WINDOWS_ABSOLUTE.match(target_text):
        return "UNSAFE_LINK", "Link destination must stay inside the scanned directory."

    # Check every '..' lexically before touching the filesystem. Path.resolve()
    # would follow links, which the checker deliberately never does. Checking
    # the original components below also catches 'symlink/../file.md'.
    parts = Path(target_text).parts
    depth = len(source.parent.relative_to(root).parts)
    for component in parts:
        if component == "..":
            depth -= 1
            if depth < 0:
                return "UNSAFE_LINK", "Link destination escapes the scanned directory."
        elif component != ".":
            depth += 1

    current = source.parent
    for index, component in enumerate(parts):
        if component == "..":
            current = current.parent
            continue
        current /= component
        try:
            metadata = current.lstat()
        except (FileNotFoundError, NotADirectoryError):
            return "BROKEN_LINK", "Local link target does not exist."
        except OSError:
            return "BROKEN_LINK", "Local link target could not be checked."
        if stat.S_ISLNK(metadata.st_mode):
            return "UNSAFE_LINK", "Link destination uses a symbolic link."
        if index < len(parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
            return "BROKEN_LINK", "Local link target does not exist."
    return None


def _scan_file(root: Path, source: Path) -> list[Finding]:
    """Read and check one Markdown file; report inaccessible or non-UTF-8 input."""

    relative = source.relative_to(root).as_posix()
    try:
        text = source.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return [Finding(relative, 1, "READ_ERROR", "error", "Markdown file could not be read as UTF-8.")]

    lines = _mask_code(text).splitlines()
    sections: set[str] = set()
    findings: list[Finding] = []
    for index, line in enumerate(lines):
        number = index + 1
        heading = _ATX_HEADING.match(line)
        if heading:
            title = re.sub(r"[ \t]+#+[ \t]*$", "", heading.group(1)).strip()
            sections.add(title.casefold())
        elif _SETEXT_UNDERLINE.fullmatch(line) and index > 0 and lines[index - 1].strip():
            sections.add(lines[index - 1].strip().casefold())

        if _OPEN_TASK.match(line):
            findings.append(Finding(relative, number, "OPEN_TASK", "warning", "Unchecked task remains in the runbook."))
        for match in _INLINE_LINK.finditer(line):
            destination = match.group(1) if match.group(1) is not None else match.group(2)
            issue = _link_issue(root, source, destination)
            if issue:
                code, message = issue
                findings.append(Finding(relative, number, code, "error", message))

    for section in REQUIRED_SECTIONS:
        if section.casefold() not in sections:
            findings.append(Finding(relative, 1, "MISSING_SECTION", "error", f"Missing required section: {section}."))
    return findings


def scan_directory(root: Path) -> ScanResult:
    """Recursively check ``.md`` files, skipping hidden/ignored dirs and symlinks.

    The root must be an existing, real directory. Findings use root-relative
    POSIX paths and deterministic ordering. No network access or target-file
    reads take place during link validation.
    """

    try:
        candidate = Path(root).expanduser()
        if candidate.is_symlink() or not candidate.is_dir():
            raise ValueError("Choose an existing directory that is not a symbolic link.")
        root_path = Path(os.path.abspath(candidate))
    except (TypeError, OSError, RuntimeError) as exc:
        raise ValueError("Choose a readable local directory to scan.") from exc

    sources: list[Path] = []
    findings: list[Finding] = []

    def directory_error(error: OSError) -> None:
        directory = Path(error.filename) if error.filename else root_path
        try:
            relative = directory.relative_to(root_path).as_posix()
        except ValueError:
            relative = "."
        findings.append(Finding(relative, 1, "READ_ERROR", "error", "Directory could not be read."))

    for directory, subdirectories, filenames in os.walk(
        root_path, topdown=True, followlinks=False, onerror=directory_error
    ):
        parent = Path(directory)
        subdirectories[:] = sorted(
            name for name in subdirectories
            if not name.startswith(".")
            and name not in _IGNORED_DIRECTORIES
            and not (parent / name).is_symlink()
        )
        for name in sorted(filenames):
            source = parent / name
            if source.suffix.lower() == ".md" and not source.is_symlink() and source.is_file():
                sources.append(source)

    for source in sorted(sources, key=lambda path: path.relative_to(root_path).as_posix()):
        findings.extend(_scan_file(root_path, source))
    findings.sort(key=lambda finding: (finding.path, finding.line, finding.code, finding.message))
    return ScanResult(files_scanned=len(sources), findings=findings)
