# Sort Excel/CSV File Utility

Category: `Files` · Project: `Sort-Excel-CSV-File-Utility`

## Problem

Reads a file of records, sorts them, and then writes them back to the file.
Allow the user to choose various sort styles and sorting based on a particular
field.

## Features

- CSV parsing with automatic delimiter detection (`,`, `;`, tab, `|`).
- Per-column type inference: `numeric`, `date` or `text`.
- Multi-key sorting with per-key direction and optional forced type:
  `--key age:desc --key name:asc --key joined:date`.
- Stable sort: equal records keep their original relative order.
- Missing/blank values always sort last, regardless of direction.
- Case-insensitive text comparison.
- `--in-place` rewrites the input after saving a `<name>.bak` backup.
- `--output` writes elsewhere; `--columns` projects and reorders fields;
  `--no-header` treats the first row as data; `--list-columns` shows inferred types.
- Clear guidance for `.xlsx`: convert to CSV first (see notes).

## Requirements

Python 3.10+ and the standard library only.

## Usage

```bash
# Sort by age descending, then name ascending
python3 solution.py people.csv --key age:desc --key name --output sorted.csv

# Date sort, in place, with a custom backup suffix
python3 solution.py log.csv --key joined:date:desc --in-place --backup-suffix .orig

# Inspect the columns and inferred types
python3 solution.py people.csv --list-columns

# Keep only two columns, without a header row
python3 solution.py raw.csv --no-header --key col1:numeric --columns col1,col2

# Scripted demonstration
python3 solution.py --demo
```

Options:

| Option | Meaning |
| --- | --- |
| `input` | CSV file to read |
| `-k, --key SPEC` | `FIELD[:asc|desc][:text|numeric|date]`; repeatable |
| `-o, --output PATH` | Write sorted CSV here |
| `--in-place` | Overwrite input after copying it to `<input><suffix>` |
| `--backup-suffix S` | Backup suffix for `--in-place` (default `.bak`) |
| `--delimiter C` | Force a delimiter instead of auto-detecting |
| `--encoding E` | Encoding for read/write, default `utf-8` (a UTF-8 BOM is tolerated) |
| `--no-header` | Treat the first row as data; columns become `col1`, `col2`, ... |
| `--columns LIST` | Comma-separated columns to keep, in output order |
| `--list-columns` | Print column names and inferred types |
| `--demo` | Run the offline demonstration |

### Excel `.xlsx`

A standard-library program cannot read `.xlsx` (it is a ZIP of XML parts with
no built-in parser). The tool detects `.xlsx` input and explains the conversion
instead of failing obscurely. Convert first, for example:

```bash
libreoffice --headless --convert-to csv --outdir . workbook.xlsx
python3 solution.py workbook.csv --key amount:desc
```

## Example Output

```
Loaded people.csv
Inferred types: name=text, team=text, age=numeric, joined=date, score=numeric

Original records:
name   team   age  joined      score
-----  -----  ---  ----------  -----
Zoe    Blue   29   2021-05-17  88.5
...
Sorted by age desc, name asc:
name   team   age  joined      score
-----  -----  ---  ----------  -----
Noah   Green  41   2015-07-08  72.0
Elena  Blue   38   2018-12-05  84.0
adam   Red    34   2019-11-02  91.0
Ivy    Red    34   2020-03-15  88.5
...

Newest join date first: 2023-09-21 (oldest 2015-07-08)
Stable tie order for Blue: ['Zoe', 'Maya', 'Elena']

In-place write verified; backup preserved at people.csv.bak
Case-insensitive name ordering verified.

Demo complete: CSV sort utility works.
```

## Implementation Notes

- A column is inferred numeric when every non-empty value parses as a number,
  date when every value matches one of the supported formats, otherwise text.
  Inference looks at the whole column, not a sample.
- Sorting builds one converted value tuple per row and compares with
  `functools.cmp_to_key`. The comparator applies each key's direction in turn
  and returns 0 for full ties, so Python's stable sort preserves input order.
- Supported date formats: `YYYY-MM-DD`, `YYYY/MM/DD`, `YYYY-MM-DDTHH:MM:SS`,
  `DD-Mon-YYYY`, `DD Mon YYYY`, `Mon DD, YYYY`.
- Complexity is O(k · n log n) comparisons for n rows and k keys; conversion is
  done once per row.
- Limitations: xlsx is out of scope (documented above), no formula evaluation,
  no locale-specific date parsing, and quoted multiline fields are supported by
  the `csv` module but rows must have a consistent field count.
