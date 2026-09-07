# Changelog

All notable changes to fountain2pdf are documented here.

## [Unreleased]

### Fixed

- The gap between a speech and a following stage direction (or scene
  heading) was too large: `speech_gap` was emitted as its own spacer and
  the next element then added its own space on top. The inter-speech gap
  is now carried as the speech's `spaceAfter`, so reportlab collapses it
  against the next element's leading space (taking the larger of the two)
  instead of stacking them.

## [0.1.1] - 2026-09-07

### Fixed

- Removed a strip of blank space that could appear at the top of a page
  (most visibly with the `apt` style). The gap that separates two
  speeches was a standalone `Spacer`, which reportlab honours even at the
  top of a frame; when a speech ended close to the bottom margin the
  spacer was pushed onto the next page and printed above its first line.
  Inter-speech gaps and preliminary-section blank lines now collapse to
  nothing when they land at the top of a page.

## [0.1] - 2026-08-15

Initial release. `fountain2pdf` converts a [Fountain](https://fountain.io)-formatted
script into a formatted PDF, with page layout driven entirely by a
swappable `Style` object - see the README for the full architecture and
`styles/base.py` for the complete list of what a style can control.

### House styles

- **`modern`** (default) - Dramatists Guild "Modern Play Format": centered
  character names on their own line, dialogue below, top-right pagination.
- **`apt`** - Australian Plays Transform submission format: character name
  and the first line of dialogue share one line with a hanging indent,
  running header strap, roman-numeral front matter.
- **`samuel_french`** - Samuel French / SFI submission format: centered
  names with short (one-word) parentheticals inline, underlined act/scene
  headings, underlined "Cast of Characters" entries.

### Fountain parsing

- Title page (`Key: value` block), section headings (`#`/`##` as Act/Scene
  dividers), scene headings (`INT./EXT./EST.` or forced `.Scene Heading`,
  including forced scene numbers like `#2A#`), character cues (all-caps or
  forced `@Name`), parentheticals, dialogue, action/stage direction,
  transitions, centered text, forced action (`!`) and lyric (`~`) lines,
  page breaks (`===`), inline emphasis (`*italic*`, `**bold**`,
  `***bold italic***`, `_underline_`), markdown-style links
  (`[text](url)`), and boneyard/notes stripping.
- Body text before the first scene heading is treated as a preface
  (author's notes, epigraphs, etc.) rather than stage direction, with
  blank lines preserved as paragraph breaks and `-`/`1.` lines rendered as
  real bulleted/numbered lists.

### Preliminary pages

- `Characters` / `Setting` / `Time` / `Scene Breakdown` title-page keys
  each generate their own preliminary page (Setting and Time combine onto
  one "Setting & Time" page); any that are omitted are simply skipped.
- The same sections can instead be written as markdown-style headings
  (`***Characters***`, etc.) in the script body before the first scene,
  for writers who'd rather keep them as visible text.
- A `Name   Description` or `Name: Description` line (space- or
  colon-separated) renders as a two-column entry, hanging-indented so
  every description lines up regardless of name length.

### Pagination

- Arabic numbering starting at the first scene, with everything before it
  (title page, preliminary pages, preface) either unnumbered or in
  lowercase roman numerals, per style.
- Page number position, alignment, and format string are all
  style-configurable, as is a running "PLAY TITLE | SCENE" header strap.

### Dialogue and speeches

- Two character-cue layouts, chosen per style: name and dialogue sharing a
  line (with a hanging indent for wrapped/continuation lines), or the name
  on its own centered line with dialogue below.
- A leading parenthetical can merge onto the same line as the dialogue
  that follows it, or onto the character name's own line for a one-word
  direction, depending on the style; later parentheticals in the same
  speech always get their own line.
- A speech too long for the remaining space on a page now breaks across
  the page boundary instead of moving to the next page as a whole, with an
  optional "(MORE)" / continued cue (wording configurable per style).

### Other

- `--anonymise` strips contact-related title-page fields (contact, email,
  phone, address, credit, author, ...) for blind submission, without
  touching the script body.

### Known limitations

- Dual dialogue (`^`) is not laid out side-by-side.
- A break in a speech can only fall between two lines, never mid-line - an
  uninterrupted line longer than a full page still can't be split.
- The header strap and from-body pagination each require a full extra
  rendering pass, roughly doubling build time.
