"""
fountain2pdf.styles.base
-------------------------
The Style dataclass is the contract between a style module (e.g. styles/apt.py)
and the rendering engine (engine.py). A style module's job is to build and
return one of these from a `get_style()` function - it owns all decisions
about margins, fonts, sizes and layout flags; the engine just reads them.

To add a new style:
  1. Create styles/yourstyle.py with a get_style() -> Style function.
  2. Register it in styles/__init__.py's STYLES dict.
  3. Run with --style yourstyle.
"""

from dataclasses import dataclass


@dataclass
class Style:
    key: str                # CLI --style value, e.g. "apt"
    display_name: str       # human-readable name, shown in --help / errors

    # Page geometry (reportlab points)
    page_size: tuple
    left_margin: float
    right_margin: float
    top_margin: float
    bottom_margin: float

    # Resolved font names, already registered with reportlab by the style
    # module (via fonts.register_family or similar) before this is built.
    font_regular: str
    font_bold: str
    font_italic: str
    font_bold_italic: str
    using_real_font: bool          # False if a base-14 fallback had to be used
    font_fallback_message: str     # printed to stderr when using_real_font is False

    # Type sizes (points)
    body_size: float
    leading: float
    title_size: float
    byline_size: float

    # Character-cue / dialogue table layout
    name_col_width: float
    dialogue_gutter: float
    speech_gap: float              # extra space between two different speeches

    # Character cues
    character_size: float
    character_bold: bool

    # Action / stage-direction paragraph
    action_left_indent: float
    action_right_indent: float
    action_size: float
    action_color: tuple            # (r, g, b), each 0..1

    # Act headings
    act_bold: bool
    act_underline: bool
    act_italic: bool
    act_size: float
    act_alignment: str  # "left" | "center" | "right"

    # Act/scene headings
    scene_bold: bool
    scene_underline: bool
    scene_italic: bool
    scene_size: float
    scene_alignment: str  # "left" | "center" | "right"

    # Running page header ("PLAY TITLE | SCENE"), centered at top of page
    header_strap: bool

    # Pagination
    paginate_from_body: bool       # number pages 1.. from the first scene heading,
                                    # leaving title/preliminary/preface pages unnumbered
    pagination_font: str
    pagination_size: float
    pagination_format: str = "{n}"  # e.g. "{n}." for a trailing period
    preface_roman_numerals: bool = False  # number pages before the first scene
                                    # heading with lowercase roman numerals
                                    # (only meaningful when paginate_from_body
                                    # is True; the title page itself stays
                                    # unnumbered, matching Arabic pagination)

    # Forced scene numbers ("INT. HOUSE - DAY #2A#") - where, if anywhere,
    # to display the number attached to a scene heading.
    scene_number_position: str = "hide"    # "hide" | "before" | "after"
    scene_number_format: str = "{n}."      # template applied to the number
    scene_number_in_header_strap: bool = False  # include it in the running header?

    # Character-cue layout. APT-style formats share the name and dialogue on
    # one line (a hanging-indent table); "Modern Play Format" styles put the
    # name on its own centered line, with dialogue as separate paragraphs
    # below it. character_alignment only matters when character_on_own_line
    # is True - in the shared-line table layout the name always sits flush
    # left in its own column, regardless of this setting.
    character_on_own_line: bool = False
    character_alignment: str = "left"      # "left" | "center" | "right"

    # Action / stage-direction paragraph
    action_italic: bool = True             # False for styles that set stage
                                            # direction in the regular face

    # Parentheticals within a speech ("(beat)"). Only parenthetical_italic
    # applies to both layouts; parenthetical_left_indent (extra indent past
    # the dialogue's own margin) only applies when character_on_own_line is
    # True - the shared-line table layout has no separate indent for these.
    parenthetical_italic: bool = True
    parenthetical_left_indent: float = 0

    # Where page numbers are drawn.
    pagination_position: str = "bottom"    # "top" | "bottom"
    pagination_alignment: str = "center"   # "left" | "center" | "right"

    scene_section_uppercase: bool = True   # uppercase depth>1 sections ("## Scene
                                            # One"); Act sections (depth 1) and true
                                            # scene_heading elements (INT./EXT./forced
                                            # ".") are always uppercased regardless
