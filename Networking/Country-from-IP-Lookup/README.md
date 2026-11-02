# Country from IP Lookup

## Problem

Enter an IP address and find the country that IP is registered in. Optional:
find the IP automatically.

Part of the **Networking** category in the Mega Project List.

## Features

- Classifies private, loopback, link-local, multicast, documentation,
  CGNAT and reserved addresses entirely offline — those are never sent to an
  external service.
- Looks up public addresses through the ipwho.is HTTPS API with a timeout.
- Reports country, country code, region, city, organisation and timezone.
- Accepts multiple addresses, reads lists from files, and supports `--me` to
  look up the machine's own public address.
- JSON output and graceful failure when the network or API is unavailable.
- `--demo` classifies six non-public addresses offline and attempts one public
  lookup with a 2-second timeout; it exits 0 whether or not the network works.

## Requirements

Python 3.10+ and its standard library. Public lookups need internet access;
private/loopback classification and the demo's offline portion do not.

## Usage

```bash
python3 solution.py --demo
python3 solution.py 8.8.8.8
python3 solution.py 8.8.8.8 1.1.1.1 2606:4700:4700::1111
python3 solution.py --file addresses.txt --timeout 3
python3 solution.py --me
python3 solution.py 10.0.0.5 8.8.8.8 --json
```

| Option | Meaning |
| --- | --- |
| `ips` | One or more IP addresses (IPv4 or IPv6). |
| `-f, --file` | Read addresses from a file, one per line; `#` comments allowed. |
| `--me` | Look up this machine's public IP and location. |
| `--timeout` | API timeout in seconds (default `5`). |
| `--json` | Emit structured results. |
| `--demo` | Run the offline demonstration. |

## Example Output

```
$ python3 solution.py --demo
Demo: offline classification of private and special-use addresses

  10.0.0.5         private      private network (RFC 1918, not routable)
  192.168.1.10     private      private network (RFC 1918, not routable)
  127.0.0.1        loopback     loopback address (this host)
  169.254.10.20    link-local   link-local address (not routable)
  203.0.113.7      reserved     documentation network (TEST-NET-3)
  100.64.0.1       reserved     carrier-grade NAT (RFC 6598)

Demo: public address lookup (network optional, 2s timeout)

  8.8.8.8          public       San Jose, California, United States (US) - Google LLC
  Source: ipwho.is; country=United States (US)

Demo complete: 7 addresses handled, exit 0 regardless of network.
```

When the API cannot be reached, the public line becomes
`lookup unavailable: <reason>` and the program still exits cleanly.

## Implementation Notes

Non-public ranges are matched with the `ipaddress` module plus explicit
networks for CGNAT, TEST-NET and benchmarking ranges. Only addresses that pass
`is_global` are sent to `https://ipwho.is/<ip>`; the response is parsed
defensively because fields may be absent. Every request has a connect/read
timeout and all `URLError`, `HTTPError`, timeout and JSON errors are converted
into an error field rather than a traceback.

A public lookup failure produces exit code 1 in normal use (the input was valid
but the answer could not be obtained); invalid IP syntax also returns 1. The
demo always returns 0. GeoIP results are approximate and depend on the external
provider's database and rate limits.
