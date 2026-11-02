# Patient / Doctor Scheduler

**Category:** Classes · **Project:** `Classes/Patient-Doctor-Scheduler`

## Problem

Create a patient class and a doctor class. Have a doctor that can handle
multiple patients and set up a scheduling program where a doctor can only
handle 16 patients during an 8 hour work day.

## Features

- `Patient` record with id, name, date of birth, optional phone and age
  calculation.
- `Doctor` with specialty, configurable 8-hour working day, 30-minute slots and
  a hard capacity of 16 patients per day.
- `Appointment` immutable record with start/end times, reason and overlap
  detection.
- `Scheduler` supports adding patients/doctors, booking, cancelling,
  availability queries, daily loads, per-doctor day schedules and per-patient
  schedules.
- Conflict prevention: doctor double-booking, patient double-booking (even
  across doctors), weekends, off-grid times and daily capacity.
- `--demo` prints a full day schedule, patient view and rejection messages.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py
python3 solution.py --today 2026-06-08
```

- `--demo` runs a scripted clinic day (three doctors, five patients), shows
  conflicts and cancellation, and exits 0.
- `--today YYYY-MM-DD` sets the default date used by interactive prompts.
- With no arguments the interactive menu manages doctors and patients, books
  appointments (listing free slots), prints day/patient schedules and cancels
  appointments.

## Example Output

```
== Patient / Doctor Scheduler Demo ==
Doctors work 8-hour days: 16 slots x 30 min = max 16 patients/day.

-- Booking appointments --
  APT-0001: Ava Thompson with Dr. Maya Chen at 09:00 (Annual physical)
  APT-0002: Noah Williams with Dr. Maya Chen at 09:30 (Blood pressure review)
  APT-0003: Mia Rodriguez with Dr. Maya Chen at 10:00 (Vaccination)
  APT-0004: Liam Brown with Dr. Omar Haddad at 09:00 (Chest pain follow-up)
  APT-0005: Ava Thompson with Dr. Omar Haddad at 10:30 (ECG review)
  APT-0006: Sofia Garcia with Dr. Lena Fischer at 11:00 (Eczema check)

-- Monday schedule --
Schedule for Monday, June 08, 2026
==============================================================
Dr. Maya Chen - General Practice (3/16 patients)
   09:00-09:30  Ava Thompson (P-001)  Annual physical
   09:30-10:00  Noah Williams (P-002)  Blood pressure review
   10:00-10:30  Mia Rodriguez (P-003)  Vaccination
   13 slot(s) still free
Dr. Omar Haddad - Cardiology (2/16 patients)
   09:00-09:30  Liam Brown (P-004)  Chest pain follow-up
   10:30-11:00  Ava Thompson (P-001)  ECG review
   14 slot(s) still free

-- Conflicts and invalid requests --
  doctor double-booked -> Dr. Maya Chen is already booked at 09:00 on 2026-06-08
  patient double-booked -> Ava Thompson already has Dr. Maya Chen at 09:00 on 2026-06-08
  weekend              -> Dr. Maya Chen does not work on Saturdays
  off-grid time        -> 08:15 is not a slot for Dr. Maya Chen (slots run 09:00-17:00)
  unknown patient      -> unknown patient: P-999
```

## Implementation Notes

`Doctor.slots` is generated from `work_start`, `slot_minutes` and the fixed
eight-hour work day; the default is 16 × 30 minutes = 09:00–17:00. The
16-patient cap is a separate `capacity_per_day` that is validated to be at most
16, so a doctor with shorter slots can have more than 16 grid slots but still
cannot accept a seventeenth patient. `Scheduler.schedule` enforces the cap
explicitly and `available_slots` returns nothing once it is reached.

Booking checks, in order: doctor works that weekday → start is on the slot grid
→ doctor is below capacity → no existing appointment at that slot → no
overlapping appointment for the same patient with any doctor. The overlap test
compares `datetime` spans rather than just start times, so it also works if a
doctor is configured with a different slot length.

Appointments are stored in a dict keyed by id; per-doctor/day and per-patient
views filter that dict, which is O(n) in total appointments and entirely
adequate for a single clinic. `--demo` is deterministic: fixed dates, doctors
and patients, with no clock or network access.
