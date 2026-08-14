"""
fountain2pdf.fonts
--------------------
Shared helper for finding and registering a real TrueType/OpenType font
family (regular/bold/italic/bold-italic) with reportlab, for style modules
that want something other than the built-in base-14 PDF fonts (Helvetica,
Times, Courier).

Fonts like Palatino are commercial and not embeddable by us - this module
looks for font files already installed on the machine running the script
(or a folder the user points it at) and registers whichever it finds first.
If nothing is found, the caller decides on a fallback.
"""

import os

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def register_family(display_name, candidates, fallback, extra_dir=None):
    """Try to find and register a font family under `display_name`.

    Args:
        display_name: base name to register the font under, e.g. "Palatino".
            The four faces are registered as "Palatino", "Palatino-Bold",
            "Palatino-Italic", "Palatino-BoldItalic".
        candidates: list of dicts, each describing one place to look:
            {"regular": path, "bold": path, "italic": path, "bold_italic": path}
            Optionally include "subfont": {"regular": 0, "bold": 1, ...} for
            TrueType Collections (.ttc) where all four faces live in one file
            at different indices.
        fallback: (regular, bold, italic, bold_italic) built-in PDF font
            names to use if no candidate is found, e.g.
            ("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic").
        extra_dir: optional directory to check first, containing files named
            "<display_name>-Regular.ttf" / "-Bold" / "-Italic" / "-BoldItalic"
            (.ttf or .otf).

    Returns:
        (regular, bold, italic, bold_italic, found) where `found` is True if
        a real font was registered, False if the fallback was used.
    """
    search_list = list(candidates)
    if extra_dir:
        search_list = [_dir_candidate(extra_dir, display_name)] + search_list

    names = {
        "regular": display_name,
        "bold": f"{display_name}-Bold",
        "italic": f"{display_name}-Italic",
        "bold_italic": f"{display_name}-BoldItalic",
    }

    for cand in search_list:
        try:
            paths = {k: cand[k] for k in ("regular", "bold", "italic", "bold_italic")}
            if not all(os.path.isfile(p) for p in set(paths.values())):
                continue
            subfonts = cand.get("subfont")
            for key, font_name in names.items():
                idx = subfonts[key] if subfonts else 0
                pdfmetrics.registerFont(TTFont(font_name, paths[key], subfontIndex=idx))
            pdfmetrics.registerFontFamily(
                display_name,
                normal=names["regular"],
                bold=names["bold"],
                italic=names["italic"],
                boldItalic=names["bold_italic"],
            )
            return names["regular"], names["bold"], names["italic"], names["bold_italic"], True
        except Exception:
            continue

    return (*fallback, False)


def _dir_candidate(dir_path, display_name):
    def find(*stems):
        for stem in stems:
            for ext in (".ttf", ".otf"):
                p = os.path.join(dir_path, stem + ext)
                if os.path.isfile(p):
                    return p
        # no match - return a path that won't exist, so the isfile() check
        # in register_family filters this candidate out cleanly
        return os.path.join(dir_path, stems[0] + ".ttf")

    return {
        "regular": find(f"{display_name}-Regular"),
        "bold": find(f"{display_name}-Bold"),
        "italic": find(f"{display_name}-Italic"),
        "bold_italic": find(f"{display_name}-BoldItalic", f"{display_name}-BoldOblique"),
    }
