#!/usr/bin/env python3
"""Airline and hotel reservation system with tiered, demand-based pricing.

Domain model
------------
``Flight`` manages a seat map split into travel classes; ``Hotel`` manages
rooms booked over date ranges.  Both price dynamically from current occupancy
and expose availability queries.  ``ReservationSystem`` is the facade the CLI
uses to create and cancel reservations across either venue.

The demo is fully scripted (no input, no network) and uses a fixed as-of date
so its output is reproducible.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Sequence


class ReservationError(Exception):
    """Raised when a reservation cannot be created or cancelled."""


def q(value: Decimal) -> Decimal:
    """Round a monetary amount to cents."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money(value: Decimal) -> str:
    return f"${value:,.2f}"


class SeatClass(Enum):
    """Travel classes, ordered from cheapest to most expensive."""

    ECONOMY = ("Economy", Decimal("1.00"))
    PREMIUM = ("Premium", Decimal("1.35"))
    BUSINESS = ("Business", Decimal("1.90"))
    FIRST = ("First", Decimal("3.00"))

    def __init__(self, label: str, multiplier: Decimal) -> None:
        self.label = label
        self.multiplier = multiplier


class RoomType(Enum):
    """Hotel room categories and their rate multipliers."""

    STANDARD = ("Standard", Decimal("1.00"))
    DELUXE = ("Deluxe", Decimal("1.40"))
    SUITE = ("Suite", Decimal("2.20"))

    def __init__(self, label: str, multiplier: Decimal) -> None:
        self.label = label
        self.multiplier = multiplier


@dataclass(frozen=True)
class DateRange:
    """A hotel stay: check-in inclusive, check-out exclusive."""

    check_in: date
    check_out: date

    def __post_init__(self) -> None:
        if self.check_out <= self.check_in:
            raise ValueError("check-out must be after check-in")

    @property
    def nights(self) -> tuple[date, ...]:
        return tuple(
            self.check_in + timedelta(days=offset)
            for offset in range((self.check_out - self.check_in).days)
        )

    def overlaps(self, other: "DateRange") -> bool:
        return self.check_in < other.check_out and other.check_in < self.check_out


@dataclass(frozen=True)
class Seat:
    """A single seat on a flight."""

    code: str
    seat_class: SeatClass


@dataclass
class Reservation:
    """A confirmed booking for a flight seat or a hotel room."""

    reservation_id: str
    kind: str  # "flight" or "hotel"
    customer: str
    venue: str  # flight number or hotel name
    item: str  # seat code or room number
    start: date
    end: date
    total: Decimal
    status: str = "CONFIRMED"

    @property
    def nights(self) -> int:
        return max(1, (self.end - self.start).days)

    def describe(self) -> str:
        when = self.start.isoformat()
        if self.kind == "hotel":
            when += f" -> {self.end.isoformat()} ({self.nights} night(s))"
        return (
            f"{self.reservation_id:<9} {self.kind:<6} {self.customer:<10} "
            f"{self.venue:<12} {self.item:<5} {when:<25} {money(self.total):>10} "
            f"{self.status}"
        )


class Flight:
    """A flight with a 20-row, 6-seat-per-row cabin and dynamic fares."""

    COLUMNS = "ABCDEF"
    ROWS = 20
    CLASS_RANGES = (
        (range(1, 3), SeatClass.FIRST),
        (range(3, 6), SeatClass.BUSINESS),
        (range(6, 11), SeatClass.PREMIUM),
        (range(11, 21), SeatClass.ECONOMY),
    )

    def __init__(
        self,
        number: str,
        origin: str,
        destination: str,
        departure: date,
        base_fare: Decimal,
    ) -> None:
        if not number.strip() or not origin.strip() or not destination.strip():
            raise ValueError("flight number, origin and destination are required")
        if base_fare <= 0:
            raise ValueError("base fare must be positive")
        self.number = number.strip().upper()
        self.origin = origin.strip()
        self.destination = destination.strip()
        self.departure = departure
        self.base_fare = Decimal(str(base_fare))
        self._seats: dict[str, Seat] = {}
        for row in range(1, self.ROWS + 1):
            for column in self.COLUMNS:
                self._seats[f"{row}{column}"] = Seat(
                    f"{row}{column}", self.class_for_row(row)
                )
        self._bookings: dict[str, Reservation] = {}

    @classmethod
    def class_for_row(cls, row: int) -> SeatClass:
        for rows, seat_class in cls.CLASS_RANGES:
            if row in rows:
                return seat_class
        raise ValueError(f"row {row} is outside the cabin")

    @property
    def seats(self) -> tuple[Seat, ...]:
        return tuple(self._seats.values())

    @property
    def bookings(self) -> tuple[Reservation, ...]:
        return tuple(self._bookings.values())

    @property
    def occupancy(self) -> float:
        return len(self._bookings) / len(self._seats)

    def booked_seats(self) -> set[str]:
        return {reservation.item for reservation in self._bookings.values()}

    def available_seats(self, seat_class: SeatClass | None = None) -> list[Seat]:
        """Free seats, optionally restricted to one travel class."""
        booked = self.booked_seats()
        return [
            seat
            for seat in self._seats.values()
            if seat.code not in booked
            and (seat_class is None or seat.seat_class is seat_class)
        ]

    def price_for(self, seat: Seat) -> Decimal:
        """Fare = base fare x class multiplier x demand multiplier."""
        demand = Decimal("1.0") + Decimal("0.5") * Decimal(str(self.occupancy))
        return q(self.base_fare * seat.seat_class.multiplier * demand)

    def quote(self, seat_class: SeatClass = SeatClass.ECONOMY) -> Decimal:
        """Cheapest current fare in a class, or raise if it is sold out."""
        seats = self.available_seats(seat_class)
        if not seats:
            raise ReservationError(f"{self.number}: {seat_class.label} is sold out")
        return min(self.price_for(seat) for seat in seats)

    def reserve(
        self,
        reservation_id: str,
        customer: str,
        seat_class: SeatClass | None = None,
        seat_code: str | None = None,
    ) -> Reservation:
        """Book a specific seat, or the first free seat in ``seat_class``."""
        if seat_code is not None:
            seat = self._seats.get(seat_code.strip().upper())
            if seat is None:
                raise ReservationError(f"{self.number}: no seat {seat_code}")
            if seat_class is not None and seat.seat_class is not seat_class:
                raise ReservationError(
                    f"seat {seat.code} is {seat.seat_class.label}, not {seat_class.label}"
                )
            if seat.code in self.booked_seats():
                raise ReservationError(f"seat {seat.code} is already booked")
        else:
            seat_class = seat_class or SeatClass.ECONOMY
            seats = self.available_seats(seat_class)
            if not seats:
                raise ReservationError(f"{self.number}: {seat_class.label} is sold out")
            seat = seats[0]
        reservation = Reservation(
            reservation_id=reservation_id,
            kind="flight",
            customer=customer,
            venue=self.number,
            item=seat.code,
            start=self.departure,
            end=self.departure,
            total=self.price_for(seat),
        )
        self._bookings[reservation_id] = reservation
        return reservation

    def cancel(self, reservation_id: str) -> Reservation:
        try:
            return self._bookings.pop(reservation_id)
        except KeyError:
            raise ReservationError(
                f"{self.number}: no active reservation {reservation_id}"
            ) from None

    def seat_map(self) -> str:
        """ASCII cabin map; ``XX`` marks a booked seat."""
        booked = self.booked_seats()
        lines = ["      A  B  C    D  E  F"]
        for row in range(1, self.ROWS + 1):
            cells = []
            for column in self.COLUMNS:
                code = f"{row}{column}"
                cells.append("XX" if code in booked else "..")
            lines.append(
                f" {row:>2}   {cells[0]} {cells[1]} {cells[2]}    "
                f"{cells[3]} {cells[4]} {cells[5]}"
            )
        return "\n".join(lines)

    def class_summary(self) -> str:
        lines = []
        for seat_class in SeatClass:
            seats = [s for s in self._seats.values() if s.seat_class is seat_class]
            free = len(self.available_seats(seat_class))
            lines.append(
                f"  {seat_class.label:<8} rows {seats[0].code[:-1]}-"
                f"{seats[-1].code[:-1]:<3} {free:>3}/{len(seats):<3} free  "
                f"from {money(self.quote(seat_class)) if free else 'sold out'}"
            )
        return "\n".join(lines)


@dataclass(frozen=True)
class Room:
    """A hotel room with a number and a rate tier."""

    number: str
    room_type: RoomType

    def __post_init__(self) -> None:
        if not self.number.strip():
            raise ValueError("room number must not be empty")

    @property
    def label(self) -> str:
        return f"{self.number} ({self.room_type.label})"


class Hotel:
    """A hotel whose rooms are booked over date ranges."""

    def __init__(
        self,
        name: str,
        city: str,
        base_rate: Decimal,
        rooms: Sequence[Room | tuple[str, RoomType]],
    ) -> None:
        if not rooms:
            raise ValueError("a hotel needs at least one room")
        if base_rate <= 0:
            raise ValueError("base rate must be positive")
        self.name = name.strip()
        self.city = city.strip()
        self.base_rate = Decimal(str(base_rate))
        parsed = [entry if isinstance(entry, Room) else Room(*entry) for entry in rooms]
        self._rooms: dict[str, Room] = {room.number: room for room in parsed}
        if len(self._rooms) != len(parsed):
            raise ValueError("room numbers must be unique")
        self._bookings: dict[str, Reservation] = {}

    @property
    def rooms(self) -> tuple[Room, ...]:
        return tuple(self._rooms.values())

    @property
    def bookings(self) -> tuple[Reservation, ...]:
        return tuple(self._bookings.values())

    def room(self, number: str) -> Room:
        try:
            return self._rooms[number]
        except KeyError:
            raise ReservationError(f"{self.name}: no room {number}") from None

    def room_type(self, number: str) -> RoomType:
        return self.room(number).room_type

    def occupancy_on(self, night: date) -> float:
        occupied = sum(
            1
            for booking in self._bookings.values()
            if booking.start <= night < booking.end
        )
        return occupied / len(self._rooms)

    def nightly_rate(self, room: Room, night: date) -> Decimal:
        """Room rate for one night: base x tier x demand x weekend."""
        demand = Decimal("1.0") + Decimal("0.25") * Decimal(str(self.occupancy_on(night)))
        weekend = Decimal("1.20") if night.weekday() in (4, 5) else Decimal("1.00")
        return q(self.base_rate * room.room_type.multiplier * demand * weekend)

    def is_available(self, room_number: str, stay: DateRange) -> bool:
        for booking in self._bookings.values():
            if booking.item == room_number and stay.overlaps(
                DateRange(booking.start, booking.end)
            ):
                return False
        return True

    def available_rooms(self, room_type: RoomType, stay: DateRange) -> list[str]:
        return [
            number
            for number, room in self._rooms.items()
            if room.room_type is room_type and self.is_available(number, stay)
        ]

    def quote(self, room_type: RoomType, stay: DateRange) -> Decimal:
        """Total for the first available room of a type, before booking."""
        rooms = self.available_rooms(room_type, stay)
        if not rooms:
            raise ReservationError(f"{self.name}: no {room_type.label} room available")
        room = self._rooms[rooms[0]]
        return q(
            sum(
                (self.nightly_rate(room, night) for night in stay.nights),
                Decimal("0"),
            )
        )

    def reserve(
        self, reservation_id: str, customer: str, room_type: RoomType, stay: DateRange
    ) -> Reservation:
        rooms = self.available_rooms(room_type, stay)
        if not rooms:
            raise ReservationError(f"{self.name}: no {room_type.label} room available")
        room = self._rooms[rooms[0]]
        total = q(
            sum(
                (self.nightly_rate(room, night) for night in stay.nights),
                Decimal("0"),
            )
        )
        reservation = Reservation(
            reservation_id=reservation_id,
            kind="hotel",
            customer=customer,
            venue=self.name,
            item=room.number,
            start=stay.check_in,
            end=stay.check_out,
            total=total,
        )
        self._bookings[reservation_id] = reservation
        return reservation

    def cancel(self, reservation_id: str) -> Reservation:
        try:
            return self._bookings.pop(reservation_id)
        except KeyError:
            raise ReservationError(
                f"{self.name}: no active reservation {reservation_id}"
            ) from None

    def availability_report(self, stay: DateRange) -> str:
        lines = [f"{self.name} ({self.city}) availability {stay.check_in} -> {stay.check_out}:"]
        for room_type in RoomType:
            rooms = self.available_rooms(room_type, stay)
            quote = (
                money(self.quote(room_type, stay)) if rooms else "sold out"
            )
            lines.append(
                f"  {room_type.label:<8} {len(rooms):>2}/"
                f"{sum(1 for room in self._rooms.values() if room.room_type is room_type):<2} free  "
                f"{quote:>12} total"
            )
        return "\n".join(lines)


class ReservationSystem:
    """Facade over flights and hotels with shared reservation ids."""

    def __init__(self) -> None:
        self.flights: dict[str, Flight] = {}
        self.hotels: dict[str, Hotel] = {}
        self._reservations: dict[str, Reservation] = {}
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"RSV-{self._counter:04d}"

    def add_flight(self, flight: Flight) -> Flight:
        if flight.number in self.flights:
            raise ReservationError(f"flight {flight.number} already exists")
        self.flights[flight.number] = flight
        return flight

    def add_hotel(self, hotel: Hotel) -> Hotel:
        if hotel.name in self.hotels:
            raise ReservationError(f"hotel {hotel.name} already exists")
        self.hotels[hotel.name] = hotel
        return hotel

    def flight(self, number: str) -> Flight:
        """Return a flight by number or raise :class:`ReservationError`."""
        try:
            return self.flights[number.strip().upper()]
        except KeyError:
            raise ReservationError(f"unknown flight: {number}") from None

    def hotel(self, name: str) -> Hotel:
        """Return a hotel by name or raise :class:`ReservationError`."""
        try:
            return self.hotels[name.strip()]
        except KeyError:
            raise ReservationError(f"unknown hotel: {name}") from None

    def book_flight(
        self,
        flight_number: str,
        customer: str,
        seat_class: SeatClass | None = None,
        seat_code: str | None = None,
    ) -> Reservation:
        reservation = self.flight(flight_number).reserve(
            self._next_id(), customer, seat_class, seat_code
        )
        self._reservations[reservation.reservation_id] = reservation
        return reservation

    def book_hotel(
        self,
        hotel_name: str,
        customer: str,
        room_type: RoomType,
        check_in: date,
        nights: int,
    ) -> Reservation:
        if nights <= 0:
            raise ReservationError("nights must be positive")
        stay = DateRange(check_in, check_in + timedelta(days=nights))
        reservation = self.hotel(hotel_name).reserve(
            self._next_id(), customer, room_type, stay
        )
        self._reservations[reservation.reservation_id] = reservation
        return reservation

    def get(self, reservation_id: str) -> Reservation:
        try:
            return self._reservations[reservation_id]
        except KeyError:
            raise ReservationError(f"unknown reservation: {reservation_id}") from None

    def cancel(self, reservation_id: str) -> Reservation:
        reservation = self.get(reservation_id)
        if reservation.status == "CANCELLED":
            raise ReservationError(f"{reservation_id} is already cancelled")
        if reservation.kind == "flight":
            self.flight(reservation.venue).cancel(reservation_id)
        else:
            self.hotel(reservation.venue).cancel(reservation_id)
        reservation.status = "CANCELLED"
        return reservation

    @property
    def reservations(self) -> tuple[Reservation, ...]:
        return tuple(self._reservations.values())

    @property
    def revenue(self) -> Decimal:
        return q(
            sum(
                (r.total for r in self._reservations.values() if r.status == "CONFIRMED"),
                Decimal("0"),
            )
        )

    def reservation_report(self) -> str:
        header = (
            f"{'ID':<9} {'TYPE':<6} {'CUSTOMER':<10} {'VENUE':<12} "
            f"{'UNIT':<5} {'WHEN':<25} {'TOTAL':>10} STATUS"
        )
        lines = [header, "-" * len(header)]
        lines.extend(reservation.describe() for reservation in self._reservations.values())
        if not self._reservations:
            lines.append("(no reservations)")
        return "\n".join(lines)


def build_sample_system() -> ReservationSystem:
    """Create the deterministic demo inventory."""
    system = ReservationSystem()
    system.add_flight(
        Flight("NA-101", "San Francisco", "New York", date(2026, 6, 10), Decimal("220"))
    )
    system.add_flight(
        Flight("NA-202", "New York", "London", date(2026, 6, 12), Decimal("480"))
    )
    system.add_hotel(
        Hotel(
            "Harbor House",
            "Boston",
            Decimal("150"),
            [Room(f"10{n}", RoomType.STANDARD) for n in range(1, 5)]
            + [Room(f"20{n}", RoomType.DELUXE) for n in range(1, 4)]
            + [Room(f"30{n}", RoomType.SUITE) for n in range(1, 3)],
        )
    )
    return system


def run_demo() -> int:
    """Walk through booking, dynamic pricing, conflicts and cancellation."""
    system = build_sample_system()
    print("== Airline / Hotel Reservation Demo ==")
    print("Demo inventory: two flights and one hotel, June 2026.\n")

    flight = system.flights["NA-101"]
    print(f"Flight {flight.number}: {flight.origin} -> {flight.destination} "
          f"on {flight.departure} (base fare {money(flight.base_fare)})")
    print(flight.class_summary())
    print("\n-- Cabin map (XX = booked) --")
    print(flight.seat_map())

    print("\n-- Booking flights --")
    alice = system.book_flight("NA-101", "Alice", SeatClass.ECONOMY)
    print(f"  {alice.reservation_id}: Alice, seat {alice.item} "
          f"({SeatClass.ECONOMY.label}) {money(alice.total)}")
    bob = system.book_flight("NA-101", "Bob", seat_code="3C")
    print(f"  {bob.reservation_id}: Bob, seat {bob.item} "
          f"({SeatClass.BUSINESS.label}) {money(bob.total)}")
    carol = system.book_flight("NA-101", "Carol", SeatClass.FIRST)
    print(f"  {carol.reservation_id}: Carol, seat {carol.item} "
          f"({SeatClass.FIRST.label}) {money(carol.total)}")

    print("\n-- Demand pricing: economy after 3 seats are sold --")
    print(f"  Economy fare now {money(flight.quote(SeatClass.ECONOMY))} "
          f"(occupancy {flight.occupancy:.1%})")
    dave = system.book_flight("NA-101", "Dave", SeatClass.ECONOMY)
    print(f"  {dave.reservation_id}: Dave, seat {dave.item} {money(dave.total)}")

    print("\n-- Conflict handling --")
    for label, action in (
        ("seat 3C again", lambda: system.book_flight("NA-101", "Eve", seat_code="3C")),
        ("wrong fare class", lambda: system.book_flight("NA-101", "Eve", SeatClass.FIRST, "12A")),
        ("unknown flight", lambda: system.book_flight("NA-999", "Eve")),
    ):
        try:
            action()
            print(f"  {label:<16} -> unexpectedly succeeded")
        except ReservationError as exc:
            print(f"  {label:<16} -> {exc}")

    stay = DateRange(date(2026, 6, 5), date(2026, 6, 8))  # Fri-Sun nights
    hotel = system.hotels["Harbor House"]
    print(f"\n-- Hotel '{hotel.name}' for {stay.check_in} -> {stay.check_out} "
          f"({len(stay.nights)} nights, weekend surcharge applies) --")
    print(hotel.availability_report(stay))
    first = system.book_hotel("Harbor House", "Alice", RoomType.STANDARD, stay.check_in, 3)
    print(f"  {first.reservation_id}: Alice, room {first.item} {money(first.total)}")
    second = system.book_hotel("Harbor House", "Bob", RoomType.STANDARD, stay.check_in, 3)
    print(f"  {second.reservation_id}: Bob, room {second.item} {money(second.total)} "
          f"(higher: hotel now {hotel.occupancy_on(stay.check_in):.0%} occupied)")
    print("\n" + hotel.availability_report(stay))

    print("\n-- Room overlap and date validation --")
    overlap = DateRange(date(2026, 6, 7), date(2026, 6, 9))
    print(f"  room 101 free for {overlap.check_in} -> {overlap.check_out}: "
          f"{hotel.is_available('101', overlap)}")
    print(f"  room 103 free for {overlap.check_in} -> {overlap.check_out}: "
          f"{hotel.is_available('103', overlap)}")
    try:
        DateRange(date(2026, 6, 5), date(2026, 6, 5))
    except ValueError as exc:
        print(f"  bad date range    -> {exc}")

    print("\n-- All reservations --")
    print(system.reservation_report())

    print("\n-- Cancel Bob's flight --")
    system.cancel(bob.reservation_id)
    print(f"  {bob.reservation_id} cancelled; seat {bob.item} is free again: "
          f"{bob.item in {s.code for s in flight.available_seats()}}")
    print(f"  Confirmed revenue: {money(system.revenue)}")
    print(f"  Active reservations: {sum(1 for r in system.reservations if r.status == 'CONFIRMED')} "
          f"of {len(system.reservations)}")
    return 0


def prompt_date(message: str, default: date) -> date:
    raw = input(f"{message} [{default.isoformat()}]: ").strip()
    return date.fromisoformat(raw) if raw else default


def prompt_class() -> SeatClass:
    options = ", ".join(f"{i + 1}={c.label}" for i, c in enumerate(SeatClass))
    raw = input(f"Class ({options}) [1]: ").strip() or "1"
    return list(SeatClass)[int(raw) - 1]


def prompt_room_type() -> RoomType:
    options = ", ".join(f"{i + 1}={t.label}" for i, t in enumerate(RoomType))
    raw = input(f"Room type ({options}) [1]: ").strip() or "1"
    return list(RoomType)[int(raw) - 1]


def interactive(today: date) -> int:
    """Menu-driven reservation console."""
    system = build_sample_system()
    while True:
        print(
            "\n1) Flights          2) Seat map         3) Book flight\n"
            "4) Hotel availability 5) Book hotel     6) Reservations\n"
            "7) Cancel           8) Quit"
        )
        try:
            choice = input("Choice: ").strip()
        except EOFError:
            print()
            return 0
        try:
            if choice == "1":
                for flight in system.flights.values():
                    print(f"{flight.number} {flight.origin}->{flight.destination} "
                          f"{flight.departure} occupancy {flight.occupancy:.0%}")
                    print(flight.class_summary())
            elif choice == "2":
                print(system.flights[input("Flight number: ").strip().upper()].seat_map())
            elif choice == "3":
                number = input("Flight number: ").strip().upper()
                customer = input("Passenger name: ").strip()
                seat = input("Seat (blank = auto-assign): ").strip() or None
                reservation = system.book_flight(
                    number, customer, prompt_class() if not seat else None, seat
                )
                print(f"Booked {reservation.reservation_id}, seat {reservation.item}, "
                      f"{money(reservation.total)}.")
            elif choice == "4":
                name = input("Hotel name: ").strip()
                check_in = prompt_date("Check-in", today + timedelta(days=7))
                nights = int(input("Nights [2]: ").strip() or "2")
                stay = DateRange(check_in, check_in + timedelta(days=nights))
                print(system.hotel(name).availability_report(stay))
            elif choice == "5":
                name = input("Hotel name: ").strip()
                customer = input("Guest name: ").strip()
                room_type = prompt_room_type()
                check_in = prompt_date("Check-in", today + timedelta(days=7))
                nights = int(input("Nights [2]: ").strip() or "2")
                reservation = system.book_hotel(name, customer, room_type, check_in, nights)
                print(f"Booked {reservation.reservation_id}, room {reservation.item}, "
                      f"{money(reservation.total)}.")
            elif choice == "6":
                print(system.reservation_report())
            elif choice == "7":
                reservation = system.cancel(input("Reservation id: ").strip().upper())
                print(f"Cancelled {reservation.reservation_id}.")
            elif choice == "8":
                print("Goodbye.")
                return 0
            else:
                print("Please choose 1-8.")
        except (ReservationError, ValueError, KeyError, IndexError) as exc:
            print(f"Error: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Book airline seats and hotel rooms with tiered, dynamic pricing.",
        epilog="Run without arguments for the interactive reservation menu.",
    )
    parser.add_argument("--demo", action="store_true", help="run the scripted demo")
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=date.today(),
        metavar="YYYY-MM-DD",
        help="reference date for interactive booking defaults (default: today)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.demo:
        return run_demo()
    try:
        return interactive(args.today)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
