"""
fountain2pdf.engine
---------------------
Renders parsed Fountain elements into a PDF, driven entirely by a
styles.base.Style object (see styles/apt.py for an example). This module
has no knowledge of any one house style - all margins, fonts, sizes and
layout flags come from the Style passed in.

Also implements two features common to formal play-submission styles:

  - A running header strap ("PLAY TITLE | SCENE") centered at the top of
    each dialogue page, kept in sync with the most recent Act/Scene heading.
  - Pagination that starts at the first page of dialogue, leaving the title
    page and any preliminary pages unnumbered.

Both are driven by Style.header_strap / Style.paginate_from_body, so a
style that doesn't want them can simply turn them off.

Character cues support two layouts, chosen per-style via
Style.character_on_own_line: name and dialogue sharing the first line in a
hanging-indent table (APT and similar screenplay-adjacent formats), or the
name as its own centered line with dialogue as separate paragraphs below
(Dramatists Guild "Modern Play Format" and similar).

A speech that doesn't fit in the remaining space on a page breaks across
the page boundary rather than being pushed to the next page as a whole -
see _SpeechFlowable. Style.more_continued controls whether that break gets
a "(MORE)" / "(CONT'D)" cue or is left unmarked.

Known simplification: a break can only happen *between* two
dialogue/parenthetical lines (or between the character name and the first
line), never in the middle of one - so a single line so long it doesn't
fit on any one page is still pushed to the next page as a whole.

A note on reportlab, for anyone new to it: reportlab builds a PDF in two
steps. First you create a list of "flowables" - Paragraph, Spacer,
PageBreak, Table, etc. - which describe *what* to draw but not *where*;
each one knows how to lay itself out and how tall it is, but has no idea
what page it'll land on. Then you hand that list ("the story") to a
SimpleDocTemplate and call .build() on it, which flows the flowables down
the page(s) one after another, starting a new page whenever the current
one runs out of room (or a PageBreak() forces one). This module's job is
almost entirely "turn a list of parser.Element into a list of flowables" -
see _build_story() below, which is the heart of the module.
"""

import io
import re

from reportlab.lib.colors import Color
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    KeepTogether,
    Table,
    TableStyle,
    Flowable,
)

from parser import render_inline

# The three "preliminary" pages (Characters / Setting & Time / Scene
# Breakdown) that can appear right after the title page. Each entry is
# (heading text to print, [title-page keys to look for, in priority
# order]) - see _preliminary_flowables() below for how this list is used.
PRELIMINARY_SECTIONS = [
    ("CHARACTERS", ["characters", "character"]),
    ("SETTING & TIME", ["setting", "time"]),
    ("SCENE BREAKDOWN", ["scene breakdown", "scenes", "scene_breakdown"]),
]

# Style objects store alignment as a plain string ("left"/"center"/"right")
# so a styles/*.py file doesn't need to import anything from reportlab just
# to set one field. This dict translates that string into the actual
# reportlab constant (just an integer under the hood) that ParagraphStyle
# expects.
_ALIGN_MAP = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}


def _styles(style):
    """Build the full set of reportlab ParagraphStyle objects for one
    render, from a Style config object. Returns a dict keyed by name (e.g.
    "dialogue", "action") - _build_story() below looks styles up by that
    name as it walks the parsed elements. Rebuilding this fresh for every
    render (rather than caching it) keeps things simple: nothing here holds
    state between pages or between builds.

    A ParagraphStyle is reportlab's bundle of "how should this block of
    text look" - font, size, line spacing (leading), alignment, indents,
    and spacing before/after the paragraph. A Paragraph flowable (created
    later, in _build_story) always takes one of these plus the actual text.
    """
    return {
        "title": ParagraphStyle(
            "title", fontName=style.font_regular, fontSize=style.title_size,
            leading=style.title_size * 1.2, alignment=TA_CENTER, spaceAfter=18,
        ),
        "byline": ParagraphStyle(
            "byline", fontName=style.font_regular, fontSize=style.byline_size,
            leading=style.byline_size * 1.2, alignment=TA_CENTER, spaceAfter=6,
        ),
        "contact": ParagraphStyle(
            "contact", fontName=style.font_regular, fontSize=style.body_size,
            leading=style.leading, alignment=TA_LEFT,
        ),
        "prelim_heading": ParagraphStyle(
            "prelim_heading",
            fontName=style.font_bold if style.prelim_heading_bold else style.font_regular,
            fontSize=style.body_size,
            leading=style.leading, alignment=TA_CENTER, spaceBefore=0, spaceAfter=14,
        ),
        "prelim_body": ParagraphStyle(
            "prelim_body", fontName=style.font_regular, fontSize=style.body_size,
            leading=style.leading, alignment=TA_LEFT, spaceAfter=4,
        ),
        "act": ParagraphStyle(
            "act",
            # Pick the one font file that matches this style's bold/italic
            # flags. reportlab doesn't synthesize bold or italic on the fly
            # from a regular font - each combination (regular, bold,
            # italic, bold+italic) has to be a separately registered font,
            # so we choose between the four up front. This chain of
            # `... if ... else ... if ... else ...` is a Python
            # conditional expression (a "ternary"); reading it top to
            # bottom, the first condition that's True wins.
            fontName=(
                style.font_bold_italic if (style.act_bold and style.act_italic) else
                style.font_bold if style.act_bold else
                style.font_italic if style.act_italic else
                style.font_regular
            ),
            fontSize=style.act_size,
            leading=style.leading,
            alignment=_ALIGN_MAP[style.act_alignment],
            spaceBefore=6,
            spaceAfter=18,
        ),
        "scene_heading": ParagraphStyle(
            "scene_heading",
            fontName=(
                style.font_bold_italic if (style.scene_bold and style.scene_italic) else
                style.font_bold if style.scene_bold else
                style.font_italic if style.scene_italic else
                style.font_regular
            ),
            fontSize=style.scene_size,
            leading=style.leading,
            alignment=_ALIGN_MAP[style.scene_alignment],
            spaceBefore=6,
            spaceAfter=18,
        ),
        "character": ParagraphStyle(
            "character",
            fontName=style.font_bold if style.character_bold else style.font_regular,
            fontSize=style.character_size,
            leading=style.leading, alignment=_ALIGN_MAP[style.character_alignment],
            spaceBefore=0, spaceAfter=0,
        ),
        "dialogue": ParagraphStyle(
            "dialogue", fontName=style.font_regular, fontSize=style.body_size,
            leading=style.leading, alignment=TA_LEFT, leftIndent=0, rightIndent=0,
            spaceBefore=0, spaceAfter=0,
        ),
        "parenthetical": ParagraphStyle(
            "parenthetical",
            fontName=style.font_italic if style.parenthetical_italic else style.font_regular,
            fontSize=style.body_size, leading=style.leading, alignment=TA_LEFT,
            leftIndent=style.parenthetical_left_indent,
            textColor=Color(*style.action_color),
            spaceBefore=0, spaceAfter=0,
        ),
        # Only used by the shared-line (character_on_own_line=False) table
        # layout, for a speech's *second* and later lines: the first line
        # shares a table row with the character name (see
        # _character_block_parts), but every line after that is its own
        # standalone paragraph so a page break can fall between them. These
        # two styles give those standalone paragraphs the same hanging
        # indent the table would have given them, so they still line up
        # under the dialogue column rather than under the name.
        "dialogue_continued": ParagraphStyle(
            "dialogue_continued", fontName=style.font_regular, fontSize=style.body_size,
            leading=style.leading, alignment=TA_LEFT,
            leftIndent=style.name_col_width + style.dialogue_gutter, rightIndent=0,
            spaceBefore=0, spaceAfter=0,
        ),
        "parenthetical_continued": ParagraphStyle(
            "parenthetical_continued",
            fontName=style.font_italic if style.parenthetical_italic else style.font_regular,
            fontSize=style.body_size, leading=style.leading, alignment=TA_LEFT,
            leftIndent=style.name_col_width + style.dialogue_gutter,
            textColor=Color(*style.action_color),
            spaceBefore=0, spaceAfter=0,
        ),
        "more_continued": ParagraphStyle(
            "more_continued", fontName=style.font_regular, fontSize=style.body_size,
            leading=style.leading, alignment=TA_CENTER, spaceBefore=6, spaceAfter=0,
        ),
        "action": ParagraphStyle(
            "action", fontName=style.font_italic if style.action_italic else style.font_regular,
            fontSize=style.action_size,
            leading=style.leading, alignment=_ALIGN_MAP[style.action_alignment],
            leftIndent=style.action_left_indent, rightIndent=style.action_right_indent,
            # Color(*style.action_color) unpacks the (r, g, b) tuple from
            # the style into Color's three positional arguments - the same
            # as writing Color(style.action_color[0], style.action_color[1],
            # style.action_color[2]).
            textColor=Color(*style.action_color),
            spaceBefore=10, spaceAfter=10,
        ),
        "preface": ParagraphStyle(
            "preface", fontName=style.font_regular, fontSize=style.body_size,
            leading=style.leading, alignment=TA_LEFT,
            spaceBefore=10, spaceAfter=10,
        ),
        "preface_list": ParagraphStyle(
            "preface_list", fontName=style.font_regular, fontSize=style.body_size,
            leading=style.leading, alignment=TA_LEFT,
            leftIndent=18, bulletIndent=0,
            spaceBefore=2, spaceAfter=2,
        ),
        "transition": ParagraphStyle(
            "transition", fontName=style.font_bold, fontSize=style.body_size,
            leading=style.leading, alignment=TA_CENTER, spaceBefore=10, spaceAfter=10,
        ),
        "centered": ParagraphStyle(
            "centered", fontName=style.font_regular, fontSize=style.body_size,
            leading=style.leading, alignment=TA_CENTER, spaceBefore=6, spaceAfter=6,
        ),
    }


def _title_page_flowables(title_page, styles):
    """Build the flowables for the title page: title, byline (credit +
    author), then any remaining title-page keys (address, contact details,
    etc.) as a lower block of plain text."""
    # Spacer(width, height) just reserves vertical space - width is ignored
    # for a Spacer used in a single-column story like this one, only height
    # matters. 28.35 points per cm, so this is "leave about 6.5cm blank"
    # before the title starts, roughly centering it on the page.
    flow = [Spacer(1, 6.5 * 28.35)]  # ~6.5cm, matches the old title-page layout

    # title_page is a dict[str, list[str]] (see parser._parse_title_page) -
    # every value is a list because a title-page key can span several
    # lines (e.g. a multi-line "Contact:" block). " ".join(...) collapses
    # that back down to one string; `.get("title", [])` returns an empty
    # list if there's no "title" key at all, so the join still works.
    title = " ".join(title_page.get("title", [])) or "Untitled"
    flow.append(Paragraph(render_inline(title), styles["title"]))

    # `title_page.get("author", title_page.get("authors", []))` tries the
    # singular key first and falls back to the plural if that's missing -
    # a nested .get() call used as the default value of the outer one.
    author = " ".join(title_page.get("author", title_page.get("authors", [])))
    credit = " ".join(title_page.get("credit", []))
    if credit:
        flow.append(Paragraph(render_inline(credit), styles["byline"]))
    if author:
        flow.append(Paragraph(render_inline(author), styles["byline"]))

    contact_lines = []
    for key, value in title_page.items():
        if key in ("title", "author", "authors", "credit"):
            continue
        # Skip anything that's actually a Characters/Setting/Scene
        # Breakdown key - those get their own preliminary pages (see
        # _preliminary_flowables) rather than showing up here as if they
        # were address details. This is a generator expression inside
        # any(): "is `key` equal to any alias, across every (heading,
        # keys) pair in PRELIMINARY_SECTIONS?" - it short-circuits and
        # returns True as soon as one match is found.
        if any(key == k for _, keys in PRELIMINARY_SECTIONS for k in keys):
            continue
        contact_lines.extend(value)
    if contact_lines:
        flow.append(Spacer(1, 6.5 * 28.35))
        for line in contact_lines:
            flow.append(Paragraph(render_inline(line), styles["contact"]))

    return flow


def _get_first(title_page, keys):
    """Return the first non-empty value found in title_page for any of
    `keys` (tried in order), or None if none of them are present. Used so
    a preliminary section can accept a couple of different spellings of
    its key (e.g. "characters" or "character")."""
    for k in keys:
        if k in title_page and title_page[k]:
            return title_page[k]
    return None


# A "Name<some gap>Description" line, e.g. "ALEX              41 years old" -
# writers commonly line these up with runs of spaces so they read as a
# column when viewed in a fixed-width editor. `\s{2,}` (two or more
# whitespace characters) is the separator: a *single* space is treated as
# just part of an ordinary sentence (so "KARIM and DR ABEL are played by
# the same actor." is correctly left alone), while two-or-more spaces is
# read as "the writer meant this as a column break". `(\S.*?)` (non-greedy)
# for the name lets it contain single spaces itself (e.g. "DR ABEL",
# "PROFESSOR DE VOS") while still stopping at the first big gap.
NAME_DESCRIPTION_RE = re.compile(r"^(\S.*?)\s{2,}(\S.*)$")

# The other common way writers format one of these entries: "Name:
# Description" (a colon, then at least one space) - e.g. "JOHN DOE: 45
# years old, a university professor." Tried only if the space-gap pattern
# above doesn't match.
NAME_DESCRIPTION_COLON_RE = re.compile(r"^(\S.*?):\s+(\S.*)$")

# Extra horizontal gap (points) between the name column and the
# description column in a preliminary section - the same idea as
# Style.dialogue_gutter, just not style-configurable since this is a
# best-effort fallback for source formatting, not a house-style rule.
_NAME_DESCRIPTION_GUTTER = 12


def _split_name_description(line):
    """If `line` looks like "Name<big gap>Description" or "Name:
    Description", return (name, description). Otherwise return None,
    meaning it should just be rendered as an ordinary paragraph."""
    m = NAME_DESCRIPTION_RE.match(line)
    if m:
        return m.group(1), m.group(2)
    m = NAME_DESCRIPTION_COLON_RE.match(line)
    return (m.group(1), m.group(2)) if m else None


def _name_description_row(name, description, name_col_width, available_width, styles, style):
    """One "Name   description" entry as a two-column, borderless table -
    the same technique _character_block_flowable uses for dialogue: a
    fixed-width left column and reportlab-driven wrapping in the right
    column give every row's description the same hanging indent, however
    long its name is, without depending on literal spaces in the source
    (which reportlab's Paragraph would collapse to one anyway - Paragraph
    text is interpreted a bit like HTML, where runs of whitespace aren't
    significant)."""
    name_rendered = render_inline(name)
    if style.name_description_name_underline:
        name_rendered = f"<u>{name_rendered}</u>"
    name_para = Paragraph(name_rendered, styles["prelim_body"])
    desc_para = Paragraph(render_inline(description), styles["prelim_body"])
    table = Table(
        [[name_para, desc_para]],
        colWidths=[name_col_width, available_width - name_col_width],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                # A bit of bottom padding on every row, so consecutive rows
                # don't sit flush against each other - Table doesn't pick
                # up a Paragraph's own spaceAfter the way stacked
                # Paragraphs flowing directly in the story would.
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (1, 0), (1, -1), _NAME_DESCRIPTION_GUTTER),
            ]
        )
    )
    return KeepTogether([table])


def _preliminary_flowables(title_page, styles, style):
    """Characters / Setting & Time / Scene Breakdown pages, built from
    whatever matching title-page keys the writer supplied. Any section with
    no matching key is simply skipped."""
    available_width = style.page_size[0] - style.left_margin - style.right_margin
    pages = []
    for heading, keys in PRELIMINARY_SECTIONS:
        if heading == "SETTING & TIME":
            # This one section is special-cased because it merges two
            # separate title-page keys ("setting" and "time") into a
            # single page, rather than looking up one list of aliases the
            # way the other two sections do.
            setting = _get_first(title_page, ["setting"])
            time_ = _get_first(title_page, ["time"])
            # `(setting or []) + (time_ or [])`: _get_first can return None,
            # and you can't concatenate None with a list, so this swaps in
            # an empty list wherever the value was missing before adding
            # the two together.
            lines = (setting or []) + (time_ or [])
        else:
            lines = _get_first(title_page, keys)
        if not lines:
            continue

        # Work out which lines in *this* section look like "Name
        # Description" entries, so a plain sentence elsewhere in the same
        # section (e.g. a note about doubling roles) isn't forced into a
        # column it was never meant to be part of.
        splits = [_split_name_description(line) for line in lines]
        names = [name for name, _ in (s for s in splits if s)]
        name_col_width = 0
        if names:
            # Size the shared name column to fit the *longest* name in
            # this section, so every row's description lines up in the
            # same place regardless of how short or long its own name is -
            # measured in the actual font/size these names will be drawn
            # in, rather than guessed from character count.
            name_col_width = (
                max(stringWidth(name, style.font_regular, style.body_size) for name in names)
                + _NAME_DESCRIPTION_GUTTER
            )

        heading_text = f"<u>{heading}</u>" if style.prelim_heading_underline else heading
        flow = [Paragraph(heading_text, styles["prelim_heading"])]
        for line, split in zip(lines, splits):
            if line == "":
                # A blank-line marker from _extract_markdown_breakdowns -
                # a paragraph break in the source, rendered as extra
                # vertical space rather than an empty line of text (an
                # empty Paragraph would just collapse to ~nothing).
                flow.append(_CollapsingSpacer(1, style.leading))
            elif split:
                name, description = split
                flow.append(
                    _name_description_row(
                        name, description, name_col_width, available_width, styles, style
                    )
                )
            else:
                flow.append(Paragraph(render_inline(line), styles["prelim_body"]))
        # Each section becomes its own list of flowables here (`pages` is a
        # list of lists) rather than one flat list, because _build_story()
        # needs to insert a PageBreak() between sections - it can't do that
        # unless it knows where one section's flowables end and the next
        # one's begin.
        pages.append(flow)
    return pages


def _tint_hex(style):
    """Build a "#rrggbb" hex string reportlab's inline <font color="..."> tag
    can use, from the style's (r, g, b) tuple where each channel is a float
    0..1. `round(c * 255)` scales that up to a 0..255 byte value, and
    "%02x" formats it as two lowercase hex digits (e.g. 26 -> "1a"),
    zero-padded so single-digit values still take up two characters."""
    return "#%02x%02x%02x" % tuple(round(c * 255) for c in style.action_color)


def _character_block_parts(name, lines, style, styles):
    """APT-style layout: the character name and the *first* line of the
    speech share one table row (a fixed-width left column for the name,
    the "tab stop" - reportlab has no built-in way to draw a hanging
    indent whose label is a separately-styled flowable, so a one-row,
    two-column table is the standard workaround). Every line after the
    first becomes its own standalone paragraph, indented to line up under
    that same column, rather than being crammed into the table too -
    returning a flat list of independent parts like this (instead of one
    combined flowable) is what lets a page break land between any two of
    them; see _SpeechFlowable, which is what actually uses this list."""
    name_para = Paragraph(render_inline(name), styles["character"])
    if not lines:
        # A character cue with no dialogue at all (unusual, but the parser
        # doesn't forbid it) - just the name, no table needed.
        return [name_para]

    tint_hex = _tint_hex(style)

    def render_line(kind, text):
        rendered = render_inline(text)
        if kind == "parenthetical" and style.parenthetical_italic:
            rendered = f"<i>{rendered}</i>"
        return rendered

    first_kind, first_text = lines[0]
    first_rendered = render_line(first_kind, first_text)
    # `consumed` is how many of `lines` end up on this shared first line -
    # normally just the one. But a parenthetical with no dialogue before
    # it reads as part of the same beat as the dialogue that follows it
    # ("(dialling) Be calm. Be direct."), so if that's what we've got,
    # pull the next line in too rather than leaving the parenthetical
    # stranded alone on the name's row with the dialogue starting fresh
    # underneath. Only the *leading* parenthetical gets this treatment -
    # one appearing later, mid-speech, still gets its own line below (see
    # the `lines[consumed:]` loop), since by then it's interrupting
    # dialogue that's already under way rather than introducing it.
    consumed = 1
    if first_kind == "parenthetical":
        first_rendered = f'<font color="{tint_hex}">{first_rendered}</font>'
        if len(lines) > 1 and lines[1][0] != "parenthetical":
            second_kind, second_text = lines[1]
            first_rendered = f"{first_rendered} {render_line(second_kind, second_text)}"
            consumed = 2
    first_para = Paragraph(first_rendered, styles["dialogue"])

    available_width = style.page_size[0] - style.left_margin - style.right_margin
    dialogue_col_width = available_width - style.name_col_width

    # A one-row, two-column Table: [[name_para, first_para]] is a list
    # containing one row, which is itself a list of the two cells in that
    # row. colWidths fixes each column's width explicitly (rather than
    # letting the table size itself to its content), which is what makes
    # every character name column line up at the same x position.
    table = Table(
        [[name_para, first_para]],
        colWidths=[style.name_col_width, dialogue_col_width],
        hAlign="LEFT",
    )
    # TableStyle takes a list of (command, (start_col, start_row),
    # (end_col, end_row), value) tuples. (0, 0), (-1, -1) means "from the
    # first cell to the last cell" - -1 is Python's usual "count from the
    # end" indexing, so this covers the whole table regardless of its
    # actual size. Padding is zeroed out on all sides so the table doesn't
    # add any space beyond what the paragraph styles already specify,
    # except for a manually-set left padding on the second column, which
    # is what actually creates the gap between the name and the dialogue.
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (1, 0), (1, -1), style.dialogue_gutter),
            ]
        )
    )

    parts = [table]
    for kind, text in lines[consumed:]:
        rendered = render_line(kind, text)
        style_key = "parenthetical_continued" if kind == "parenthetical" else "dialogue_continued"
        parts.append(Paragraph(rendered, styles[style_key]))
    return parts


def _short_parenthetical_word(text):
    """The inner text of a one-word (or shorter) parenthetical like
    "(laughing)" or "(patiently.)", or None if `text` has more than one
    word in it (once the parentheses themselves are stripped off)."""
    inner = text.strip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1]
    return inner if len(inner.split()) <= 1 else None


def _character_own_line_parts(name, lines, style, styles):
    """"Modern Play Format" layout: the character name is its own centered
    paragraph, with dialogue and parentheticals as separate full-width
    paragraphs below it - as opposed to APT's table layout, which puts the
    name and the first line of dialogue on the same line. Already a flat
    list of independent parts, one per line - nothing further to split up
    here, unlike the table layout above - except for one style-specific
    wrinkle (see character_short_parenthetical_inline below)."""
    name_rendered = render_inline(name)
    consumed = 0
    if style.character_short_parenthetical_inline and lines and lines[0][0] == "parenthetical":
        word = _short_parenthetical_word(lines[0][1])
        if word is not None:
            # A one-word direction right after the cue, e.g. "(laughing)",
            # reads as part of the same beat as the name itself - "JOHN
            # (laughing)" on one line - so it's folded into the name's own
            # paragraph instead of getting a line (and a whole beat) to
            # itself. A longer parenthetical here still gets its own line
            # below, same as one appearing later in the speech.
            name_rendered = f"{name_rendered} ({render_inline(word)})"
            consumed = 1
    parts = [Paragraph(name_rendered, styles["character"])]
    for kind, text in lines[consumed:]:
        rendered = render_inline(text)
        if kind == "parenthetical":
            parts.append(Paragraph(rendered, styles["parenthetical"]))
        else:
            parts.append(Paragraph(rendered, styles["dialogue"]))
    return parts


class _SpeechFlowable(Flowable):
    """A character cue plus its full speech, able to split across a page
    break between any two of its `parts` (the table/paragraph produced by
    _character_block_parts or _character_own_line_parts) - unlike wrapping
    those parts in KeepTogether, which used to force the entire speech
    onto one page. Only used when Style.more_continued is set; otherwise
    _build_story just adds `parts` straight to the story and lets
    reportlab's normal flowable-by-flowable pagination handle the break
    silently (see flush_char_block).

    This is a fairly deep dive into reportlab internals, so a bit of extra
    background for anyone who hasn't written a custom Flowable before:
    reportlab decides whether a flowable fits on the current page by
    calling its wrap(availWidth, availHeight) method, which must return
    (width, height) - if that height doesn't fit, reportlab calls
    split(availWidth, availHeight) instead, which must return a list of
    *replacement* flowables: the first is added to the current page, the
    rest go on to be tried (and, if necessary, split again) on the next
    one. The base Flowable class's default split() just returns [],
    meaning "not splittable, move the whole thing to the next page" - that
    default is what KeepTogether relies on; this class overrides it with
    real logic instead.
    """

    def __init__(self, name, parts, style, styles, min_lead=1, space_after=0):
        Flowable.__init__(self)
        self.name = name
        self.parts = parts
        self.style = style
        self.styles = styles
        # The gap that separates this speech from whatever follows it.
        # Carried as spaceAfter (the attribute reportlab's frame looks
        # for) rather than as a trailing Spacer flowable so that (a) it
        # collapses against the next element's own spaceBefore instead of
        # stacking on top of it - reportlab takes the larger of the two,
        # so a stage direction after a speech no longer gets speech_gap +
        # its own spaceBefore - and (b) reportlab discards it at a page
        # break, so it can never print as a blank strip at the top of the
        # next page.
        self.spaceAfter = space_after
        # How many of `parts` must always be kept together as one
        # unsplittable leading chunk - see split() for why this exists.
        # Clamped to len(parts) so a very short speech (e.g. just a name,
        # no dialogue at all) doesn't ask for more parts than it has.
        self.min_lead = min(min_lead, len(parts)) if parts else 0

    def wrap(self, availWidth, availHeight):
        # Each part's *natural* height, i.e. as if it had a whole empty
        # page to itself - a huge availHeight sentinel gets that out of a
        # part's own wrap() without it trying to split itself. Cached on
        # self so split() and draw() (called shortly after, at the same
        # width) don't need to redo this measurement.
        self._avail_width = availWidth
        self._heights = [p.wrap(availWidth, 0xFFFFFFF)[1] for p in self.parts]
        self.width = availWidth
        self.height = sum(self._heights)
        return self.width, self.height

    def split(self, availWidth, availHeight):
        more_para = None
        more_height = 0
        if self.style.more_continued:
            more_para = Paragraph(self.style.more_text, self.styles["more_continued"])
            more_height = more_para.wrap(availWidth, availHeight)[1]

        # reportlab's contract for split() is that the *first* flowable in
        # the returned list must actually fit in availHeight - if it
        # doesn't, reportlab has no valid way to place anything on the
        # current page and raises a LayoutError. So unlike a first pass at
        # this, this doesn't force the first part in unconditionally: if
        # even that alone doesn't fit in what's left on this page, there's
        # nothing valid to split here, and returning [] tells reportlab to
        # push this flowable onto a fresh page and ask again there
        # (starting a page with the room already used up by page furniture
        # is the normal, expected reason this happens).
        #
        # min_lead raises the bar on "that alone" from just the first part
        # to the first `min_lead` parts together. This matters for the
        # character_on_own_line layout, where the name and the first line
        # of dialogue are two *separate* parts (parts[0] and parts[1]):
        # without this, a page with just enough room left for the bare
        # name would strand it there with a "(MORE)" cue directly under it
        # and no actual dialogue - technically a valid split, but not one
        # anyone would want to read. Requiring the name and its first line
        # to fit together avoids that, at the cost of possibly leaving a
        # bit more blank space at the foot of the page.
        budget = availHeight - more_height
        lead_height = sum(self._heights[: self.min_lead])
        if not self._heights or lead_height > budget:
            return []

        fitted = list(self.parts[: self.min_lead])
        used = lead_height
        for part, h in zip(self.parts[self.min_lead :], self._heights[self.min_lead :]):
            if used + h > budget:
                break
            fitted.append(part)
            used += h

        remaining = self.parts[len(fitted):]
        if not remaining:
            # Nothing left over - reportlab only calls split() when wrap()
            # already reported this doesn't fit, so this shouldn't
            # normally happen, but there's nothing useful to split if it
            # does.
            return []

        this_page = list(fitted)
        if more_para is not None:
            this_page.append(more_para)

        next_parts = list(remaining)
        # The continuation gets its own repeated name (+ "(Cont.)") when
        # more_continued is on - always as a standalone paragraph, never
        # part of a table, regardless of which layout built the original
        # `parts` - so it needs the same "name plus its first line" min_lead
        # protection the character_on_own_line layout uses, in case this
        # speech needs a *third* page (or more) and the same stranding bug
        # would otherwise recur there.
        next_min_lead = self.min_lead
        if self.style.more_continued:
            cont_name = f"{self.name} {self.style.continued_text}"
            next_parts = [Paragraph(render_inline(cont_name), self.styles["character"])] + next_parts
            next_min_lead = min(2, len(next_parts))

        # Each half is wrapped in a *new* _SpeechFlowable rather than
        # returned as raw parts: reportlab will call wrap() on both of
        # these again by itself before drawing/placing them, and if
        # `next_parts` still doesn't fit on the following page either,
        # split() will simply be called on it again there - the same
        # logic handles a speech that needs three, four, or more pages
        # without this class needing to know that in advance.
        # The trailing gap belongs only on the piece that actually ends
        # the speech: the first piece is followed by the "(MORE)" cue and
        # a page break, not by the next element.
        return [
            _SpeechFlowable(self.name, this_page, self.style, self.styles, self.min_lead),
            _SpeechFlowable(
                self.name, next_parts, self.style, self.styles, next_min_lead,
                space_after=self.spaceAfter,
            ),
        ]

    def draw(self):
        # By the time draw() runs, self.canv (the current reportlab
        # canvas) has been set by the framework, and the canvas origin has
        # already been translated so that (0, 0) here is this flowable's
        # own bottom-left corner - draw() only ever needs to think in
        # those local coordinates, never in page coordinates.
        cur_top = self.height
        for part, h in zip(self.parts, self._heights):
            cur_top -= h
            part.drawOn(self.canv, 0, cur_top)


class _ScribeDocTemplate(SimpleDocTemplate):
    """SimpleDocTemplate subclass used for a first, throwaway build pass
    that discovers, for each page:
      - the most recent Act/Scene heading text (for the header strap)
      - the page on which the first scene heading landed (for pagination
        that starts counting at the first scene, and for the header strap,
        which shouldn't appear over preliminary/preface pages)

    This has to be a separate pass rather than read live during the real
    build: reportlab calls onPage at the *start* of a page, before that
    page's flowables (and afterFlowable) have run, so information about
    "what's on this page" isn't available yet when this page's header
    would need to be drawn. Flowables opt in by having an `apt_scene`
    and/or `apt_body_start` attribute set before being added to the story;
    afterFlowable is reportlab's documented extension point for this kind
    of thing (the same mechanism used to build tables of contents).
    """

    def __init__(self, *args, **kwargs):
        # Subclassing SimpleDocTemplate: this class *is* one (it inherits
        # every method SimpleDocTemplate has), plus the extra bits added
        # here. `SimpleDocTemplate.__init__(self, *args, **kwargs)` runs
        # the parent class's normal setup first (`*args`/`**kwargs` just
        # forward on whatever arguments this class was constructed with,
        # unexamined), then the two lines below add our own extra state on
        # top of it.
        SimpleDocTemplate.__init__(self, *args, **kwargs)
        self.dialogue_start_page = None
        self.scene_events = []  # [(page_number, scene_text), ...] in order

    def afterFlowable(self, flowable):
        # reportlab calls this automatically after laying out each
        # flowable during doc.build() - we never call it ourselves.
        # getattr(flowable, "apt_scene", None) reads the flowable's
        # apt_scene attribute if it has one, or returns None if it
        # doesn't (a plain flowable.apt_scene would raise an
        # AttributeError instead) - most flowables never get this
        # attribute set at all, so this has to tolerate its absence.
        scene = getattr(flowable, "apt_scene", None)
        if scene is not None:
            self.scene_events.append((self.page, scene))
        if getattr(flowable, "apt_body_start", False) and self.dialogue_start_page is None:
            self.dialogue_start_page = self.page


# A lookup table for converting an integer into lowercase Roman numerals,
# largest value first. Each entry also includes the "subtractive" forms
# (900 -> "cm", 400 -> "cd", etc.) so the conversion loop below doesn't
# need any special-case logic for them.
_ROMAN_NUMERALS = [
    (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
    (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
    (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
]


def _to_roman(n):
    """Convert a positive integer to a lowercase Roman numeral string."""
    result = []
    # Greedy algorithm: repeatedly subtract off the largest value from the
    # table that still fits, appending its symbol each time, until nothing
    # is left. E.g. for n=14: 10 fits once ("x", n becomes 4), then 4 fits
    # once ("iv", n becomes 0) -> "xiv".
    for value, symbol in _ROMAN_NUMERALS:
        while n >= value:
            result.append(symbol)
            n -= value
    return "".join(result)


def _draw_centered_mixed(canvas, y, segments):
    """Draw `segments` (list of (text, font, size, color)) as one centered
    line, each segment in its own font - used for the two-tone header strap."""
    # Unlike a Paragraph, drawing directly on the canvas (as this and
    # on_page() below do) means we're fully responsible for positioning:
    # reportlab won't wrap or center anything for us. To center a line
    # made of several differently-styled runs, we first have to measure
    # the total width of all of them combined, then start drawing from
    # (page_width - total_width) / 2 so the whole line is centered as one
    # unit, advancing `x` by each segment's own width as we go.
    total_width = sum(canvas.stringWidth(text, font, size) for text, font, size, _ in segments)
    x = (canvas._pagesize[0] - total_width) / 2.0
    for text, font, size, color in segments:
        canvas.setFont(font, size)
        canvas.setFillColor(color)
        canvas.drawString(x, y, text)
        x += canvas.stringWidth(text, font, size)


class _CollapsingSpacer(Spacer):
    """A vertical gap that shrinks to nothing when it would land at the very
    top of a page, and behaves exactly like Spacer(width, height) anywhere
    else.

    reportlab suppresses a Paragraph's own spaceBefore at the top of a
    frame, but a standalone Spacer is always honoured - so a plain
    Spacer that gets pushed past a page boundary (because the flowable
    before it ended within `height` points of the bottom margin) prints
    as a blank strip above the first line of text on the next page. Used
    for the blank-line marker inside a preliminary section; the gap
    between speeches is handled differently (as the speech's spaceAfter -
    see flush_char_block).
    """

    def wrap(self, availWidth, availHeight):
        frame = getattr(self, "_frame", None)
        if frame is not None and getattr(frame, "_atTop", False):
            return availWidth, 0
        return Spacer.wrap(self, availWidth, availHeight)


def _build_story(style, styles, title_page, elements):
    """Build the flowable list. Called twice by build_pdf (once for a
    throwaway metadata-collection pass, once for the real build), since
    flowables get consumed/positioned during doc.build() and can't be
    reused across two builds."""
    story = []
    at_fresh_page = False  # True right after a PageBreak, before any content has landed on it

    if title_page:
        story.extend(_title_page_flowables(title_page, styles))
        story.append(PageBreak())
        at_fresh_page = True

    for page_flow in _preliminary_flowables(title_page, styles, style):
        story.extend(page_flow)
        story.append(PageBreak())
        at_fresh_page = True

    pending_character = None   # name of the speech currently being built, or None
    pending_lines = []         # [(kind, text), ...] for that speech
    scene_marked = False       # has the first Act/Scene heading been tagged yet?

    # mark_scene_start and flush_char_block below are *nested functions*
    # (functions defined inside another function). Because they're defined
    # inside _build_story, they can see and use _build_story's local
    # variables directly - `story`, `style`, `styles`, and so on - without
    # those being passed in as arguments. This is called a "closure": each
    # nested function "closes over" the variables from the function it was
    # defined in. It's a common Python pattern for helpers that are only
    # ever used in one place and need access to a handful of the enclosing
    # function's local state.
    #
    # There's one wrinkle: by default, a nested function can *read* an
    # enclosing variable but assigning to it (`scene_marked = True`) would
    # instead create a brand new *local* variable inside the nested
    # function, shadowing the outer one rather than changing it. The
    # `nonlocal` keyword below tells Python "no, when I assign to this
    # name, modify the enclosing function's variable" - without it,
    # scene_marked would never actually update.

    def mark_scene_start(flowable):
        """Tag the first Act/Scene structural heading (a `section` - "#"/"##" -
        or a `scene_heading` - INT./EXT./forced ".") so pagination and the
        header strap both start there, leaving any title/preliminary/preface
        pages before it out of the Arabic page count."""
        nonlocal scene_marked
        if not scene_marked:
            # Setting an attribute directly on a flowable instance like
            # this works because reportlab flowables are ordinary Python
            # objects - you can attach arbitrary extra attributes to them
            # just like any other object, and _ScribeDocTemplate.afterFlowable
            # above later reads this one back with getattr().
            flowable.apt_body_start = True
            scene_marked = True
        return flowable

    def flush_char_block():
        nonlocal at_fresh_page, pending_character
        if pending_character is not None:
            if style.character_on_own_line:
                parts = _character_own_line_parts(pending_character, pending_lines, style, styles)
                # The name is its own paragraph, separate from the first
                # line of dialogue/parenthetical that follows it - keep
                # the two together as one unsplittable unit (see
                # _SpeechFlowable.split) so a page break can't strand the
                # bare name with nothing else. The table layout doesn't
                # need this: its first part already *is* the name and
                # first line combined into one row.
                min_lead = 2
            else:
                parts = _character_block_parts(pending_character, pending_lines, style, styles)
                min_lead = 1
            # The gap to the next element travels as the speech's own
            # spaceAfter rather than a trailing Spacer flowable: reportlab
            # then collapses it against the next element's spaceBefore
            # (taking the larger of the two, so a following stage
            # direction no longer gets speech_gap *plus* its own
            # spaceBefore) and drops it entirely at a page break (so it
            # can't surface as blank space at the top of the next page).
            if style.more_continued:
                # Wrapped in the one custom flowable, so a page break
                # partway through gets a "(MORE)"/"(CONT'D)" cue - see
                # _SpeechFlowable.
                story.append(
                    _SpeechFlowable(
                        pending_character, parts, style, styles, min_lead,
                        space_after=style.speech_gap,
                    )
                )
            else:
                # No wrapper at all: `parts` are already independent
                # flowables (a table, then a Paragraph per further line),
                # so reportlab's normal story-flowing logic already breaks
                # between them - and even mid-paragraph within one of
                # them, via each Paragraph's own built-in split() - without
                # any help from us. The gap rides on the last part.
                parts[-1].spaceAfter = getattr(parts[-1], "spaceAfter", 0) + style.speech_gap
                story.extend(parts)
            pending_character = None
            # list.clear() empties the list in place; pending_lines still
            # refers to the *same* list object afterwards (as opposed to
            # `pending_lines = []`, which would point the name at a new,
            # separate list - fine here too, but .clear() is the more
            # direct way to say "empty this list" when you don't need a
            # fresh object).
            pending_lines.clear()
            at_fresh_page = False

    # The main pass over the parsed elements: for each one, either start
    # accumulating a character's speech (character/parenthetical/dialogue
    # types don't immediately produce a flowable - they get buffered in
    # pending_character/pending_lines until flush_char_block() is called),
    # or - for every other type - flush whatever speech was pending, then
    # build and append that element's own flowable(s).
    for el in elements:
        if el.type == "character":
            flush_char_block()
            pending_character = el.text.upper()
            continue

        if el.type == "parenthetical":
            pending_lines.append(("parenthetical", el.text))
            continue

        if el.type == "dialogue":
            pending_lines.append(("dialogue", el.text))
            continue

        # any non character/parenthetical/dialogue element closes the block
        flush_char_block()

        if el.type == "section":
            depth = el.meta.get("depth", 1)
            heading_style = styles["act"] if depth == 1 else styles["scene_heading"]
            if depth == 1:
                text = el.text.upper()
            else:
                text = el.text.upper() if style.scene_section_uppercase else el.text
            if (style.act_underline if depth == 1 else style.scene_underline):
                text = f"<u>{text}</u>"
            para = Paragraph(text, heading_style)
            # apt_scene isn't a reportlab attribute - it's our own marker,
            # read back later by _ScribeDocTemplate.afterFlowable (during
            # the probe pass) to build the header strap's "which scene is
            # current on this page" lookup.
            para.apt_scene = el.text.upper()
            if depth == 1 and story and not at_fresh_page:
                story.append(PageBreak())
            story.append(mark_scene_start(para))
            at_fresh_page = False
        elif el.type == "scene_heading":
            heading_text = el.text.upper()
            number = el.meta.get("scene_number")
            display_text = heading_text
            if number and style.scene_number_position != "hide":
                formatted = style.scene_number_format.format(n=number)
                if style.scene_number_position == "before":
                    display_text = f"{formatted} {heading_text}"
                else:  # "after"
                    display_text = f"{heading_text} {formatted}"
            rendered = render_inline(display_text)
            if style.scene_underline:
                rendered = f"<u>{rendered}</u>"
            para = Paragraph(rendered, styles["scene_heading"])
            para.apt_scene = display_text if style.scene_number_in_header_strap else heading_text
            story.append(mark_scene_start(para))
            at_fresh_page = False
        elif el.type == "action":
            story.append(Paragraph(render_inline(el.text), styles["action"]))
            at_fresh_page = False
        elif el.type == "preface":
            story.append(Paragraph(render_inline(el.text), styles["preface"]))
            at_fresh_page = False
        elif el.type == "preface_list_item":
            marker = el.meta.get("marker", "•")
            # bulletText draws a hanging bullet/number to the left of the
            # paragraph's own left margin, using the style's bulletIndent -
            # this is reportlab's built-in support for exactly this kind of
            # list-item layout, so we don't have to fake it with manual
            # indentation and a literal "•" character in the text.
            para = Paragraph(render_inline(el.text), styles["preface_list"], bulletText=marker)
            story.append(para)
            at_fresh_page = False
        elif el.type == "transition":
            story.append(Paragraph(render_inline(el.text.upper()), styles["transition"]))
            at_fresh_page = False
        elif el.type == "centered":
            story.append(Paragraph(render_inline(el.text), styles["centered"]))
            at_fresh_page = False
        elif el.type == "page_break":
            if not at_fresh_page:
                story.append(PageBreak())
                at_fresh_page = True
        # unknown types are silently skipped

    flush_char_block()  # don't lose a speech that was still pending at the very end
    return story


def build_pdf(style, title_page, elements, output_path):
    """Top-level entry point: turn parsed Fountain (title_page + elements)
    into a PDF at output_path, using the given Style. Called once per run
    from cli.py."""
    styles = _styles(style)
    doc_kwargs = dict(
        pagesize=style.page_size,
        leftMargin=style.left_margin,
        rightMargin=style.right_margin,
        topMargin=style.top_margin,
        bottomMargin=style.bottom_margin,
        title=" ".join(title_page.get("title", [])) or "Untitled",
        author=" ".join(title_page.get("author", [])) or "",
    )

    # Pass 1: throwaway build purely to discover, per page, which page
    # dialogue starts on and which scene is "current" - see
    # _ScribeDocTemplate for why this can't be determined during the real
    # build's onPage callback. io.BytesIO() gives reportlab an in-memory
    # buffer to write this disposable PDF into instead of a real file on
    # disk, since we only care about the page/scene bookkeeping this pass
    # produces as a side effect, not the PDF bytes themselves.
    probe_doc = _ScribeDocTemplate(io.BytesIO(), **doc_kwargs)
    probe_doc.build(_build_story(style, styles, title_page, elements))

    dialogue_start_page = probe_doc.dialogue_start_page
    # Build a page -> "current scene" lookup, so on_page() below can just
    # do a dict lookup instead of re-deriving this every time it draws a
    # page. `events` is the list of (page_number, scene_text) pairs
    # collected during the probe pass, in the order those scenes were
    # encountered; `ei` walks through it once, left to right, carrying
    # `last_scene` forward onto every page number in between two events.
    scene_by_page = {}
    last_scene = ""
    events = probe_doc.scene_events
    ei = 0
    for p in range(1, probe_doc.page + 1):
        while ei < len(events) and events[ei][0] <= p:
            last_scene = events[ei][1]
            ei += 1
        scene_by_page[p] = last_scene

    play_title = (" ".join(title_page.get("title", [])) or "").upper()

    def on_page(canvas, doc_):
        # reportlab calls this once per page during the *real* build
        # (passed in as onFirstPage/onLaterPages below), after that page's
        # content has been drawn, giving us a chance to add page furniture
        # like page numbers and the header strap directly onto the canvas.
        # canvas.saveState()/.restoreState() bracket our drawing so any
        # font/color changes we make don't leak into reportlab's own
        # subsequent drawing for the page content.
        canvas.saveState()

        page_num_text = None
        if style.paginate_from_body:
            if dialogue_start_page is not None and doc_.page >= dialogue_start_page:
                page_num_text = style.pagination_format.format(
                    n=doc_.page - dialogue_start_page + 1
                )
            elif style.preface_roman_numerals and (doc_.page > 1 or not title_page):
                preface_start_page = 2 if title_page else 1
                page_num_text = style.pagination_format.format(
                    n=_to_roman(doc_.page - preface_start_page + 1)
                )
        else:
            if doc_.page > 1 or not title_page:
                page_num_text = style.pagination_format.format(n=doc_.page)

        if page_num_text is not None:
            canvas.setFont(style.pagination_font, style.pagination_size)
            canvas.setFillColor(Color(0, 0, 0))
            y = (
                style.page_size[1] - (style.top_margin / 2.0)
                if style.pagination_position == "top"
                else style.bottom_margin / 2.0
            )
            # drawString/drawRightString/drawCentredString all take an (x,
            # y) *baseline* position, not a bounding box - reportlab's
            # coordinate system has y=0 at the *bottom* of the page (the
            # opposite of most screen/GUI coordinate systems), which is why
            # "near the top" means a *large* y value here.
            if style.pagination_alignment == "left":
                canvas.drawString(style.left_margin, y, page_num_text)
            elif style.pagination_alignment == "right":
                canvas.drawRightString(style.page_size[0] - style.right_margin, y, page_num_text)
            else:
                canvas.drawCentredString(style.page_size[0] / 2.0, y, page_num_text)

        if style.header_strap and play_title and dialogue_start_page is not None \
                and doc_.page >= dialogue_start_page:
            scene = scene_by_page.get(doc_.page, "")
            y = style.page_size[1] - style.top_margin + (style.top_margin / 3.0)
            segments = [(play_title, style.font_bold, style.body_size, Color(0, 0, 0))]
            if scene:
                segments.append((" | ", style.font_regular, style.body_size, Color(0, 0, 0)))
                segments.append((scene, style.font_regular, style.body_size, Color(0, 0, 0)))
            _draw_centered_mixed(canvas, y, segments)

        canvas.restoreState()

    # Pass 2: the real build, now with header/pagination fully known
    # upfront. A plain SimpleDocTemplate is used this time (not our
    # _ScribeDocTemplate subclass) since we no longer need to collect
    # anything during this pass - on_page is registered for both the first
    # page and every later page, so it runs once per page as the PDF is
    # produced.
    doc = SimpleDocTemplate(output_path, **doc_kwargs)
    doc.build(_build_story(style, styles, title_page, elements), onFirstPage=on_page, onLaterPages=on_page)
