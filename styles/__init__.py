"""
Style registry for fountain2pdf.

To add a new style:
  1. Create styles/yourstyle.py with a get_style() -> styles.base.Style function.
  2. Add it to STYLES below.
  3. Run: python cli.py script.fountain --style yourstyle
"""

from . import apt

STYLES = {
    "apt": apt,
}


def load_style(key):
    if key not in STYLES:
        available = ", ".join(sorted(STYLES))
        raise ValueError(f"Unknown style '{key}'. Available styles: {available}")
    return STYLES[key].get_style()
