"""
Style registry for fountain2pdf.

To add a new style:
  1. Create styles/yourstyle.py with a get_style() -> styles.base.Style function.
  2. Add it to STYLES below.
  3. Run: python cli.py script.fountain --style yourstyle
"""

# `from . import apt` imports the sibling module styles/apt.py (the `.`
# means "this same package", i.e. the styles/ folder this __init__.py file
# lives in) and binds it to the name `apt` - so below we're storing a
# reference to the *module itself*, not calling anything in it yet. Each
# style module just needs to expose one function, get_style(), which
# load_style() below calls only once someone actually asks for that style.
from . import apt
from . import modern
from . import samuel_french

# The registry: maps the string a user types after --style on the command
# line to the module that knows how to build that style's config. Adding a
# new style module here is what makes `--style yourstyle` work in cli.py.
STYLES = {
    "apt": apt,
    "modern": modern,
    "samuel_french": samuel_french,
}


def load_style(key):
    """Look up a style by its CLI key and build a fresh Style object for
    it. Raises ValueError with a helpful message if the key isn't
    registered - cli.py's argparse --style choices already prevents this
    in normal use, but this is a clear error for any other caller."""
    if key not in STYLES:
        available = ", ".join(sorted(STYLES))
        raise ValueError(f"Unknown style '{key}'. Available styles: {available}")
    # STYLES[key] is the module (e.g. the `apt` module object); .get_style()
    # calls the function of that name defined in that module, which does
    # the actual work of building and returning a styles.base.Style
    # instance (see styles/apt.py or styles/modern.py for what that
    # involves - font lookup, margins, etc).
    return STYLES[key].get_style()
