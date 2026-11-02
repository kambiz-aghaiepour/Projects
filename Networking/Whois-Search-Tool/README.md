# Whois Search Tool

## Problem

Enter an IP or host address and have it looked up through WHOIS, returning the
results.

Part of the **Networking** category in the Mega Project List.

## Features

- Native WHOIS over TCP port 43 — no web scraping or API key.
- Automatic server selection: IANA for domains, ARIN for IP addresses.
- Follows one registry referral (`ReferralServer`/`refer`), with a built-in
  TLD-to-registry fallback when IANA returns no referral (e.g. `.com`).
- Parses common fields: registrar, creation/update/expiry dates, organisation,
  country, net range, CIDR, abuse contact, name servers and domain status.
- Full raw response by default, `--summary` for parsed fields, `--json` for
  structured output.
- `--server` to query a specific WHOIS server and `--no-follow` to disable
  referrals.
- `--demo` parses bundled `example.com` and `8.8.8.8` snapshots with no network.

## Requirements

Python 3.10+ and its standard library. Live queries need outbound TCP port 43;
the demo is fully offline.

## Usage

```bash
python3 solution.py --demo
python3 solution.py example.com
python3 solution.py 8.8.8.8 --summary
python3 solution.py example.com --summary --timeout 5
python3 solution.py example.com --server whois.verisign-grs.com
python3 solution.py example.com --json > whois.json
```

| Option | Meaning |
| --- | --- |
| `query` | Domain name or IP address (URLs are normalised to their host). |
| `--server` | Query this WHOIS server instead of auto-selecting. |
| `--no-follow` | Do not follow the registry referral. |
| `--timeout` | Socket timeout in seconds (default `10`). |
| `--summary` | Print parsed fields instead of the full raw response. |
| `--json` | Emit the query trail, parsed fields, name servers and statuses. |
| `--demo` | Parse the bundled offline snapshots. |

## Example Output

```
$ python3 solution.py --demo
Demo mode: bundled WHOIS snapshots (no network queries).

Query: example.com (domain)
  Registrar       RESERVED-Internet Assigned Numbers Authority
  Creation Date   1995-08-14T04:00:00Z
  Updated Date    2024-08-14T07:01:38Z
  Expiry Date     2025-08-13T04:00:00Z
  Name servers    A.IANA-SERVERS.NET, B.IANA-SERVERS.NET
  Status          clientDeleteProhibited ...; clientTransferProhibited ...

Query: 8.8.8.8 (ipv4)
  Creation Date   2014-03-14
  Updated Date    2023-12-28
  Organisation    Google LLC
  Country         US
  NetRange        8.8.8.0 - 8.8.8.255
  CIDR            8.8.8.0/24
  Abuse Email     network-abuse@google.com

Demo complete: WHOIS field extraction verified on bundled snapshots.
```

## Implementation Notes

The client opens a TCP connection, sends the query followed by CRLF, and reads
until the server closes or a 2 MB safety cap is reached. Domain queries start
at `whois.iana.org`; if that response contains a `refer:`/`ReferralServer:`
line, the referred server is queried once. Because IANA sometimes omits the
referral (as with `.com`), a small TLD map provides a fallback registry server.
IP queries start at `whois.arin.net` and follow its RIR referral when present.

Field parsing is regex-based and tolerant of leading whitespace, which registry
responses commonly use. It extracts a useful subset rather than implementing
full RPSL; unusual registry formats may need the raw output. WHOIS servers
rate-limit and sometimes block port 43, so `--server`, `--timeout` and the
bundled snapshots are available as fallbacks. The demo data is a static
snapshot and is not refreshed live.
