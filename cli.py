#!/usr/bin/env python3
"""
fountain2pdf - convert a Fountain (.fountain) file into a formatted PDF.

Usage:
    python cli.py input.fountain
    python cli.py input.fountain -o output.pdf
    python cli.py input.fountain --style apt
    python cli.py input.fountain --anonymise
"""

import argparse
import os
import sys

from parser import parse_fountain
from anonymize import anonymize_title_page
from styles import STYLES, load_style
from engine import build_pdf


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="fountain2pdf",
        description="Convert a Fountain-formatted script into a formatted PDF.",
    )
    ap.add_argument("input", help="Path to the .fountain source file")
    ap.add_argument(
        "-o", "--output", help="Output PDF path (default: same name as input, .pdf)"
    )
    ap.add_argument(
        "--style", default="apt", choices=sorted(STYLES),
        help="Output format style (default: apt)",
    )
    ap.add_argument(
        "--anonymise", "--anonymize", dest="anonymise", action="store_true",
        help=(
            "Produce a blind-submission copy: strips contact-related fields "
            "(contact, email, phone, address, ...) from the title page. "
            "Does not scan the body text for contact details typed inline."
        ),
    )
    args = ap.parse_args(argv)

    if not os.path.isfile(args.input):
        ap.error(f"input file not found: {args.input}")

    output_path = args.output or os.path.splitext(args.input)[0] + ".pdf"

    with open(args.input, "r", encoding="utf-8") as f:
        text = f.read()

    title_page, elements = parse_fountain(text)

    if args.anonymise:
        title_page, removed = anonymize_title_page(title_page)
        if removed:
            print(f"Anonymising: removed title-page fields: {', '.join(removed)}")
        else:
            print("Anonymising: no contact-related title-page fields found to remove.")

    style = load_style(args.style)
    if not style.using_real_font:
        print(style.font_fallback_message, file=sys.stderr)

    build_pdf(style, title_page, elements, output_path)

    print(f"Wrote {output_path}  ({len(elements)} elements parsed, style: {style.key})")


if __name__ == "__main__":
    sys.exit(main())
