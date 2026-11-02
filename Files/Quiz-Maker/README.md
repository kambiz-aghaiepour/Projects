# Quiz Maker

Category: `Files` · Project: `Quiz-Maker`

## Problem

Make an application which takes various questions from a file, picked randomly,
and puts together a quiz for students. Each quiz can be different and then reads
a key to grade the quizzes.

## Features

- JSON question bank with three question types:
  - `multiple_choice` — 2+ choices, answer as index, letter or exact text
  - `true_false` — answer as `true`/`false` (also accepts yes/no, t/f)
  - `short_answer` — one or more accepted answers, case/whitespace tolerant
- Validates the bank up front: unknown types, missing prompts, duplicate ids and
  out-of-range choice answers produce clear errors.
- Random selection of `--count` questions, optionally reproducible with `--seed`.
- Writes the student quiz (no answers) and a separate answer key JSON.
- Grades a JSON answer file against the key with per-question feedback,
  the correct answer and an optional explanation.
- Lists every question in a bank with `--list`.
- Interactive mode when run with no arguments on a terminal.
- `--demo` builds, answers and grades a seeded quiz offline.

## Requirements

Python 3.10+ and the standard library only.

## Usage

```bash
# Build a 5-question quiz with a reproducible selection
python3 solution.py --bank questions.json --build --count 5 --seed 42 \
    --quiz-out quiz.txt --key-out key.json

# Grade a completed answer file
python3 solution.py --grade answers.json --key key.json

# See what is in the bank
python3 solution.py --bank questions.json --list

# Scripted end-to-end example
python3 solution.py --demo
```

Options:

| Option | Meaning |
| --- | --- |
| `--bank PATH` | JSON question bank (required for build/list) |
| `--build` | Build a quiz |
| `--count N` | Questions per quiz (default 5, or the bank size if smaller) |
| `--seed N` | Seed the random selection for reproducibility |
| `--quiz-out PATH` | Write the student quiz text file |
| `--key-out PATH` | Write the answer key JSON file |
| `--grade PATH` | Grade this JSON answer file |
| `--key PATH` | Answer key to grade against |
| `--list` | List questions in the bank |
| `--demo` | Run the offline demonstration |

### Question bank format

```json
{
  "title": "Python Warm-up",
  "questions": [
    {
      "id": "list-comp",
      "type": "multiple_choice",
      "prompt": "Which expression builds a list of squares?",
      "choices": ["[x*x for x in range(5)]", "map(x*x, range(5))"],
      "answer": 0,
      "explanation": "Square brackets build a list.",
      "tags": ["python"]
    },
    {
      "id": "gil",
      "type": "true_false",
      "prompt": "The GIL serialises CPython bytecode execution.",
      "answer": true
    },
    {
      "id": "encoding",
      "type": "short_answer",
      "prompt": "Python 3's default source encoding?",
      "answer": ["UTF-8", "utf8"]
    }
  ]
}
```

### Answer file format

```json
{"quiz_id": "optional", "answers": {"list-comp": "A", "gil": true, "encoding": "utf-8"}}
```

A flat `{"list-comp": "A", ...}` object is also accepted.

## Example Output

```
Loaded bank: Python & Computer Science Warm-up (8 questions)

--- quiz.txt ---
Python & Computer Science Warm-up
=================================

Seed: 42
Questions: 5

1. A mutable default argument such as def f(x=[]) is shared between calls.
   A) True
   B) False
...
5. Which command creates and switches to a new branch?
   A) git branch new
   B) git checkout -b new
   C) git merge new
   D) git remote add new

--- graded feedback ---
  1. [CORRECT] A mutable default argument such as def f(x=[]) is shared between calls.
     you answered True
...
  4. [WRONG] What is the average-case complexity of lookup in a hash table?
     you answered B; correct answer: A) O(1)
     Why: Hashing gives constant-time average lookup.

Score: 3/5 (60.0%)

Demo complete: build + key + grade pipeline works.
```

## Implementation Notes

- Selection uses `random.Random(seed).sample`, so a seed always yields the same
  subset and the same quiz ordering. Without a seed, each quiz differs.
- Answers are canonicalised at load time (choice index, boolean, list of
  accepted strings). Grading accepts letters, indices and exact choice text for
  multiple choice, and normalises case and whitespace for short answers.
- The quiz renderer only receives question prompts and choices; the answer key
  is a separate document, so the student file cannot leak answers.
- Grading is O(number of questions) with O(1) lookups per response.
- Limitation: short answers are exact-match (plus numeric equality), not fuzzy;
  there is no partial credit, no time limit and no web UI.
