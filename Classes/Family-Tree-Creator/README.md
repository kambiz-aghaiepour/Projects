# Family Tree Creator

## Problem

Create a class called Person which will have a name, when they were born and
when (and if) they died. Allow the user to create these Person classes and put
them into a family tree structure. Print out the tree to the screen.

This is the **Classes / Family Tree Creator** project: a directed family graph
with parent/child and spouse links, cycle detection, relationship queries,
ASCII rendering and JSON persistence.

Project location: `Classes/Family-Tree-Creator/` (`README.md` and
`solution.py`).

## Features

- `Person` stores a name, ISO birth date, optional death date and notes, and
  derives `is_alive`, age, a compact lifespan and a display string.
- `FamilyTree` creates people with stable numeric IDs, resolves them by `#id`
  or unique name, and maintains links bidirectionally.
- `add_parent()` / `add_child()` reject self-parenting, duplicate links and
  **cycles** (e.g. making a descendant a parent of their own ancestor).
- `add_spouse()` creates a symmetric partnership and rejects self-marriage and
  duplicate links.
- Queries: `ancestors()`, `descendants()`, `siblings()`, `roots()`; results are
  de-duplicated (diamond-shaped families are handled) and sorted by birth.
- ASCII tree renderer with spouses shown inline and shared descendants printed
  once; accepts an optional root to print a subtree.
- JSON save/load round-trips all people, IDs, dates, parents and spouses.
- Interactive editor and scriptable flags for all read-only operations.

## Requirements

Python 3.10+. Standard library only (`datetime.date`, `json`, `argparse`).

## Usage

```bash
python3 solution.py --demo
python3 solution.py --tree
python3 solution.py --tree --root "Emma Bennett"
python3 solution.py --list
python3 solution.py --ancestors "Sophie Foster"
python3 solution.py --descendants "Arthur Bennett"
python3 solution.py --tree --save family.json
python3 solution.py --data family.json --tree
```

Options:

| Option | Meaning |
| --- | --- |
| `--demo` | Build the sample family and exercise every feature. |
| `--data FILE` | Load a family from JSON (otherwise the sample family is used). |
| `--tree` | Print the ASCII tree, optionally rooted with `--root`. |
| `--root PERSON` | Start the tree at a person (`#id` or unique name). |
| `--list` | Print the people table. |
| `--ancestors PERSON` | List all known ancestors. |
| `--descendants PERSON` | List all known descendants. |
| `--save FILE` | Save the family after the actions. |

With no options an interactive editor is shown: `1` tree, `2` list, `3` add
person, `4` link parent, `5` link spouse, `6` ancestors, `7` descendants,
`8` save, `9` load, `q` quit. Names may be entered as `#12` or as text; an
ambiguous name is reported with the matching IDs.

## Example Output

```text
=== Family Tree Creator: demo ===

Family tree with 13 people and 5 root(s).

 ID  Name                 Born        Died         Age Parents Children
-----------------------------------------------------------------------
  1  Arthur Bennett       1920-04-12  1998-11-03    78       0        3
  2  Margaret Hale        1923-02-08  2010-06-21    87       0        3
  3  Susan Bennett        1948-09-02  -              -       2        1
  4  Robert Bennett       1951-01-30  -              -       2        2
  5  Linda Bennett        1954-07-14  -              -       2        0
  6  Paul Wright          1946-05-19  -              -       0        1
  7  Laura Wright         1975-03-25  -              -       2        0
  8  Helen Carter         1953-08-11  -              -       0        2
  9  Emma Bennett         1978-12-04  -              -       2        2
 10  Daniel Bennett       1981-06-16  -              -       2        0
 11  James Foster         1977-10-22  -              -       0        2
 12  Sophie Foster        2005-02-14  -              -       2        0
 13  Leo Foster           2008-08-08  -              -       2        0

Family tree:
Arthur Bennett (1920-1998)  + Margaret Hale (1923-2010)
|-- Susan Bennett (b. 1948)  + Paul Wright (b. 1946)
|   +-- Laura Wright (b. 1975)
|-- Robert Bennett (b. 1951)  + Helen Carter (b. 1953)
|   |-- Emma Bennett (b. 1978)  + James Foster (b. 1977)
|   |   |-- Sophie Foster (b. 2005)
|   |   +-- Leo Foster (b. 2008)
|   +-- Daniel Bennett (b. 1981)
+-- Linda Bennett (b. 1954)

Ancestors of Sophie Foster (6):
  Arthur Bennett (1920-1998)
  Margaret Hale (1923-2010)
  Robert Bennett (b. 1951)
  Helen Carter (b. 1953)
  James Foster (b. 1977)
  Emma Bennett (b. 1978)

Descendants of Arthur Bennett (8):
  Susan Bennett (b. 1948)
  Robert Bennett (b. 1951)
  Linda Bennett (b. 1954)
  Laura Wright (b. 1975)
  Emma Bennett (b. 1978)
  Daniel Bennett (b. 1981)
  Sophie Foster (b. 2005)
  Leo Foster (b. 2008)

Siblings of Emma Bennett: Daniel Bennett

Validation checks:
  cycle: rejected -> cannot make Sophie Foster a parent of Arthur Bennett: Arthur Bennett is already an ancestor of Sophie Foster (cycle)
  self-parent: rejected -> Arthur Bennett cannot be their own parent
  death before birth: rejected -> Time Traveller cannot die (1999-01-01) before being born (2000-01-01)

Saved and reloaded 13 people from JSON (2629 bytes); tree matches: True
  Ancestors of Sophie after reload: 6

Demo complete.
```

## Implementation Notes

- Relationships are stored as object references on both sides:
  `child.parents` and `parent.children` are updated together, as are
  `spouse` lists. `Person` uses identity equality (`eq=False`) so duplicate
  names never collapse into one node.
- Cycle detection walks the prospective parent's ancestor set and refuses the
  link if the child is already there. This keeps parent/child edges a DAG,
  which makes rendering and queries terminate for any valid tree.
- `ancestors()` and `descendants()` use an iterative BFS with a `person_id`
  visited set, so shared ancestors (cousin marriages, multiple paths) appear
  once and deep families do not hit the recursion limit.
- Rendering selects all parentless people as roots, sorts siblings by birth,
  prints `+--` for the last child and `|--` otherwise, and tracks a global
  visited set. Spouses are annotated inline (`+ Name`) and marked visited so
  they do not produce a second copy of the same subtree. `render(root)` prints
  just that person's descendants.
- Dates are validated at construction: no future birth/death, death cannot
  precede birth. Age is whole years at death (or today for living people).
- JSON shape: `{"people": [{"id", "name", "birth", "death", "notes",
  "parents": [ids], "spouses": [ids]}]}`. Loading creates every person first,
  then links relationships, so forward references work. IDs are preserved and
  the next ID is derived from the maximum.
- The sample family has four generations and 13 people; the demo's cycle test
  deliberately tries to make Sophie a parent of Arthur and shows the rejection
  message.
