"""
fountain2pdf.styles.modern
----------------------------
Dramatists Guild "Modern Play Format", per the annotated example page at
https://www.dramatistsguild.com/sites/default/files/2019-12/modernformat-New.pdf
(a page from Tennessee Williams' "Not About Nightingales"), cross-checked
against the Guild's general submission formatting guide at
https://www.dramatistsguild.com/sites/default/files/2020-01/General-SFI-Formatting-Guidelines-Complete.pdf:

  - US Letter, 1" top/right/bottom margins, 1.5" left margin (the extra
    0.5" accounts for binding)
  - 12pt Times New Roman throughout (reportlab's built-in Times-Roman
    family, so no font file needs to be located on the machine)
  - Character names: centered, all caps, plain (not bold), on their own
    line - dialogue follows as separate single-spaced paragraphs below,
    flush with the page margins (no extra indent)
  - Stage action: plain (not italic), starting roughly at the horizontal
    center of the page and running to the right margin, with a blank line
    before and after
  - Parentheticals within a speech: plain, indented slightly past the
    dialogue's own margin
  - Act headings: caps, centered, not underlined ("ACT II")
  - Scene headings: title case, centered, underlined ("Scene 6")
  - No running header strap - the Guild format doesn't use one
  - Pagination: page number only (e.g. "16."), top right of the page,
    starting at the first page of the play; the title page and any
    preliminary pages (cast list, setting/time, etc.) are left unnumbered
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

from styles.base import Style


def get_style():
    return Style(
        key="modern",
        display_name="Dramatists Guild Modern Play Format",
        page_size=letter,
        left_margin=1.5 * inch,
        right_margin=1 * inch,
        top_margin=1 * inch,
        bottom_margin=1 * inch,
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
        action_left_indent=(letter[0] / 2.0) - (1.5 * inch),  # dialogue's left margin is 1.5in;
                                                                # action starts at the page's
                                                                # horizontal center instead
        action_right_indent=0,
        action_color=(0, 0, 0),
        action_size=12,
        action_italic=False,
        parenthetical_italic=False,
        parenthetical_left_indent=0.5 * inch,
        act_bold=False,
        act_underline=False,
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
        scene_number_format="Scene {n}.",
        scene_number_in_header_strap=False,
    )
