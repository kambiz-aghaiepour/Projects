#!/usr/bin/env python3
"""Family Tree Creator.

``Person`` records a name, birth date, optional death date and notes.
``FamilyTree`` links people as parents, children and spouses, rejects cycles,
answers ancestor/descendant queries, renders an ASCII tree and persists the
whole family to JSON.

Run ``python3 solution.py --demo`` to build and print a sample family.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional


class FamilyTreeError(Exception):
    """Raised for invalid people, dates or relationships."""


def parse_date(value: str) -> date:
    """Parse an ISO date (YYYY-MM-DD) with a friendly error."""
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise FamilyTreeError(f"invalid date {value!r}; expected YYYY-MM-DD") from exc


@dataclass(eq=False)
class Person:
    """A person in the family tree.

    Relationships are stored on both sides by :class:`FamilyTree`; construct
    people directly or through ``FamilyTree.add_person``.
    """

    name: str
    birth: date
    death: Optional[date] = None
    person_id: int = 0
    notes: str = ""
    parents: list["Person"] = field(default_factory=list, repr=False)
    children: list["Person"] = field(default_factory=list, repr=False)
    spouses: list["Person"] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.name = " ".join(self.name.split())
        if not self.name:
            raise FamilyTreeError("person name cannot be empty")
        if not isinstance(self.birth, date):
            raise FamilyTreeError("birth must be a date")
        if self.birth > date.today():
            raise FamilyTreeError(f"birth date for {self.name} is in the future")
        if self.death is not None:
            if not isinstance(self.death, date):
                raise FamilyTreeError("death must be a date or None")
            if self.death < self.birth:
                raise FamilyTreeError(
                    f"{self.name} cannot die ({self.death}) before being born ({self.birth})"
                )
            if self.death > date.today():
                raise FamilyTreeError(f"death date for {self.name} is in the future")

    @property
    def is_alive(self) -> bool:
        return self.death is None

    def age(self, on: Optional[date] = None) -> int:
        """Age in whole years at death, or on *on* (default today) if alive."""
        end = self.death or on or date.today()
        years = end.year - self.birth.year
        if (end.month, end.day) < (self.birth.month, self.birth.day):
            years -= 1
        return max(0, years)

    def lifespan(self) -> str:
        """Compact dates: ``1920-1998`` for the dead, ``b. 1990`` for the living."""
        if self.death is None:
            return f"b. {self.birth.year}"
        return f"{self.birth.year}-{self.death.year}"

    def display(self) -> str:
        return f"{self.name} ({self.lifespan()})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.person_id,
            "name": self.name,
            "birth": self.birth.isoformat(),
            "death": self.death.isoformat() if self.death else None,
            "notes": self.notes,
        }

    def __str__(self) -> str:
        return self.display()


class FamilyTree:
    """A collection of people connected by parent/child and spouse links."""

    def __init__(self) -> None:
        self._people: dict[int, Person] = {}
        self._next_id = 1

    def __len__(self) -> int:
        return len(self._people)

    @property
    def people(self) -> list[Person]:
        return sorted(self._people.values(), key=lambda person: person.person_id)

    # -- creation and lookup -------------------------------------------
    def add_person(self, name: str, birth: date | str, death: date | str | None = None,
                   notes: str = "", person_id: Optional[int] = None) -> Person:
        """Create a person and add them to the tree."""
        if isinstance(birth, str):
            birth = parse_date(birth)
        if isinstance(death, str):
            death = parse_date(death)
        identifier = person_id if person_id is not None else self._next_id
        if identifier in self._people:
            raise FamilyTreeError(f"person id {identifier} is already used")
        person = Person(name, birth, death, identifier, notes)
        self._people[identifier] = person
        self._next_id = max(self._next_id, identifier + 1)
        return person

    def get(self, identifier: int) -> Person:
        try:
            return self._people[identifier]
        except KeyError as exc:
            raise FamilyTreeError(f"no person with id {identifier}") from exc

    def find(self, reference: str) -> Person:
        """Resolve ``#12`` or a unique name to a person."""
        text = reference.strip()
        if text.startswith("#"):
            text = text[1:]
        if text.isdigit():
            return self.get(int(text))
        matches = [person for person in self._people.values()
                   if person.name.lower() == text.lower()]
        if not matches:
            matches = [person for person in self._people.values()
                       if text.lower() in person.name.lower()]
        if not matches:
            raise FamilyTreeError(f"no person matching {reference!r}")
        if len(matches) > 1:
            choices = ", ".join(f"#{person.person_id} {person.name}" for person in matches)
            raise FamilyTreeError(f"{reference!r} is ambiguous: {choices}")
        return matches[0]

    # -- relationships --------------------------------------------------
    def add_parent(self, parent: Person, child: Person) -> None:
        """Link *parent* to *child*, rejecting duplicate links and cycles."""
        parent = self.get(parent.person_id)
        child = self.get(child.person_id)
        if parent is child:
            raise FamilyTreeError(f"{parent.name} cannot be their own parent")
        if any(existing is parent for existing in child.parents):
            raise FamilyTreeError(f"{parent.name} is already a parent of {child.name}")
        if child in self.ancestors(parent):
            raise FamilyTreeError(
                f"cannot make {parent.name} a parent of {child.name}: "
                f"{child.name} is already an ancestor of {parent.name} (cycle)"
            )
        child.parents.append(parent)
        parent.children.append(child)

    def add_child(self, parent: Person, child: Person) -> None:
        """Convenience alias for ``add_parent(parent, child)``."""
        self.add_parent(parent, child)

    def add_spouse(self, first: Person, second: Person) -> None:
        """Record a symmetric marriage/partnership link."""
        first = self.get(first.person_id)
        second = self.get(second.person_id)
        if first is second:
            raise FamilyTreeError(f"{first.name} cannot be married to themselves")
        if any(existing is second for existing in first.spouses):
            raise FamilyTreeError(f"{first.name} and {second.name} are already spouses")
        first.spouses.append(second)
        second.spouses.append(first)

    # -- queries --------------------------------------------------------
    def ancestors(self, person: Person) -> list[Person]:
        """Every known ancestor, breadth-first and sorted by birth."""
        found: dict[int, Person] = {}
        queue = list(person.parents)
        while queue:
            current = queue.pop(0)
            if current.person_id in found:
                continue
            found[current.person_id] = current
            queue.extend(current.parents)
        return sorted(found.values(), key=lambda item: (item.birth, item.name))

    def descendants(self, person: Person) -> list[Person]:
        """Every known descendant, breadth-first and sorted by birth."""
        found: dict[int, Person] = {}
        queue = list(person.children)
        while queue:
            current = queue.pop(0)
            if current.person_id in found:
                continue
            found[current.person_id] = current
            queue.extend(current.children)
        return sorted(found.values(), key=lambda item: (item.birth, item.name))

    def siblings(self, person: Person) -> list[Person]:
        """People sharing at least one parent, excluding *person*."""
        found = {child.person_id: child for parent in person.parents for child in parent.children}
        found.pop(person.person_id, None)
        return sorted(found.values(), key=lambda item: (item.birth, item.name))

    def roots(self) -> list[Person]:
        """People with no recorded parents."""
        return sorted(
            (person for person in self._people.values() if not person.parents),
            key=lambda item: (item.birth, item.name),
        )

    # -- rendering ------------------------------------------------------
    def render(self, root: Optional[Person] = None) -> str:
        """Render descendants of *root* (or every root) as an ASCII tree."""
        if not self._people:
            return "(empty family tree)"
        starts = [root] if root is not None else self.roots()
        visited: set[int] = set()
        blocks: list[str] = []
        for person in starts:
            if person.person_id in visited:
                continue
            lines: list[str] = []
            self._render_node(person, "", True, True, visited, lines)
            blocks.append("\n".join(lines))
        if not blocks:
            return "(no root found)"
        return "\n\n".join(blocks)

    def _render_node(self, person: Person, prefix: str, is_last: bool,
                     is_root: bool, visited: set[int], lines: list[str]) -> None:
        connector = "" if is_root else prefix + ("+-- " if is_last else "|-- ")
        spouse_text = ""
        if person.spouses:
            spouses = sorted(person.spouses, key=lambda item: (item.birth, item.name))
            spouse_text = "  + " + ", ".join(spouse.display() for spouse in spouses)
        lines.append(f"{connector}{person.display()}{spouse_text}")
        visited.add(person.person_id)
        # A spouse is shown inline; do not start a second tree for them.
        for spouse in person.spouses:
            visited.add(spouse.person_id)

        children = sorted(person.children, key=lambda item: (item.birth, item.name))
        child_prefix = prefix + ("" if is_root else ("    " if is_last else "|   "))
        for index, child in enumerate(children):
            if child.person_id in visited:
                continue
            self._render_node(child, child_prefix, index == len(children) - 1,
                              False, visited, lines)

    def people_table(self) -> str:
        header = (f"{'ID':>3}  {'Name':<20} {'Born':<11} {'Died':<11} "
                  f"{'Age':>4} {'Parents':>7} {'Children':>8}")
        lines = [header, "-" * len(header)]
        for person in self.people:
            died = person.death.isoformat() if person.death else "-"
            age = str(person.age()) if person.death else "-"
            lines.append(
                f"{person.person_id:>3}  {person.name:<20} {person.birth.isoformat():<11} "
                f"{died:<11} {age:>4} {len(person.parents):>7} {len(person.children):>8}"
            )
        return "\n".join(lines)

    # -- persistence ----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "people": [
                {
                    **person.to_dict(),
                    "parents": [parent.person_id for parent in person.parents],
                    "spouses": [spouse.person_id for spouse in person.spouses],
                }
                for person in self.people
            ]
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FamilyTree":
        if not isinstance(data, dict):
            raise FamilyTreeError("family file must contain a JSON object")
        records = data.get("people")
        if not isinstance(records, list):
            raise FamilyTreeError("family file must contain a 'people' list")
        if not all(isinstance(record, dict) for record in records):
            raise FamilyTreeError("each person must be a JSON object")
        tree = cls()
        for record in records:
            try:
                tree.add_person(
                    name=str(record["name"]),
                    birth=str(record["birth"]),
                    death=str(record["death"]) if record.get("death") else None,
                    notes=str(record.get("notes", "")),
                    person_id=int(record.get("id", 0)) or None,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise FamilyTreeError(f"invalid person record: {exc}") from exc
        for record in records:
            if "id" not in record:
                raise FamilyTreeError(f"person {record.get('name', '?')!r} is missing an id")
            person = tree.get(int(record["id"]))
            for parent_id in record.get("parents", []):
                parent = tree.get(int(parent_id))
                if any(existing is parent for existing in person.parents):
                    continue
                tree.add_parent(parent, person)
            for spouse_id in record.get("spouses", []):
                spouse = tree.get(int(spouse_id))
                if any(existing is spouse for existing in person.spouses):
                    continue
                tree.add_spouse(person, spouse)
        return tree

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "FamilyTree":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise FamilyTreeError(f"family file not found: {path}") from exc
        except OSError as exc:
            raise FamilyTreeError(f"cannot read family file {path}: {exc}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise FamilyTreeError(f"invalid JSON in {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise FamilyTreeError("family file must contain a JSON object")
        return cls.from_dict(data)


def build_sample_tree() -> FamilyTree:
    """Build a four-generation family used by the demo and default session."""
    tree = FamilyTree()
    arthur = tree.add_person("Arthur Bennett", date(1920, 4, 12), date(1998, 11, 3),
                             "Carpenter from Leeds")
    margaret = tree.add_person("Margaret Hale", date(1923, 2, 8), date(2010, 6, 21))
    tree.add_spouse(arthur, margaret)

    susan = tree.add_person("Susan Bennett", date(1948, 9, 2))
    robert = tree.add_person("Robert Bennett", date(1951, 1, 30))
    linda = tree.add_person("Linda Bennett", date(1954, 7, 14))
    for child in (susan, robert, linda):
        tree.add_child(arthur, child)
        tree.add_child(margaret, child)

    paul = tree.add_person("Paul Wright", date(1946, 5, 19))
    tree.add_spouse(susan, paul)
    laura = tree.add_person("Laura Wright", date(1975, 3, 25))
    tree.add_child(susan, laura)
    tree.add_child(paul, laura)

    helen = tree.add_person("Helen Carter", date(1953, 8, 11))
    tree.add_spouse(robert, helen)
    emma = tree.add_person("Emma Bennett", date(1978, 12, 4))
    daniel = tree.add_person("Daniel Bennett", date(1981, 6, 16))
    for child in (emma, daniel):
        tree.add_child(robert, child)
        tree.add_child(helen, child)

    james = tree.add_person("James Foster", date(1977, 10, 22))
    tree.add_spouse(emma, james)
    sophie = tree.add_person("Sophie Foster", date(2005, 2, 14), notes="Studies botany")
    leo = tree.add_person("Leo Foster", date(2008, 8, 8))
    for child in (sophie, leo):
        tree.add_child(emma, child)
        tree.add_child(james, child)
    return tree


def run_demo() -> int:
    """Print the tree, query relationships, reject cycles and reload JSON."""
    print("=== Family Tree Creator: demo ===\n")
    tree = build_sample_tree()
    print(f"Family tree with {len(tree)} people and {len(tree.roots())} root(s).\n")
    print(tree.people_table())

    print("\nFamily tree:")
    print(tree.render())

    sophie = tree.find("Sophie Foster")
    ancestors = tree.ancestors(sophie)
    print(f"\nAncestors of {sophie.name} ({len(ancestors)}):")
    for person in ancestors:
        print(f"  {person.display()}")

    arthur = tree.find("Arthur Bennett")
    descendants = tree.descendants(arthur)
    print(f"\nDescendants of {arthur.name} ({len(descendants)}):")
    for person in descendants:
        print(f"  {person.display()}")

    emma = tree.find("Emma Bennett")
    print(f"\nSiblings of {emma.name}: "
          + (", ".join(person.name for person in tree.siblings(emma)) or "none"))

    print("\nValidation checks:")
    try:
        tree.add_parent(sophie, arthur)
    except FamilyTreeError as exc:
        print(f"  cycle: rejected -> {exc}")
    try:
        tree.add_parent(arthur, arthur)
    except FamilyTreeError as exc:
        print(f"  self-parent: rejected -> {exc}")
    try:
        Person("Time Traveller", date(2000, 1, 1), date(1999, 1, 1))
    except FamilyTreeError as exc:
        print(f"  death before birth: rejected -> {exc}")

    with tempfile.TemporaryDirectory(prefix="family-tree-demo-") as tmp:
        path = Path(tmp) / "family.json"
        tree.save(path)
        loaded = FamilyTree.load(path)
        same = loaded.render() == tree.render()
        print(f"\nSaved and reloaded {len(loaded)} people from JSON "
              f"({path.stat().st_size} bytes); tree matches: {same}")
        print(f"  Ancestors of Sophie after reload: {len(loaded.ancestors(loaded.find('Sophie Foster')))}")

    print("\nDemo complete.")
    return 0


def _prompt(text: str) -> str:
    try:
        return input(text).strip()
    except EOFError:
        return ""


def run_interactive(tree: FamilyTree) -> int:
    """Menu for building and querying a family tree."""
    print("Family Tree Creator. People are addressed by #id or unique name.")
    while True:
        try:
            choice = input(
                "\n[1] tree [2] list [3] add person [4] link parent [5] link spouse "
                "[6] ancestors [7] descendants [8] save [9] load [q] quit > "
            ).strip().lower()
        except EOFError:
            print()
            return 0
        if choice in {"q", "quit", "0"}:
            return 0
        try:
            if choice == "1":
                print(tree.render())
            elif choice == "2":
                print(tree.people_table())
            elif choice == "3":
                name = _prompt("Full name: ")
                birth = _prompt("Birth date (YYYY-MM-DD): ")
                death = _prompt("Death date (blank if living): ") or None
                notes = _prompt("Notes (optional): ")
                person = tree.add_person(name, birth, death, notes)
                print(f"Added #{person.person_id} {person.display()}.")
            elif choice == "4":
                parent = tree.find(_prompt("Parent (#id or name): "))
                child = tree.find(_prompt("Child (#id or name): "))
                tree.add_parent(parent, child)
                print(f"{parent.name} is now a parent of {child.name}.")
            elif choice == "5":
                first = tree.find(_prompt("First spouse: "))
                second = tree.find(_prompt("Second spouse: "))
                tree.add_spouse(first, second)
                print(f"{first.name} and {second.name} are now spouses.")
            elif choice == "6":
                person = tree.find(_prompt("Person: "))
                print("\n".join(item.display() for item in tree.ancestors(person)) or "  (none)")
            elif choice == "7":
                person = tree.find(_prompt("Person: "))
                print("\n".join(item.display() for item in tree.descendants(person)) or "  (none)")
            elif choice == "8":
                path = Path(_prompt("Save to [family.json]: ") or "family.json")
                tree.save(path)
                print(f"Saved {len(tree)} people to {path}.")
            elif choice == "9":
                path = Path(_prompt("Load from [family.json]: ") or "family.json")
                tree = FamilyTree.load(path)
                print(f"Loaded {len(tree)} people.")
            else:
                print("  1 tree, 2 list, 3 add, 4 parent, 5 spouse, 6 ancestors, "
                      "7 descendants, 8 save, 9 load, q quit")
        except (FamilyTreeError, ValueError) as exc:
            print(f"Error: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a family tree, link relatives and print an ASCII tree.",
        epilog="With no options an interactive editor is shown.",
    )
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    parser.add_argument("--data", type=Path, metavar="FILE", help="load a family from JSON")
    parser.add_argument("--tree", action="store_true", help="print the whole tree")
    parser.add_argument("--root", metavar="PERSON", help="with --tree, start from this person")
    parser.add_argument("--list", action="store_true", help="list people in a table")
    parser.add_argument("--ancestors", metavar="PERSON", help="list all ancestors")
    parser.add_argument("--descendants", metavar="PERSON", help="list all descendants")
    parser.add_argument("--save", type=Path, metavar="FILE", help="save the family to JSON")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()

    try:
        tree = FamilyTree.load(args.data) if args.data else build_sample_tree()
    except FamilyTreeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        if args.list:
            print(tree.people_table())
        if args.tree or args.root:
            root = tree.find(args.root) if args.root else None
            print(tree.render(root))
        if args.ancestors:
            person = tree.find(args.ancestors)
            print(f"Ancestors of {person.name} ({len(tree.ancestors(person))}):")
            print("\n".join(f"  {item.display()}" for item in tree.ancestors(person)) or "  (none)")
        if args.descendants:
            person = tree.find(args.descendants)
            print(f"Descendants of {person.name} ({len(tree.descendants(person))}):")
            print("\n".join(f"  {item.display()}" for item in tree.descendants(person)) or "  (none)")
        if args.save:
            tree.save(args.save)
            print(f"Saved {len(tree)} people to {args.save}.")
        if not any([args.list, args.tree, args.root, args.ancestors, args.descendants, args.save]):
            return run_interactive(tree)
    except FamilyTreeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
