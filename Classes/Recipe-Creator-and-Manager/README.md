# Recipe Creator and Manager

## Problem

Create a recipe class with ingredients and put them in a recipe manager
program that organizes them into categories like desserts, main courses or by
ingredients like chicken, beef, soups, pies etc.

This is the **Classes / Recipe Creator and Manager** project: an exercise in
object-oriented modelling (composition, value objects, a manager collection)
with JSON persistence and a small interactive CLI.

Project location: `Classes/Recipe-Creator-and-Manager/` (`README.md` and
`solution.py`).

## Features

- `Ingredient` value object with name, quantity and unit; validates positive
  quantities and canonicalises unit aliases (`grams`, `tbsp`, `cups`, ...).
- `Recipe` holds a category, serving count, ingredient list and ordered steps.
  Recipes can be rescaled to any serving count without mutating the original.
- `RecipeManager` supports add/remove/lookup, category grouping, ingredient
  search, free-text search (name, category, ingredients and method) and
  aggregated shopping lists for a menu.
- Shopping lists merge compatible units (g/kg, ml/l, tsp/tbsp/cup) and convert
  back to friendly units (`1.2 kg`, not `1200 g`).
- JSON save/load with clear validation errors for malformed files.
- Six sample recipes (two desserts, two mains, two soups) for the demo.
- Interactive menu when run without arguments; scriptable flags otherwise.

## Requirements

Python 3.10+. Standard library only.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --list
python3 solution.py --category soup
python3 solution.py --ingredient chicken
python3 solution.py --recipe "Lemon Tart" --scale 12
python3 solution.py --menu "Roast Chicken with Herbs" "Lemon Tart"
python3 solution.py --save my_recipes.json
python3 solution.py --data my_recipes.json --category soup
```

Options:

| Option | Meaning |
| --- | --- |
| `--demo` | Scripted tour of every feature; no input or files required. |
| `--data FILE` | Load a recipe box from JSON before doing anything else. |
| `--empty` | Start with an empty box instead of the six built-in sample recipes. |
| `--list` | Print the recipe catalog. |
| `--category NAME` | List recipes in a category (`dessert`, `main course`, `soup`, ...). |
| `--ingredient NAME` | Find recipes containing an ingredient (substring match). |
| `--recipe NAME` | Show ingredients and method; combine with `--scale`. |
| `--scale SERVINGS` | Rescale the `--recipe` output to this serving count. |
| `--menu RECIPE...` | Build a combined shopping list for the named recipes. |
| `--save FILE` | Save the loaded (or demo) recipe box after the action. |

With no options an interactive menu is shown (`1` list, `2` view, `3` category,
`4` ingredient, `5` scale, `6` shopping list, `7` add, `8` save, `9` load,
`q` quit).

## Example Output

```text
=== Recipe Creator and Manager: demo ===

Recipe box contains 6 recipes.

Recipe                         Category       Serves  Ingred.
--------------------------------------------------------------
Chocolate Lava Cake            dessert             4        5
Lemon Tart                     dessert             8        6
Mushroom Risotto               main course         4        7
Roast Chicken with Herbs       main course         4        6
Chicken Noodle Soup            soup                6        7
Tomato Basil Soup              soup                4        6

Categories:
  dessert (2): Chocolate Lava Cake, Lemon Tart
  main course (2): Mushroom Risotto, Roast Chicken with Herbs
  soup (2): Chicken Noodle Soup, Tomato Basil Soup

Recipes using chicken:
  - Roast Chicken with Herbs [main course] serves 4, 6 ingredients, 4 steps
  - Chicken Noodle Soup [soup] serves 6, 7 ingredients, 4 steps

Scaled recipe: Roast Chicken with Herbs from 4 to 6 servings
  2.7 kg whole chicken
  75 g butter
  6 sprigs thyme
  1.5 lemons
  4.5 cloves garlic
  1.2 kg potatoes

Shopping list for dinner (chicken for 6, lemon tart for 8):
       175 g  butter
       150 g  caster sugar
      200 ml  double cream
           3  eggs
  4.5 cloves  garlic
         5.5  lemons
       200 g  plain flour
      1.2 kg  potatoes
    6 sprigs  thyme
      2.7 kg  whole chicken

Saved and reloaded 6 recipes from JSON (6470 bytes).

Validation checks:
  zero servings: rejected -> servings must be a positive integer
  empty ingredient: rejected -> ingredient name cannot be empty
  duplicate recipe: rejected -> a recipe named 'Lemon Tart' already exists
  unknown recipe: rejected -> no recipe named 'Sushi'

Demo complete.
```

## Implementation Notes

- `Recipe.scale()` multiplies every ingredient quantity and returns a **new**
  recipe, so the original stays intact; steps are copied by value.
- Shopping-list aggregation converts known units to a base unit (`g` for mass,
  `ml` for volume) before summing, then formats back to kg/l when the total is
  large. Unknown units are summed only with the identical unit.
- Ingredient quantities are floats, so `1.5 lemons` or `4.5 cloves` can appear
  when scaling indivisible ingredients; the program reports exactly what the
  arithmetic produces rather than silently rounding.
- Storage format: `{"recipes": [{"name", "category", "servings",
  "ingredients": [{"name", "quantity", "unit"}], "steps": [...]}]}`.
- Lookups are case-insensitive linear scans; with a handful of recipes this is
  simpler than maintaining secondary indexes. Adding a duplicate name is
  rejected.
- Invalid JSON, missing files, non-positive quantities/servings and unknown
  recipe names produce a clear `RecipeError` message and exit code 1.
