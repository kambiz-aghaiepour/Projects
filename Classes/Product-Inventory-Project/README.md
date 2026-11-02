# Product Inventory Project

**Category:** Classes · **Project:** `Classes/Product-Inventory-Project`

## Problem

Create an application which manages an inventory of products. Create a product
class which has a price, id, and quantity on hand. Then create an inventory
class which keeps track of various products and can sum up the inventory value.

## Features

- `Product` dataclass with validated id, name, unit price and quantity.
- `Inventory` keeps products keyed by id and supports:
  - add (with duplicate-id detection) and remove products
  - restock and sell stock with insufficient-stock errors
  - low-stock queries at a configurable threshold
  - total unit count and total inventory value
- Fixed-width table rendering shared by the demo and interactive menu.
- Interactive console for day-to-day inventory work.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py
python3 solution.py --low-stock-threshold 10
```

- `--demo` runs a scripted, non-interactive tour of the API and exits 0.
- `--low-stock-threshold N` sets the threshold used by the interactive
  low-stock report (default 5).
- With no arguments the program starts an interactive menu: list, add,
  restock, sell, remove, low stock, total value, quit.

## Example Output

```
== Product Inventory Demo ==
Loaded 5 products, 46 units.

ID       NAME                         PRICE   QTY       VALUE
-------------------------------------------------------------
P-1001   Mechanical Keyboard      $   89.99    12 $  1,079.88
P-1002   USB-C Hub                $   34.50     4 $    138.00
P-1003   27-inch Monitor          $  219.00     7 $  1,533.00
P-1004   Ergonomic Mouse          $   49.95     3 $    149.85
P-1005   Laptop Stand             $   29.00    20 $    580.00

Total inventory value: $3,480.73

Sold 2 x USB-C Hub for $69.00.
Restocked 5 x 27-inch Monitor.
Discontinued P-1005 (Laptop Stand).

-- Low stock (<= 5 units) --
  P-1002: USB-C Hub (2 left)
  P-1004: Ergonomic Mouse (3 left)
```

## Implementation Notes

`Product` is a dataclass whose `__post_init__` normalises the id and rejects
blank names, negative prices and non-integer or negative quantities. `value`
is price × quantity rounded to cents.

`Inventory` stores products in insertion order in a dict, so lookup, add,
restock and sell are O(1); `total_value`, `low_stock` and table rendering are
O(n). Duplicate ids are rejected unless `add_product(..., merge=True)` is used,
which adds the incoming quantity to the existing product.

Money is represented as `float` because this project only reports aggregate
values; a production ledger would use `Decimal` (as the Bank Account Manager
does). The CLI catches domain exceptions and turns them into readable messages
rather than tracebacks.
