"""
fountain2pdf.styles.apt
-------------------------
Australian Plays Transform (APT) play submission style, per
"APT Submissions Style Guide" (08/13/21):

  - A4, top margin 40mm, left/right/bottom margins 25mm
  - Palatino Regular/Bold/Italic, 10pt throughout the manuscript
    (title page: 35pt title, 18pt playwright name)
  - Character names: bold caps, flush LEFT (not centered)
  - After the name, a tab, then dialogue starts on the same line
  - A second-line tab so wrapped dialogue lines align under the first
  - Single-spaced within a speech, double-spaced between speeches
  - Stage directions in italic, 90% tint black, flush left (no extra indent)
  - Running header strap each page: "PLAY TITLE | SCENE", title in bold
    caps, scene in regular caps, both centered
  - Pagination: centered at the bottom. Arabic numbering starts at the
    first page of the first scene heading; pages before that (title page
    excepted, which stays unnumbered) are numbered with lowercase roman
    numerals
  - Forced scene numbers ("INT. HOUSE - DAY #2A#") are printed at the
    start of the Scene Heading as "2A." and are left out of the running
    header strap

Palatino is a commercial font, so it isn't bundled here - this module looks
for it (or a free equivalent) already installed on the machine running the
script. Set the FOUNTAIN2PDF_PALATINO_DIR environment variable to a folder
containing Palatino-Regular/-Bold/-Italic/-BoldItalic.ttf (or .otf) files to
point it somewhere specific; otherwise it checks the standard macOS/Windows
install locations, and falls back to Times-Roman with a warning.

This file is a good template to copy when adding a new style: apart from
the font-hunting section below (only needed if your style wants a
commercial/non-bundled font), the real content is the single Style(...)
call in get_style(), which is just a long list of `field=value` settings -
see styles/base.py for what each field means.
"""

import os

from reportlab.lib.pagesizes import A4
# reportlab measures everything internally in "points" (1/72 inch, the
# standard unit in print/typesetting), but that's not a natural unit to
# write margins in by hand. `mm` here is a plain number - the number of
# points in one millimetre - so writing `25 * mm` converts "25 millimetres"
# into the point value reportlab actually wants, right at the point of use.
from reportlab.lib.units import mm

import fonts
from styles.base import Style

# os.environ is a dict-like object holding the current process's
# environment variables; .get() (rather than plain indexing with []) means
# "give me this variable's value if it's set, or None if it isn't" instead
# of raising a KeyError when a user hasn't set it - this variable is
# optional, so None here just means "no directory override; fonts.py will
# fall back to the standard install-location candidates below."
PALATINO_DIR = os.environ.get("FOUNTAIN2PDF_PALATINO_DIR")

# Places to look for a real Palatino (or metric-compatible equivalent)
# font, tried in order by fonts.register_family() until one is found - see
# fonts.py for exactly how each of these dicts gets used.
PALATINO_CANDIDATES = [
    {  # macOS ships an actual Palatino as a TrueType collection
        "regular": "/System/Library/Fonts/Palatino.ttc",
        "bold": "/System/Library/Fonts/Palatino.ttc",
        "italic": "/System/Library/Fonts/Palatino.ttc",
        "bold_italic": "/System/Library/Fonts/Palatino.ttc",
        "subfont": {"regular": 0, "bold": 1, "italic": 2, "bold_italic": 3},
    },
    {  # Windows ships "Palatino Linotype" as separate TTFs
        "regular": r"C:\Windows\Fonts\pala.ttf",
        "bold": r"C:\Windows\Fonts\palab.ttf",
        "italic": r"C:\Windows\Fonts\palai.ttf",
        "bold_italic": r"C:\Windows\Fonts\palabi.ttf",
    },
    {  # Linux: TeX Gyre Pagella, a free metric-compatible clone
        # (e.g. `apt install fonts-texgyre`)
        "regular": "/usr/share/fonts/opentype/texgyre/texgyrepagella-regular.otf",
        "bold": "/usr/share/fonts/opentype/texgyre/texgyrepagella-bold.otf",
        "italic": "/usr/share/fonts/opentype/texgyre/texgyrepagella-italic.otf",
        "bold_italic": "/usr/share/fonts/opentype/texgyre/texgyrepagella-bolditalic.otf",
    },
]


def get_style():
    """Build and return this style's Style object. Called once per run by
    styles.load_style("apt") whenever `--style apt` is used."""
    # fonts.register_family returns a 5-item tuple; this line unpacks it
    # straight into five separate names in one step; rather than
    # `result = fonts.register_family(...)` followed by `reg =
    # result[0]`, etc. Python matches them up positionally, left to right.
    reg, bold, ital, bi, found = fonts.register_family(
        "Palatino",
        PALATINO_CANDIDATES,
        fallback=("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"),
        extra_dir=PALATINO_DIR,
    )
    # A conditional expression again (see engine.py's _styles() for more on
    # these): if a real Palatino was `found`, there's nothing to warn
    # about, so the message is just an empty string; otherwise it's this
    # longer explanation, which cli.py prints to stderr when
    # style.using_real_font is False.
    fallback_message = (
        ""
        if found
        else (
            "fountain2pdf [apt style]: could not find a Palatino font file on "
            "this system (checked FOUNTAIN2PDF_PALATINO_DIR, standard macOS/"
            "Windows install paths, and TeX Gyre Pagella). Falling back to "
            "Times-Roman. Set FOUNTAIN2PDF_PALATINO_DIR to a folder containing "
            "Palatino-Regular/-Bold/-Italic/-BoldItalic.ttf (or .otf) to fix this."
        )
    )

    # Every argument below is passed by keyword (`field=value`), which is
    # why the order doesn't have to match the order fields were declared
    # in styles/base.py's Style class - keyword arguments are matched up
    # by name, not by position. This is the one place all of APT's actual
    # formatting decisions live; engine.py never hardcodes anything
    # APT-specific, it only ever reads values back out of this object.
    return Style(
        key="apt",
        display_name="Australian Plays Transform (APT) submission format",
        page_size=A4,
        left_margin=25 * mm,
        right_margin=25 * mm,
        top_margin=40 * mm,
        bottom_margin=25 * mm,
        font_regular=reg,
        font_bold=bold,
        font_italic=ital,
        font_bold_italic=bi,
        using_real_font=found,
        font_fallback_message=fallback_message,
        body_size=10,
        leading=13,
        title_size=35,
        byline_size=18,
        name_col_width=32 * mm,
        dialogue_gutter=6,
        speech_gap=13,
        character_size=10,
        character_bold=False,
        action_left_indent=0,
        action_right_indent=0,
        action_color=(0.1, 0.1, 0.1),  # ~90% tint black
        action_size=10,
        act_bold=True,
        act_underline=False,
        act_italic=False,
        act_alignment="left",
        act_size=10,
        scene_bold=True,
        scene_underline=False,
        scene_italic=False,
        scene_alignment="left",
        scene_size=10,
        header_strap=True,
        paginate_from_body=True,
        preface_roman_numerals=True,
        pagination_font=bold,
        pagination_size=10,
        pagination_format="{n}",
        scene_number_position="before",
        scene_number_format="SCENE {n}:",
        scene_number_in_header_strap=False,
    )
