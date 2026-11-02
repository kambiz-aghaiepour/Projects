# Site Checker with Time Scheduling

## Problem

An application that attempts to connect to a website or server every so many
minutes or at a given time and checks whether it is up. If it is down, it
notifies you by email or by posting a notice on screen.

Part of the **Networking** category in the Mega Project List.

## Features

- HTTP/HTTPS checks with status code, latency and error reporting.
- Prominent on-screen `NOTICE` whenever a site is down.
- Fixed-interval scheduling (`--interval`) or daily clock times (`--at`).
- Optional SMTP email alerts with STARTTLS support.
- Bounded runs (`--count`) or continuous monitoring (`--count 0`).
- Graceful handling of DNS failures, refused connections, timeouts and HTTP
  error statuses.
- `--demo` serves a local page and also checks a closed local port, exercising
  both the up and down paths offline.

## Requirements

Python 3.10+ and its standard library. Email alerts need a reachable SMTP
server; none is required for checks or for `--demo`.

## Usage

```bash
python3 solution.py --demo
python3 solution.py https://example.com
python3 solution.py https://example.com --interval 300 --count 0
python3 solution.py https://example.com --at 09:00,18:00
python3 solution.py https://example.com --interval 60 --count 5 \
    --email-to ops@example.com --smtp-host smtp.example.com --smtp-port 587 --smtp-tls
```

| Option | Meaning |
| --- | --- |
| `url` | URL or bare hostname to check. |
| `--interval` | Seconds between checks (default `300`). |
| `--at` | Comma-separated daily times (`HH:MM`) instead of an interval. |
| `--count` | Number of checks; `0` runs until interrupted (default `1`). |
| `--timeout` | HTTP timeout in seconds (default `10`). |
| `--email-to` | Address for down alerts. |
| `--smtp-host/--smtp-port/--smtp-user/--smtp-from/--smtp-tls` | SMTP settings; the password comes from `SMTP_PASSWORD`. |
| `--demo` | Run the offline up/down demonstration. |

## Example Output

```
$ python3 solution.py --demo
Demo web server listening on http://127.0.0.1:32945

[2026-11-02 18:52:34] UP    http://127.0.0.1:32945/ HTTP 200 in 5 ms
[2026-11-02 18:52:34] DOWN  http://127.0.0.1:42855/ (URLError: [Errno 111] Connection refused) after 0 ms
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  NOTICE: site is DOWN - http://127.0.0.1:42855/
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

Demo summary: 1 up, 1 down.
On-screen notification was raised for the unreachable site.
Demo complete (no external network used).
```

## Implementation Notes

Checks use `urllib.request` with a custom user agent and a hard timeout.
Responses with status 200–399 count as up; `HTTPError` statuses (4xx/5xx) and
transport failures count as down. Redirects are followed by urllib. Scheduling
is local-time based: `--at` computes the next matching clock time (today or
tomorrow), while `--interval` sleeps between checks. Email is sent only after a
failed check and SMTP errors are reported without stopping the monitor.

The scheduler keeps state in memory only, so restarting resets the schedule
and does not retain history. There is no retry/backoff beyond the configured
interval, and no persistence of past outages.
