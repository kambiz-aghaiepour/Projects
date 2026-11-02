# Web Board (Forum)

## Problem

> Create a forum for you and your buddies to post, administer and share
> thoughts and ideas.

This is project **Web Board (Forum)** in the **Web** category of the Mega
Project List.

## Features

- Three seeded **boards** (General Discussion, Projects, Off Topic), with thread
  and post counts plus last-activity times on the index.
- **Threads and posts** stored in SQLite, with 10-item **pagination** on both
  board and thread pages.
- **Quoting**: a Quote link prefills the reply box with `> author wrote:` and
  records the quoted post id (`replying to post #N`).
- **Edit and delete your own posts** without an account system: the HttpOnly
  session cookie owns everything posted from that browser. Editing marks the
  post as edited; deletion leaves a tombstone so the conversation still makes
  sense.
- **Moderation**: a key (`FORUM_MODERATOR_KEY`, or generated and printed at
  startup) unlocks a dashboard where threads can be **locked, pinned or
  deleted**, and moderators may edit or delete any post.
- Locked threads hide the reply form and reject POSTed replies with `403`.
- Pinned threads sort before ordinary threads.
- Plain-text posts are HTML-escaped; names are required and lengths are capped.
- `/health` JSON counts, responsive CSS, no external assets or JavaScript
  dependencies.

## Requirements

Python 3.10+ and the standard library only (no `requirements.txt` needed).

## Usage

```bash
# Scripted walkthrough: posting, quoting, editing, pagination, moderation
python3 solution.py --demo

# Run the forum with your own moderator key
FORUM_MODERATOR_KEY='let-me-in' python3 solution.py --port 8000

# Or let it generate one and print it
python3 solution.py --db forum.db

python3 solution.py --help
```

| Option | Meaning |
| --- | --- |
| `--demo` | End-to-end HTTP walkthrough, then exit |
| `--serve` | Start the server (implicit when no action is given) |
| `--port N` | Listening port (default 8000) |
| `--db PATH` | SQLite database file (default `forum.db`) |
| `--verbose` | Log HTTP requests |

Environment: `FORUM_MODERATOR_KEY` sets the moderator key. Without it, a random
key is generated per process and printed once. The key is compared by SHA-256
digest with `hmac.compare_digest`.

## Example Output

```text
$ python3 solution.py --demo
Web Board (Forum) demo
======================
  database     : 3 boards, 11 threads, 11 posts

  [PASS] post bodies escape HTML
  [PASS] pagination compacts long ranges
  [PASS] board index lists the seeded boards
  [PASS] board page shows the new-thread form
  [PASS] thread can be created
  [PASS] new thread has a numeric id
  [PASS] quote link prefills the reply
  [PASS] reply is appended with its quote
  [PASS] author can open the edit form
  [PASS] author can edit their own post
  [PASS] a different session cannot edit the reply
  [PASS] author can delete their own post
  [PASS] threads paginate ten per page
  [PASS] moderation requires sign-in
  [PASS] wrong moderator key is rejected
  [PASS] moderator key signs in
  [PASS] moderator can lock a thread
  [PASS] locked threads reject new replies
  [PASS] locked thread hides the reply form
  [PASS] pinned thread floats to the top
  [PASS] moderator can delete a thread
  [PASS] moderator sign-out is effective
  [PASS] health endpoint reports totals

23/23 checks passed
```

## Implementation Notes

- `forum_store.py` owns the schema: `boards`, `threads`, `posts`, `sessions` and
  `owners` (a `(session_id, post_id)` join table used for author permissions).
  Every query goes through an `RLock` because the threaded HTTP server shares one
  SQLite connection.
- Threads are soft-deleted (`deleted=1`) and posts likewise; public queries
  filter them out and direct links to deleted threads return `404`.
- `updated_at` moves forward on each reply, which drives both board ordering and
  "last activity". Pinned threads are ordered first.
- The demo uses two independent cookie jars to prove that an unrelated session
  cannot edit someone else's post, then promotes one session to moderator and
  exercises lock, pin and delete.
- Board and thread pages use the `threads_board` and `posts_thread` indexes
  with LIMIT/OFFSET pagination, so each request reads roughly one page of rows.
- Limitations: display names are self-asserted (no passwords for regular
  posters), there are no file attachments, private messages, email
  notifications or full-text search. Moderation POSTs rely on the `SameSite=Lax`
  session cookie rather than per-form CSRF tokens.
