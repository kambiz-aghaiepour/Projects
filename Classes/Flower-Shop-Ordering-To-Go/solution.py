#!/usr/bin/env python3
"""Flower Shop Ordering To Go.

Models a small florist: ``Flower`` objects track per-stem price and stock,
``Bouquet`` recipes consume those flowers, and ``FlowerShop`` takes orders,
fulfils or cancels them, flags low stock and suggests reorders.  The whole
shop can be saved to and loaded from JSON.

Run ``python3 solution.py --demo`` for a scripted day at the shop.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


class ShopError(Exception):
    """Base error for invalid shop operations."""


class StockError(ShopError):
    """Raised when there are not enough stems to satisfy an order."""


def money(value: float) -> str:
    """Format a currency amount."""
    return f"${value:,.2f}"


@dataclass
class Flower:
    """A flower variety sold by the stem."""

    name: str
    price: float
    stock: int
    reorder_threshold: int = 10
    supplier: str = ""

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        if not self.name:
            raise ShopError("flower name cannot be empty")
        if self.price <= 0:
            raise ShopError(f"price for {self.name!r} must be positive")
        if self.stock < 0:
            raise ShopError(f"stock for {self.name!r} cannot be negative")
        if self.reorder_threshold < 0:
            raise ShopError("reorder threshold cannot be negative")

    @property
    def needs_reorder(self) -> bool:
        """True when stock has fallen to or below the reorder point."""
        return self.stock <= self.reorder_threshold

    @property
    def inventory_value(self) -> float:
        return self.price * self.stock

    def take(self, quantity: int) -> None:
        """Remove stems from stock, refusing to go negative."""
        if quantity <= 0:
            raise ShopError("quantity to take must be positive")
        if quantity > self.stock:
            raise StockError(
                f"only {self.stock} {self.name} stem(s) in stock, requested {quantity}"
            )
        self.stock -= quantity

    def restock(self, quantity: int) -> float:
        """Add stems and return the wholesale cost."""
        if quantity <= 0:
            raise ShopError("restock quantity must be positive")
        self.stock += quantity
        return round(quantity * self.price, 2)

    def reorder_quantity(self, target_multiple: int = 3) -> int:
        """Suggested order size to reach a comfortable stock level."""
        target = max(self.reorder_threshold * target_multiple, self.reorder_threshold + 5)
        return max(0, target - self.stock)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "price": self.price,
            "stock": self.stock,
            "reorder_threshold": self.reorder_threshold,
            "supplier": self.supplier,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Flower":
        if not isinstance(data, dict):
            raise ShopError("each flower must be a JSON object")
        try:
            return cls(
                name=str(data["name"]),
                price=float(data["price"]),
                stock=int(data["stock"]),
                reorder_threshold=int(data.get("reorder_threshold", 10)),
                supplier=str(data.get("supplier", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ShopError(f"invalid flower entry: {exc}") from exc


class Bouquet:
    """A recipe of stems sold as one arrangement.

    ``markup`` is applied to the wholesale stem cost and ``wrap_cost`` covers
    wrapping and labour, giving the retail price.
    """

    def __init__(self, name: str, description: str = "", markup: float = 1.6,
                 wrap_cost: float = 3.0) -> None:
        self.name = name.strip()
        self.description = description.strip()
        if not self.name:
            raise ShopError("bouquet name cannot be empty")
        if markup < 1:
            raise ShopError("markup must be at least 1.0")
        if wrap_cost < 0:
            raise ShopError("wrap cost cannot be negative")
        self.markup = markup
        self.wrap_cost = wrap_cost
        self._items: dict[str, tuple[Flower, int]] = {}

    @property
    def items(self) -> list[tuple[Flower, int]]:
        return list(self._items.values())

    @property
    def stems(self) -> int:
        return sum(quantity for _, quantity in self._items.values())

    def add(self, flower: Flower, quantity: int = 1) -> "Bouquet":
        """Add stems of *flower*, merging with an existing line."""
        if quantity <= 0:
            raise ShopError("bouquet quantity must be positive")
        key = flower.name.lower()
        if key in self._items:
            existing, count = self._items[key]
            self._items[key] = (existing, count + quantity)
        else:
            self._items[key] = (flower, quantity)
        return self

    def remove(self, flower_name: str, quantity: int = 1) -> None:
        key = flower_name.strip().lower()
        if key not in self._items:
            raise ShopError(f"{self.name} does not contain {flower_name!r}")
        flower, count = self._items[key]
        if quantity >= count:
            del self._items[key]
        else:
            self._items[key] = (flower, count - quantity)

    @property
    def cost(self) -> float:
        """Wholesale cost of one bouquet."""
        return round(sum(flower.price * quantity for flower, quantity in self._items.values()), 2)

    @property
    def price(self) -> float:
        """Retail price of one bouquet."""
        return round(self.cost * self.markup + self.wrap_cost, 2)

    @property
    def margin(self) -> float:
        return round(self.price - self.cost, 2)

    def max_bouquets(self) -> int:
        """How many complete bouquets current stock allows."""
        if not self._items:
            return 0
        return min(flower.stock // quantity for flower, quantity in self._items.values())

    def limiting_flower(self) -> tuple[Flower, int]:
        """Return the scarcest flower and how many stems are available."""
        if not self._items:
            raise ShopError(f"{self.name} has no flowers")
        flower, quantity = min(
            self._items.values(), key=lambda item: item[0].stock // item[1]
        )
        return flower, flower.stock

    def detail(self) -> str:
        lines = [f"{self.name} - {self.description or 'seasonal arrangement'}",
                 f"  {self.stems} stems, wholesale {money(self.cost)}, "
                 f"retail {money(self.price)} (margin {money(self.margin)})"]
        for flower, quantity in self._items.values():
            lines.append(f"    {quantity:>3} x {flower.name:<14} @ {money(flower.price)}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "markup": self.markup,
            "wrap_cost": self.wrap_cost,
            "items": [{"flower": flower.name, "quantity": quantity}
                      for flower, quantity in self._items.values()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], catalog: dict[str, Flower]) -> "Bouquet":
        if not isinstance(data, dict):
            raise ShopError("each bouquet must be a JSON object")
        try:
            bouquet = cls(
                name=str(data["name"]),
                description=str(data.get("description", "")),
                markup=float(data.get("markup", 1.6)),
                wrap_cost=float(data.get("wrap_cost", 3.0)),
            )
            items = data.get("items", [])
            if not isinstance(items, list):
                raise ShopError("bouquet items must be a list")
            for item in items:
                if not isinstance(item, dict):
                    raise ShopError("each bouquet item must be a JSON object")
                name = str(item["flower"])
                flower = catalog.get(name.lower())
                if flower is None:
                    raise ShopError(
                        f"bouquet {bouquet.name!r} references unknown flower {name!r}"
                    )
                bouquet.add(flower, int(item["quantity"]))
            return bouquet
        except (KeyError, TypeError, ValueError) as exc:
            raise ShopError(f"invalid bouquet entry: {exc}") from exc


@dataclass
class Order:
    """A customer order for a number of bouquets."""

    order_id: str
    customer: str
    bouquet: str
    quantity: int
    unit_price: float
    status: str = "pending"

    @property
    def total(self) -> float:
        return round(self.unit_price * self.quantity, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "customer": self.customer,
            "bouquet": self.bouquet,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Order":
        if not isinstance(data, dict):
            raise ShopError("each order must be a JSON object")
        try:
            return cls(
                order_id=str(data["order_id"]),
                customer=str(data["customer"]),
                bouquet=str(data["bouquet"]),
                quantity=int(data["quantity"]),
                unit_price=float(data["unit_price"]),
                status=str(data.get("status", "pending")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ShopError(f"invalid order entry: {exc}") from exc


class FlowerShop:
    """Catalog, bouquet menu, stock control and orders."""

    def __init__(self, name: str = "Flower Shop") -> None:
        self.name = name
        self.flowers: dict[str, Flower] = {}
        self.bouquets: dict[str, Bouquet] = {}
        self.orders: list[Order] = []
        self._next_order = 1001

    # -- catalog --------------------------------------------------------
    def add_flower(self, flower: Flower) -> None:
        key = flower.name.lower()
        if key in self.flowers:
            raise ShopError(f"{flower.name!r} is already in the catalog")
        self.flowers[key] = flower

    def flower(self, name: str) -> Flower:
        try:
            return self.flowers[name.strip().lower()]
        except KeyError as exc:
            raise ShopError(f"unknown flower {name!r}") from exc

    def add_bouquet(self, bouquet: Bouquet) -> None:
        key = bouquet.name.lower()
        if key in self.bouquets:
            raise ShopError(f"bouquet {bouquet.name!r} already exists")
        self.bouquets[key] = bouquet

    def bouquet(self, name: str) -> Bouquet:
        try:
            return self.bouquets[name.strip().lower()]
        except KeyError as exc:
            raise ShopError(f"unknown bouquet {name!r}") from exc

    @property
    def inventory_value(self) -> float:
        return round(sum(flower.inventory_value for flower in self.flowers.values()), 2)

    def low_stock(self) -> list[Flower]:
        return sorted(
            (flower for flower in self.flowers.values() if flower.needs_reorder),
            key=lambda item: (item.stock - item.reorder_threshold, item.name),
        )

    # -- ordering -------------------------------------------------------
    def create_order(self, bouquet_name: str, quantity: int, customer: str) -> Order:
        """Reserve stock and create a pending order."""
        if not isinstance(quantity, int) or quantity <= 0:
            raise ShopError("order quantity must be a positive integer")
        customer = customer.strip()
        if not customer:
            raise ShopError("customer name cannot be empty")
        bouquet = self.bouquet(bouquet_name)
        available = bouquet.max_bouquets()
        if available < quantity:
            flower, stems = bouquet.limiting_flower()
            per_bouquet = next(qty for item, qty in bouquet.items if item is flower)
            raise StockError(
                f"cannot make {quantity} x {bouquet.name}: only {available} available; "
                f"{flower.name} stock is {stems} (needs {per_bouquet} per bouquet)"
            )
        for flower, per_bouquet in bouquet.items:
            flower.take(per_bouquet * quantity)
        order = Order(f"ORD-{self._next_order}", customer, bouquet.name,
                      quantity, bouquet.price)
        self._next_order += 1
        self.orders.append(order)
        return order

    def _pending(self, order_id: str) -> Order:
        for order in self.orders:
            if order.order_id == order_id:
                if order.status != "pending":
                    raise ShopError(f"order {order_id} is {order.status}, not pending")
                return order
        raise ShopError(f"unknown order {order_id!r}")

    def fulfill(self, order_id: str) -> Order:
        order = self._pending(order_id)
        order.status = "fulfilled"
        return order

    def cancel(self, order_id: str) -> Order:
        """Cancel a pending order and return its stems to stock."""
        order = self._pending(order_id)
        bouquet = self.bouquet(order.bouquet)
        for flower, per_bouquet in bouquet.items:
            flower.restock(per_bouquet * order.quantity)
        order.status = "cancelled"
        return order

    # -- stock ----------------------------------------------------------
    def reorder_all(self) -> list[tuple[Flower, int, float]]:
        """Restock every low flower; return (flower, quantity, cost) rows."""
        results: list[tuple[Flower, int, float]] = []
        for flower in self.low_stock():
            quantity = flower.reorder_quantity()
            if quantity:
                results.append((flower, quantity, flower.restock(quantity)))
        return results

    # -- reporting ------------------------------------------------------
    def catalog_table(self) -> str:
        header = f"{'Flower':<16} {'Price':>7} {'Stock':>6} {'Reorder at':>10}  Status"
        lines = [header, "-" * len(header)]
        for flower in sorted(self.flowers.values(), key=lambda item: item.name):
            status = "REORDER" if flower.needs_reorder else "ok"
            lines.append(
                f"{flower.name:<16} {money(flower.price):>7} {flower.stock:>6} "
                f"{flower.reorder_threshold:>10}  {status}"
            )
        return "\n".join(lines)

    def bouquet_table(self) -> str:
        header = f"{'Bouquet':<18} {'Stems':>5} {'Cost':>9} {'Retail':>9} {'Available':>9}"
        lines = [header, "-" * len(header)]
        for bouquet in sorted(self.bouquets.values(), key=lambda item: item.name):
            lines.append(
                f"{bouquet.name:<18} {bouquet.stems:>5} {money(bouquet.cost):>9} "
                f"{money(bouquet.price):>9} {bouquet.max_bouquets():>9}"
            )
        return "\n".join(lines)

    def sales_report(self) -> str:
        fulfilled = [order for order in self.orders if order.status == "fulfilled"]
        pending = [order for order in self.orders if order.status == "pending"]
        cancelled = [order for order in self.orders if order.status == "cancelled"]
        revenue = round(sum(order.total for order in fulfilled), 2)
        pending_value = round(sum(order.total for order in pending), 2)
        units = sum(order.quantity for order in fulfilled)
        sellers: dict[str, int] = {}
        for order in fulfilled:
            sellers[order.bouquet] = sellers.get(order.bouquet, 0) + order.quantity
        top = max(sellers.items(), key=lambda item: item[1]) if sellers else ("-", 0)
        return "\n".join([
            f"Orders: {len(self.orders)} ({len(fulfilled)} fulfilled, "
            f"{len(pending)} pending, {len(cancelled)} cancelled)",
            f"Revenue: {money(revenue)} from {units} bouquet(s)",
            f"Pending value: {money(pending_value)}",
            f"Best seller: {top[0]} ({top[1]} bouquet(s))",
            f"Inventory at wholesale: {money(self.inventory_value)}",
        ])

    # -- persistence ----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "next_order": self._next_order,
            "flowers": [flower.to_dict() for flower in self.flowers.values()],
            "bouquets": [bouquet.to_dict() for bouquet in self.bouquets.values()],
            "orders": [order.to_dict() for order in self.orders],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FlowerShop":
        if not isinstance(data, dict):
            raise ShopError("shop file must contain a JSON object")
        shop = cls(str(data.get("name", "Flower Shop")))
        flowers = data.get("flowers", [])
        bouquets = data.get("bouquets", [])
        orders = data.get("orders", [])
        if not all(isinstance(item, list) for item in (flowers, bouquets, orders)):
            raise ShopError("flowers, bouquets and orders must be lists")
        for item in flowers:
            shop.add_flower(Flower.from_dict(item))
        for item in bouquets:
            shop.add_bouquet(Bouquet.from_dict(item, shop.flowers))
        for item in orders:
            shop.orders.append(Order.from_dict(item))
        try:
            shop._next_order = int(data.get("next_order", 1001 + len(shop.orders)))
        except (TypeError, ValueError) as exc:
            raise ShopError(f"invalid next_order value: {exc}") from exc
        return shop

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "FlowerShop":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ShopError(f"shop file not found: {path}") from exc
        except OSError as exc:
            raise ShopError(f"cannot read shop file {path}: {exc}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ShopError(f"invalid JSON in {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ShopError("shop file must contain a JSON object")
        return cls.from_dict(data)


def build_sample_shop() -> FlowerShop:
    """A deterministic florist used by the demo and the default CLI session."""
    shop = FlowerShop("Petal & Stem")
    for flower in [
        Flower("Rose", 2.50, 120, 30, "Bloom Supply"),
        Flower("Tulip", 1.20, 80, 20, "Dutch Fields"),
        Flower("Lily", 3.40, 40, 15, "Bloom Supply"),
        Flower("Eucalyptus", 0.80, 60, 20, "Green Stems Co"),
        Flower("Baby's Breath", 0.60, 100, 25, "Green Stems Co"),
        Flower("Sunflower", 2.10, 15, 20, "Sunny Acres"),
    ]:
        shop.add_flower(flower)

    romance = Bouquet("Romance", "Classic red roses with soft greenery", 1.7, 3.50)
    romance.add(shop.flower("Rose"), 12)
    romance.add(shop.flower("Eucalyptus"), 4)
    romance.add(shop.flower("Baby's Breath"), 3)
    shop.add_bouquet(romance)

    spring = Bouquet("Spring Morning", "Tulips, lilies and airy filler", 1.6, 3.00)
    spring.add(shop.flower("Tulip"), 8)
    spring.add(shop.flower("Lily"), 3)
    spring.add(shop.flower("Baby's Breath"), 5)
    shop.add_bouquet(spring)

    golden = Bouquet("Golden Hour", "Sunflowers with eucalyptus", 1.55, 2.50)
    golden.add(shop.flower("Sunflower"), 5)
    golden.add(shop.flower("Eucalyptus"), 6)
    shop.add_bouquet(golden)
    return shop


def run_demo() -> int:
    """Walk through a day of orders, cancellations, reorders and reporting."""
    print("=== Flower Shop Ordering To Go: demo ===\n")
    shop = build_sample_shop()
    print(f"{shop.name}: {len(shop.flowers)} flower varieties, "
          f"{len(shop.bouquets)} bouquet recipes\n")
    print("Flower catalog:")
    print(shop.catalog_table())
    print("\nBouquet menu:")
    print(shop.bouquet_table())

    first = shop.create_order("Romance", 2, "Emma")
    print(f"\nOrder {first.order_id}: {first.customer} bought {first.quantity} x "
          f"{first.bouquet} for {money(first.total)} ({first.status})")
    print(f"  Roses left: {shop.flower('Rose').stock}")

    second = shop.create_order("Golden Hour", 2, "Noah")
    print(f"Order {second.order_id}: {second.customer} bought {second.quantity} x "
          f"{second.bouquet} for {money(second.total)} ({second.status})")
    print(f"  Sunflowers left: {shop.flower('Sunflower').stock}")

    print("\nTrying to order 5 more Golden Hour:")
    try:
        shop.create_order("Golden Hour", 5, "Olivia")
    except StockError as exc:
        print(f"  rejected -> {exc}")

    shop.fulfill(first.order_id)
    shop.cancel(second.order_id)
    print(f"\n{first.order_id} fulfilled; {second.order_id} cancelled and stock restored.")
    print(f"  Sunflowers after cancellation: {shop.flower('Sunflower').stock}")

    low = shop.low_stock()
    print(f"\nLow stock ({len(low)}):")
    for flower in low:
        print(f"  {flower.name}: {flower.stock} left, reorder point {flower.reorder_threshold}, "
              f"suggest ordering {flower.reorder_quantity()}")

    print("\nReordering:")
    for flower, quantity, cost in shop.reorder_all():
        print(f"  +{quantity:>3} {flower.name:<14} cost {money(cost):>8} "
              f"-> stock {flower.stock}")
    print(f"  Inventory value now {money(shop.inventory_value)}")

    print("\nSales report:")
    print(shop.sales_report())

    with tempfile.TemporaryDirectory(prefix="flower-shop-demo-") as tmp:
        path = Path(tmp) / "shop.json"
        shop.save(path)
        loaded = FlowerShop.load(path)
        print(f"\nSaved and reloaded {len(loaded.flowers)} flowers, "
              f"{len(loaded.bouquets)} bouquets, {len(loaded.orders)} orders "
              f"({path.stat().st_size} bytes).")
        print(f"  Rose stock preserved: {loaded.flower('Rose').stock}")
        print(f"  Next order id: ORD-{loaded._next_order}")

    print("\nDemo complete.")
    return 0


def run_interactive(shop: FlowerShop) -> int:
    """Menu-driven shop counter."""
    print(f"{shop.name} counter. Type 'h' for help.")
    while True:
        try:
            choice = input("\n[1] catalog [2] bouquets [3] order [4] fulfil [5] cancel "
                           "[6] restock [7] report [8] save [9] load [q] quit > ").strip().lower()
        except EOFError:
            print()
            return 0
        try:
            if choice in {"q", "quit", "0"}:
                return 0
            if choice == "1":
                print(shop.catalog_table())
            elif choice == "2":
                print(shop.bouquet_table())
            elif choice == "3":
                name = input("Bouquet: ")
                quantity = int(input("Quantity: ") or "1")
                customer = input("Customer: ")
                order = shop.create_order(name, quantity, customer)
                print(f"{order.order_id} created for {money(order.total)}.")
            elif choice == "4":
                order = shop.fulfill(input("Order id: ").strip().upper())
                print(f"{order.order_id} fulfilled.")
            elif choice == "5":
                order = shop.cancel(input("Order id: ").strip().upper())
                print(f"{order.order_id} cancelled; stock restored.")
            elif choice == "6":
                rows = shop.reorder_all()
                for flower, quantity, cost in rows:
                    print(f"  +{quantity} {flower.name} for {money(cost)}")
                print("  Nothing to reorder." if not rows else "  Done.")
            elif choice == "7":
                print(shop.sales_report())
            elif choice == "8":
                path = Path(input("Save to [shop.json]: ") or "shop.json")
                shop.save(path)
                print(f"Saved to {path}.")
            elif choice == "9":
                path = Path(input("Load from [shop.json]: ") or "shop.json")
                shop = FlowerShop.load(path)
                print(f"Loaded {shop.name}.")
            else:
                print("  1 catalog, 2 bouquets, 3 order, 4 fulfil, 5 cancel, "
                      "6 restock, 7 report, 8 save, 9 load, q quit")
        except (ShopError, ValueError) as exc:
            print(f"Error: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Order bouquets, track flower stock and reorder low varieties.",
        epilog="With no options an interactive counter is shown.",
    )
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    parser.add_argument("--data", type=Path, metavar="FILE", help="load a shop from JSON")
    parser.add_argument("--catalog", action="store_true", help="show flowers and bouquets")
    parser.add_argument("--order", metavar="BOUQUET", help="place an order")
    parser.add_argument("--quantity", type=int, default=1, help="order quantity (default 1)")
    parser.add_argument("--customer", default="Walk-in", help="customer name")
    parser.add_argument("--fulfill", metavar="ORDER_ID", help="fulfil a pending order")
    parser.add_argument("--cancel", metavar="ORDER_ID", help="cancel a pending order")
    parser.add_argument("--restock", action="store_true", help="reorder every low-stock flower")
    parser.add_argument("--report", action="store_true", help="show the sales report")
    parser.add_argument("--save", type=Path, metavar="FILE", help="save the shop to JSON")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()

    try:
        shop = FlowerShop.load(args.data) if args.data else build_sample_shop()
    except ShopError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        if args.catalog:
            print("Flower catalog:")
            print(shop.catalog_table())
            print("\nBouquet menu:")
            print(shop.bouquet_table())
        if args.order:
            order = shop.create_order(args.order, args.quantity, args.customer)
            print(f"{order.order_id}: {order.quantity} x {order.bouquet} for "
                  f"{money(order.total)} ({order.status})")
        if args.fulfill:
            order = shop.fulfill(args.fulfill.upper())
            print(f"{order.order_id} fulfilled ({money(order.total)}).")
        if args.cancel:
            order = shop.cancel(args.cancel.upper())
            print(f"{order.order_id} cancelled and stock restored.")
        if args.restock:
            rows = shop.reorder_all()
            for flower, quantity, cost in rows:
                print(f"+{quantity} {flower.name} for {money(cost)}")
            if not rows:
                print("Nothing needs reordering.")
        if args.report:
            print(shop.sales_report())
        if args.save:
            shop.save(args.save)
            print(f"Saved to {args.save}.")
        if not any([args.catalog, args.order, args.fulfill, args.cancel,
                    args.restock, args.report, args.save]):
            return run_interactive(shop)
    except (ShopError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
