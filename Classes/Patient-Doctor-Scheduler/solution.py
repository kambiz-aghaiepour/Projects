#!/usr/bin/env python3
"""Patient / doctor scheduling with a hard 16-patient daily capacity.

A doctor works an 8-hour day split into 16 thirty-minute slots (09:00-17:00 by
default).  ``Scheduler`` prevents double-booking a doctor, booking one patient
in two places at once, weekend appointments and out-of-grid times, and refuses
to exceed each doctor's daily capacity.

The domain classes (``Patient``, ``Doctor``, ``Appointment``, ``Scheduler``)
are independent of the CLI.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

SLOT_MINUTES = 30
SLOTS_PER_DAY = 16
WORKDAY_MINUTES = 8 * 60


class SchedulerError(Exception):
    """Raised when an appointment cannot be scheduled or cancelled."""


@dataclass(frozen=True)
class Patient:
    """A patient record."""

    patient_id: str
    name: str
    date_of_birth: date
    phone: str = ""

    def __post_init__(self) -> None:
        if not self.patient_id.strip():
            raise ValueError("patient id must not be empty")
        if not self.name.strip():
            raise ValueError("patient name must not be empty")
        if not isinstance(self.date_of_birth, date):
            raise ValueError("date of birth must be a date")
        if self.date_of_birth > date.today():
            raise ValueError("date of birth cannot be in the future")
        if self.phone and not self.phone.strip():
            raise ValueError("phone must not be blank when provided")

    def age_on(self, on: date) -> int:
        years = on.year - self.date_of_birth.year
        before_birthday = (on.month, on.day) < (
            self.date_of_birth.month,
            self.date_of_birth.day,
        )
        return years - int(before_birthday)

    def __str__(self) -> str:
        return f"{self.patient_id} {self.name}"


@dataclass(frozen=True)
class Appointment:
    """A booked 30-minute slot."""

    appointment_id: str
    doctor_id: str
    patient_id: str
    day: date
    start: time
    duration_minutes: int = SLOT_MINUTES
    reason: str = ""

    @property
    def starts_at(self) -> datetime:
        return datetime.combine(self.day, self.start)

    @property
    def ends_at(self) -> datetime:
        return self.starts_at + timedelta(minutes=self.duration_minutes)

    @property
    def end(self) -> time:
        return self.ends_at.time()

    def overlaps(self, other: "Appointment") -> bool:
        return self.starts_at < other.ends_at and other.starts_at < self.ends_at

    def __str__(self) -> str:
        window = f"{self.start:%H:%M}-{self.end:%H:%M}"
        return f"{self.day} {window} [{self.appointment_id}]"


class Doctor:
    """A doctor with a fixed daily slot grid and patient capacity."""

    def __init__(
        self,
        doctor_id: str,
        name: str,
        specialty: str,
        work_start: time = time(9, 0),
        slot_minutes: int = SLOT_MINUTES,
        capacity_per_day: int = SLOTS_PER_DAY,
    ) -> None:
        if not doctor_id.strip() or not name.strip():
            raise ValueError("doctor id and name are required")
        if slot_minutes <= 0:
            raise ValueError("slot length must be positive")
        if WORKDAY_MINUTES % slot_minutes:
            raise ValueError("slot length must divide an 8-hour work day")
        if not 1 <= capacity_per_day <= SLOTS_PER_DAY:
            raise ValueError(f"capacity must be between 1 and {SLOTS_PER_DAY} patients/day")
        self.doctor_id = doctor_id.strip().upper()
        self.name = name.strip()
        self.specialty = specialty.strip() or "General Practice"
        self.work_start = work_start
        self.slot_minutes = slot_minutes
        self.capacity_per_day = capacity_per_day
        self.slots_per_day = WORKDAY_MINUTES // slot_minutes

    @property
    def slots(self) -> tuple[time, ...]:
        """All bookable start times in one eight-hour working day."""
        origin = datetime.combine(date(2000, 1, 1), self.work_start)
        return tuple(
            (origin + timedelta(minutes=self.slot_minutes * index)).time()
            for index in range(self.slots_per_day)
        )

    @property
    def work_end(self) -> time:
        origin = datetime.combine(date(2000, 1, 1), self.work_start)
        return (origin + timedelta(minutes=WORKDAY_MINUTES)).time()

    def works_on(self, day: date) -> bool:
        """Monday-Friday only."""
        return day.weekday() < 5

    def __str__(self) -> str:
        return f"{self.doctor_id} {self.name} ({self.specialty})"


class Scheduler:
    """Registry of patients, doctors and appointments."""

    def __init__(self) -> None:
        self._patients: dict[str, Patient] = {}
        self._doctors: dict[str, Doctor] = {}
        self._appointments: dict[str, Appointment] = {}
        self._counter = 0

    @property
    def patients(self) -> tuple[Patient, ...]:
        return tuple(self._patients.values())

    @property
    def doctors(self) -> tuple[Doctor, ...]:
        return tuple(self._doctors.values())

    @property
    def appointments(self) -> tuple[Appointment, ...]:
        return tuple(self._appointments.values())

    def add_patient(self, patient: Patient) -> Patient:
        if patient.patient_id in self._patients:
            raise SchedulerError(f"patient {patient.patient_id} already exists")
        self._patients[patient.patient_id] = patient
        return patient

    def add_doctor(self, doctor: Doctor) -> Doctor:
        if doctor.doctor_id in self._doctors:
            raise SchedulerError(f"doctor {doctor.doctor_id} already exists")
        self._doctors[doctor.doctor_id] = doctor
        return doctor

    def get_patient(self, patient_id: str) -> Patient:
        key = patient_id.strip().upper()
        try:
            return self._patients[key]
        except KeyError:
            raise SchedulerError(f"unknown patient: {key}") from None

    def get_doctor(self, doctor_id: str) -> Doctor:
        key = doctor_id.strip().upper()
        try:
            return self._doctors[key]
        except KeyError:
            raise SchedulerError(f"unknown doctor: {key}") from None

    def appointments_for(self, doctor_id: str, day: date) -> list[Appointment]:
        doctor = self.get_doctor(doctor_id)
        return sorted(
            (
                appointment
                for appointment in self._appointments.values()
                if appointment.doctor_id == doctor.doctor_id and appointment.day == day
            ),
            key=lambda appointment: appointment.start,
        )

    def available_slots(self, doctor_id: str, day: date) -> list[time]:
        doctor = self.get_doctor(doctor_id)
        if not doctor.works_on(day):
            return []
        appointments = self.appointments_for(doctor_id, day)
        if len(appointments) >= doctor.capacity_per_day:
            return []
        booked = {appointment.start for appointment in appointments}
        return [slot for slot in doctor.slots if slot not in booked]

    def daily_load(self, doctor_id: str, day: date) -> tuple[int, int]:
        doctor = self.get_doctor(doctor_id)
        return len(self.appointments_for(doctor_id, day)), doctor.capacity_per_day

    def schedule(
        self,
        doctor_id: str,
        patient_id: str,
        day: date,
        start: time,
        reason: str = "",
    ) -> Appointment:
        """Book a slot after checking working day, grid, capacity and conflicts."""
        doctor = self.get_doctor(doctor_id)
        patient = self.get_patient(patient_id)
        if not doctor.works_on(day):
            raise SchedulerError(f"{doctor.name} does not work on {day:%A}s")
        if start not in doctor.slots:
            raise SchedulerError(
                f"{start:%H:%M} is not a slot for {doctor.name} "
                f"(slots run {doctor.work_start:%H:%M}-{doctor.work_end:%H:%M})"
            )
        existing = self.appointments_for(doctor_id, day)
        if len(existing) >= doctor.capacity_per_day:
            raise SchedulerError(
                f"{doctor.name} is at capacity ({doctor.capacity_per_day} patients/day)"
            )
        if any(appointment.start == start for appointment in existing):
            raise SchedulerError(
                f"{doctor.name} is already booked at {start:%H:%M} on {day}"
            )
        candidate = Appointment(
            "",
            doctor.doctor_id,
            patient.patient_id,
            day,
            start,
            doctor.slot_minutes,
            reason,
        )
        for appointment in self._appointments.values():
            if appointment.patient_id == patient.patient_id and appointment.overlaps(candidate):
                other_doctor = self.get_doctor(appointment.doctor_id)
                raise SchedulerError(
                    f"{patient.name} already has {other_doctor.name} at "
                    f"{appointment.start:%H:%M} on {appointment.day}"
                )
        self._counter += 1
        appointment = Appointment(
            appointment_id=f"APT-{self._counter:04d}",
            doctor_id=doctor.doctor_id,
            patient_id=patient.patient_id,
            day=day,
            start=start,
            duration_minutes=doctor.slot_minutes,
            reason=reason,
        )
        self._appointments[appointment.appointment_id] = appointment
        return appointment

    def cancel(self, appointment_id: str) -> Appointment:
        key = appointment_id.strip().upper()
        try:
            appointment = self._appointments.pop(key)
        except KeyError:
            raise SchedulerError(f"unknown appointment: {key}") from None
        return appointment

    def patient_appointments(self, patient_id: str) -> list[Appointment]:
        patient = self.get_patient(patient_id)
        return sorted(
            (
                appointment
                for appointment in self._appointments.values()
                if appointment.patient_id == patient.patient_id
            ),
            key=lambda appointment: (appointment.day, appointment.start),
        )

    def day_report(self, day: date) -> str:
        lines = [f"Schedule for {day:%A, %B %d, %Y}", "=" * 62]
        for doctor in self.doctors:
            appointments = self.appointments_for(doctor.doctor_id, day)
            lines.append(
                f"{doctor.name} - {doctor.specialty} "
                f"({len(appointments)}/{doctor.capacity_per_day} patients)"
            )
            if not appointments:
                lines.append("   no appointments")
            for appointment in appointments:
                patient = self.get_patient(appointment.patient_id)
                reason = f"  {appointment.reason}" if appointment.reason else ""
                lines.append(
                    f"   {appointment.start:%H:%M}-{appointment.end:%H:%M}  "
                    f"{patient.name} ({patient.patient_id}){reason}"
                )
            free = len(self.available_slots(doctor.doctor_id, day))
            lines.append(f"   {free} slot(s) still free")
        return "\n".join(lines)

    def patient_report(self, patient_id: str) -> str:
        patient = self.get_patient(patient_id)
        lines = [f"Appointments for {patient.name} ({patient.patient_id})"]
        appointments = self.patient_appointments(patient_id)
        if not appointments:
            lines.append("  none booked")
        for appointment in appointments:
            doctor = self.get_doctor(appointment.doctor_id)
            reason = f" - {appointment.reason}" if appointment.reason else ""
            lines.append(
                f"  {appointment.day} {appointment.start:%H:%M}-{appointment.end:%H:%M} "
                f"with {doctor.name}{reason}"
            )
        return "\n".join(lines)


def build_sample_scheduler() -> Scheduler:
    """Create the deterministic demo doctors, patients and bookings."""
    scheduler = Scheduler()
    for doctor in (
        Doctor("D-01", "Dr. Maya Chen", "General Practice"),
        Doctor("D-02", "Dr. Omar Haddad", "Cardiology"),
        Doctor("D-03", "Dr. Lena Fischer", "Dermatology"),
    ):
        scheduler.add_doctor(doctor)
    for patient in (
        Patient("P-001", "Ava Thompson", date(1988, 4, 12), "555-0101"),
        Patient("P-002", "Noah Williams", date(1975, 11, 3), "555-0102"),
        Patient("P-003", "Mia Rodriguez", date(1996, 7, 21), "555-0103"),
        Patient("P-004", "Liam Brown", date(1962, 2, 9), "555-0104"),
        Patient("P-005", "Sofia Garcia", date(2001, 9, 30), "555-0105"),
    ):
        scheduler.add_patient(patient)
    return scheduler


def run_demo() -> int:
    """Book, report on, conflict-test and cancel appointments."""
    scheduler = build_sample_scheduler()
    monday = date(2026, 6, 8)
    print("== Patient / Doctor Scheduler Demo ==")
    print(f"Doctors work 8-hour days: {SLOTS_PER_DAY} slots x {SLOT_MINUTES} min "
          f"= max {SLOTS_PER_DAY} patients/day.\n")

    bookings = (
        ("D-01", "P-001", time(9, 0), "Annual physical"),
        ("D-01", "P-002", time(9, 30), "Blood pressure review"),
        ("D-01", "P-003", time(10, 0), "Vaccination"),
        ("D-02", "P-004", time(9, 0), "Chest pain follow-up"),
        ("D-02", "P-001", time(10, 30), "ECG review"),
        ("D-03", "P-005", time(11, 0), "Eczema check"),
    )
    print("-- Booking appointments --")
    for doctor_id, patient_id, start, reason in bookings:
        appointment = scheduler.schedule(doctor_id, patient_id, monday, start, reason)
        doctor = scheduler.get_doctor(doctor_id)
        patient = scheduler.get_patient(patient_id)
        print(f"  {appointment.appointment_id}: {patient.name} with {doctor.name} "
              f"at {start:%H:%M} ({reason})")

    print("\n-- Monday schedule --")
    print(scheduler.day_report(monday))

    print("\n-- Patient view: Ava Thompson --")
    print(scheduler.patient_report("P-001"))

    print("\n-- Conflicts and invalid requests --")
    invalid = (
        ("doctor double-booked", lambda: scheduler.schedule("D-01", "P-004", monday, time(9, 0))),
        ("patient double-booked", lambda: scheduler.schedule("D-03", "P-001", monday, time(9, 0))),
        ("weekend", lambda: scheduler.schedule("D-01", "P-004", date(2026, 6, 13), time(9, 0))),
        ("off-grid time", lambda: scheduler.schedule("D-01", "P-004", monday, time(8, 15))),
        ("unknown patient", lambda: scheduler.schedule("D-01", "P-999", monday, time(11, 0))),
    )
    for label, action in invalid:
        try:
            action()
            print(f"  {label:<20} -> unexpectedly succeeded")
        except SchedulerError as exc:
            print(f"  {label:<20} -> {exc}")

    print("\n-- Availability for Dr. Maya Chen --")
    free = scheduler.available_slots("D-01", monday)
    used, capacity = scheduler.daily_load("D-01", monday)
    print(f"  {used}/{capacity} patients booked; free: "
          + ", ".join(f"{slot:%H:%M}" for slot in free))

    print("\n-- Cancel APT-0002 --")
    cancelled = scheduler.cancel("APT-0002")
    print(f"  cancelled {cancelled}; free slots now: "
          + ", ".join(f"{slot:%H:%M}" for slot in scheduler.available_slots("D-01", monday)))
    print(f"  Dr. Chen load: {scheduler.daily_load('D-01', monday)[0]}/16")

    print("\n-- Tuesday schedule (empty) --")
    print(scheduler.day_report(date(2026, 6, 9)))
    return 0


def prompt_date(message: str, default: date) -> date:
    raw = input(f"{message} [{default.isoformat()}]: ").strip()
    return date.fromisoformat(raw) if raw else default


def prompt_time(message: str, default: time) -> time:
    raw = input(f"{message} [{default:%H:%M}]: ").strip()
    return time.fromisoformat(raw) if raw else default


def interactive(today: date) -> int:
    """Menu-driven scheduler console with no preloaded data."""
    scheduler = Scheduler()
    menu = (
        "\n1) Doctors         2) Patients         3) Add patient\n"
        "4) Add doctor      5) Book appointment 6) Day schedule\n"
        "7) Patient schedule 8) Cancel          9) Quit"
    )
    while True:
        print(menu)
        try:
            choice = input("Choice: ").strip()
        except EOFError:
            print()
            return 0
        try:
            if choice == "1":
                for doctor in scheduler.doctors:
                    print(f"{doctor} slots {doctor.slots[0]:%H:%M}-{doctor.work_end:%H:%M} "
                          f"({doctor.capacity_per_day} patients/day)")
            elif choice == "2":
                for patient in scheduler.patients:
                    print(f"{patient} born {patient.date_of_birth}")
            elif choice == "3":
                patient = Patient(
                    input("Patient id: ").strip(),
                    input("Name: ").strip(),
                    prompt_date("Date of birth", date(1990, 1, 1)),
                    input("Phone (optional): ").strip(),
                )
                scheduler.add_patient(patient)
                print(f"Added {patient}.")
            elif choice == "4":
                doctor = Doctor(
                    input("Doctor id: ").strip(),
                    input("Name: ").strip(),
                    input("Specialty: ").strip(),
                )
                scheduler.add_doctor(doctor)
                print(f"Added {doctor}.")
            elif choice == "5":
                doctor_id = input("Doctor id: ").strip()
                patient_id = input("Patient id: ").strip()
                day = prompt_date("Date", today)
                free = scheduler.available_slots(doctor_id, day)
                if free:
                    print("Free slots: " + ", ".join(f"{slot:%H:%M}" for slot in free))
                start = prompt_time("Time", free[0] if free else time(9, 0))
                reason = input("Reason (optional): ").strip()
                appointment = scheduler.schedule(doctor_id, patient_id, day, start, reason)
                print(f"Booked {appointment}.")
            elif choice == "6":
                print(scheduler.day_report(prompt_date("Date", today)))
            elif choice == "7":
                print(scheduler.patient_report(input("Patient id: ").strip()))
            elif choice == "8":
                appointment = scheduler.cancel(input("Appointment id: ").strip())
                print(f"Cancelled {appointment}.")
            elif choice == "9":
                print("Goodbye.")
                return 0
            else:
                print("Please choose 1-9.")
        except (SchedulerError, ValueError, KeyError) as exc:
            print(f"Error: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Schedule patients with doctors at 16 slots per 8-hour day.",
        epilog="Run without arguments for the interactive scheduler.",
    )
    parser.add_argument("--demo", action="store_true", help="run the scripted demo")
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=date.today(),
        metavar="YYYY-MM-DD",
        help="default date for interactive prompts (default: today)",
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
