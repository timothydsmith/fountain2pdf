# fountain2pdf

A command-line tool that converts a [Fountain](https://fountain.io)-formatted
script into a formatted PDF, using a swappable house-style engine.

## Requirements

```
pip install -r requirements.txt
```

The only direct dependency is [reportlab](https://pypi.org/project/reportlab/).

## Usage

```
python cli.py input.fountain
python cli.py input.fountain -o output.pdf
python cli.py input.fountain --style samuel_french
python cli.py input.fountain --anonymise
```

If `-o` is omitted, the output is written next to the input file with a
`.pdf` extension. If `--style` is omitted, `modern` is used.

## Architecture

```
cli.py         entry point: argument parsing, wires everything together
parser.py      Fountain source text -> structured elements
anonymize.py   strips contact-related title-page fields
fonts.py       shared TrueType font discovery/registration helper
engine.py      generic PDF renderer, driven entirely by a Style object
styles/
  base.py           the Style dataclass - the contract between a style and engine.py
  modern.py         the "modern" style (Dramatists Guild Modern Play Format)
  apt.py            the "apt" style (Australian Plays Transform submission format)
  samuel_french.py  the "samuel_french" style (Samuel French / SFI submission format)
  __init__.py       style registry (STYLES dict, load_style())
```

`engine.py` has no house-style knowledge baked in - every margin, font,
size, color and layout flag it uses comes from the `Style` object passed to
it. That's what makes styles pluggable: adding a new house style never
means touching the renderer, only adding a new `styles/*.py` module.

### Adding a new style

1. Create `styles/yourstyle.py` with a `get_style()` function that returns
   a `styles.base.Style`. `styles/modern.py` is the simplest example to
   copy from (it only uses reportlab's built-in fonts); `styles/apt.py`
   additionally shows how to look up and register a real font like
   Palatino via `fonts.register_family()`.
2. Register it in `styles/__init__.py`: add `from . import yourstyle`, and
   add `"yourstyle": yourstyle` to the `STYLES` dict.
3. Run with `--style yourstyle`.

Every layout decision - margins, fonts and sizes, whether a character's
name shares a line with their dialogue or gets a line to itself, scene
heading casing and underlining, how page numbers are positioned and
formatted, whether a broken speech gets a "(MORE)"/continued cue, and much
more - is a field on `Style`. Check `styles/base.py` for the full list and
what each field controls.

## Styles

Three house styles are included; pick one with `--style`:

| Key | Style |
|---|---|
| `modern` (default) | Dramatists Guild "Modern Play Format" |
| `apt` | Australian Plays Transform submission format |
| `samuel_french` | Samuel French / SFI submission format |

They differ in more than just fonts and margins - for example `modern` and
`samuel_french` give the character name its own centered line with dialogue
below it, while `apt` puts the name and the first line of dialogue side by
side. For what a particular style actually produces, read that style
module's docstring (e.g. `styles/apt.py`) rather than this file - the point
of a pluggable style engine is that the house-style detail lives with the
style, not duplicated here.

**Fonts.** `modern` and `samuel_french` use reportlab's built-in
Times-Roman, so there's nothing to install. `apt` wants Palatino, a
commercial font not bundled here - it looks for it (or a free equivalent)
already on the machine running the script and falls back to Times-Roman
with a printed warning if it can't find one. See `styles/apt.py` for the
search locations and the `FOUNTAIN2PDF_PALATINO_DIR` override.

### Preliminary pages

If your Fountain title page includes any of these keys, a page is
generated for each (in this order), between the title page and the first
page of the script:

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

If you'd rather keep this information as visible script text instead of
title-page metadata, write it as a markdown-style heading in the body
before your first scene - `***Characters***`, `***Scene Breakdown***`,
etc. - followed by the same content; it's extracted into the same
preliminary pages either way. A "Name   Description" or "Name:
Description" line (aligned with spaces or a colon) renders as a two-column
entry with the description hanging-indented under itself, however long the
name is.

## Anonymising for blind submission

```
python cli.py input.fountain --anonymise
```

Strips any title-page field whose key contains `contact`, `email`,
`e-mail`, `phone`, `mobile`, `tel`, `address`, `credit`, or `author`
(case-insensitive) before rendering, and prints which fields it removed.
Everything else (title, draft date, characters, setting, etc.) is left
alone.

**Scope:** this only touches title-page metadata. It does not scan the body
of the script for contact details typed inline into dialogue or action
text - if you've put a phone number or email address in the script body
itself, remove it by hand.

## Supported Fountain syntax

| Fountain markup | Renders as |
|---|---|
| `Title:` / `Credit:` / `Author:` block at top of file | Title page |
| `Characters:` / `Setting:` / `Time:` / `Scene Breakdown:` title-page keys, or the same as `***Characters***`-style headings in the body before the first scene | Preliminary pages |
| `# Heading` | ACT divider, starts a new page (alignment/underline/case per style) |
| `## Heading` | SCENE divider (alignment/underline/case per style) |
| `INT. ...` / `EXT. ...` / `.Forced Scene Heading` | Scene heading |
| `... #2A#` at the end of a scene heading | Forced scene number - shown or hidden, and positioned/formatted, per style |
| `ALL CAPS LINE` immediately followed by text | Character cue + dialogue |
| `@Name` | Forced character cue (any case) |
| `(parenthetical)` under a character | Parenthetical - shares a line with the cue or the dialogue, or gets its own line, depending on the style and its position in the speech |
| `>Transition TO:` or `... TO:` | Centered transition |
| `>Centered text<` | Centered text |
| `!Forced action` | Action line (bypasses the all-caps character-cue check) |
| `~Lyric line` | Action line, forced regardless of caps |
| `- item` / `1. item` before the first scene | Bulleted/numbered list (preface text only) |
| `[link text](url)` | Hyperlink |
| `===` | Explicit page break |
| `*italic*`, `**bold**`, `***bold italic***`, `_underline_` | Inline emphasis |
| `/* boneyard */`, `[[note]]` | Stripped out (not rendered) |

Body text before the first scene heading (author's notes, epigraphs, and
the like, other than any preliminary-page headings pulled out of it) is
rendered as plain preface text rather than stage direction, with blank
lines preserved as paragraph breaks.

## Known limitations

- **Dual dialogue** (`^`) is not laid out side-by-side - the marker is
  dropped and the dialogue renders as a normal single column.
- A break in a speech (for pagination, or for a "(MORE)"/continued cue
  where the style uses one) can only fall *between* two dialogue or
  parenthetical lines, never in the middle of one - so a single line so
  long it doesn't fit on any one page is still pushed to the next page as
  a whole.
- The header strap and pagination-from-body logic each require a full
  extra rendering pass to work out ahead of time which page dialogue
  starts on and what scene is active on each page (reportlab draws page
  headers before that page's content is laid out, so this can't be known
  during a single pass). This roughly doubles build time - unnoticeable
  for a script-length document, but worth knowing about.
