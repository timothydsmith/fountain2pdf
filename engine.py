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

Known simplification: a character cue and its full speech are kept
together as one flowable (no MORE/CONT'D continuation markers), so a very
long uninterrupted speech that doesn't fit the remainder of a page is
pushed to the next page as a whole rather than split mid-speech.
"""

import io

from reportlab.lib.colors import Color
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    KeepTogether,
    Table,
    TableStyle,
)

from parser import render_inline

PRELIMINARY_SECTIONS = [
    # (heading text, title-page keys to look for, in priority order)
    ("CHARACTERS", ["characters", "character"]),
    ("SETTING & TIME", ["setting", "time"]),
    ("SCENE BREAKDOWN", ["scene breakdown", "scenes", "scene_breakdown"]),
]

_ALIGN_MAP = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}


def _styles(style):
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
            "prelim_heading", fontName=style.font_bold, fontSize=style.body_size,
            leading=style.leading, alignment=TA_CENTER, spaceBefore=0, spaceAfter=14,
        ),
        "prelim_body": ParagraphStyle(
            "prelim_body", fontName=style.font_regular, fontSize=style.body_size,
            leading=style.leading, alignment=TA_LEFT, spaceAfter=4,
        ),
        "act": ParagraphStyle(
            "act",
            fontName=(
                style.font_bold_italic if (style.act_bold and style.act_italic) else
                style.font_bold if style.act_bold else
                style.font_italic if style.act_italic else
                style.font_regular
            ),
            fontSize=style.act_size, leading=style.leading, alignment=_ALIGN_MAP[style.act_alignment],
            spaceBefore=6, spaceAfter=18,
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
            leading=style.leading, alignment=_ALIGN_MAP[style.scene_alignment], spaceBefore=6, spaceAfter=18,
        ),
        "character": ParagraphStyle(
            "character",
            fontName=style.font_bold if style.character_bold else style.font_regular,
            fontSize=style.character_size,
            leading=style.leading, alignment=TA_LEFT, spaceBefore=0, spaceAfter=0,
        ),
        "dialogue": ParagraphStyle(
            "dialogue", fontName=style.font_regular, fontSize=style.body_size,
            leading=style.leading, alignment=TA_LEFT, leftIndent=0, rightIndent=0,
            spaceBefore=0, spaceAfter=0,
        ),
        "action": ParagraphStyle(
            "action", fontName=style.font_italic, fontSize=style.action_size,
            leading=style.leading, alignment=TA_LEFT,
            leftIndent=style.action_left_indent, rightIndent=style.action_right_indent,
            textColor=Color(*style.action_color),
            spaceBefore=10, spaceAfter=10,
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
    flow = [Spacer(1, 6.5 * 28.35)]  # ~6.5cm, matches the old title-page layout

    title = " ".join(title_page.get("title", [])) or "Untitled"
    flow.append(Paragraph(render_inline(title), styles["title"]))

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
        if any(key == k for _, keys in PRELIMINARY_SECTIONS for k in keys):
            continue
        contact_lines.extend(value)
    if contact_lines:
        flow.append(Spacer(1, 6.5 * 28.35))
        for line in contact_lines:
            flow.append(Paragraph(render_inline(line), styles["contact"]))

    return flow


def _get_first(title_page, keys):
    for k in keys:
        if k in title_page and title_page[k]:
            return title_page[k]
    return None


def _preliminary_flowables(title_page, styles):
    """Characters / Setting & Time / Scene Breakdown pages, built from
    whatever matching title-page keys the writer supplied. Any section with
    no matching key is simply skipped."""
    pages = []
    for heading, keys in PRELIMINARY_SECTIONS:
        if heading == "SETTING & TIME":
            setting = _get_first(title_page, ["setting"])
            time_ = _get_first(title_page, ["time"])
            lines = (setting or []) + (time_ or [])
        else:
            lines = _get_first(title_page, keys)
        if not lines:
            continue
        flow = [Paragraph(heading, styles["prelim_heading"])]
        for line in lines:
            flow.append(Paragraph(render_inline(line), styles["prelim_body"]))
        pages.append(flow)
    return pages


def _character_block_flowable(name, lines, style, styles):
    """Two-column, borderless table: character name in a fixed-width left
    column (the 'tab stop'), parenthetical + dialogue in the right column.
    Table columns give wrapped lines a free, exact hanging indent - every
    continuation line lines up under the first."""
    name_para = Paragraph(render_inline(name), styles["character"])

    tint_hex = "#%02x%02x%02x" % tuple(round(c * 255) for c in style.action_color)
    parts = []
    for kind, text in lines:
        rendered = render_inline(text)
        if kind == "parenthetical":
            parts.append(f'<font color="{tint_hex}"><i>{rendered}</i></font>')
        else:
            parts.append(rendered)
    content_para = Paragraph("<br/>".join(parts) if parts else "", styles["dialogue"])

    available_width = style.page_size[0] - style.left_margin - style.right_margin
    dialogue_col_width = available_width - style.name_col_width

    table = Table(
        [[name_para, content_para]],
        colWidths=[style.name_col_width, dialogue_col_width],
        hAlign="LEFT",
    )
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
    return KeepTogether([table])


class _ScribeDocTemplate(SimpleDocTemplate):
    """SimpleDocTemplate subclass used for a first, throwaway build pass
    that discovers, for each page:
      - the most recent Act/Scene heading text (for the header strap)
      - the page on which the first body flowable landed (for pagination
        that starts counting at the first page of dialogue)

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
        SimpleDocTemplate.__init__(self, *args, **kwargs)
        self.dialogue_start_page = None
        self.scene_events = []  # [(page_number, scene_text), ...] in order

    def afterFlowable(self, flowable):
        scene = getattr(flowable, "apt_scene", None)
        if scene is not None:
            self.scene_events.append((self.page, scene))
        if getattr(flowable, "apt_body_start", False) and self.dialogue_start_page is None:
            self.dialogue_start_page = self.page


def _draw_centered_mixed(canvas, y, segments):
    """Draw `segments` (list of (text, font, size, color)) as one centered
    line, each segment in its own font - used for the two-tone header strap."""
    total_width = sum(canvas.stringWidth(text, font, size) for text, font, size, _ in segments)
    x = (canvas._pagesize[0] - total_width) / 2.0
    for text, font, size, color in segments:
        canvas.setFont(font, size)
        canvas.setFillColor(color)
        canvas.drawString(x, y, text)
        x += canvas.stringWidth(text, font, size)


def _build_story(style, styles, title_page, elements):
    """Build the flowable list. Called twice by build_pdf (once for a
    throwaway metadata-collection pass, once for the real build), since
    flowables get consumed/positioned during doc.build() and can't be
    reused across two builds."""
    story = []
    at_fresh_page = False

    if title_page:
        story.extend(_title_page_flowables(title_page, styles))
        story.append(PageBreak())
        at_fresh_page = True

    for page_flow in _preliminary_flowables(title_page, styles):
        story.extend(page_flow)
        story.append(PageBreak())
        at_fresh_page = True

    pending_character = None   # name of the speech currently being built, or None
    pending_lines = []         # [(kind, text), ...] for that speech
    body_marked = False        # has the first body flowable been tagged yet?

    def mark_body_start(flowable):
        nonlocal body_marked
        if not body_marked:
            flowable.apt_body_start = True
            body_marked = True
        return flowable

    def flush_char_block():
        nonlocal at_fresh_page, pending_character
        if pending_character is not None:
            block = _character_block_flowable(pending_character, pending_lines, style, styles)
            story.append(mark_body_start(block))
            story.append(Spacer(1, style.speech_gap))
            pending_character = None
            pending_lines.clear()
            at_fresh_page = False

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
            text = el.text.upper()
            if style.act_underline and depth == 1:
                text = f"<u>{text}</u>"
            para = Paragraph(text, heading_style)
            para.apt_scene = el.text.upper()
            if depth == 1 and story and not at_fresh_page:
                story.append(PageBreak())
            story.append(mark_body_start(para))
            at_fresh_page = False
        elif el.type == "scene_heading":
            para = Paragraph(render_inline(el.text.upper()), styles["scene_heading"])
            para.apt_scene = el.text.upper()
            story.append(mark_body_start(para))
            at_fresh_page = False
        elif el.type == "action":
            story.append(mark_body_start(Paragraph(render_inline(el.text), styles["action"])))
            at_fresh_page = False
        elif el.type == "transition":
            story.append(
                mark_body_start(Paragraph(render_inline(el.text.upper()), styles["transition"]))
            )
            at_fresh_page = False
        elif el.type == "centered":
            story.append(mark_body_start(Paragraph(render_inline(el.text), styles["centered"])))
            at_fresh_page = False
        elif el.type == "page_break":
            if not at_fresh_page:
                story.append(PageBreak())
                at_fresh_page = True
        # unknown types are silently skipped

    flush_char_block()
    return story


def build_pdf(style, title_page, elements, output_path):
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
    # build's onPage callback.
    probe_doc = _ScribeDocTemplate(io.BytesIO(), **doc_kwargs)
    probe_doc.build(_build_story(style, styles, title_page, elements))

    dialogue_start_page = probe_doc.dialogue_start_page
    scene_by_page = {}
    last_scene = ""
    events = probe_doc.scene_events
    ei = 0
    for p in range(1, probe_doc.page + 1):
        while ei < len(events) and events[ei][0] < p:
            last_scene = events[ei][1]
            ei += 1
        scene_by_page[p] = last_scene

    play_title = (" ".join(title_page.get("title", [])) or "").upper()

    def on_page(canvas, doc_):
        canvas.saveState()

        if style.paginate_from_body:
            show_number = dialogue_start_page is not None and doc_.page >= dialogue_start_page
            page_num = (doc_.page - dialogue_start_page + 1) if show_number else None
        else:
            show_number = doc_.page > 1 or not title_page
            page_num = doc_.page

        if show_number and page_num is not None:
            canvas.setFont(style.pagination_font, style.pagination_size)
            canvas.setFillColor(Color(0, 0, 0))
            canvas.drawCentredString(
                style.page_size[0] / 2.0,
                style.bottom_margin / 2.0,
                style.pagination_format.format(n=page_num),
            )

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

    # Pass 2: the real build, now with header/pagination fully known upfront.
    doc = SimpleDocTemplate(output_path, **doc_kwargs)
    doc.build(_build_story(style, styles, title_page, elements), onFirstPage=on_page, onLaterPages=on_page)
