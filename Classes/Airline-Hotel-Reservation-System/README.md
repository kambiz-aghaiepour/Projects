# Airline / Hotel Reservation System

**Category:** Classes · **Project:** `Classes/Airline-Hotel-Reservation-System`

## Problem

Create a reservation system which books airline seats or hotel rooms. It
charges various rates for particular sections of the plane or hotel. Keep track
of when rooms will be available and can be scheduled.

## Features

- **Flights** with a 20-row, six-seat cabin split into First, Business,
  Premium and Economy classes; each class has its own fare multiplier.
- **Hotels** with explicit `Room` records (number + tier), booked over
  check-in / check-out date ranges.
- **Dynamic pricing**:
  - flight fare = base fare × class multiplier × (1 + 0.5 × cabin occupancy)
  - hotel night = base rate × room multiplier × occupancy factor × weekend
    surcharge (Friday and Saturday nights)
- Availability queries by class/room type, seat maps, conflict detection for
  occupied seats and overlapping stays, and cancellation that frees inventory.
- A shared reservation ledger with sequential ids and confirmed revenue.
- `DateRange` enforces a check-out after check-in and computes nights.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py
python3 solution.py --today 2026-06-01
```

- `--demo` runs a scripted booking/cancellation walkthrough (no input, no
  network) and exits 0.
- `--today YYYY-MM-DD` sets the reference date used for interactive booking
  defaults.
- With no arguments the interactive menu offers flight listings, seat maps,
  flight booking, hotel availability, hotel booking, reservation listing and
  cancellation.

## Example Output

```
Flight NA-101: San Francisco -> New York on 2026-06-10 (base fare $220.00)
  Economy  rows 11-20   60/60  free  from $220.00
  Premium  rows 6-10   30/30  free  from $297.00
  Business rows 3-5    18/18  free  from $418.00
  First    rows 1-2    12/12  free  from $660.00

-- Booking flights --
  RSV-0001: Alice, seat 11A (Economy) $220.00
  RSV-0002: Bob, seat 3C (Business) $419.74
  RSV-0003: Carol, seat 1A (First) $665.50

-- Demand pricing: economy after 3 seats are sold --
  Economy fare now $222.75 (occupancy 2.5%)
  RSV-0004: Dave, seat 11B $222.75

-- Conflict handling --
  seat 3C again    -> seat 3C is already booked
  wrong fare class -> seat 12A is Economy, not First
  unknown flight   -> unknown flight: NA-999

Harbor House (Boston) availability 2026-06-05 -> 2026-06-08:
  Standard  4/4  free       $510.00 total
  Deluxe    3/3  free       $714.00 total
  Suite     2/2  free     $1,122.00 total
  RSV-0007: Alice, room 101 $510.00
  RSV-0008: Bob, room 102 $524.17 (higher: hotel now 22% occupied)
```

## Implementation Notes

The cabin is generated from row ranges, so availability and seat maps are
derived from a dict of `Seat` records rather than stored twice. A booking's
seat is its `item`; cancelling pops the reservation and the seat immediately
becomes available again.

Hotel occupancy is recomputed per night from active reservations, so a booking
made later in the day sees the higher demand price. Each hotel night is priced
separately and summed, which makes weekend surcharges and per-night demand
straightforward. `Decimal` is used for all money and quantised to cents with
`ROUND_HALF_UP`.

Reservation ids are allocated by `ReservationSystem` before a venue validates
the request, so a rejected request can leave a gap in the sequence — the same
behaviour as many real booking systems. Search and cancellation are O(1) by id;
availability is O(rooms × bookings) and is intended for small properties, not
a full inventory service.
