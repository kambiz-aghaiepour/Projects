# Mail Checker (POP3 / IMAP)

## Problem

The user enters account information including the mail server, protocol type
(POP3 or IMAP) and credentials; the application checks for email at a given
interval.

Part of the **Networking** category in the Mega Project List.

## Features

- IMAP4 and POP3, each with SSL by default and optional plaintext.
- Reports total messages, unread count (IMAP) and recent message headers.
- RFC 2047 header decoding for internationalised senders and subjects.
- Polling loop with configurable interval and finite/infinite run counts.
- JSON output for scripting.
- Password from `--password`, `MAIL_PASSWORD`, or an interactive prompt.
- `--demo` runs a simulated mailbox through the same reporting and polling
  logic, with no server, credentials or network.

## Requirements

Python 3.10+ and its standard library. A real check needs an IMAP or POP3
account; the demo needs nothing.

## Usage

```bash
python3 solution.py --demo
MAIL_PASSWORD=secret python3 solution.py --protocol imap \
    --host imap.example.com --user me@example.com
MAIL_PASSWORD=secret python3 solution.py --protocol pop3 \
    --host pop3.example.com --user me@example.com --no-ssl --port 110
MAIL_PASSWORD=secret python3 solution.py --protocol imap \
    --host imap.example.com --user me --interval 120 --count 0 --limit 10
```

| Option | Meaning |
| --- | --- |
| `--protocol` | `imap` (default) or `pop3`. |
| `--host`, `--port` | Server and optional port override. |
| `--user`, `--password` | Credentials; prefer the `MAIL_PASSWORD` environment variable. |
| `--mailbox` | IMAP mailbox to select (default `INBOX`). |
| `--no-ssl` | Use a plaintext connection instead of SSL. |
| `--interval`, `--count` | Seconds between checks and number of checks (`0` = forever). |
| `--limit` | Recent messages to display (default `5`). |
| `--timeout` | Socket timeout for login and fetches (default `10`). |
| `--json` | Emit each report as JSON. |
| `--demo` | Run the simulated demonstration. |

## Example Output

```
$ python3 solution.py --demo
Demo mode: simulated mailbox (no server or credentials needed).
Real IMAP/POP3 code paths are used when --host/--user are supplied.

Mailbox check - IMAP demo@imap.example.test
----------------------------------------------------------------
  Total messages: 3   Unread: 1
  Latest messages:
    #3    Mon, 02 Nov 2026 09:30:00 +0000  billing@example.net
          Invoice 2026-11 is ready
    #2    Mon, 02 Nov 2026 08:02:00 +0000  newsletter@example.org
          Weekly digest: 5 stories
    #1    Mon, 02 Nov 2026 07:15:00 +0000  alerts@status.example
          Scheduled maintenance notice

  [simulating 1 new message and a 0.2s polling interval]

Mailbox check - IMAP demo@imap.example.test
----------------------------------------------------------------
  Total messages: 4   Unread: 2
  New since last check: 1
  ...
Demo complete: polling, header decoding and new-mail detection work.
```

## Implementation Notes

IMAP checks log in, `SELECT` the mailbox read-only, count `UNSEEN` messages and
fetch only the `FROM`, `SUBJECT` and `DATE` headers with `BODY.PEEK`, so no
message is marked read. POP3 has no read/unread flag, so all messages are
reported as unread and headers are fetched with `TOP` (falling back to `RETR`).
Both paths set socket timeouts and always attempt a clean logout/quit.

Polling compares the current total with the previous total to report new mail;
this is intentionally simple and can miscount if messages are deleted between
checks. The tool displays headers only, not bodies or attachments, and does not
store credentials on disk.
