"""
fountain2pdf.styles.samuel_french
------------------------------------
Samuel French / SFI submission format, per the Dramatists Guild's "General
SFI Formatting Guidelines" at
https://www.dramatistsguild.com/sites/default/files/2020-01/General-SFI-Formatting-Guidelines-Complete.pdf
("SFI" is Samuel French, Inc., the play publisher and licensor now part of
Concord Theatricals) - the same document already used as a cross-check
source for styles/modern.py, but this style follows its own worked example
(pages 6-7 of the PDF) directly rather than the shorter annotated page
modern.py is based on:

  - US Letter, 1" top/right/bottom margins, 1.5" left margin if bound
  - 12pt Times New Roman throughout
  - Character names: centered, all caps, plain (not bold) - and, unlike
    modern.py, a *one-word* parenthetical direction right after the cue
    shares its line ("JOHN (patiently.)") rather than getting a line of
    its own; a longer one still goes on its own line, three indents in
    from the dialogue's own margin
  - Dialogue: flush with the page margins, single-spaced, starting on the
    line below the name (not sharing the name's line, unlike apt.py)
  - Stage action: plain (not italic), centered, per the worked example's
    "(Enter JENNIFER, left.)"
  - Act headings: caps, centered, underlined ("ACT I")
  - Scene headings: title case, centered, underlined, no trailing period
    ("Scene 1")
  - No running header strap
  - Pagination: top right, starting at the first page of the play; the
    title page and preliminary pages (cast list, place/time) are left
    unnumbered
  - A speech that breaks across a page gets a "(MORE)" cue and resumes
    with the character's name plus "(Cont.)"

Two things this style deliberately simplifies relative to the source
document, rather than adding more one-off engine machinery for a single
style to use:

  - The guide's ideal is composite Act-Scene-Page numbers ("II - 1 - 51"),
    with the note that continuous numbering (not resetting page count at
    each act/scene) is what's actually preferred; this style implements
    that preference with plain sequential numbers rather than the full
    composite format.
  - The guide's cast/place/time preliminary pages are headed "Cast of
    Characters" / "Place" / "Time" (Place and Time as two separate pages);
    this style reuses the same combined "CHARACTERS" / "SETTING & TIME"
    preliminary pages every other style uses (see engine.PRELIMINARY_SECTIONS),
    just restyled to this format's underlined, non-bold heading treatment.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

from styles.base import Style


def get_style():
    """Build and return this style's Style object. Called once per run by
    styles.load_style("samuel_french")."""
    return Style(
        key="samuel_french",
        display_name="Samuel French / SFI Submission Format",
        page_size=letter,
        left_margin=1.5 * inch,
        right_margin=1 * inch,
        top_margin=1 * inch,
        bottom_margin=1 * inch,
        # Reportlab's built-in Times-Roman family, same as modern.py - no
        # font file needs to be located on the machine.
        font_regular="Times-Roman",
        font_bold="Times-Bold",
        font_italic="Times-Italic",
        font_bold_italic="Times-BoldItalic",
        using_real_font=True,
        font_fallback_message="",
        body_size=12,
        leading=14,
        title_size=24,
        byline_size=14,
        name_col_width=0,       # unused - character_on_own_line layout doesn't use the table
        dialogue_gutter=0,      # unused - character_on_own_line layout doesn't use the table
        speech_gap=14,
        character_size=12,
        character_bold=False,
        character_on_own_line=True,
        character_alignment="center",
        character_short_parenthetical_inline=True,
        action_left_indent=0,
        action_right_indent=0,
        action_color=(0, 0, 0),
        action_size=12,
        action_italic=False,
        action_alignment="center",
        parenthetical_italic=False,
        # "Three indents in" for a longer parenthetical that interrupts a
        # speech - one indent is defined by the guide as 12 spaces in
        # Times New Roman (calibrated against 5 monospace characters in
        # Courier New, i.e. about 0.5"), so three is roughly 1.5".
        parenthetical_left_indent=3 * 0.5 * inch,
        act_bold=False,
        act_underline=True,
        act_italic=False,
        act_alignment="center",
        act_size=12,
        scene_bold=False,
        scene_underline=True,
        scene_italic=False,
        scene_alignment="center",
        scene_size=12,
        scene_section_uppercase=False,
        header_strap=False,
        paginate_from_body=True,
        preface_roman_numerals=False,
        pagination_font="Times-Roman",
        pagination_size=12,
        pagination_format="{n}.",
        pagination_position="top",
        pagination_alignment="right",
        scene_number_position="before",
        # A trailing period only matters here for a *forced* scene heading
        # that names a location too (e.g. Fountain's ".Alex's Apartment
        # #1#") - it's what separates "Scene 1" from the location name
        # that follows it ("Scene 1. ALEX'S APARTMENT"). A bare "## Scene
        # One" markdown section, which is what the worked example in the
        # source PDF actually shows, doesn't go through this field at all
        # (see engine._build_story's "section" branch) so it's unaffected
        # either way.
        scene_number_format="Scene {n}.",
        scene_number_in_header_strap=False,
        # The guide only actually describes the continuation cue on the
        # far side of a page break ("insert (Cont.) after the name"), not
        # a matching cue at the point of the break itself - but pairing it
        # with a "(MORE)" is universal professional practice and the
        # engine only supports the two as a pair, so both are turned on.
        more_continued=True,
        more_text="(MORE)",
        continued_text="(Cont.)",
        prelim_heading_bold=False,
        prelim_heading_underline=True,
        name_description_name_underline=True,
    )
