# Security

Classical cryptography and code breaking.

Each project lives in its own subdirectory with a `README.md` and a runnable `solution.py`.

- [Caesar Cipher](Caesar-Cipher/) — Implement a Caesar cipher, both encoding and decoding. The key is an integer from 1 to 25. This cipher rotates the letters of the alphabet (A to Z). The encoding replaces each letter with the 1st to 25th next letter in the alphabet (wrapping Z to A). This simple monoalphabetic substitution cipher provides almost no security.

## Running a project

```bash
cd <Project-Directory>
python3 solution.py --demo
```

Every program supports `--help`; most run interactively with no arguments. Image-based projects list Pillow in `requirements.txt`.
