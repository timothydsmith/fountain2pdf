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
    # If the caller pointed us at a specific directory, check it first -
    # `list(candidates)` makes a shallow copy so this function doesn't
    # mutate the list the caller passed in, then we prepend our extra
    # candidate to that copy.
    search_list = list(candidates)
    if extra_dir:
        search_list = [_dir_candidate(extra_dir, display_name)] + search_list

    # The four PDF font names we'll register each face under, if we find
    # one. reportlab identifies fonts purely by these string names later
    # (e.g. a Style's font_bold field is just "Palatino-Bold"), so this
    # dict's values are what get handed back to the caller as the return
    # value below.
    names = {
        "regular": display_name,
        "bold": f"{display_name}-Bold",
        "italic": f"{display_name}-Italic",
        "bold_italic": f"{display_name}-BoldItalic",
    }

    # Try each candidate location in order, stopping at (and returning
    # from) the first one that actually works.
    for cand in search_list:
        try:
            # A dict comprehension: build a new dict {"regular": path,
            # "bold": path, ...} by pulling just those four keys out of
            # `cand` - equivalent to a for loop that does
            # `paths[k] = cand[k]` for each k, but as one expression.
            paths = {k: cand[k] for k in ("regular", "bold", "italic", "bold_italic")}
            # set(paths.values()) de-duplicates the paths first - a
            # TrueType Collection candidate has all four faces pointing at
            # the *same* .ttc file, so without this we'd needlessly check
            # os.path.isfile on the same path four times.
            if not all(os.path.isfile(p) for p in set(paths.values())):
                # This candidate is missing at least one required file -
                # skip it and try the next one.
                continue
            subfonts = cand.get("subfont")
            for key, font_name in names.items():
                # A TrueType Collection (.ttc) bundles several font faces
                # into one file; subfontIndex picks which one. For a plain
                # .ttf/.otf file there's only ever one face, at index 0, so
                # `subfonts[key] if subfonts else 0` falls back to that
                # when this candidate has no "subfont" entry at all.
                idx = subfonts[key] if subfonts else 0
                pdfmetrics.registerFont(TTFont(font_name, paths[key], subfontIndex=idx))
            # Beyond registering each face individually, reportlab also
            # needs to be told which four names belong together as one
            # "family" - this is what lets a Paragraph's <b>/<i> markup
            # (see parser.render_inline) automatically pick the right face
            # for the base font.
            pdfmetrics.registerFontFamily(
                display_name,
                normal=names["regular"],
                bold=names["bold"],
                italic=names["italic"],
                boldItalic=names["bold_italic"],
            )
            return names["regular"], names["bold"], names["italic"], names["bold_italic"], True
        except Exception:
            # Anything going wrong while trying this candidate (a
            # corrupted font file, an unreadable path, etc.) just means
            # "this one didn't work" - move on and try the next candidate
            # rather than letting the whole program crash over one bad
            # font file.
            continue

    # None of the candidates worked - hand back the caller's fallback font
    # names instead. `(*fallback, False)` unpacks the 4-item fallback tuple
    # back out into individual values and adds `False` after them, so the
    # return shape here (5 individual values) always matches the "found a
    # real font" branch above, just with found=False.
    return (*fallback, False)


def _dir_candidate(dir_path, display_name):
    """Build a single "candidate" dict (in the same shape register_family
    expects) that looks for "<display_name>-Regular.ttf" and friends
    inside `dir_path`."""

    def find(*stems):
        # `*stems` collects however many arguments are passed into a
        # tuple, so `find("A", "B")` tries filename stem "A" first, then
        # "B" - used below for the bold-italic face, which different
        # foundries name "-BoldItalic" or "-BoldOblique".
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
