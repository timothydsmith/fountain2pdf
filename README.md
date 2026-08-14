# fountain2pdf

A command-line tool that converts a [Fountain](https://fountain.io)-formatted
script into a formatted PDF, using a swappable house-style engine.

## Requirements

```
pip install reportlab
```

## Usage

```
python cli.py input.fountain
python cli.py input.fountain -o output.pdf
python cli.py input.fountain --style apt
python cli.py input.fountain --anonymise
```

If `-o` is omitted, the output is written next to the input file with a
`.pdf` extension.

## Architecture

```
cli.py         entry point: argument parsing, wires everything together
parser.py      Fountain source text -> structured elements
anonymize.py   strips contact-related title-page fields
fonts.py       shared TrueType font discovery/registration helper
engine.py      generic PDF renderer, driven entirely by a Style object
styles/
  base.py      the Style dataclass - the contract between a style and engine.py
  apt.py       the "apt" style (Australian Plays Transform submission format)
  __init__.py  style registry (STYLES dict, load_style())
```

`engine.py` has no house-style knowledge baked in - every margin, font,
size, color and layout flag it uses comes from the `Style` object passed to
it. That's what makes styles pluggable.

### Adding a new style

1. Create `styles/yourstyle.py` with a `get_style()` function that returns
   a `styles.base.Style` (see `styles/apt.py` for a complete example,
   including how to look up and register a real font like Palatino via
   `fonts.register_family()`).
2. Register it in `styles/__init__.py`:
   ```python
   from . import yourstyle
   STYLES = {"apt": apt, "yourstyle": yourstyle}
   ```
3. Run with `--style yourstyle`.

Every layout decision - margins, fonts and sizes, dialogue-table column
widths, spacing between speeches, stage-direction color, whether there's a
running header strap, how pagination is numbered - is a field on `Style`.
Check `styles/base.py` for the full list and what each field controls.

## The `apt` style

Implements the Australian Plays Transform submission format (see the APT
Submissions Style Guide):

- A4, 40mm top margin, 25mm left/right/bottom
- Palatino 10pt throughout (title page: 35pt title, 18pt playwright name)
- Character names in bold caps, flush left, followed by a tab and the
  dialogue on the same line; wrapped lines hang-indent to the same column
- Single-spaced within a speech, double-spaced between different speeches
- Stage directions in italic, 90% tint black, flush left (no extra indent)
- A running header strap at the top of each dialogue page: play title in
  bold caps, current scene in regular caps, centered, separated by " | "
- Pagination centered at the bottom, starting at "1" on the first page of
  dialogue - the title page and any preliminary pages are unnumbered

**Preliminary pages.** If your Fountain title page includes any of these
keys, a page is generated for each (in this order), between the title page
and the first page of dialogue:

```
Title: The Last Rehearsal
Author: Tim
Characters:
    MARGARET, sixties
    DAVID, thirty
Setting: A community theatre green room
Time: The present, late at night
Scene Breakdown:
    Act One: Scene One, Scene Two
    Act Two: Scene One
```

`Characters` and `Scene Breakdown` (or `Scenes`) each get their own page;
`Setting` and `Time` are combined onto one "Setting & Time" page. Any of
these you omit are simply skipped - none are required.

**Palatino.** It's a commercial font, so it isn't bundled here. The style
looks for it (or a free equivalent) already on the machine running the
script:

- **macOS**: nothing to do - Palatino ships in `/System/Library/Fonts/Palatino.ttc`.
- **Windows**: nothing to do - "Palatino Linotype" ships in `C:\Windows\Fonts`.
- **Linux**: install `fonts-texgyre` (the free, metric-compatible "TeX Gyre
  Pagella") - it's checked automatically, or set `FOUNTAIN2PDF_PALATINO_DIR`
  to a folder containing your own `Palatino-Regular/-Bold/-Italic/-BoldItalic.ttf`
  (or `.otf`) files.

If nothing is found, it falls back to Times-Roman and prints a warning to
stderr - the substitution is never silent.

## Anonymising for blind submission

```
python cli.py input.fountain --anonymise
```

Strips any title-page field whose key contains `contact`, `email`, `phone`,
`mobile`, `tel`, or `address` (case-insensitive) before rendering, and
prints which fields it removed. Everything else (title, author name, draft
date, characters, setting, etc.) is left alone.

**Scope:** this only touches title-page metadata. It does not scan the body
of the script for contact details typed inline into dialogue or action
text - if you've put a phone number or email address in the script body
itself, remove it by hand.

## Supported Fountain syntax

| Fountain markup | Renders as |
|---|---|
| `Title:` / `Credit:` / `Author:` block at top of file | Title page |
| `Characters:` / `Setting:` / `Time:` / `Scene Breakdown:` | Preliminary pages (apt style) |
| `# Heading` | ACT divider (starts a new page), centered |
| `## Heading` | SCENE divider, centered |
| `INT. ...` / `EXT. ...` / `.Forced Scene Heading` | Centered scene heading |
| `ALL CAPS LINE` immediately followed by text | Character cue + dialogue |
| `@Name` | Forced character cue (any case) |
| `(parenthetical)` under a character | Italic parenthetical, inline with dialogue |
| `>Transition TO:` or `... TO:` | Centered transition |
| `>Centered text<` | Centered text |
| `!Forced action` | Action line (bypasses the all-caps character-cue check) |
| `~Lyric line` | Action line, forced regardless of caps |
| `===` | Explicit page break |
| `*italic*`, `**bold**`, `***bold italic***`, `_underline_` | Inline emphasis |
| `/* boneyard */`, `[[note]]` | Stripped out (not rendered) |

## Known limitations

- **Dual dialogue** (`^`) is not laid out side-by-side - the marker is
  dropped and the dialogue renders as a normal single column.
- **No `(MORE)` / `(CONT'D)` handling.** A character cue and its dialogue
  are kept together as one unit; a very long uninterrupted speech that
  doesn't fit the remainder of a page moves to the next page as a whole.
- Scene numbers (`#123#`) are not parsed or printed.
- The header strap and pagination-from-body logic each require a full
  extra rendering pass to work out ahead of time which page dialogue
  starts on and what scene is active on each page (reportlab draws page
  headers before that page's content is laid out, so this can't be known
  during a single pass). This roughly doubles build time - unnoticeable
  for a script-length document, but worth knowing about.
