# Flower Shop Ordering To Go

## Problem

Create a flower shop application which deals in flower objects and uses those
flower objects in a bouquet object which can then be sold. Keep track of the
number of objects and when you may need to order more.

This is the **Classes / Flower Shop Ordering To Go** project: object
composition (`Flower` → `Bouquet` → `FlowerShop`), stock control, order
fulfilment and simple business reporting.

Project location: `Classes/Flower-Shop-Ordering-To-Go/` (`README.md` and
`solution.py`).

## Features

- `Flower` tracks per-stem wholesale price, stock, reorder threshold and
  supplier. `take()` never allows negative stock; `restock()` returns cost;
  `needs_reorder` flips at the threshold and `reorder_quantity()` suggests an
  order size.
- `Bouquet` composes flowers with quantities, enforces a positive markup and
  wrap cost, and computes wholesale cost, retail price, margin, stem count and
  how many complete bouquets current stock supports.
- `FlowerShop` manages the flower catalog and bouquet menu, places orders while
  reserving stock atomically, fulfils or cancels orders (cancelling restores
  stock), reports low stock, reorders every low variety and produces a sales
  report.
- Stock is checked before any stems are removed, so a failed order never
  leaves a partially reserved bouquet.
- JSON persistence includes flowers, bouquet recipes, orders and the next
  order number; loading reconstructs the same live object graph.
- Demo drives a full day: catalog, two orders, a rejected oversized order,
  fulfilment, cancellation, reorder and save/reload.

## Requirements

Python 3.10+. Standard library only (`dataclasses`, `json`, `argparse`).

## Usage

```bash
python3 solution.py --demo
python3 solution.py --catalog
python3 solution.py --order "Romance" --quantity 2 --customer "Emma"
python3 solution.py --order "Spring Morning" --quantity 1 --fulfill ORD-1001
python3 solution.py --restock --report
python3 solution.py --data shop.json --order "Golden Hour" --quantity 1 --save shop.json
```

Options:

| Option | Meaning |
| --- | --- |
| `--demo` | Scripted shop day; no input or files needed. |
| `--data FILE` | Load a saved shop instead of the built-in sample catalog. |
| `--catalog` | Show the flower stock table and bouquet menu. |
| `--order BOUQUET` | Place an order for the named bouquet. |
| `--quantity N` | Number of bouquets (default 1). |
| `--customer NAME` | Customer name (default `Walk-in`). |
| `--fulfill ORDER_ID` | Mark a pending order fulfilled. |
| `--cancel ORDER_ID` | Cancel a pending order and restore its stems. |
| `--restock` | Reorder every flower at or below its threshold. |
| `--report` | Print the sales report. |
| `--save FILE` | Save the shop after the actions. |

With no options an interactive counter is shown (`1` catalog, `2` bouquets,
`3` order, `4` fulfil, `5` cancel, `6` restock, `7` report, `8` save, `9` load,
`q` quit).

## Example Output

```text
=== Flower Shop Ordering To Go: demo ===

Petal & Stem: 6 flower varieties, 3 bouquet recipes

Flower catalog:
Flower             Price  Stock Reorder at  Status
--------------------------------------------------
Baby's Breath      $0.60    100         25  ok
Eucalyptus         $0.80     60         20  ok
Lily               $3.40     40         15  ok
Rose               $2.50    120         30  ok
Sunflower          $2.10     15         20  REORDER
Tulip              $1.20     80         20  ok

Bouquet menu:
Bouquet            Stems      Cost    Retail Available
------------------------------------------------------
Golden Hour           11    $15.30    $26.22         3
Romance               19    $35.00    $63.00        10
Spring Morning        16    $22.80    $39.48        10

Order ORD-1001: Emma bought 2 x Romance for $126.00 (pending)
  Roses left: 96
Order ORD-1002: Noah bought 2 x Golden Hour for $52.44 (pending)
  Sunflowers left: 5

Trying to order 5 more Golden Hour:
  rejected -> cannot make 5 x Golden Hour: only 1 available; Sunflower stock is 5 (needs 5 per bouquet)

ORD-1001 fulfilled; ORD-1002 cancelled and stock restored.
  Sunflowers after cancellation: 15

Low stock (1):
  Sunflower: 15 left, reorder point 20, suggest ordering 45

Reordering:
  + 45 Sunflower      cost   $94.50 -> stock 60
  Inventory value now $696.00

Sales report:
Orders: 2 (1 fulfilled, 0 pending, 1 cancelled)
Revenue: $126.00 from 2 bouquet(s)
Pending value: $0.00
Best seller: Romance (2 bouquet(s))
Inventory at wholesale: $696.00

Saved and reloaded 6 flowers, 3 bouquets, 2 orders (2430 bytes).
  Rose stock preserved: 96
  Next order id: ORD-1003

Demo complete.
```

## Implementation Notes

- `Bouquet._items` maps lower-cased flower names to `(Flower, quantity)` so
  adding the same flower twice merges lines instead of duplicating ingredients.
- `max_bouquets()` is `min(stock // per_bouquet)` over every component; the
  same calculation in `limiting_flower()` identifies which flower caps
  availability. `create_order()` checks this number *before* calling
  `take()` on any flower.
- Orders reserve stock at placement (status `pending`), so two customers
  cannot both buy the last bouquet. `fulfill()` only changes status;
  `cancel()` also returns stems to stock. Only pending orders can transition.
- Retail price is `round(wholesale_cost * markup + wrap_cost, 2)`, with markup
  and wrap configurable per bouquet. Revenue counts fulfilled orders only.
- Reorder target is `max(threshold * 3, threshold + 5)`, i.e. a low variety is
  topped up to three times its reorder point.
- JSON shape: `{name, next_order, flowers[], bouquets[], orders[]}`; bouquet
  items reference flowers by name. Loading validates references and duplicate
  catalog names.
- Money is stored as floats and rounded at the boundaries; this is adequate
  for a demo but a production shop would use integer cents or `Decimal`.
