#!/usr/bin/env python3
"""Where is user-visible English that does not come from a message catalog? (Part 7, ADR-011)

Used to trace "show the interface in Spanish" (system-026, system-027) to the code
that has to change, and kept afterwards as a guard so new English cannot creep in.

    python scripts/find_untranslated_text.py            # web layer + templates (must be empty)
    python scripts/find_untranslated_text.py --all      # also list service sentences (deferred, ADR-011)
    python scripts/find_untranslated_text.py --check    # exit 1 if the web layer or templates have any

What counts as a finding:
- templates/*.html: text between tags, and the visible attributes (placeholder,
  aria-label, title, alt), after every {{ ... }}, {% ... %} and {# ... #} is removed.
  The brand name "EventHub" and text without letters (·, →, —) are allowed.
- app/web/*.py: a string literal that reads like a sentence (starts with a capital
  letter and contains a space), except docstrings. Identifiers such as error codes,
  header names and log messages (lower case) do not match.
- --all also lists sentences raised by the feature services and the wiring, labelled
  "shown by code" (the web layer shows the catalog text for that error code) or
  "stays English" (built from the input; ADR-011 decision 6). They are reported, not failed.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
WEB = ROOT / "app" / "web"
# Sentences raised below the web layer that a page can show. A function filter keeps out
# errors that never reach a page (for example the session-timeout configuration check).
SERVICE_FILES: dict[str, set[str] | None] = {
    "app/web/services.py": None,  # the port-level error for an unavailable service
    "app/wiring.py": None,
    "app/identity/service.py": None,
    "app/identity/policy.py": {"normalize_email"},
    "app/admin/service.py": None,
}

# The brand name and currency codes (USD, JPY) are identifiers, not English.
ALLOWED_WORDS = re.compile(r"\bEventHub\b|\b[A-Z]{3}\b")
JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.DOTALL)
VISIBLE_ATTRIBUTES = {"placeholder", "aria-label", "title", "alt"}
SENTENCE = re.compile(r"^[A-Z][^\n]*\s")
SERVICE_SENTENCE = re.compile(r"^[A-Za-z][^\n]*\s")  # identity writes "email must be ..." in lower case


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    text: str
    kind: str  # "template", "web", "service, shown by code", "service, stays English"

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.kind}] {self.text}"


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:  # a file outside the repository (the scanner's own tests)
        return path.as_posix()


def _has_words(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]", ALLOWED_WORDS.sub("", text)))


class _TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[int, str]] = []
        self._skip = 0  # inside <style> or <script>

    def handle_starttag(self, tag, attrs):
        if tag in {"style", "script"}:
            self._skip += 1
        for name, value in attrs:
            if name in VISIBLE_ATTRIBUTES and value and _has_words(value):
                self.found.append((self.getpos()[0], f'{name}="{value.strip()}"'))

    def handle_endtag(self, tag):
        if tag in {"style", "script"} and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        text = " ".join(data.split())
        if not self._skip and text and _has_words(text):
            leading_newlines = data[: len(data) - len(data.lstrip())].count("\n")
            self.found.append((self.getpos()[0] + leading_newlines, text))


def scan_template(path: Path) -> list[Finding]:
    source = path.read_text(encoding="utf-8")
    # Blank out Jinja but keep the newlines, so line numbers stay true.
    stripped = JINJA.sub(lambda m: "\n" * m.group(0).count("\n"), source)
    collector = _TextCollector()
    collector.feed(stripped)
    collector.close()
    return [Finding(_rel(path), line, text, "template") for line, text in collector.found]


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def _literal_text(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):  # f"Exchange rate for {code} saved."
        return "".join(v.value if isinstance(v, ast.Constant) else "{…}" for v in node.values)
    return None


def scan_python(
    path: Path, kind: str, functions: set[str] | None = None, shown_by_code: frozenset[str] = frozenset()
) -> list[Finding]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = _docstring_ids(tree)
    rel = _rel(path)
    pattern = SERVICE_SENTENCE if kind == "service" else SENTENCE
    seen_parts: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            seen_parts.update(id(v) for v in node.values)
    scopes: list[ast.AST] = [tree]
    if functions is not None:
        scopes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in functions]
    found: list[Finding] = []
    for scope in scopes:
        for node in ast.walk(scope):
            if id(node) in docstrings or id(node) in seen_parts:
                continue
            text = _literal_text(node)
            if text is None or not pattern.match(text):
                continue
            label = kind
            if kind == "service":
                call = _raising_call(node, tree)
                if call is None:
                    continue
                code = _service_error_code(call)
                label = "service, shown by code" if code in shown_by_code else "service, stays English"
            found.append(Finding(rel, node.lineno, " ".join(text.split()), label))
    return found


def _call_name(call: ast.Call) -> str:
    return call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", "")


def _raising_call(literal: ast.AST, tree: ast.AST) -> ast.Call | None:
    """For service files: the exception call a sentence is passed to, if any."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and any(
            literal is a for a in [*node.args, *(k.value for k in node.keywords)]
        ):
            return node if _call_name(node).endswith("Error") else None
    return None


def _service_error_code(call: ast.Call) -> str | None:
    """ServiceError("invalid-credentials", "Invalid email or password.") -> "invalid-credentials"."""
    first = call.args[0] if call.args else None
    if (
        _call_name(call) == "ServiceError"
        and isinstance(first, ast.Constant)
        and isinstance(first.value, str)
    ):
        return first.value
    return None


def _codes_shown_by_code() -> frozenset[str]:
    """The service-error codes the web layer shows from the catalog (ADR-011 decision 6)."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from app.web import SERVICE_ERROR_KEYS
    except ImportError:  # before Part 7 nothing was shown by code
        return frozenset()
    return frozenset(SERVICE_ERROR_KEYS)


def scan(include_services: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(TEMPLATES.glob("*.html")):
        findings += scan_template(path)
    for path in sorted(WEB.glob("*.py")):
        if _rel(path) not in SERVICE_FILES:
            findings += scan_python(path, "web")
    if include_services:
        shown = _codes_shown_by_code()
        for name, functions in SERVICE_FILES.items():
            findings += scan_python(ROOT / name, "service", functions, shown)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true", help="also list service sentences (not failed)")
    parser.add_argument("--check", action="store_true", help="exit 1 if templates or app/web have findings")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252: "→" would crash
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    findings = scan(include_services=args.all)
    for finding in findings:
        print(finding)
    blocking = [f for f in findings if not f.kind.startswith("service")]
    by_file: dict[str, int] = {}
    for f in findings:
        by_file[f.path] = by_file.get(f.path, 0) + 1
    print(f"\n{len(blocking)} untranslated text(s) in templates and app/web", end="")
    if args.all:
        by_code = sum(f.kind == "service, shown by code" for f in findings)
        english = sum(f.kind == "service, stays English" for f in findings)
        print(f"; service sentences: {by_code} shown by code, {english} stay English (ADR-011)", end="")
    print()
    for path, count in sorted(by_file.items(), key=lambda kv: -kv[1]):
        print(f"  {count:4d}  {path}")
    return 1 if args.check and blocking else 0


if __name__ == "__main__":
    sys.exit(main())
