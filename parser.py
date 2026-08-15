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

How this module fits together, for anyone new to the codebase: the public
entry point is parse_fountain() at the bottom of the file. It turns raw
Fountain text into two things: a `title_page` dict (Key: value pairs from
the top of the file) and a flat list of `Element` objects representing
everything else, in reading order. engine.py then walks that Element list
and turns it into a PDF. This module knows nothing about PDFs or fonts -
its only job is "turn text into a structured list of tagged fragments".
"""

import re


class Element:
    """One piece of parsed script content - a scene heading, a line of
    dialogue, an action paragraph, etc. `type` says which kind it is (the
    rest of the codebase checks this string, e.g. `el.type == "dialogue"`),
    `text` is the actual content, and `meta` is a small dict for anything
    extra a particular type needs (e.g. a scene_heading's forced number).

    __slots__ below is a small memory/speed optimisation: by default every
    Python object gets a dict to hold its attributes, which is flexible but
    a bit wasteful when you create thousands of small, fixed-shape objects
    like this one (a typical script parses into thousands of Elements).
    __slots__ tells Python "this class only ever has these three
    attributes", so instances skip the per-object dict entirely. The
    trade-off is you can no longer add a new attribute that isn't listed
    here - e.g. `el.foo = 1` would raise an AttributeError.
    """

    __slots__ = ("type", "text", "meta")

    def __init__(self, type_, text="", meta=None):
        self.type = type_
        self.text = text
        # `meta or {}`: if the caller passes meta=None (the default) or an
        # empty dict, this falls back to a fresh {} instead. Using `{}` as
        # a *default argument value* directly (def __init__(self, meta={})）
        # would be a classic Python bug: default argument values are only
        # evaluated once, when the function is defined, so every Element
        # that didn't pass meta would end up sharing (and mutating) the
        # exact same dict. Defaulting to None and building the dict inside
        # the function body avoids that trap.
        self.meta = meta or {}

    def __repr__(self):
        # __repr__ controls what you see when you print() an Element or
        # inspect one in a debugger. !r inside the f-string calls repr()
        # on that value too, so strings show their quotes - easier to spot
        # stray whitespace than str()'s plain output would be.
        return f"Element({self.type!r}, {self.text!r}, {self.meta!r})"


# --- Regular expressions used throughout the parser ------------------------
#
# A quick primer on the syntax below, since regexes are dense if you haven't
# used them much: `^`/`$` anchor to the start/end of the string (or line, in
# MULTILINE mode - we don't use that here, we match one line at a time
# instead). `[...]` is a character class ("any one of these characters").
# `+` means "one or more of the previous thing", `*` means "zero or more",
# `?` means "zero or one" (optional). `(...)` captures a group we can pull
# back out with `.group(1)`, `.group(2)`, etc. `\s` is whitespace, `\.` is a
# literal dot (a bare `.` in regex means "any character", so it has to be
# escaped to mean an actual period).

# A scene heading: starts with INT, EXT, EST, INT/EXT, or I/E, followed by a
# period or a space. re.IGNORECASE means "int." and "INT." both match.
SCENE_HEADING_RE = re.compile(r"^(INT|EXT|EST|INT\.?/EXT|I/E)[\.\s]", re.IGNORECASE)

# A title-page "Key: value" line, e.g. "Title: My Play" or "Draft date: 2026".
# Group 1 is the key (letters/digits/spaces/underscore/hyphen), group 2 is
# whatever follows the colon (can be empty, if the value is on later
# indented lines instead - see _parse_title_page).
TITLE_PAGE_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 _\-]*):\s*(.*)$")

# A transition line that ends in "TO:", e.g. "CUT TO:" or "SMASH TO:".
TRANSITION_RE = re.compile(r"^[A-Z0-9 .'\-]+TO:$")

# A page break: a line of three or more "=" characters and nothing else.
PAGE_BREAK_RE = re.compile(r"^={3,}$")

# A section heading: one or more leading "#" characters (the count is the
# nesting depth - "#" = Act, "##" = Scene, and so on), then the heading text.
SECTION_RE = re.compile(r"^(#+)\s*(.*)$")

# A forced scene number tacked onto the end of a scene heading, per the
# Fountain spec, e.g. "INT. HOUSE - DAY #2A#" - the number between the two
# "#" characters can mix letters and digits.
SCENE_NUMBER_RE = re.compile(r"\s*#([0-9A-Za-z][0-9A-Za-z.\-]*)#\s*$")

# A markdown-style bullet list item: "-", "*", or "+", then at least one
# space, then the item text.
LIST_BULLET_RE = re.compile(r"^[-*+]\s+(.+)$")

# A markdown-style ordered list item: one or more digits, then "." or ")",
# then at least one space, then the item text.
LIST_ORDERED_RE = re.compile(r"^(\d+)[.)]\s+(.+)$")


def split_scene_number(text):
    """Split a forced scene number (e.g. "INT. HOUSE - DAY #2A#") off the
    end of a scene heading line, per the Fountain spec. Returns
    (heading_text, number_or_None)."""
    # .search() (rather than .match()) looks for the pattern anywhere in
    # the string, but since SCENE_NUMBER_RE ends with `$` it can only ever
    # match right at the end of the line anyway.
    m = SCENE_NUMBER_RE.search(text)
    if not m:
        return text, None
    # text[: m.start()] is everything before the matched "#2A#" part;
    # .rstrip() trims the trailing space that was in front of it.
    return text[: m.start()].rstrip(), m.group(1)


def strip_boneyard_and_notes(text):
    """Remove Fountain "boneyard" comments (/* ... */) and inline notes
    ([[ ... ]]) before parsing proper starts, so their contents never leak
    into the output as stray text."""
    # re.DOTALL makes `.` also match newlines, so a boneyard/note block that
    # spans multiple lines gets removed in one go rather than leaving
    # fragments behind. `.*?` (non-greedy) stops at the *first* closing
    # marker instead of the *last* one in the file - important, since a
    # greedy `.*` would swallow everything between the first `/*` and the
    # last `*/` in the whole script.
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"\[\[.*?\]\]", "", text, flags=re.DOTALL)
    return text


def is_all_caps_name(line):
    """True if every *letter* in `line` is uppercase (punctuation, digits
    and spaces are ignored) - the Fountain heuristic for "this line is
    probably a character cue"."""
    # A list comprehension: builds a new list by keeping only the
    # characters for which the condition (c.isalpha()) is true. Equivalent
    # to, but more compact than:
    #   letters = []
    #   for c in line:
    #       if c.isalpha():
    #           letters.append(c)
    letters = [c for c in line if c.isalpha()]
    if not letters:
        # A line with no letters at all (e.g. just punctuation) can't
        # sensibly be "all caps", so treat it as not a match.
        return False
    # all(...) is a builtin that returns True only if every item in the
    # iterable is truthy - here, every letter passes c.isupper().
    return all(c.isupper() for c in letters)


# A character cue with a trailing "extension" in parentheses, e.g.
# "MARGARET (V.O.)". Group 1 is the name, group 2 is the "(V.O.)" part.
# `\S` is "any non-whitespace character" - used here so the name's capture
# doesn't include trailing spaces before the parenthetical.
CHARACTER_EXTENSION_RE = re.compile(r"^(.*\S)\s*(\([^)]*\))\s*$")


def strip_character_extension(name):
    """Split a trailing parenthetical extension off a character cue, e.g.
    "MARGARET (V.O.)" -> "MARGARET". Per the Fountain spec, character
    extensions may be uppercase or lowercase and shouldn't affect whether
    the line is recognised as a character cue - only the name itself needs
    to be all-caps."""
    m = CHARACTER_EXTENSION_RE.match(name)
    # The conditional expression `a if cond else b` picks m.group(1) when
    # the regex matched, otherwise falls back to the original, unmodified
    # name (this is a plain, non-caps-check-worthy dialogue name).
    return m.group(1) if m else name


def escape_xml(text):
    """Escape the handful of characters that are special in the small XML
    subset reportlab's Paragraph markup uses (<b>, <i>, etc.), so that a
    literal "&" or "<" typed by the writer doesn't get misread as markup.
    Order matters: "&" must be escaped first, otherwise the "&amp;" we
    produce for a literal "&" would itself get escaped a second time."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# Markdown-style link syntax: [link text](https://example.com). Group 1 is
# the visible text, group 2 is the URL. `[^\[\]]+` means "one or more
# characters that are not '[' or ']'", which keeps the text group from
# accidentally swallowing a second, adjacent [link](url).
LINK_RE = re.compile(r"\[([^\[\]]+)\]\((\S+?)\)")


def render_inline(text):
    """Escape XML, then translate Fountain emphasis and markdown links
    ([text](url)) into reportlab markup."""
    text = escape_xml(text)
    # re.sub's replacement argument can be a function instead of a string:
    # it's called once per match with the Match object, and whatever it
    # returns is substituted in. Here we use a `lambda` (an anonymous,
    # one-expression function) to build the <a href="..."> tag from the
    # two captured groups.
    text = LINK_RE.sub(
        lambda m: f'<a href="{m.group(2)}" color="blue"><u>{m.group(1)}</u></a>', text
    )
    # forced line break: line ends with two-or-more trailing spaces in source,
    # already trimmed by caller in most paths, so this mainly covers the
    # dialogue/action join case where we insert explicit breaks.
    #
    # The next four substitutions handle Fountain's emphasis markers. Order
    # matters here too: the longest marker (***bold italic***) has to be
    # tried before the shorter ones (**bold**, *italic*), otherwise the two
    # extra asterisks of a ***triple*** would just look like the start/end
    # of a **double** match and get misinterpreted. `.+?` is a non-greedy
    # "one or more of anything", so `**a** and **b**` matches as two
    # separate bold runs instead of one bold run spanning "a** and **b".
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # The italic pattern additionally uses lookaround assertions -
    # `(?<!\*)` ("not preceded by an asterisk") and `(?!\*)` ("not followed
    # by an asterisk") - so that the single asterisks belonging to an
    # already-handled **bold** or ***bold italic*** run (which by this
    # point still exist in the original text, since re.sub scans the
    # original string, not the partially-replaced one, within a single
    # call) don't get misread as a second, single-asterisk italic marker.
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"_(.+?)_", r"<u>\1</u>", text)
    return text


def _starts_new_element(line):
    """True if a (stripped, non-blank) line looks like the start of some
    element other than a continuation of the current action paragraph."""
    if not line:
        return False
    # `line[0] in "#!~>@"` is a neat trick for "is the first character one
    # of these five?" - checking membership in a short string is the same
    # as checking membership in a list of those characters, just terser.
    if line[0] in "#!~>@":
        return True
    if line.startswith(".") and not line.startswith(".."):
        # A single leading "." forces a scene heading, but Fountain
        # reserves ".." (and beyond) so writers can start an action line
        # with a literal ellipsis without it being mistaken for one.
        return True
    if PAGE_BREAK_RE.match(line):
        return True
    if line.startswith("="):
        # A synopsis line (a single "=" followed by text) also isn't part
        # of an action paragraph, even though it's handled separately from
        # a true page break (PAGE_BREAK_RE, three-or-more "=") elsewhere.
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


# A standalone markdown-emphasised heading line: *Text*, **Text**,
# ***Text***, or _Text_ - the SAME wrapping character (or run of up to
# three asterisks) has to open and close it. `\1` is a *backreference*: it
# means "whatever group 1 actually matched", not "one more asterisk" - so
# this pattern only matches when the closing marker is identical to the
# opening one (e.g. "**Text**" but not "**Text*").
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
    # dict.get(key) returns None if the key isn't present, instead of
    # raising a KeyError the way dict[key] would - handy here since "no
    # match" is an expected, normal outcome, not an error.
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
    # Nothing in the file ever starts the "real" script - treat the whole
    # remainder as front matter.
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
    # Copy the list rather than mutating the caller's - `lines[i] = ""`
    # below writes into this local copy only, so the original list passed
    # in by the caller is left untouched. (Lists are mutable and passed by
    # reference in Python, so without this copy we'd be silently editing
    # someone else's data.)
    lines = list(lines)
    extracted = {}
    active_key = None  # which section (if any) subsequent lines belong to

    for i in range(start_idx, end):
        stripped = lines[i].strip()
        if not stripped:
            # A blank line inside an active section is a paragraph break
            # the writer intended (e.g. separating a cast list from a note
            # about doubled roles) - record it as a single "" marker so the
            # renderer can turn it into a visible gap later (see engine.py's
            # _preliminary_flowables). `extracted.get(active_key)` guards
            # against marking a blank line before any real content has been
            # seen yet, and the `!= ""` check collapses several blank
            # source lines in a row into just one marker, rather than
            # stacking up extra gaps for each one.
            if active_key and extracted.get(active_key) and extracted[active_key][-1] != "":
                extracted[active_key].append("")
            continue
        if PAGE_BREAK_RE.match(stripped):
            # A page break always ends whatever section was active, so a
            # block of unrelated body text after it doesn't get scooped up
            # into the previous section by mistake.
            active_key = None
            continue
        heading_key = _match_breakdown_heading(stripped)
        if heading_key:
            active_key = heading_key
            lines[i] = ""
            continue
        if active_key:
            # dict.setdefault(key, []) returns the existing list for `key`
            # if there is one, or inserts and returns a fresh empty list if
            # not - a one-line way to say "append to this key's list,
            # creating the list on first use".
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
    # The title page, if present, is the block of non-blank lines at the
    # very top of the file - collect them first, then decide below whether
    # they actually look like a title page at all.
    block = []
    i = 0
    while i < len(lines) and lines[i].strip() != "":
        block.append(lines[i])
        i += 1

    if not block or not TITLE_PAGE_KEY_RE.match(block[0]):
        # No leading block at all, or the first line isn't "Key: value" -
        # this file has no title page, so the whole thing is body text.
        return {}, 0

    # Every line in the block must either start a new "Key: value" pair, or
    # be an indented continuation of the previous key's value - otherwise
    # this isn't really a title page (e.g. it's a scene that happens to
    # start with a line matching TITLE_PAGE_KEY_RE by coincidence).
    # `all(...)` over a generator expression here means "check this
    # condition for every line in block, stopping early if one fails".
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
            # .lower() so lookups elsewhere (e.g. title_page.get("title"))
            # don't have to worry about how the writer capitalised the key
            # in the source file.
            current_key = m.group(1).strip().lower()
            val = m.group(2).strip()
            title_page.setdefault(current_key, []).append(val)
        elif current_key:
            # An indented continuation line for whichever key we last saw -
            # e.g. a multi-line "Contact:" block with the address on
            # several following lines.
            title_page[current_key].append(l.strip())

    idx = i
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    return title_page, idx


def parse_fountain(text):
    """Parse Fountain source text.

    Returns (title_page: dict[str, list[str]], elements: list[Element]).
    """
    # Normalise line endings first, so the rest of the parser (which splits
    # on plain "\n") doesn't have to care whether the source file used
    # Windows (\r\n), old Mac (\r), or Unix (\n) line endings.
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

    # The main parsing loop. `idx` is a cursor into `lines` that we move
    # forward by hand (rather than using a `for` loop) because several
    # branches below need to consume more than one line at a time (e.g. a
    # character cue followed by several lines of dialogue) before the loop
    # continues. Every branch below ends by advancing `idx` and either
    # `continue`-ing back to the top of the loop or falling through to the
    # default "action paragraph" handling at the bottom.
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
            depth = len(m.group(1))  # number of leading "#" characters
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
                # `{"scene_number": number} if number else None` - Element's
                # __init__ turns a None meta into {} anyway, so this just
                # avoids storing a "scene_number": None entry when there
                # wasn't actually a forced number.
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

        # Character cue detection: either explicitly forced with a leading
        # "@" (e.g. "@McDonald's"), or inferred - an all-caps line that has
        # a non-blank line right after it (dialogue can't be empty).
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
            # Everything up to the next blank line belongs to this
            # character's speech: parentheticals like "(beat)" become their
            # own element, everything else is a plain dialogue line.
            while idx < n and lines[idx].strip() != "":
                dline = lines[idx].strip()
                if dline.startswith("(") and dline.endswith(")"):
                    elements.append(Element("parenthetical", dline))
                else:
                    elements.append(Element("dialogue", dline))
                idx += 1
            continue

        if stripped.startswith("~"):
            # Forced italic action/lyric line - the "italic" flag in meta
            # isn't actually read anywhere downstream right now (the engine
            # always renders "action" elements in the style's configured
            # action font), but it's kept here in case a future style wants
            # to distinguish these.
            elements.append(Element("action", stripped[1:].strip(), {"italic": True}))
            idx += 1
            continue

        if stripped.startswith("!"):
            # Forced action - overrides the all-caps-line-becomes-a-
            # character-cue heuristic above for a line that would otherwise
            # be mistaken for one.
            elements.append(Element("action", stripped[1:].strip()))
            idx += 1
            continue

        # List items (bullet or numbered) only count as such before the
        # first scene heading - this is what lets writers format a preface
        # "Song List" as a real bulleted list instead of it being read as
        # ordinary stage direction.
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

        # Default case: an action paragraph (or, before the first scene
        # heading, a preface paragraph - see el_type below). Keep consuming
        # lines, joined with a space, until a blank line or something that
        # _starts_new_element() recognises as a different kind of element.
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
