#!/usr/bin/env python3
"""Product inventory manager.

The domain model (:class:`Product` and :class:`Inventory`) is deliberately
independent of the command line interface so it can be reused or unit-tested
without any I/O.  The CLI offers a scripted demo and an interactive menu.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Iterable, Sequence


class InventoryError(Exception):
    """Raised when an inventory operation cannot be completed."""


@dataclass
class Product:
    """A single product (SKU) tracked by the inventory."""

    product_id: str
    name: str
    price: float
    quantity: int = 0

    def __post_init__(self) -> None:
        self.product_id = self.product_id.strip().upper()
        self.name = self.name.strip()
        if not self.product_id:
            raise ValueError("product id must not be empty")
        if not self.name:
            raise ValueError("product name must not be empty")
        if not isinstance(self.price, (int, float)) or self.price < 0:
            raise ValueError("price must be a non-negative number")
        if not isinstance(self.quantity, int) or isinstance(self.quantity, bool):
            raise ValueError("quantity must be a whole number")
        if self.quantity < 0:
            raise ValueError("quantity must not be negative")

    @property
    def value(self) -> float:
        """Total value of the units on hand, rounded to cents."""
        return round(self.price * self.quantity, 2)

    def __str__(self) -> str:
        return f"{self.product_id:<8} {self.name:<24} ${self.price:>8,.2f} {self.quantity:>5}"


class Inventory:
    """A collection of products keyed by product id."""

    def __init__(self, products: Iterable[Product] = ()) -> None:
        self._products: dict[str, Product] = {}
        for product in products:
            self.add_product(product)

    def __len__(self) -> int:
        return len(self._products)

    def __iter__(self):
        return iter(self._products.values())

    def __contains__(self, product_id: object) -> bool:
        return str(product_id).upper() in self._products

    @property
    def products(self) -> tuple[Product, ...]:
        """Products in insertion order."""
        return tuple(self._products.values())

    def add_product(self, product: Product, *, merge: bool = False) -> Product:
        """Add a product; optionally merge quantities for an existing id."""
        if product.product_id in self._products:
            if not merge:
                raise InventoryError(
                    f"product {product.product_id} already exists"
                )
            existing = self._products[product.product_id]
            existing.quantity += product.quantity
            return existing
        self._products[product.product_id] = product
        return product

    def remove_product(self, product_id: str) -> Product:
        """Remove and return a product, discarding any remaining stock."""
        key = product_id.strip().upper()
        try:
            return self._products.pop(key)
        except KeyError:
            raise InventoryError(f"unknown product: {key}") from None

    def get(self, product_id: str) -> Product:
        """Return a product by id or raise :class:`InventoryError`."""
        key = product_id.strip().upper()
        try:
            return self._products[key]
        except KeyError:
            raise InventoryError(f"unknown product: {key}") from None

    def restock(self, product_id: str, units: int) -> Product:
        """Add ``units`` to a product's quantity."""
        if units <= 0:
            raise InventoryError("restock quantity must be positive")
        product = self.get(product_id)
        product.quantity += units
        return product

    def sell(self, product_id: str, units: int) -> float:
        """Sell ``units`` and return the revenue; stock must be sufficient."""
        if units <= 0:
            raise InventoryError("sale quantity must be positive")
        product = self.get(product_id)
        if units > product.quantity:
            raise InventoryError(
                f"only {product.quantity} unit(s) of {product.product_id} in stock"
            )
        product.quantity -= units
        return round(product.price * units, 2)

    def low_stock(self, threshold: int = 5) -> list[Product]:
        """Products whose quantity is at or below ``threshold``."""
        if threshold < 0:
            raise InventoryError("threshold must not be negative")
        return [p for p in self._products.values() if p.quantity <= threshold]

    @property
    def total_units(self) -> int:
        return sum(p.quantity for p in self._products.values())

    @property
    def total_value(self) -> float:
        """Sum of price times quantity across all products."""
        return round(sum(p.value for p in self._products.values()), 2)


def render_table(products: Sequence[Product]) -> str:
    """Render products as a fixed-width table."""
    header = f"{'ID':<8} {'NAME':<24} {'PRICE':>9} {'QTY':>5} {'VALUE':>11}"
    lines = [header, "-" * len(header)]
    for product in products:
        lines.append(
            f"{product.product_id:<8} {product.name:<24} "
            f"${product.price:>8,.2f} {product.quantity:>5} ${product.value:>10,.2f}"
        )
    if not products:
        lines.append("(no products)")
    return "\n".join(lines)


def run_demo() -> int:
    """Exercise the API end to end with no user input."""
    inventory = Inventory(
        [
            Product("P-1001", "Mechanical Keyboard", 89.99, 12),
            Product("P-1002", "USB-C Hub", 34.50, 4),
            Product("P-1003", "27-inch Monitor", 219.00, 7),
            Product("P-1004", "Ergonomic Mouse", 49.95, 3),
            Product("P-1005", "Laptop Stand", 29.00, 20),
        ]
    )
    print("== Product Inventory Demo ==")
    print(f"Loaded {len(inventory)} products, {inventory.total_units} units.\n")
    print(render_table(inventory.products))
    print(f"\nTotal inventory value: ${inventory.total_value:,.2f}")

    revenue = inventory.sell("P-1002", 2)
    print(f"\nSold 2 x USB-C Hub for ${revenue:,.2f}.")
    inventory.restock("P-1003", 5)
    print("Restocked 5 x 27-inch Monitor.")
    removed = inventory.remove_product("P-1005")
    print(f"Discontinued {removed.product_id} ({removed.name}).\n")

    print("-- Updated inventory --")
    print(render_table(inventory.products))
    print(f"\nTotal inventory value: ${inventory.total_value:,.2f}")
    print(f"Total units on hand:   {inventory.total_units}")

    low = inventory.low_stock(threshold=5)
    print("\n-- Low stock (<= 5 units) --")
    for product in low:
        print(f"  {product.product_id}: {product.name} ({product.quantity} left)")
    if not low:
        print("  none")

    print("\n-- Invalid operations are rejected --")
    for action, func in (
        ("selling 99 hubs", lambda: inventory.sell("P-1002", 99)),
        ("unknown product", lambda: inventory.get("P-9999")),
        ("duplicate id", lambda: inventory.add_product(Product("P-1001", "Clone", 1.0))),
    ):
        try:
            func()
        except InventoryError as exc:
            print(f"  {action:<20} -> {exc}")
    return 0


def prompt(message: str, default: str = "") -> str:
    """Prompt for a string, accepting an optional default."""
    suffix = f" [{default}]" if default else ""
    value = input(f"{message}{suffix}: ").strip()
    return value or default


def interactive(low_threshold: int) -> int:
    """Run a small menu-driven inventory console."""
    inventory = Inventory()
    menu = (
        "\n1) List products   2) Add product      3) Restock\n"
        "4) Sell            5) Remove product   6) Low stock\n"
        "7) Total value     8) Quit"
    )
    print("Product Inventory Manager")
    while True:
        print(menu)
        try:
            choice = input("Choice: ").strip()
        except EOFError:
            print()
            return 0
        try:
            if choice == "1":
                print(render_table(inventory.products))
            elif choice == "2":
                product = Product(
                    prompt("Product id"),
                    prompt("Name"),
                    float(prompt("Price", "0")),
                    int(prompt("Quantity", "0")),
                )
                inventory.add_product(product)
                print(f"Added {product.product_id}.")
            elif choice == "3":
                pid = prompt("Product id")
                units = int(prompt("Units to add", "1"))
                inventory.restock(pid, units)
                print(f"{pid} now has {inventory.get(pid).quantity} units.")
            elif choice == "4":
                pid = prompt("Product id")
                units = int(prompt("Units to sell", "1"))
                revenue = inventory.sell(pid, units)
                print(f"Sold {units} unit(s) for ${revenue:,.2f}.")
            elif choice == "5":
                removed = inventory.remove_product(prompt("Product id"))
                print(f"Removed {removed.product_id}.")
            elif choice == "6":
                for product in inventory.low_stock(low_threshold):
                    print(f"  {product.product_id}: {product.name} ({product.quantity})")
            elif choice == "7":
                print(f"Total value: ${inventory.total_value:,.2f}")
            elif choice == "8":
                print("Goodbye.")
                return 0
            else:
                print("Please choose 1-8.")
        except (InventoryError, ValueError) as exc:
            print(f"Error: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage a product inventory and report its total value.",
        epilog="Run without arguments for the interactive menu.",
    )
    parser.add_argument(
        "--demo", action="store_true", help="run a scripted non-interactive demo"
    )
    parser.add_argument(
        "--low-stock-threshold",
        type=int,
        default=5,
        metavar="N",
        help="flag products with at most N units (default: 5)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.low_stock_threshold < 0:
        print("error: --low-stock-threshold must not be negative", file=sys.stderr)
        return 2
    if args.demo:
        return run_demo()
    try:
        return interactive(args.low_stock_threshold)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
