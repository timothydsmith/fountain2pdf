#!/usr/bin/env python3
"""
fountain2pdf - convert a Fountain (.fountain) file into a formatted PDF.

Usage:
    python cli.py input.fountain
    python cli.py input.fountain -o output.pdf
    python cli.py input.fountain --style apt
    python cli.py input.fountain --anonymise

Styles: modern (Dramatists Guild Modern Play Format, default), apt
(Australian Plays Transform submission format), samuel_french (Samuel
French / SFI submission format).

This is the "glue" file: it doesn't know how Fountain parsing or PDF
rendering actually work, it just reads command-line arguments, calls
parser.parse_fountain() to turn the input file into structured data, then
calls engine.build_pdf() to turn that into a PDF. If you're tracing through
how the whole program fits together, main() below is the natural starting
point - read it top to bottom and follow the imported functions into their
own modules from there.
"""

import argparse
import os
import sys

from parser import parse_fountain
from anonymize import anonymize_title_page
from styles import STYLES, load_style
from engine import build_pdf


def main(argv=None):
    # argparse is Python's standard library for command-line argument
    # parsing: you describe each argument you accept once, and it handles
    # reading sys.argv, producing --help text, and reporting errors for
    # bad input, all for free.
    #
    # `argv=None` as the function's default means "if the caller doesn't
    # pass a list of arguments explicitly, fall back to argparse's own
    # default of reading sys.argv" - this makes main() easy to call
    # directly from a test with a specific argument list, while still
    # working normally as a real CLI entry point (see the bottom of this
    # file).
    ap = argparse.ArgumentParser(
        prog="fountain2pdf",
        description="Convert a Fountain-formatted script into a formatted PDF.",
    )
    # A positional argument (no leading "--"): the user must supply it,
    # e.g. `python cli.py myplay.fountain`.
    ap.add_argument("input", help="Path to the .fountain source file")
    ap.add_argument(
        "-o", "--output", help="Output PDF path (default: same name as input, .pdf)"
    )
    ap.add_argument(
        # `choices=sorted(STYLES)` restricts this argument to the style
        # keys actually registered in styles/__init__.py (see that module
        # for how STYLES is built) - passing an unknown style name makes
        # argparse print an error and exit before main() even continues,
        # rather than this code having to check it by hand.
        "--style", default="modern", choices=sorted(STYLES),
        help="Output format style (default: modern)",
    )
    ap.add_argument(
        # Two different flag spellings ("--anonymise"/"--anonymize") both
        # map to the same `args.anonymise` attribute via `dest=`, so
        # British and American spellers both get what they expect.
        # action="store_true" means this flag takes no value - it's just
        # present or absent, becoming True or False respectively.
        "--anonymise", "--anonymize", dest="anonymise", action="store_true",
        help=(
            "Produce a blind-submission copy: strips contact-related fields "
            "(contact, email, phone, address, ...) from the title page. "
            "Does not scan the body text for contact details typed inline."
        ),
    )
    # Parses argv (or sys.argv if argv is None) according to the
    # definitions above, returning a Namespace object whose attributes
    # (args.input, args.output, args.style, args.anonymise) hold whatever
    # the user passed in (or each argument's default).
    args = ap.parse_args(argv)

    if not os.path.isfile(args.input):
        # ap.error() prints a usage message to stderr and exits the
        # program with a non-zero status - the standard argparse way to
        # report "your input was invalid" for problems argparse itself
        # couldn't catch (like a file that doesn't exist).
        ap.error(f"input file not found: {args.input}")

    # If the user didn't pass -o/--output, default to the input filename
    # with its extension swapped for ".pdf" - os.path.splitext splits a
    # path into (everything before the last dot, the extension including
    # the dot), so we keep the first half and append our own extension.
    output_path = args.output or os.path.splitext(args.input)[0] + ".pdf"

    # The `with open(...) as f:` block is a context manager: it guarantees
    # the file gets closed automatically once the block ends, even if an
    # exception is raised while reading it - equivalent to, but safer than,
    # manually calling f.close() afterwards.
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
        # Printed to stderr (rather than stdout, which is used for normal
        # progress messages) so it's clearly visible as a warning even if
        # the caller is piping stdout somewhere else.
        print(style.font_fallback_message, file=sys.stderr)

    build_pdf(style, title_page, elements, output_path)

    print(f"Wrote {output_path}  ({len(elements)} elements parsed, style: {style.key})")


if __name__ == "__main__":
    # This guard only runs main() when the file is executed directly
    # (`python cli.py ...`), not when it's imported as a module from
    # somewhere else (e.g. a test file doing `from cli import main`) -
    # `__name__` is only ever the literal string "__main__" in the former
    # case. sys.exit(main()) passes main()'s return value on as the
    # process's exit code; main() currently always falls off the end and
    # implicitly returns None, which sys.exit() treats as "exit code 0",
    # i.e. success.
    sys.exit(main())
