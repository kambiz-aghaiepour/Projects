# PDF Generator

Category: `Files` · Project: `PDF-Generator`

## Problem

An application which can read in a text file, HTML file or some other file and
generates a PDF file out of it.

## Features

- Converts plain text (paragraphs separated by blank lines) to a paginated PDF.
- Converts simple HTML: `<h1>`–`<h3>`, `<p>`, `<ul>/<ol>/<li>` (rendered as
  bullet items), `<b>/<strong>`, `<i>/<em>`, `<br>`, `<hr>`, and
  `<div class="page-break">`.
- A4 or US Letter page sizes, configurable margins, body font size and line spacing.
- Automatic word wrapping and pagination, with widow control for headings/paragraphs.
- Footer page numbers (`Page N of M`) on every page.
- Bold, italic and bold-italic runs using the standard Helvetica family.
- Correct PDF structure: catalog, page tree, font resources, content streams,
  byte-offset xref table, trailer, `%%EOF`.
- `--validate` re-parses a PDF, checks the header/xref offsets and reports the
  page count.
- `--demo` generates and validates PDFs from both a text and an HTML sample.

## Requirements

Python 3.10+ and the standard library only. No PDF library, no font files and
no network access are needed.

## Usage

```bash
# Text file -> PDF next to the input
python3 solution.py notes.txt

# HTML with an explicit output path and Letter page size
python3 solution.py report.html -o report.pdf --page-size letter --margin 72

# Journal article style: 11 pt, 1.5 line spacing, custom title
python3 solution.py paper.html -o paper.pdf --font-size 11 --line-spacing 1.5 \
    --title "A Study of Standard Libraries"

# Check an existing (classic xref) PDF
python3 solution.py --validate report.pdf

# Scripted demonstration
python3 solution.py --demo
```

Options:

| Option | Meaning |
| --- | --- |
| `input` | `.txt` or `.html`/`.htm` input file |
| `-o, --output PATH` | Output PDF (default: input name with `.pdf`) |
| `--format {auto,text,html}` | Input format; `auto` uses the file extension |
| `--page-size {a4,letter}` | Page geometry (default `a4`) |
| `--margin POINTS` | Margin in PDF points (default 56.7 ≈ 2 cm) |
| `--font-size PT` | Body font size (default 11) |
| `--line-spacing FACTOR` | Line height multiple (default 1.35) |
| `--title TEXT` | PDF metadata title |
| `--validate PDF` | Validate a PDF and print its page count |
| `--demo` | Run the offline demonstration |

### HTML subset

```html
<h1>Title</h1>
<p>Text with <b>bold</b>, <i>italic</i> and <b><i>both</i></b>.</p>
<ul><li>First bullet</li><li>Second bullet</li></ul>
<hr>
<p>Line one<br>Line two</p>
<div class="page-break"></div>
<h2>Starts on a new page</h2>
```

Other tags are ignored; their text is still rendered. CSS, images, tables and
JavaScript are not interpreted.

## Example Output

```
Text PDF : from_text.pdf  1970 bytes  1 page(s)  9 objects
HTML blocks parsed: 10 -> ['heading', 'paragraph', 'heading', 'bullet', 'bullet', 'rule', 'paragraph', 'pagebreak', 'heading', 'paragraph']
HTML PDF : from_html.pdf  3066 bytes  2 page(s)  11 objects
Header   : b'%PDF-1.4'
Letter-size variant validated.
Validator rejected a non-PDF file as expected.

Demo complete: PDF generation and validation work.
```

## Implementation Notes

- **Layout:** blocks flow down the page; each line is measured with an
  approximate Helvetica advance-width table (narrow/wide letters and digits get
  distinct widths). A line that would cross the bottom margin starts a new page.
  Page numbers are appended after pagination so `N of M` is known.
- **PDF structure:** object 1 is the catalog, 2 the page tree, 3–6 the four
  Helvetica fonts, 7 the info dictionary, then a page object and content stream
  per page. The xref table records the exact byte offset of every object, and
  the trailer points at the catalog and info dictionary.
- **Text encoding:** strings use WinAnsi (cp1252) with octal escapes for
  non-ASCII bytes, so curly quotes and accented Latin characters work. Text
  outside cp1252 is replaced rather than corrupted.
- **Validation:** `--validate` checks the `%PDF-` header, the final `%%EOF`,
  the `startxref` offset, every xref entry's object offset, and counts
  `/Type /Page` objects.
- **Limitations:** no font embedding (viewers substitute Helvetica), no images
  or tables, no CSS layout, and validation supports classic xref tables rather
  than compressed xref streams. Font metrics are approximations, so very wide
  glyph runs may sit slightly inside or outside the nominal right margin.
