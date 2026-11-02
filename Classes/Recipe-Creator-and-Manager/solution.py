#!/usr/bin/env python3
"""Recipe Creator and Manager.

An object-oriented recipe box: recipes hold ingredients and ordered steps,
belong to a category, can be rescaled to a different number of servings and
combined into an aggregated shopping list.  Everything can be persisted to
JSON.

Run ``python3 solution.py --demo`` for a scripted tour.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

# Canonical unit -> (base unit, multiplier).  Only compatible units are merged
# in shopping lists; unknown units are kept verbatim.
UNIT_BASE: dict[str, tuple[str, float]] = {
    "g": ("g", 1.0),
    "kg": ("g", 1000.0),
    "ml": ("ml", 1.0),
    "l": ("ml", 1000.0),
    "tsp": ("ml", 5.0),
    "tbsp": ("ml", 15.0),
    "cup": ("ml", 240.0),
}

UNIT_ALIASES: dict[str, str] = {
    "g": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "ml": "ml", "millilitre": "ml", "millilitres": "ml",
    "milliliter": "ml", "milliliters": "ml",
    "l": "l", "litre": "l", "litres": "l", "liter": "l", "liters": "l",
    "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "tbsp": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    "cup": "cup", "cups": "cup",
    "clove": "clove", "cloves": "clove",
    "piece": "piece", "pieces": "piece",
    "pinch": "pinch", "pinches": "pinch",
    "slice": "slice", "slices": "slice",
    "sprig": "sprig", "sprigs": "sprig",
    "can": "can", "cans": "can",
}


class RecipeError(Exception):
    """Raised for invalid recipes or lookups."""


def canonical_unit(unit: str) -> str:
    """Normalise a unit name, keeping unknown units lower-cased."""
    cleaned = unit.strip().lower()
    return UNIT_ALIASES.get(cleaned, cleaned)


def format_number(value: float) -> str:
    """Format a quantity without trailing zeros."""
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value))}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


COUNT_UNITS = {"piece", "clove", "pinch", "slice", "sprig", "can"}


def unit_label(quantity: float, unit: str) -> str:
    """Return a display label, pluralising countable units."""
    if unit == "piece":
        return ""
    if unit in COUNT_UNITS:
        return unit if abs(quantity - 1) < 1e-9 else unit + "s"
    return unit


def format_amount(quantity: float, unit: str) -> str:
    """Format a quantity in the friendliest compatible unit."""
    if unit == "g" and quantity >= 1000:
        return f"{format_number(quantity / 1000)} kg"
    if unit == "ml" and quantity >= 1000:
        return f"{format_number(quantity / 1000)} l"
    return f"{format_number(quantity)} {unit}".strip()


@dataclass
class Ingredient:
    """A single ingredient line in a recipe."""

    name: str
    quantity: float
    unit: str = "piece"

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        if not self.name:
            raise RecipeError("ingredient name cannot be empty")
        if self.quantity <= 0:
            raise RecipeError(f"quantity for {self.name!r} must be positive")
        self.unit = canonical_unit(self.unit or "piece")

    def scaled(self, factor: float) -> "Ingredient":
        """Return a copy with the quantity multiplied by *factor*."""
        return Ingredient(self.name, round(self.quantity * factor, 4), self.unit)

    def base_quantity(self) -> tuple[float, str]:
        """Return (quantity, base unit) for shopping-list aggregation."""
        base = UNIT_BASE.get(self.unit)
        if base is None:
            return self.quantity, self.unit
        base_unit, multiplier = base
        return self.quantity * multiplier, base_unit

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "quantity": self.quantity, "unit": self.unit}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Ingredient":
        if not isinstance(data, dict):
            raise RecipeError("each ingredient must be a JSON object")
        try:
            return cls(str(data["name"]), float(data["quantity"]),
                       str(data.get("unit", "piece")))
        except (KeyError, TypeError, ValueError) as exc:
            raise RecipeError(f"invalid ingredient entry: {exc}") from exc

    def __str__(self) -> str:
        if self.unit in UNIT_BASE:
            amount = format_amount(self.quantity, self.unit)
        else:
            label = unit_label(self.quantity, self.unit)
            amount = f"{format_number(self.quantity)} {label}".strip()
        return f"{amount} {self.name}".strip()


@dataclass
class Recipe:
    """A named recipe with a category, ingredient list and method steps."""

    name: str
    category: str
    servings: int = 4
    ingredients: list[Ingredient] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.category = self.category.strip().lower()
        if not self.name:
            raise RecipeError("recipe name cannot be empty")
        if not self.category:
            raise RecipeError("recipe category cannot be empty")
        if self.servings <= 0:
            raise RecipeError("servings must be a positive integer")

    # -- construction ---------------------------------------------------
    def add_ingredient(self, name: str, quantity: float, unit: str = "piece") -> "Recipe":
        self.ingredients.append(Ingredient(name, quantity, unit))
        return self

    def add_step(self, text: str) -> "Recipe":
        text = text.strip()
        if not text:
            raise RecipeError("a step cannot be empty")
        self.steps.append(text)
        return self

    # -- behaviour ------------------------------------------------------
    def scale(self, servings: int) -> "Recipe":
        """Return a new recipe rescaled to *servings* portions."""
        if servings <= 0:
            raise RecipeError("target servings must be positive")
        factor = servings / self.servings
        return Recipe(
            name=self.name,
            category=self.category,
            servings=servings,
            ingredients=[item.scaled(factor) for item in self.ingredients],
            steps=list(self.steps),
        )

    def uses_ingredient(self, term: str) -> bool:
        needle = term.strip().lower()
        return any(needle in item.name.lower() for item in self.ingredients)

    def matches(self, term: str) -> bool:
        """Match against name, category, ingredients or step text."""
        needle = term.strip().lower()
        if needle in self.name.lower() or needle in self.category:
            return True
        if any(needle in item.name.lower() for item in self.ingredients):
            return True
        return any(needle in step.lower() for step in self.steps)

    def summary(self) -> str:
        return (
            f"{self.name} [{self.category}] serves {self.servings}, "
            f"{len(self.ingredients)} ingredients, {len(self.steps)} steps"
        )

    def detail(self) -> str:
        lines = [self.name.upper(), "=" * len(self.name), f"Category: {self.category}",
                 f"Serves: {self.servings}", "", "Ingredients:"]
        lines.extend(f"  - {item}" for item in self.ingredients)
        lines.extend(["", "Method:"])
        lines.extend(f"  {index}. {step}" for index, step in enumerate(self.steps, 1))
        return "\n".join(lines)

    # -- persistence ----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "servings": self.servings,
            "ingredients": [item.to_dict() for item in self.ingredients],
            "steps": list(self.steps),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Recipe":
        if not isinstance(data, dict):
            raise RecipeError("each recipe must be a JSON object")
        raw_ingredients = data.get("ingredients", [])
        raw_steps = data.get("steps", [])
        if not isinstance(raw_ingredients, list) or not isinstance(raw_steps, list):
            raise RecipeError("ingredients and steps must be lists")
        if not all(isinstance(item, dict) for item in raw_ingredients):
            raise RecipeError("each ingredient must be a JSON object")
        try:
            return cls(
                name=str(data["name"]),
                category=str(data["category"]),
                servings=int(data.get("servings", 4)),
                ingredients=[Ingredient.from_dict(item) for item in raw_ingredients],
                steps=[str(step) for step in raw_steps],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RecipeError(f"invalid recipe entry: {exc}") from exc


class RecipeManager:
    """A collection of recipes with category/ingredient search and storage."""

    def __init__(self, recipes: Optional[Iterable[Recipe]] = None) -> None:
        self.recipes: list[Recipe] = []
        for recipe in recipes or []:
            self.add(recipe)

    def add(self, recipe: Recipe) -> None:
        if self.find(recipe.name) is not None:
            raise RecipeError(f"a recipe named {recipe.name!r} already exists")
        self.recipes.append(recipe)

    def remove(self, name: str) -> Recipe:
        recipe = self.find(name)
        if recipe is None:
            raise RecipeError(f"no recipe named {name!r}")
        self.recipes.remove(recipe)
        return recipe

    def find(self, name: str) -> Optional[Recipe]:
        needle = name.strip().lower()
        for recipe in self.recipes:
            if recipe.name.lower() == needle:
                return recipe
        return None

    def require(self, name: str) -> Recipe:
        recipe = self.find(name)
        if recipe is None:
            raise RecipeError(f"no recipe named {name!r}")
        return recipe

    def categories(self) -> dict[str, list[Recipe]]:
        grouped: dict[str, list[Recipe]] = defaultdict(list)
        for recipe in self.recipes:
            grouped[recipe.category].append(recipe)
        return {key: sorted(value, key=lambda item: item.name) for key, value in sorted(grouped.items())}

    def by_category(self, category: str) -> list[Recipe]:
        needle = category.strip().lower()
        return [recipe for recipe in self.recipes if recipe.category == needle]

    def by_ingredient(self, term: str) -> list[Recipe]:
        return [recipe for recipe in self.recipes if recipe.uses_ingredient(term)]

    def search(self, term: str) -> list[Recipe]:
        return [recipe for recipe in self.recipes if recipe.matches(term)]

    def shopping_list(self, selection: Iterable[tuple[Recipe, int]]) -> list[str]:
        """Aggregate ingredients for (recipe, servings) pairs.

        Compatible units are summed in their base unit and formatted back to
        kg/l where sensible.  The result is a sorted list of display lines.
        """
        totals: dict[tuple[str, str], float] = defaultdict(float)
        for recipe, servings in selection:
            scaled = recipe if servings == recipe.servings else recipe.scale(servings)
            for item in scaled.ingredients:
                quantity, base = item.base_quantity()
                totals[(item.name.lower(), base)] += quantity

        lines: list[str] = []
        for (name, unit), quantity in sorted(totals.items()):
            if unit in COUNT_UNITS:
                amount = f"{format_number(quantity)} {unit_label(quantity, unit)}".strip()
            else:
                amount = format_amount(quantity, unit)
            lines.append(f"  {amount:>10}  {name}")
        return lines

    # -- persistence ----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"recipes": [recipe.to_dict() for recipe in self.recipes]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecipeManager":
        if not isinstance(data, dict):
            raise RecipeError("recipe file must contain a JSON object")
        raw = data.get("recipes")
        if not isinstance(raw, list):
            raise RecipeError("recipe file must contain a 'recipes' list")
        if not all(isinstance(item, dict) for item in raw):
            raise RecipeError("each recipe must be a JSON object")
        return cls(Recipe.from_dict(item) for item in raw)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "RecipeManager":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RecipeError(f"recipe file not found: {path}") from exc
        except OSError as exc:
            raise RecipeError(f"cannot read recipe file {path}: {exc}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RecipeError(f"invalid JSON in {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise RecipeError("recipe file must contain a JSON object")
        return cls.from_dict(data)


def build_sample_manager() -> RecipeManager:
    """Create a deterministic sample recipe box used by the demo."""
    manager = RecipeManager()

    lemon = Recipe("Lemon Tart", "dessert", 8)
    lemon.add_ingredient("plain flour", 200, "g")
    lemon.add_ingredient("butter", 100, "g")
    lemon.add_ingredient("caster sugar", 150, "g")
    lemon.add_ingredient("eggs", 3, "piece")
    lemon.add_ingredient("lemons", 4, "piece")
    lemon.add_ingredient("double cream", 200, "ml")
    lemon.add_step("Rub the flour and butter together into fine crumbs.")
    lemon.add_step("Add half the sugar and one egg; bring the dough together and chill for 30 minutes.")
    lemon.add_step("Line a tart tin, bake blind at 180 C for 15 minutes, then remove the weights.")
    lemon.add_step("Whisk the remaining eggs, sugar, lemon zest, juice and cream; pour into the case.")
    lemon.add_step("Bake at 150 C for 25 minutes until just set; cool before slicing.")
    manager.add(lemon)

    lava = Recipe("Chocolate Lava Cake", "dessert", 4)
    lava.add_ingredient("dark chocolate", 120, "g")
    lava.add_ingredient("butter", 120, "g")
    lava.add_ingredient("eggs", 2, "piece")
    lava.add_ingredient("caster sugar", 60, "g")
    lava.add_ingredient("plain flour", 40, "g")
    lava.add_step("Melt the chocolate and butter over a gentle heat.")
    lava.add_step("Whisk the eggs and sugar until pale, then fold in the chocolate.")
    lava.add_step("Fold in the flour and divide between four buttered ramekins.")
    lava.add_step("Bake at 200 C for 9 minutes; the centres should still wobble.")
    manager.add(lava)

    chicken = Recipe("Roast Chicken with Herbs", "main course", 4)
    chicken.add_ingredient("whole chicken", 1.8, "kg")
    chicken.add_ingredient("butter", 50, "g")
    chicken.add_ingredient("thyme", 4, "sprig")
    chicken.add_ingredient("lemons", 1, "piece")
    chicken.add_ingredient("garlic", 3, "clove")
    chicken.add_ingredient("potatoes", 800, "g")
    chicken.add_step("Heat the oven to 200 C and season the chicken inside and out.")
    chicken.add_step("Rub with butter, tuck in thyme, lemon halves and garlic.")
    chicken.add_step("Roast for 20 minutes, then add the potatoes and roast 45 minutes more.")
    chicken.add_step("Rest for 15 minutes before carving; serve with the pan juices.")
    manager.add(chicken)

    risotto = Recipe("Mushroom Risotto", "main course", 4)
    risotto.add_ingredient("arborio rice", 300, "g")
    risotto.add_ingredient("mushrooms", 400, "g")
    risotto.add_ingredient("onion", 1, "piece")
    risotto.add_ingredient("white wine", 150, "ml")
    risotto.add_ingredient("vegetable stock", 1, "l")
    risotto.add_ingredient("parmesan", 60, "g")
    risotto.add_ingredient("butter", 40, "g")
    risotto.add_step("Soften the onion in half the butter, then add the mushrooms.")
    risotto.add_step("Stir in the rice and toast for a minute; pour in the wine.")
    risotto.add_step("Add the stock a ladle at a time, stirring until absorbed.")
    risotto.add_step("Beat in the remaining butter and parmesan; rest for two minutes.")
    manager.add(risotto)

    noodle = Recipe("Chicken Noodle Soup", "soup", 6)
    noodle.add_ingredient("chicken thighs", 600, "g")
    noodle.add_ingredient("egg noodles", 200, "g")
    noodle.add_ingredient("carrots", 3, "piece")
    noodle.add_ingredient("celery", 3, "piece")
    noodle.add_ingredient("onion", 1, "piece")
    noodle.add_ingredient("chicken stock", 2, "l")
    noodle.add_ingredient("parsley", 20, "g")
    noodle.add_step("Sweat the diced onion, carrot and celery in a large pot.")
    noodle.add_step("Add the stock and chicken; simmer gently for 25 minutes.")
    noodle.add_step("Lift out the chicken, shred it and return it to the pot.")
    noodle.add_step("Add the noodles and cook for four minutes; finish with parsley.")
    manager.add(noodle)

    tomato = Recipe("Tomato Basil Soup", "soup", 4)
    tomato.add_ingredient("tomatoes", 1, "kg")
    tomato.add_ingredient("onion", 1, "piece")
    tomato.add_ingredient("garlic", 2, "clove")
    tomato.add_ingredient("vegetable stock", 500, "ml")
    tomato.add_ingredient("basil", 20, "g")
    tomato.add_ingredient("olive oil", 2, "tbsp")
    tomato.add_step("Roast the halved tomatoes, onion and garlic with olive oil at 200 C for 30 minutes.")
    tomato.add_step("Blend with the stock until smooth, then simmer for 10 minutes.")
    tomato.add_step("Stir through torn basil and season to taste.")
    manager.add(tomato)

    return manager


def print_catalog(manager: RecipeManager) -> None:
    print(f"{'Recipe':<30} {'Category':<14} {'Serves':>6} {'Ingred.':>8}")
    print("-" * 62)
    for recipe in sorted(manager.recipes, key=lambda item: (item.category, item.name)):
        print(f"{recipe.name:<30} {recipe.category:<14} {recipe.servings:>6} {len(recipe.ingredients):>8}")


def run_demo() -> int:
    """Scripted end-to-end tour; no input, network or external files needed."""
    print("=== Recipe Creator and Manager: demo ===\n")
    manager = build_sample_manager()

    print(f"Recipe box contains {len(manager.recipes)} recipes.\n")
    print_catalog(manager)

    print("\nCategories:")
    for category, recipes in manager.categories().items():
        print(f"  {category} ({len(recipes)}): " + ", ".join(item.name for item in recipes))

    print("\nRecipes using chicken:")
    for recipe in manager.by_ingredient("chicken"):
        print(f"  - {recipe.summary()}")

    print("\nSearch for 'lemon':")
    for recipe in manager.search("lemon"):
        print(f"  - {recipe.summary()}")

    chicken = manager.require("Roast Chicken with Herbs")
    print(f"\nScaled recipe: {chicken.name} from {chicken.servings} to 6 servings")
    scaled = chicken.scale(6)
    for item in scaled.ingredients:
        print(f"  {item}")

    print("\nShopping list for dinner (chicken for 6, lemon tart for 8):")
    tart = manager.require("Lemon Tart")
    for line in manager.shopping_list([(chicken, 6), (tart, tart.servings)]):
        print(line)

    with tempfile.TemporaryDirectory(prefix="recipe-demo-") as tmp:
        path = Path(tmp) / "recipes.json"
        manager.save(path)
        reloaded = RecipeManager.load(path)
        print(f"\nSaved and reloaded {len(reloaded.recipes)} recipes from JSON "
              f"({path.stat().st_size} bytes).")
        assert len(reloaded.recipes) == len(manager.recipes)
        assert reloaded.require("Lemon Tart").ingredients[0].name == "plain flour"

    print("\nValidation checks:")
    for label, action in [
        ("zero servings", lambda: Recipe("Bad", "dessert", 0)),
        ("empty ingredient", lambda: Recipe("Bad", "soup").add_ingredient("", 1, "g")),
        ("duplicate recipe", lambda: manager.add(Recipe("Lemon Tart", "dessert", 4))),
        ("unknown recipe", lambda: manager.require("Sushi")),
    ]:
        try:
            action()
        except RecipeError as exc:
            print(f"  {label}: rejected -> {exc}")

    print("\nDemo complete.")
    return 0


def _prompt(text: str) -> str:
    try:
        return input(text)
    except EOFError:
        raise


def interactive(manager: RecipeManager) -> int:
    """Small menu-driven recipe box."""
    print("Recipe Creator and Manager (type 'h' for help)")
    while True:
        try:
            choice = input(
                "\n[1] list [2] view [3] category [4] ingredient [5] scale "
                "[6] shopping list [7] add [8] save [9] load [q] quit > "
            ).strip().lower()
        except EOFError:
            print()
            return 0
        if choice in {"q", "quit", "0"}:
            return 0
        try:
            if choice == "1":
                print_catalog(manager)
            elif choice == "2":
                print(manager.require(_prompt("Recipe name: ")).detail())
            elif choice == "3":
                category = _prompt("Category: ")
                matches = manager.by_category(category)
                print("\n".join(f"  {item.name}" for item in matches) or "  (none)")
            elif choice == "4":
                term = _prompt("Ingredient: ")
                matches = manager.by_ingredient(term)
                print("\n".join(f"  {item.summary()}" for item in matches) or "  (none)")
            elif choice == "5":
                recipe = manager.require(_prompt("Recipe name: "))
                servings = int(_prompt(f"New serving count (currently {recipe.servings}): "))
                print(recipe.scale(servings).detail())
            elif choice == "6":
                names = _prompt("Recipe names, comma separated: ").split(",")
                selection = [(manager.require(name.strip()), manager.require(name.strip()).servings)
                             for name in names if name.strip()]
                print("\nShopping list:")
                print("\n".join(manager.shopping_list(selection)) or "  (nothing)")
            elif choice == "7":
                recipe = Recipe(_prompt("Name: "), _prompt("Category: "),
                                int(_prompt("Servings: ") or "4"))
                while True:
                    line = _prompt("Ingredient (name, qty, unit; blank to finish): ")
                    if not line:
                        break
                    name, quantity, unit = line.split(",", 2)
                    recipe.add_ingredient(name.strip(), float(quantity), unit.strip())
                while True:
                    step = _prompt("Step (blank to finish): ")
                    if not step:
                        break
                    recipe.add_step(step)
                manager.add(recipe)
                print(f"Added {recipe.name}.")
            elif choice == "8":
                path = Path(_prompt("Save to [recipes.json]: ") or "recipes.json")
                manager.save(path)
                print(f"Saved {len(manager.recipes)} recipes to {path}.")
            elif choice == "9":
                path = Path(_prompt("Load from [recipes.json]: ") or "recipes.json")
                manager = RecipeManager.load(path)
                print(f"Loaded {len(manager.recipes)} recipes.")
            else:
                print("  1 list, 2 view, 3 category, 4 ingredient, 5 scale, 6 shopping list, "
                      "7 add, 8 save, 9 load, q quit")
        except EOFError:
            print()
            return 0
        except (RecipeError, ValueError) as exc:
            print(f"Error: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, browse, scale and shop for recipes organised by category.",
        epilog="With no options an interactive menu is shown.",
    )
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    parser.add_argument("--data", type=Path, metavar="FILE", help="load recipes from a JSON file")
    parser.add_argument("--empty", action="store_true",
                        help="start with an empty recipe box instead of the samples")
    parser.add_argument("--list", action="store_true", help="list every recipe")
    parser.add_argument("--category", metavar="NAME", help="list recipes in a category")
    parser.add_argument("--ingredient", metavar="NAME", help="find recipes using an ingredient")
    parser.add_argument("--recipe", metavar="NAME", help="show one recipe")
    parser.add_argument("--scale", type=int, metavar="SERVINGS",
                        help="with --recipe, rescale to this many servings")
    parser.add_argument("--menu", nargs="+", metavar="RECIPE",
                        help="build a shopping list for the named recipes")
    parser.add_argument("--save", type=Path, metavar="FILE",
                        help="save the loaded recipe box to JSON")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()

    manager = RecipeManager()
    if args.data:
        try:
            manager = RecipeManager.load(args.data)
        except RecipeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    elif not args.empty:
        manager = build_sample_manager()

    try:
        if args.list or args.category or args.ingredient or args.recipe or args.menu:
            if args.list:
                print_catalog(manager)
            if args.category:
                matches = manager.by_category(args.category)
                print(f"{len(matches)} recipe(s) in {args.category!r}:")
                print("\n".join(f"  {item.name}" for item in matches) or "  (none)")
            if args.ingredient:
                matches = manager.by_ingredient(args.ingredient)
                print(f"{len(matches)} recipe(s) using {args.ingredient!r}:")
                print("\n".join(f"  {item.summary()}" for item in matches) or "  (none)")
            if args.recipe:
                recipe = manager.require(args.recipe)
                if args.scale:
                    recipe = recipe.scale(args.scale)
                print(recipe.detail())
            if args.menu:
                selection = []
                for name in args.menu:
                    recipe = manager.require(name)
                    selection.append((recipe, recipe.servings))
                print("Shopping list:")
                print("\n".join(manager.shopping_list(selection)))
        elif not args.save:
            return interactive(manager)

        if args.save:
            manager.save(args.save)
            print(f"Saved {len(manager.recipes)} recipes to {args.save}.")
    except (RecipeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
