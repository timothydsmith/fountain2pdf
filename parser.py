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
SCENE_NUMBER_RE = re.compile(r"\s*#([0-9A-Za-z][0-9A-Za-z.\-]*)#\s*$")
LIST_BULLET_RE = re.compile(r"^[-*+]\s+(.+)$")
LIST_ORDERED_RE = re.compile(r"^(\d+)[.)]\s+(.+)$")


def split_scene_number(text):
    """Split a forced scene number (e.g. "INT. HOUSE - DAY #2A#") off the
    end of a scene heading line, per the Fountain spec. Returns
    (heading_text, number_or_None)."""
    m = SCENE_NUMBER_RE.search(text)
    if not m:
        return text, None
    return text[: m.start()].rstrip(), m.group(1)


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


LINK_RE = re.compile(r"\[([^\[\]]+)\]\((\S+?)\)")


def render_inline(text):
    """Escape XML, then translate Fountain emphasis and markdown links
    ([text](url)) into reportlab markup."""
    text = escape_xml(text)
    text = LINK_RE.sub(
        lambda m: f'<a href="{m.group(2)}" color="blue"><u>{m.group(1)}</u></a>', text
    )
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
    if LIST_BULLET_RE.match(line) or LIST_ORDERED_RE.match(line):
        return True
    if is_all_caps_name(strip_character_extension(line)):
        return True  # conservatively treat as a potential character cue
    return False


MARKDOWN_HEADING_RE = re.compile(r"^(\*{1,3}|_)(.+)\1$")

# Aliases (case-insensitive, markdown emphasis stripped) recognised as
# preliminary-section headings when they appear as their own line, in
# markdown emphasis, in the body before the first scene heading - an
# alternative to supplying the same sections via title-page keys, for
# writers who prefer to keep breakdowns as visible script text.
BREAKDOWN_HEADING_ALIASES = {
    "characters": "characters",
    "character": "characters",
    "cast of characters": "characters",
    "setting": "setting",
    "time": "time",
    "setting & time": "setting",
    "setting and time": "setting",
    "scene breakdown": "scene breakdown",
    "scenes": "scene breakdown",
}


def _match_breakdown_heading(line):
    """If `line` is a standalone markdown-emphasised heading (*Text*,
    **Text**, ***Text***, or _Text_, with an optional trailing colon) that
    names one of the known preliminary sections, return its canonical
    title-page key. Otherwise return None."""
    line = line.strip()
    if line.endswith(":"):
        line = line[:-1].strip()
    m = MARKDOWN_HEADING_RE.match(line)
    if not m:
        return None
    inner = m.group(2).strip()
    if inner.endswith(":"):
        inner = inner[:-1].strip()
    return BREAKDOWN_HEADING_ALIASES.get(inner.lower())


def _front_matter_end(lines, start_idx):
    """Index of the first line, at or after start_idx, that begins the
    real body of the script (a section marker or a scene heading).
    Breakdown headings are only recognised before this point."""
    for i in range(start_idx, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return i
        if stripped.startswith(".") and not stripped.startswith(".."):
            return i
        if SCENE_HEADING_RE.match(stripped):
            return i
    return len(lines)


def _extract_markdown_breakdowns(lines, start_idx):
    """Pull Characters / Setting & Time / Scene Breakdown sections written
    as markdown-heading body text (rather than title-page keys) out of the
    lines between start_idx and the first scene heading, so they render as
    preliminary pages instead of being parsed as stage direction.

    Returns (extracted: dict[str, list[str]], lines: list[str]) - the
    returned `lines` list has the consumed lines blanked out in place, so
    downstream indices are unaffected.
    """
    end = _front_matter_end(lines, start_idx)
    lines = list(lines)
    extracted = {}
    active_key = None

    for i in range(start_idx, end):
        stripped = lines[i].strip()
        if not stripped:
            continue
        if PAGE_BREAK_RE.match(stripped):
            active_key = None
            continue
        heading_key = _match_breakdown_heading(stripped)
        if heading_key:
            active_key = heading_key
            lines[i] = ""
            continue
        if active_key:
            extracted.setdefault(active_key, []).append(stripped)
            lines[i] = ""

    if extracted:
        # A page break that no longer has any real content before the next
        # page break (or the end of the front matter) only existed to
        # separate a section we just pulled out - drop it too, so it
        # doesn't render as a blank page.
        i = start_idx
        while i < end:
            if PAGE_BREAK_RE.match(lines[i].strip()):
                j = i + 1
                has_content = False
                while j < end and not PAGE_BREAK_RE.match(lines[j].strip()):
                    if lines[j].strip():
                        has_content = True
                        break
                    j += 1
                if not has_content:
                    lines[i] = ""
            i += 1

    return extracted, lines


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

    extracted, lines = _extract_markdown_breakdowns(lines, idx)
    for key, values in extracted.items():
        title_page.setdefault(key, []).extend(values)

    # Anything left before the first act/section or scene heading is a
    # preface (author's notes, music notes, and the like) rather than
    # stage direction, and should be rendered as normal body text.
    preface_end = _front_matter_end(lines, idx)

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
            heading, number = split_scene_number(stripped[1:].strip())
            elements.append(
                Element("scene_heading", heading, {"scene_number": number} if number else None)
            )
            idx += 1
            continue

        if SCENE_HEADING_RE.match(stripped):
            heading, number = split_scene_number(stripped)
            elements.append(
                Element("scene_heading", heading, {"scene_number": number} if number else None)
            )
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

        if idx < preface_end:
            m_ordered = LIST_ORDERED_RE.match(stripped)
            if m_ordered:
                elements.append(
                    Element(
                        "preface_list_item",
                        m_ordered.group(2).strip(),
                        {"marker": f"{m_ordered.group(1)}."},
                    )
                )
                idx += 1
                continue

            m_bullet = LIST_BULLET_RE.match(stripped)
            if m_bullet:
                elements.append(
                    Element("preface_list_item", m_bullet.group(1).strip(), {"marker": "•"})
                )
                idx += 1
                continue

        para_start = idx
        action_lines = [stripped]
        idx += 1
        while (
            idx < n
            and lines[idx].strip() != ""
            and not _starts_new_element(lines[idx].strip())
        ):
            action_lines.append(lines[idx].strip())
            idx += 1
        el_type = "preface" if para_start < preface_end else "action"
        elements.append(Element(el_type, " ".join(action_lines)))

    return title_page, elements
