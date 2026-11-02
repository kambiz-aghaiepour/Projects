#!/usr/bin/env python3
"""Quiz Maker: build randomized quizzes from a JSON question bank and grade them.

A question bank is a JSON document with a title and a list of questions of
three kinds: ``multiple_choice`` (2+ choices and a correct index/letter),
``true_false`` and ``short_answer`` (one or more accepted answers).

Typical flow::

    python3 solution.py --bank questions.json --build --count 5 --seed 42 \
        --quiz-out quiz.txt --key-out key.json
    python3 solution.py --grade answers.json --key key.json

The quiz file never contains the answers; the answer key is written
separately so it can be withheld from students.  ``--demo`` runs the whole
build/grade cycle offline on a bundled question bank.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
import textwrap
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_TYPES = ("multiple_choice", "true_false", "short_answer")
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class QuizError(Exception):
    """Raised for malformed banks, keys or answer files."""


# --------------------------------------------------------------------------
# Question model
# --------------------------------------------------------------------------


@dataclass
class Question:
    """One question with its canonical answer and optional metadata."""

    id: str
    type: str
    prompt: str
    choices: list[str] = field(default_factory=list)
    answer: Any = None
    explanation: str = ""
    tags: list[str] = field(default_factory=list)

    def answer_text(self) -> str:
        """Human-readable rendering of the correct answer."""
        if self.type == "multiple_choice":
            idx = int(self.answer)
            return f"{LETTERS[idx]}) {self.choices[idx]}"
        if self.type == "true_false":
            return "True" if self.answer else "False"
        accepted = self.answer if isinstance(self.answer, list) else [self.answer]
        return " / ".join(str(a) for a in accepted)

    def to_key_entry(self, number: int) -> dict[str, Any]:
        return {
            "number": number,
            "id": self.id,
            "type": self.type,
            "prompt": self.prompt,
            "choices": self.choices,
            "answer": self.answer,
            "answer_text": self.answer_text(),
            "explanation": self.explanation,
        }


def _canonical_mc(value: Any, choices: list[str], qid: str) -> int:
    """Convert an index, letter or exact choice text into a 0-based index."""
    idx: int | None = None
    if isinstance(value, bool):
        raise QuizError(f"question {qid!r}: boolean is not a choice answer")
    if isinstance(value, int):
        idx = value
    elif isinstance(value, str):
        text = value.strip()
        if len(text) == 1 and text.upper() in LETTERS:
            idx = LETTERS.index(text.upper())
        elif text.isdigit():
            idx = int(text)
        else:
            folded = [c.casefold() for c in choices]
            if text.casefold() in folded:
                idx = folded.index(text.casefold())
    if idx is None or not 0 <= idx < len(choices):
        raise QuizError(f"question {qid!r}: answer {value!r} does not match any choice")
    return idx


def _canonical_tf(value: Any, qid: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {
        "true", "t", "yes", "y", "1",
    }:
        return True
    if isinstance(value, str) and value.strip().lower() in {
        "false", "f", "no", "n", "0",
    }:
        return False
    raise QuizError(f"question {qid!r}: expected true/false, got {value!r}")


def _canonical_short(value: Any, qid: str) -> list[str]:
    values = value if isinstance(value, list) else [value]
    answers = [str(v).strip() for v in values if str(v).strip()]
    if not answers:
        raise QuizError(f"question {qid!r}: short answer needs at least one value")
    return answers


def question_from_dict(raw: dict[str, Any], index: int) -> Question:
    """Validate one bank entry and return a :class:`Question`."""
    if not isinstance(raw, dict):
        raise QuizError(f"question #{index + 1}: expected an object")
    qid = str(raw.get("id") or f"q{index + 1}").strip()
    qtype = str(raw.get("type", "")).strip().lower()
    prompt = str(raw.get("prompt", "")).strip()
    if qtype not in VALID_TYPES:
        raise QuizError(f"question {qid!r}: unknown type {qtype!r}")
    if not prompt:
        raise QuizError(f"question {qid!r}: empty prompt")

    if qtype == "multiple_choice":
        choices = raw.get("choices")
        if not isinstance(choices, list) or len(choices) < 2:
            raise QuizError(f"question {qid!r}: multiple_choice needs 2+ choices")
        choices = [str(c) for c in choices]
        answer = _canonical_mc(raw.get("answer"), choices, qid)
    elif qtype == "true_false":
        choices = ["True", "False"]
        answer = _canonical_tf(raw.get("answer"), qid)
    else:
        choices = []
        answer = _canonical_short(raw.get("answer"), qid)

    return Question(
        id=qid,
        type=qtype,
        prompt=prompt,
        choices=choices,
        answer=answer,
        explanation=str(raw.get("explanation", "")).strip(),
        tags=[str(t) for t in raw.get("tags", [])],
    )


def load_bank(path: Path) -> tuple[str, list[Question]]:
    """Load and validate a question bank JSON file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise QuizError(f"bank not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise QuizError(f"bank is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        raise QuizError("bank must be an object with a 'questions' list")
    questions = [question_from_dict(q, i) for i, q in enumerate(data["questions"])]
    if not questions:
        raise QuizError("bank contains no questions")
    ids = [q.id for q in questions]
    if len(ids) != len(set(ids)):
        raise QuizError("bank contains duplicate question ids")
    return str(data.get("title", "Untitled Quiz")), questions


# --------------------------------------------------------------------------
# Building and grading
# --------------------------------------------------------------------------


def select_questions(
    questions: list[Question], count: int | None, seed: int | None
) -> list[Question]:
    """Pick ``count`` distinct questions; a seed makes the choice reproducible."""
    if count is None:
        count = min(5, len(questions))
    if count < 1:
        raise QuizError("--count must be at least 1")
    if count > len(questions):
        raise QuizError(
            f"requested {count} questions but the bank only has {len(questions)}"
        )
    rng = random.Random(seed)
    return rng.sample(questions, count)


def format_quiz(title: str, questions: list[Question], meta: dict[str, Any]) -> str:
    """Render the student-facing quiz (no answers)."""
    lines = [title, "=" * len(title), ""]
    if meta.get("seed") is not None:
        lines.append(f"Seed: {meta['seed']}")
    lines.append(f"Questions: {len(questions)}")
    lines.append("")
    width = 76
    for number, q in enumerate(questions, 1):
        lines.append(f"{number}. {q.prompt}")
        for i, choice in enumerate(q.choices):
            wrapped = textwrap.fill(
                f"{LETTERS[i]}) {choice}", width=width, subsequent_indent="     "
            )
            lines.append("   " + wrapped)
        if q.type == "short_answer":
            lines.append("   Answer: " + "_" * 40)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_key(
    title: str, questions: list[Question], seed: int | None
) -> dict[str, Any]:
    return {
        "quiz_id": uuid.uuid4().hex[:12],
        "title": title,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": seed,
        "questions": [q.to_key_entry(n) for n, q in enumerate(questions, 1)],
    }


def load_answers(path: Path) -> dict[str, Any]:
    """Accept ``{"answers": {...}}`` or a flat ``{qid: answer}`` mapping."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise QuizError(f"answers file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise QuizError(f"answers file is not valid JSON: {exc}") from exc
    if isinstance(data, dict) and isinstance(data.get("answers"), dict):
        return data["answers"]
    if isinstance(data, dict):
        return data
    raise QuizError("answers file must be a JSON object")


def _grade_one(question: dict[str, Any], response: Any) -> tuple[bool, str]:
    """Return (correct, feedback) for a single key entry."""
    qtype = question["type"]
    expected = question["answer"]
    if response is None:
        return False, "no answer given"
    try:
        if qtype == "multiple_choice":
            got = _canonical_mc(response, question["choices"], question["id"])
            return got == int(expected), f"you answered {LETTERS[got]}"
        if qtype == "true_false":
            got = _canonical_tf(response, question["id"])
            return got == bool(expected), f"you answered {got}"
    except QuizError:
        return False, f"unrecognized answer: {response!r}"

    accepted = expected if isinstance(expected, list) else [expected]
    normalized = " ".join(str(response).strip().casefold().split())
    for candidate in accepted:
        want = " ".join(str(candidate).strip().casefold().split())
        if normalized == want:
            return True, "exact match"
    try:
        if float(normalized) == float(accepted[0]):
            return True, "numeric match"
    except (TypeError, ValueError):
        pass
    return False, f"you answered {str(response).strip()!r}"


def grade_quiz(key: dict[str, Any], answers: dict[str, Any]) -> tuple[int, list[str]]:
    """Grade responses against a key; return (score, printable feedback lines)."""
    entries = key.get("questions")
    if not isinstance(entries, list) or not entries:
        raise QuizError("answer key has no questions")
    score = 0
    lines: list[str] = []
    for entry in entries:
        qid = entry["id"]
        number = entry.get("number", "?")
        correct, feedback = _grade_one(entry, answers.get(qid))
        score += int(correct)
        mark = "CORRECT" if correct else "WRONG"
        lines.append(f"{number:>3}. [{mark}] {entry['prompt']}")
        if correct:
            lines.append(f"     {feedback}")
        else:
            lines.append(f"     {feedback}; correct answer: {entry['answer_text']}")
            if entry.get("explanation"):
                lines.append(f"     Why: {entry['explanation']}")
    total = len(entries)
    percent = round(100 * score / total, 1)
    lines.append("")
    lines.append(f"Score: {score}/{total} ({percent}%)")
    return score, lines


# --------------------------------------------------------------------------
# Sample bank + demo
# --------------------------------------------------------------------------

SAMPLE_BANK: dict[str, Any] = {
    "title": "Python & Computer Science Warm-up",
    "questions": [
        {
            "id": "list-comp",
            "type": "multiple_choice",
            "prompt": "Which expression builds a list of squares for 0..4?",
            "choices": [
                "[x * x for x in range(5)]",
                "(x * x for x in range(5))",
                "map(x * x, range(5))",
                "[x ^ 2 for x in range(5)]",
            ],
            "answer": 0,
            "explanation": "A list comprehension with square brackets returns a list.",
            "tags": ["python", "syntax"],
        },
        {
            "id": "mutable-default",
            "type": "true_false",
            "prompt": "A mutable default argument such as def f(x=[]) is shared "
            "between calls.",
            "answer": True,
            "explanation": "Defaults are evaluated once, when the function is defined.",
            "tags": ["python", "pitfalls"],
        },
        {
            "id": "big-o",
            "type": "multiple_choice",
            "prompt": "What is the average-case complexity of lookup in a hash table?",
            "choices": ["O(1)", "O(log n)", "O(n)", "O(n log n)"],
            "answer": "A",
            "explanation": "Hashing gives constant-time average lookup.",
            "tags": ["algorithms"],
        },
        {
            "id": "short-gil",
            "type": "short_answer",
            "prompt": "Name the CPython mechanism that prevents multiple threads "
            "from executing Python bytecode at once (abbreviation).",
            "answer": ["GIL", "Global Interpreter Lock"],
            "explanation": "The Global Interpreter Lock serializes bytecode execution.",
            "tags": ["python", "concurrency"],
        },
        {
            "id": "http-get",
            "type": "multiple_choice",
            "prompt": "Which HTTP method is defined as safe and idempotent for reads?",
            "choices": ["GET", "POST", "PATCH", "CONNECT"],
            "answer": "GET",
            "tags": ["web"],
        },
        {
            "id": "sql-select",
            "type": "true_false",
            "prompt": "SELECT statements can be used inside a transaction.",
            "answer": True,
            "tags": ["databases"],
        },
        {
            "id": "encoding",
            "type": "short_answer",
            "prompt": "Which text encoding is the default source encoding for Python 3?",
            "answer": ["UTF-8", "utf8", "utf-8"],
            "explanation": "Python 3 source files are UTF-8 unless declared otherwise.",
            "tags": ["python"],
        },
        {
            "id": "git-branch",
            "type": "multiple_choice",
            "prompt": "Which command creates and switches to a new branch?",
            "choices": [
                "git branch new",
                "git checkout -b new",
                "git merge new",
                "git remote add new",
            ],
            "answer": 1,
            "tags": ["git"],
        },
    ],
}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def make_demo_answers(key: dict[str, Any], wrong: int = 2) -> dict[str, Any]:
    """Answer every question correctly except the last ``wrong`` ones."""
    answers: dict[str, Any] = {}
    entries = key["questions"]
    for entry in entries[: len(entries) - wrong]:
        answer = entry["answer"]
        if entry["type"] == "multiple_choice":
            answers[entry["id"]] = LETTERS[int(answer)]
        elif entry["type"] == "true_false":
            answers[entry["id"]] = bool(answer)
        else:
            accepted = answer if isinstance(answer, list) else [answer]
            answers[entry["id"]] = accepted[0]
    for entry in entries[len(entries) - wrong:]:
        if entry["type"] == "multiple_choice":
            correct_letter = LETTERS[int(entry["answer"])]
            answers[entry["id"]] = "A" if correct_letter != "A" else "B"
        elif entry["type"] == "true_false":
            answers[entry["id"]] = not bool(entry["answer"])
        else:
            answers[entry["id"]] = "deliberately wrong"
    return answers


def run_demo() -> int:
    """Build a seeded quiz, answer it, grade it, and verify determinism."""
    with tempfile.TemporaryDirectory(prefix="quizmaker-") as tmp:
        work = Path(tmp)
        bank_path = work / "questions.json"
        write_json(bank_path, SAMPLE_BANK)
        title, questions = load_bank(bank_path)
        print(f"Loaded bank: {title} ({len(questions)} questions)")

        selected = select_questions(questions, 5, seed=42)
        quiz_text = format_quiz(title, selected, {"seed": 42})
        key = build_key(title, selected, seed=42)
        quiz_path, key_path = work / "quiz.txt", work / "key.json"
        quiz_path.write_text(quiz_text, encoding="utf-8")
        write_json(key_path, key)

        print("\n--- quiz.txt ---")
        print(quiz_text, end="")
        assert "answer_text" not in quiz_text and "explanation" not in quiz_text

        answers = make_demo_answers(key, wrong=2)
        answers_path = work / "answers.json"
        write_json(answers_path, {"quiz_id": key["quiz_id"], "answers": answers})
        print(f"Wrote {quiz_path.name}, {key_path.name}, {answers_path.name}")

        score, feedback = grade_quiz(key, load_answers(answers_path))
        print("\n--- graded feedback ---")
        print("\n".join(feedback))
        assert score == 3, f"expected 3 correct, got {score}"

        again = select_questions(questions, 5, seed=42)
        assert [q.id for q in again] == [q.id for q in selected]
        print("\nDeterminism check: seed 42 selected the same 5 questions.")

        # A key without explanations for a wrong answer must still grade.
        blank_key = dict(key, questions=[dict(key["questions"][0], explanation="")])
        blank_score, _ = grade_quiz(blank_key, {key["questions"][0]["id"]: "?"})
        assert blank_score == 0
        print("Edge case check: unrecognized answer graded as wrong.")
        print("\nDemo complete: build + key + grade pipeline works.")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def interactive(bank_path: Path | None) -> int:
    """Prompt for a bank, build a quiz, collect answers and grade."""
    default = str(bank_path) if bank_path else "questions.json"
    raw = input(f"Question bank [{default}]: ").strip() or default
    try:
        title, questions = load_bank(Path(raw))
        count_raw = input(f"How many questions? [{min(5, len(questions))}]: ").strip()
        count = int(count_raw) if count_raw else min(5, len(questions))
        seed_raw = input("Random seed (blank for random): ").strip()
        seed = int(seed_raw) if seed_raw else None
        selected = select_questions(questions, count, seed)
    except (QuizError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print()
    print(format_quiz(title, selected, {"seed": seed}))
    answers: dict[str, Any] = {}
    for q in selected:
        answers[q.id] = input(f"Answer for {q.id}: ").strip()
    key = build_key(title, selected, seed)
    score, feedback = grade_quiz(key, answers)
    print("\n".join(feedback))
    return 0 if score >= 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build randomized quizzes from a JSON bank and grade answer files.",
        epilog="Run with --demo for a scripted end-to-end example.",
    )
    parser.add_argument("--bank", type=Path, help="path to the JSON question bank")
    parser.add_argument("--list", action="store_true", help="list questions in the bank")
    parser.add_argument("--build", action="store_true", help="build a quiz")
    parser.add_argument("--count", type=int, default=None,
                        help="questions per quiz (default 5, or the bank size if smaller)")
    parser.add_argument("--seed", type=int, help="RNG seed for reproducible selection")
    parser.add_argument("--quiz-out", type=Path, help="write the student quiz here")
    parser.add_argument("--key-out", type=Path, help="write the answer key JSON here")
    parser.add_argument(
        "--grade", type=Path, metavar="ANSWERS",
        help="grade a JSON answer file against --key",
    )
    parser.add_argument("--key", type=Path, help="answer key JSON for --grade")
    parser.add_argument("--demo", action="store_true", help="run the offline demo")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.demo:
        return run_demo()

    if args.grade:
        if not args.key:
            print("error: --grade requires --key", file=sys.stderr)
            return 2
        try:
            key = json.loads(args.key.read_text(encoding="utf-8"))
            score, feedback = grade_quiz(key, load_answers(args.grade))
        except (QuizError, OSError, json.JSONDecodeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print("\n".join(feedback))
        return 0 if score >= 0 else 1

    if args.bank is None:
        if args.key:
            print("error: --key is only used with --grade", file=sys.stderr)
            return 2
        if sys.stdin.isatty():
            return interactive(None)
        build_parser().print_help()
        return 0

    try:
        title, questions = load_bank(args.bank)
    except QuizError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.list:
        print(f"{title}: {len(questions)} questions")
        for i, q in enumerate(questions, 1):
            print(f"{i:>3}. [{q.type}] {q.prompt}")
        return 0

    if not args.build:
        build_parser().print_help()
        return 0

    try:
        selected = select_questions(questions, args.count, args.seed)
    except QuizError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    quiz_text = format_quiz(title, selected, {"seed": args.seed})
    key = build_key(title, selected, args.seed)
    if args.quiz_out:
        args.quiz_out.parent.mkdir(parents=True, exist_ok=True)
        args.quiz_out.write_text(quiz_text, encoding="utf-8")
        print(f"Quiz written to {args.quiz_out}")
    else:
        print(quiz_text, end="")
    if args.key_out:
        write_json(args.key_out, key)
        print(f"Answer key written to {args.key_out}")
    else:
        print("warning: no --key-out given; answers were not saved", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
