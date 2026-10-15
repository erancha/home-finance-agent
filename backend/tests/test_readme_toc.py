"""Checks that every "Contents:" link in the README jumps to a heading that exists.

GitHub builds a heading's in-page anchor from its text (lowercase, no punctuation, spaces to
hyphens); this test applies the same rule and fails on a link no heading produces.
"""
import re
from pathlib import Path

README = Path(__file__).resolve().parents[2] / "README.md"

_CONTENTS_LINK = re.compile(r"\[[^\]]+\]\(#([^)]+)\)")
_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.MULTILINE)


def _heading_target(heading_text: str) -> str:
    target = heading_text.strip().lower()
    target = re.sub(r"[^\w\s-]", "", target)
    return target.replace(" ", "-")


def test_every_contents_link_reaches_a_heading():
    text = README.read_text(encoding="utf-8")
    real_targets = {_heading_target(h) for h in _HEADING.findall(text)}
    linked_targets = _CONTENTS_LINK.findall(text)

    assert linked_targets, "expected the README to have a Contents list with in-page links"
    missing = sorted(t for t in linked_targets if t not in real_targets)
    assert not missing, f"Contents links point at headings that do not exist: {missing}"
