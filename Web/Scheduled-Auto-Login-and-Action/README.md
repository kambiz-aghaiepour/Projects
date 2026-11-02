# Scheduled Auto Login and Action

**Category:** Web · **Project:** Scheduled-Auto-Login-and-Action

## Problem

Make an application which logs into a given site on a schedule and invokes a
certain action and then logs out.

## Features

- Cookie-aware session built on `urllib` and `http.cookiejar`; cookies persist
  across the login, action and logout requests.
- Parses real HTML login forms with `html.parser`, including hidden fields such
  as CSRF tokens, and submits the form exactly as a browser would.
- Auto-detects the username field and password field (with `--username-field` /
  `--password-field` overrides) and chooses the first form containing a password.
- Configurable action: GET or POST, optional form data, or default to the page
  reached after login.
- Logout URL can be given explicitly or discovered from a link whose text/href
  contains "logout" / "sign out".
- Login success can be checked with `--success-text` or `--failure-text`;
  otherwise a redirect away from the login page plus the absence of a password
  form counts as success.
- Interval scheduling: `--once` for a single cycle, `--count N` for a fixed
  number, `--count 0` to run forever at `--interval` seconds.
- Credentials come from `--username` / `$AUTO_LOGIN_USERNAME` and a password
  environment variable (`$AUTO_LOGIN_PASSWORD` by default) or a `getpass`
  prompt — never from a command-line flag.
- `--demo` starts a mock site with a CSRF-protected login form and performs a
  real POST, cookie login, report fetch and logout — fully offline.

## Requirements

Python 3.10+ only; standard library.

## Usage

```bash
python3 solution.py --demo

AUTO_LOGIN_PASSWORD='secret' python3 solution.py \
    --login-url https://example.com/login \
    --username alice \
    --action-url https://example.com/reports \
    --once

python3 solution.py --login-url https://example.com/login \
    --username alice --action-method POST \
    --action-data report=weekly --action-data format=csv \
    --interval 3600 --count 0
```

| Option | Meaning |
| --- | --- |
| `--login-url URL` | Page containing the login form (required outside the demo). |
| `--username NAME` | Username; otherwise `$AUTO_LOGIN_USERNAME` or a prompt. |
| `--password-env VAR` | Environment variable holding the password (default `AUTO_LOGIN_PASSWORD`). |
| `--action-url URL` | Page or endpoint to invoke after login (default: the post-login page). |
| `--action-method {GET,POST}` | Action method (default GET). |
| `--action-data KEY=VALUE` | POST field for the action; repeatable. |
| `--logout-url URL` | Explicit logout URL (default: auto-detected link). |
| `--success-text TEXT` | Text that must appear for login to count as successful. |
| `--failure-text TEXT` | Text that marks a failed login. |
| `--username-field NAME` | Override the detected username input name. |
| `--password-field NAME` | Override the detected password input name. |
| `--form-index N` | Which password form to use, zero-based (default 0). |
| `--interval SECONDS` | Delay between cycles (default 3600). |
| `--count N` | Number of cycles; `0` means forever (default 1). |
| `--once` | Force exactly one cycle. |
| `--timeout SECONDS` | HTTP timeout (default 15). |
| `--demo` | Run the offline demonstration. |

Use a password manager or environment injection rather than shell history for
the password. The program never writes credentials to disk.

## Example Output

```
Scheduled Auto Login demo (offline: mock site served from this process)
Mock site: http://127.0.0.1:45755

[2026-11-02 19:05:18] cycle 1: http://127.0.0.1:45755/login
  GET  login page     200 http://127.0.0.1:45755/login
  form http://127.0.0.1:45755/login (POST, 3 fields; user='username', password='password')
  POST credentials    200 http://127.0.0.1:45755/dashboard — 'Dashboard'
  login OK: Dashboard Welcome, demo Weekly report · Log out
  GET  action         200 http://127.0.0.1:45755/reports/summary — 'Weekly report'
  GET  logout         200 http://127.0.0.1:45755/logout — 'Signed out'

Post-logout access check: GET /dashboard -> 403 (denied as expected)

Demo complete: CSRF token preserved, cookies logged in and out, action fetched — PASS.
```

## Implementation Notes

`FormParser` walks the document and records each `<form>` with its action,
method and named inputs/selects/textareas. `build_login_payload` discards submit
buttons, skips unchecked checkboxes, preserves hidden values (including the CSRF
token), and overwrites the detected username and password fields. The POST is
sent as `application/x-www-form-urlencoded`; urllib follows the 303 redirect and
the `CookieJar` automatically supplies the session cookie on subsequent
requests.

`login_succeeded` is deliberately conservative: an explicit failure string
wins, an explicit success string is authoritative, and otherwise success means
the final URL changed and the returned page no longer contains a password form.
A cycle returns failure if the login, action or logout returns HTTP ≥ 400, but
the session cookies are cleared in a `finally` block regardless.

Limitations: only server-rendered HTML forms are supported — JavaScript-rendered
logins, CAPTCHAs, WebAuthn and most two-factor flows need a real browser.
Sessions are per-cycle, so a site that requires a fresh CSRF token per action
may need extra handling. Use HTTPS endpoints; credentials sent over plain HTTP
are exposed. Automated logins can violate a site's terms, so only use this on
services where you are authorised, and keep intervals respectful.
