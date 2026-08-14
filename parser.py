"""
fountain2pdf.parser
--------------------
A pragmatic parser for Fountain (https://fountain.io) markup.

It does not attempt full spec coverage (dual dialogue and indices are not
supported), but it covers the elements that show up in the overwhelming
majority of real scripts:

  - Title page (Key: value block at the top of the file)
  - Section headings (# , ## , ###  -> used here as Act / Scene dividers)
  - Scene headings (INT./EXT./EST. ... or a forced ".Scene Heading")
  - Character cues (ALL CAPS line immediately followed by dialogue,
    or a forced "@Name")
  - Parentheticals ("(beat)")
  - Dialogue
  - Action / stage direction (default paragraph type)
  - Transitions ("> CUT TO:" or a line ending in "TO:")
  - Centered text ("> like this <")
  - Forced action ("!ALL CAPS LINE that isn't a character cue")
  - Page breaks ("===")
  - Inline emphasis: *italic*, **bold**, ***bold italic***, _underline_
  - Boneyard (/* ... */) and notes ([[ ... ]]) are stripped
"""

import re


class Element:
    __slots__ = ("type", "text", "meta")

    def __init__(self, type_, text="", meta=None):
        self.type = type_
        self.text = text
        self.meta = meta or {}

    def __repr__(self):
        return f"Element({self.type!r}, {self.text!r}, {self.meta!r})"


SCENE_HEADING_RE = re.compile(r"^(INT|EXT|EST|INT\.?/EXT|I/E)[\.\s]", re.IGNORECASE)
TITLE_PAGE_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 _\-]*):\s*(.*)$")
TRANSITION_RE = re.compile(r"^[A-Z0-9 .'\-]+TO:$")
PAGE_BREAK_RE = re.compile(r"^={3,}$")
SECTION_RE = re.compile(r"^(#+)\s*(.*)$")


def strip_boneyard_and_notes(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"\[\[.*?\]\]", "", text, flags=re.DOTALL)
    return text


def is_all_caps_name(line):
    letters = [c for c in line if c.isalpha()]
    if not letters:
        return False
    return all(c.isupper() for c in letters)


CHARACTER_EXTENSION_RE = re.compile(r"^(.*\S)\s*(\([^)]*\))\s*$")


def strip_character_extension(name):
    """Split a trailing parenthetical extension off a character cue, e.g.
    "MARGARET (V.O.)" -> "MARGARET". Per the Fountain spec, character
    extensions may be uppercase or lowercase and shouldn't affect whether
    the line is recognised as a character cue - only the name itself needs
    to be all-caps."""
    m = CHARACTER_EXTENSION_RE.match(name)
    return m.group(1) if m else name


def escape_xml(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_inline(text):
    """Escape XML, then translate Fountain emphasis into reportlab markup."""
    text = escape_xml(text)
    # forced line break: line ends with two-or-more trailing spaces in source,
    # already trimmed by caller in most paths, so this mainly covers the
    # dialogue/action join case where we insert explicit breaks.
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"_(.+?)_", r"<u>\1</u>", text)
    return text


def _starts_new_element(line):
    """True if a (stripped, non-blank) line looks like the start of some
    element other than a continuation of the current action paragraph."""
    if not line:
        return False
    if line[0] in "#!~>@":
        return True
    if line.startswith(".") and not line.startswith(".."):
        return True
    if PAGE_BREAK_RE.match(line):
        return True
    if line.startswith("="):
        return True
    if SCENE_HEADING_RE.match(line):
        return True
    if TRANSITION_RE.match(line) and line == line.upper():
        return True
    if is_all_caps_name(strip_character_extension(line)):
        return True  # conservatively treat as a potential character cue
    return False


def _parse_title_page(lines):
    """Return (title_page_dict, first_body_line_index)."""
    block = []
    i = 0
    while i < len(lines) and lines[i].strip() != "":
        block.append(lines[i])
        i += 1

    if not block or not TITLE_PAGE_KEY_RE.match(block[0]):
        return {}, 0

    looks_like_title_page = all(
        TITLE_PAGE_KEY_RE.match(l) or l.startswith((" ", "\t")) for l in block
    )
    if not looks_like_title_page:
        return {}, 0

    title_page = {}
    current_key = None
    for l in block:
        m = TITLE_PAGE_KEY_RE.match(l)
        if m:
            current_key = m.group(1).strip().lower()
            val = m.group(2).strip()
            title_page.setdefault(current_key, []).append(val)
        elif current_key:
            title_page[current_key].append(l.strip())

    idx = i
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    return title_page, idx


def parse_fountain(text):
    """Parse Fountain source text.

    Returns (title_page: dict[str, list[str]], elements: list[Element]).
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = strip_boneyard_and_notes(text)
    lines = text.split("\n")

    title_page, idx = _parse_title_page(lines)
    n = len(lines)
    elements = []

    while idx < n:
        raw = lines[idx]
        stripped = raw.strip()

        if stripped == "":
            idx += 1
            continue

        if PAGE_BREAK_RE.match(stripped):
            elements.append(Element("page_break"))
            idx += 1
            continue

        if stripped.startswith("#"):
            m = SECTION_RE.match(stripped)
            depth = len(m.group(1))
            elements.append(Element("section", m.group(2).strip(), {"depth": depth}))
            idx += 1
            continue

        # synopsis line (not a page break, which is also '=' repeated)
        if stripped.startswith("=") and not PAGE_BREAK_RE.match(stripped):
            idx += 1
            continue

        if stripped.startswith(">") and stripped.endswith("<") and len(stripped) > 2:
            elements.append(Element("centered", stripped[1:-1].strip()))
            idx += 1
            continue

        if stripped.startswith(">"):
            elements.append(Element("transition", stripped[1:].strip()))
            idx += 1
            continue

        if TRANSITION_RE.match(stripped) and stripped == stripped.upper():
            elements.append(Element("transition", stripped))
            idx += 1
            continue

        if stripped.startswith(".") and not stripped.startswith(".."):
            elements.append(Element("scene_heading", stripped[1:].strip()))
            idx += 1
            continue

        if SCENE_HEADING_RE.match(stripped):
            elements.append(Element("scene_heading", stripped))
            idx += 1
            continue

        forced_char = stripped.startswith("@")
        candidate = stripped[1:].strip() if forced_char else stripped
        next_has_content = idx + 1 < n and lines[idx + 1].strip() != ""
        name_for_caps_check = strip_character_extension(candidate)
        if candidate and not candidate.startswith("(") and (
            forced_char or (is_all_caps_name(name_for_caps_check) and next_has_content)
        ):
            # strip a trailing "^" (dual dialogue marker) - not fully supported,
            # but we drop the marker rather than print it.
            name = candidate[:-1].strip() if candidate.endswith("^") else candidate
            elements.append(Element("character", name))
            idx += 1
            while idx < n and lines[idx].strip() != "":
                dline = lines[idx].strip()
                if dline.startswith("(") and dline.endswith(")"):
                    elements.append(Element("parenthetical", dline))
                else:
                    elements.append(Element("dialogue", dline))
                idx += 1
            continue

        if stripped.startswith("~"):
            elements.append(Element("action", stripped[1:].strip(), {"italic": True}))
            idx += 1
            continue

        if stripped.startswith("!"):
            elements.append(Element("action", stripped[1:].strip()))
            idx += 1
            continue

        action_lines = [stripped]
        idx += 1
        while (
            idx < n
            and lines[idx].strip() != ""
            and not _starts_new_element(lines[idx].strip())
        ):
            action_lines.append(lines[idx].strip())
            idx += 1
        elements.append(Element("action", " ".join(action_lines)))

    return title_page, elements
