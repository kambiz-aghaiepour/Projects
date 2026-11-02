# Inverted Index

**Category:** `Data-Structures` · **Project:** `Inverted-Index`

## Problem

> An Inverted Index is a data structure used to create full text search. Given
> a set of text files, implement a program to create an inverted index. Also
> create a user interface to do a search using that inverted index which
> returns a list of files that contain the query term / terms. The search
> index can be in memory.

## Features

- Builds an in-memory inverted index mapping each term to the documents that
  contain it and the token positions of every occurrence.
- Single-term lookup, e.g. `index`.
- Multi-term **AND** queries, e.g. `inverted index` — only documents containing
  every term are returned.
- Quoted **phrase** queries, e.g. `"full text search"`, verified against stored
  token positions. Phrases and terms can be mixed in one query.
- Results ranked by summed term frequency, with a deterministic file-name
  tie-break, and a context snippet around the first match.
- Interactive search prompt with `:docs`, `:stats`, `:limit N`, `:help`, and
  `:quit` commands.
- One-shot queries, index statistics, single-file or whole-directory indexing,
  and a configurable file extension.
- `--demo` indexes four bundled sample documents and runs single-term, AND,
  phrase, and empty-result queries without any user input.

## Requirements

Python 3.10+ and the standard library only (`argparse`, `re`, `collections`,
`dataclasses`, `pathlib`). No installation step is needed.

## Usage

```bash
python3 solution.py --demo
python3 solution.py sample_docs -q "inverted index"
python3 solution.py sample_docs -q '"full text search"' -n 5
python3 solution.py sample_docs --stats
python3 solution.py sample_docs                 # interactive prompt
python3 solution.py notes.txt -q postings        # index a single file
```

Options:

- `path` — file or directory to index. Defaults to the bundled `sample_docs/`.
- `--demo` — run the scripted demonstration and exit.
- `-q/--query QUERY` — answer one query, print the ranked results, and exit.
- `-e/--extension EXT` — extension used when indexing a directory (default
  `.txt`; `txt` and `.txt` are both accepted).
- `-n/--limit N` — maximum number of results to display (default 10).
- `--stats` — print document count, vocabulary size, token count, average
  document length, and the five most frequent terms, then exit.
- `--no-snippets` — hide the context snippet under each hit.
- `-h/--help` — show usage.

Interactive commands: a plain query searches; `"quoted text"` searches for a
phrase; `:docs` lists indexed files; `:stats` shows index statistics;
`:limit N` changes the display limit; `:quit` exits. `Ctrl-D`/`Ctrl-C` also
exit cleanly.

Queries are case-insensitive. Terms are ANDed; there is no OR or NOT operator.
A missing path or an empty/unterminated query exits with status 2 and a clear
message; an empty result set is a normal, successful search.

## Example Output

Trimmed from `python3 solution.py --demo`:

```
Inverted Index demo
==============================================================
Built an in-memory index over 4 bundled documents:
  data_structures.txt
  python_notes.txt
  search_engines.txt
  security_notes.txt

Documents: 4
Vocabulary: 240 terms
Tokens: 534
Average document length: 133.5 tokens
Most frequent terms: the (37), a (26), and (16), term (13), is (12)

--------------------------------------------------------------
3 result(s) for index, showing 3:
  1. search_engines.txt  (score 4: index x4)
     ...ay to find documents that contain a word. The inverted index is the data structure that makes this possible. Instea...
  2. data_structures.txt  (score 3: index x3)
     ...supports constant time lookup on average. The inverted index uses a hash table internally: the key is a term and th...
  3. python_notes.txt  (score 2: index x2)
     ... natural choice for the term dictionary of an inverted index. Lists hold the postings for each term. The collection...
--------------------------------------------------------------
3 result(s) for inverted index, showing 3:
  1. search_engines.txt  (score 7: index x4, inverted x3)
     Full Text Search and Inverted Indexes A search engine needs a fast way to find docum...
  ...
--------------------------------------------------------------
3 result(s) for "inverted index", showing 3:
  1. data_structures.txt  (score 2: "inverted index" x2)
  ...
--------------------------------------------------------------
No documents matched: quantum
--------------------------------------------------------------
Demo complete: single-term, AND, phrase, and empty result sets shown.
```

## Implementation Notes

- **Data layout:** `_postings[term][doc_id] = [positions...]` is the inverted
  index; `_tokens[doc_id]` keeps the token sequence for phrase verification and
  `_texts[doc_id]` keeps the original text for snippets.
- **Tokenization:** case-folded runs of ASCII letters/digits, keeping internal
  apostrophes (`don't` stays one token). Punctuation and file formatting are
  ignored.
- **Query parsing:** quoted spans become phrase clauses; every other
  whitespace-separated span is tokenized into one term clause per token. All
  clauses are intersected, giving AND semantics.
- **Phrase check:** candidate documents are the intersection of the phrase
  words' postings; positions are then checked for consecutiveness.
- **Complexity:** building is O(T) time and space for T tokens. A term query is
  O(df) for its document frequency; an AND query is O(sum of df); a phrase
  query adds a linear scan over the candidate documents' positions.
- **Ranking:** score is the sum of term/phrase occurrences across all clauses,
  sorted descending, then by document id. This is deliberately simple; real
  engines use TF-IDF or BM25 and rare-term weighting.
- **Limitations:** the index lives only in memory and must be rebuilt per run;
  there is no stemming, stop-word removal, wildcard, fuzzy, OR, or NOT support.
  Phrase adjacency is based on tokens, so a phrase can match across a newline
  when no punctuation intervenes. Non-UTF-8 input is decoded with replacement
  characters rather than rejected.
