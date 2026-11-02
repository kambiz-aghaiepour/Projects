# Content Management System

## Problem

> Create a content management system (CMS) like Joomla, Drupal, PHP Nuke etc.
> Start small. Optional: Allow for the addition of modules/addons.

This is project **Content Management System** in the **Web** category of the
Mega Project List.

## Features

- SQLite-backed **posts and pages** with stable, unique URL slugs generated from
  titles (`hello-cms`, `hello-cms-2`, …).
- **Draft / published** workflow: drafts are invisible to the public and can be
  published, unpublished, edited or deleted from the dashboard.
- **Administrator login** with a password from `CMS_ADMIN_PASSWORD`, or a random
  one printed at startup. Passwords are stored as PBKDF2-HMAC-SHA256 hashes,
  sessions are random HttpOnly cookies with an eight-hour expiry, and login
  attempts are throttled.
- **CSRF protection** on every authenticated admin POST (hidden token tied to
  the session).
- **Markdown subset renderer** (separate `markdown_subset.py`): headings,
  paragraphs, fenced code, bold/italic/inline code, links, ordered and unordered
  lists, block quotes and horizontal rules. All input is HTML-escaped and
  `javascript:` links are dropped.
- Public **index**, **post** and **page** views, plus substring search over
  published titles and bodies.
- Admin **create / edit / delete / publish / unpublish** through ordinary HTML
  forms — no JavaScript framework required.
- Responsive, dependency-free CSS; `/health` JSON endpoint with content counts.

## Requirements

Python 3.10+ and the standard library only (no `requirements.txt` needed).

## Usage

```bash
# Scripted end-to-end check on an ephemeral server
python3 solution.py --demo

# Run the site, choosing your own password
CMS_ADMIN_PASSWORD='correct horse battery staple' python3 solution.py --port 8000

# Or let it generate one and print it at startup
python3 solution.py --db site.db

python3 solution.py --help
```

| Option | Meaning |
| --- | --- |
| `--demo` | Login and CRUD walkthrough over localhost, then exit |
| `--serve` | Start the server (implicit when no action is given) |
| `--port N` | Listening port (default 8000) |
| `--db PATH` | SQLite database file (default `cms.db`) |
| `--verbose` | Log HTTP requests |

Environment: `CMS_ADMIN_PASSWORD` sets the administrator password. Without it a
random password is generated for that process and printed once.

## Example Output

```text
$ python3 solution.py --demo
Content Management System demo
==============================
  database     : 2 items (1 published, 1 draft)

  [PASS] Markdown renders headings, emphasis, code, links and lists
  [PASS] HTML and javascript: URLs are neutralised
  [PASS] slugify makes URL-safe slugs
  [PASS] public index is served
  [PASS] dashboard redirects anonymous visitors to login
  [PASS] wrong password is rejected
  [PASS] correct password signs in
  [PASS] admin session exposes a CSRF token
  [PASS] draft post can be created
  [PASS] slug is generated from the title
  [PASS] draft is hidden from the public
  [PASS] publishing exposes the post
  [PASS] Markdown is rendered on the public page
  [PASS] search finds published content
  [PASS] published page is served at its slug
  [PASS] editing updates the public post
  [PASS] duplicate titles get unique slugs
  [PASS] deleting removes the page
  [PASS] stale CSRF token is rejected
  [PASS] logout ends the session
  [PASS] health endpoint reports counts

21/21 checks passed
```

## Implementation Notes

- Schema: one `posts` table carries both kinds (`kind` = `post|page`) and a
  status check constraint; `sessions` stores opaque tokens, CSRF secrets and
  expiry times. A `RLock` guards the shared connection because the HTTP server
  is threaded.
- Routing is a hand-written dispatcher in `Handler`; unknown paths and
  unpublished slugs return a styled `404` rather than leaking drafts.
- `render_markdown()` escapes the whole document before applying inline regexes,
  stashes code spans so their contents stay literal, and only allows
  `http(s)://`, `mailto:`, root-relative and fragment URLs.
- The demo runs the real server on `127.0.0.1:0`, keeps cookies in a
  `CookieJar`, scrapes the CSRF token from the editor form, and asserts the
  public HTML after each mutation.
- Rendering is linear in the size of a post; list and search queries use the
  `status`/`kind` index and cap their result sets.
- Limitations: single administrator, no media uploads, no comments, no
  revision history. The Markdown renderer is isolated in `markdown_subset.py`
  so it can be replaced independently of the CMS.
