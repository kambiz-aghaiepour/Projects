# Create Zip File Maker

Category: `Files` · Project: `Create-Zip-File-Maker`

## Problem

The user enters various files from different directories and the program zips
them up into a zip file. Optional: apply actual compression to the files.

## Features

- Add any mix of files and directories, from different locations, to one archive.
- Preserve directory structure (`notes/readme.txt`) or flatten with `--no-top-dir`.
- Rename a single file source with `--arcname`.
- Compression methods: `store` (no compression), `deflate`, `bzip2`, `lzma`;
  adjustable `--level 0-9`.
- Exclude files with repeatable globs (`--exclude '*.log' --exclude '__pycache__/*'`).
- List archive contents with sizes, compression ratio and method.
- Verify CRCs with `--test`.
- Safe extraction that rejects `..` path escapes and absolute paths.
- Atomic archive creation (temporary file, then replace).
- `--demo` builds an archive, lists it, tests it, extracts it and compares
  compressed versus stored sizes.

## Requirements

Python 3.10+ and the standard library only (`zipfile`, `fnmatch`).

## Usage

```bash
# Zip two directories, skipping logs and caches
python3 solution.py ./notes ./src -o bundle.zip --exclude '*.log' --exclude '*/__pycache__/*'

# Store without compression
python3 solution.py photo.png -o photos.zip --compression store

# Rename a single file inside the archive
python3 solution.py report.pdf -o docs.zip --arcname reports/2026/report.pdf

# Inspect, verify and extract
python3 solution.py --list bundle.zip
python3 solution.py --test bundle.zip
python3 solution.py --extract bundle.zip -d ./unpacked

# Scripted demonstration
python3 solution.py --demo
```

Options:

| Option | Meaning |
| --- | --- |
| `sources...` | Files and/or directories to add |
| `-o, --output PATH` | Archive to create (default `archive.zip`) |
| `--compression M` | `store`, `deflate`, `bzip2` or `lzma` (default `deflate`) |
| `--level N` | Compression level 0-9 (default 6; ignored for store) |
| `--exclude GLOB` | Skip matching archive paths or basenames; repeatable |
| `--arcname NAME` | Archive name for a single-file source |
| `--no-top-dir` | Put directory contents at the archive root |
| `--list ARCHIVE` | List members and compression stats |
| `--test ARCHIVE` | Verify every member's CRC |
| `--extract ARCHIVE` | Extract members safely |
| `-d, --dest PATH` | Extraction destination (default `.`) |
| `--demo` | Run the offline demonstration |

### Encryption

Python's `zipfile` can **read** archives encrypted with legacy ZipCrypto (when
the password is supplied by code), but it cannot **write** encrypted archives at
all. This tool therefore has no password option. Use 7-Zip or `zip -e` when
encryption is required, then list or extract the result normally.

## Example Output

```
  excluded notes/draft.txt
  excluded src/debug.log
Collected 3 files for the archive:
  notes/readme.txt         <- notes/readme.txt
  src/app.py               <- src/app.py
  src/data/values.csv      <- src/data/values.csv

Archive: bundle.zip (526 bytes)
Name                                           Size     Packed   Ratio  Method
notes/readme.txt                                900         46      5%  deflate
src/app.py                                      576         56     10%  deflate
src/data/values.csv                             128         84     66%  deflate
TOTAL                                          1604        186    12%  saved 88.4%

Extracted 3 files to extracted/
Deflate archive 526 bytes vs stored archive 1944 bytes
Compression reduced the archive size.

Demo complete: zip creation, listing, test and extraction work.
```

## Implementation Notes

- Directory sources are walked with `Path.rglob`; the archive name is relative
  to the directory's parent (so the top directory is kept) unless `--no-top-dir`
  is given.
- Exclusion patterns are matched against both the full archive path and the
  basename using `fnmatch.fnmatchcase`, so `*.log` catches nested files too.
- Creation writes to a temporary file in the destination directory, then
  `os.replace`s it, so a failed run never leaves a half-written archive.
- Extraction resolves every member path and checks it stays under the
  destination root before writing, preventing Zip Slip traversal.
- Empty directories are not stored; only files become members.
- Very small or already-compressed files can grow under deflate because of
  per-file format overhead; the demo reports both total sizes so the trade-off
  is visible.
