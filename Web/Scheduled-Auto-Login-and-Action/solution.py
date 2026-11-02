#!/usr/bin/env python3
"""Scheduled Auto Login and Action - log in, act, log out, repeat.

A cookie-aware urllib session parses the login page's HTML form (including
hidden CSRF fields), submits credentials, performs a configurable action, and
visits the logout link.  Cycles can run once or on a fixed interval.
``--demo`` starts a mock login site on loopback and performs a real form POST,
cookie-based login, report fetch and logout against it.
"""

from __future__ import annotations

import argparse
import getpass
import html
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

USER_AGENT = "auto-login/1.0 (+stdlib)"
LOCALHOST = "127.0.0.1"


class LoginError(Exception):
    """Raised when a login cycle cannot be completed."""


@dataclass
class Field:
    """One ``<input>``/``<select>``/``<textarea>`` inside a form."""

    name: str
    value: str
    kind: str
    checked: bool = False


@dataclass
class Form:
    """A parsed HTML form."""

    action: str
    method: str
    fields: list[Field] = field(default_factory=list)

    def action_url(self, base: str) -> str:
        """Resolve the form action against the page URL."""
        return urljoin(base, self.action or base)

    def field_named(self, name: str) -> Field | None:
        """Return the first field with ``name``."""
        return next((item for item in self.fields if item.name == name), None)

    def has_password(self) -> bool:
        """Return whether the form contains a password input."""
        return any(item.kind == "password" for item in self.fields)


class FormParser(HTMLParser):
    """Collect forms and their input values from an HTML document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[Form] = []
        self._current: Form | None = None
        self._select: Field | None = None
        self._textarea: Field | None = None
        self._textarea_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value if value is not None else "") for key, value in attrs}
        if tag == "form":
            self._current = Form(values.get("action", "").strip(),
                                 values.get("method", "get").strip().lower() or "get")
        elif self._current is not None and tag == "input":
            name = values.get("name", "").strip()
            if name:
                kind = values.get("type", "text").strip().lower() or "text"
                self._current.fields.append(
                    Field(name, values.get("value", ""), kind, "checked" in values)
                )
        elif self._current is not None and tag == "select":
            name = values.get("name", "").strip()
            if name:
                self._select = Field(name, "", "select")
                self._current.fields.append(self._select)
        elif self._current is not None and tag == "option" and self._select is not None:
            if not self._select.value or "selected" in values:
                self._select.value = values.get("value", "")
        elif self._current is not None and tag == "textarea":
            name = values.get("name", "").strip()
            if name:
                self._textarea = Field(name, "", "textarea")
                self._textarea_parts = []
                self._current.fields.append(self._textarea)
        elif self._current is not None and tag == "button":
            name = values.get("name", "").strip()
            if name:
                self._current.fields.append(
                    Field(name, values.get("value", ""), values.get("type", "submit")
                          .strip().lower() or "submit")
                )

    def handle_data(self, data: str) -> None:
        if self._textarea is not None:
            self._textarea_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "select":
            self._select = None
        elif tag == "textarea" and self._textarea is not None:
            self._textarea.value = "".join(self._textarea_parts).strip()
            self._textarea = None
        elif tag == "form":
            if self._current is not None:
                self.forms.append(self._current)
            self._current = None


class AnchorParser(HTMLParser):
    """Collect ``(href, text)`` pairs from anchors."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            values = dict(attrs)
            href = (values.get("href") or "").strip()
            if href:
                self._href = href
                self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._parts).split())))
            self._href = None
            self._parts = []


def parse_forms(document: str) -> list[Form]:
    """Parse every form in an HTML document."""
    parser = FormParser()
    parser.feed(document)
    parser.close()
    return parser.forms


def parse_links(document: str) -> list[tuple[str, str]]:
    """Parse every anchor in an HTML document."""
    parser = AnchorParser()
    parser.feed(document)
    parser.close()
    return parser.links


def page_title(document: str) -> str:
    """Extract a whitespace-normalised document title."""
    match = re.search(r"<title[^>]*>(.*?)</title>", document, re.IGNORECASE | re.DOTALL)
    return " ".join(html.unescape(match.group(1)).split()) if match else "(no title)"


def snippet(document: str, limit: int = 120) -> str:
    """Reduce an HTML page to a short single-line excerpt."""
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", document,
                  flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(html.unescape(text).split())
    return text[:limit] + ("..." if len(text) > limit else "")


@dataclass
class Response:
    """A completed HTTP response."""

    status: int
    url: str
    text: str


class Session:
    """Cookie-aware HTTP session built on urllib."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self.jar = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.jar))

    def request(self, url: str, data: dict[str, str] | None = None,
                method: str | None = None) -> Response:
        """Perform a request, returning error pages instead of raising for 4xx/5xx."""
        body = urlencode(data).encode("utf-8") if data is not None else None
        headers = {"User-Agent": USER_AGENT}
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request(url, data=body, headers=headers,
                          method=method or ("POST" if body is not None else "GET"))
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return Response(response.status, response.geturl(),
                                self._decode(response.headers, response.read(2_000_000)))
        except HTTPError as exc:
            return Response(exc.code, exc.geturl(),
                            self._decode(exc.headers, exc.read(2_000_000)))
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise LoginError(f"request to {url} failed: "
                             f"{getattr(exc, 'reason', exc)}") from exc

    @staticmethod
    def _decode(headers: Any, raw: bytes) -> str:
        charset = headers.get_content_charset() if headers else None
        return raw.decode(charset or "utf-8", errors="replace")

    def logout_locally(self) -> None:
        """Forget every cookie held by the session."""
        self.jar.clear()


def choose_login_form(forms: list[Form], index: int) -> Form:
    """Select the form used for login, preferring one with a password field."""
    candidates = [form for form in forms if form.has_password()]
    if not candidates:
        raise LoginError("no login form with a password field found on the page")
    if index < 0 or index >= len(candidates):
        raise LoginError(f"login form index {index} out of range "
                         f"({len(candidates)} form(s) with passwords)")
    return candidates[index]


def guess_username_field(form: Form) -> Field:
    """Find the most likely username/email input in a login form."""
    text_fields = [item for item in form.fields
                   if item.kind in ("text", "email", "tel")
                   and item.name and item.name.lower() not in ("search", "q")]
    preferred = [item for item in text_fields
                 if re.search(r"user|email|login|account", item.name, re.IGNORECASE)]
    if preferred:
        return preferred[0]
    if text_fields:
        return text_fields[0]
    raise LoginError("login form has no text input for a username")


def build_login_payload(form: Form, username: str, password: str,
                        username_field: str | None, password_field: str | None
                        ) -> tuple[dict[str, str], str, str]:
    """Build the form payload, preserving hidden fields and filling credentials."""
    user = form.field_named(username_field) if username_field else guess_username_field(form)
    if user is None:
        raise LoginError(f"username field {username_field!r} not found in login form")
    pass_fields = [item for item in form.fields if item.kind == "password"]
    if password_field:
        secret = form.field_named(password_field)
        if secret is None or secret.kind != "password":
            raise LoginError(f"password field {password_field!r} not found in login form")
    else:
        if not pass_fields:
            raise LoginError("login form has no password input")
        secret = pass_fields[0]

    ignored = {"submit", "button", "reset", "file", "image"}
    payload: dict[str, str] = {}
    for item in form.fields:
        if not item.name or item.kind in ignored:
            continue
        if item.name in (user.name, secret.name):
            continue
        if item.kind == "checkbox" and not item.checked:
            continue
        payload[item.name] = item.value
    payload[user.name] = username
    payload[secret.name] = password
    return payload, user.name, secret.name


def find_logout_link(document: str, base_url: str) -> str | None:
    """Find an anchor whose href or text looks like a logout link."""
    for href, text in parse_links(document):
        marker = f"{href} {text}".lower()
        if re.search(r"log[\s_-]?out|sign[\s_-]?out", marker):
            return urljoin(base_url, href)
    return None


@dataclass
class Config:
    """Everything needed for one login/action/logout cycle."""

    login_url: str
    username: str
    password: str
    action_url: str | None = None
    action_method: str = "GET"
    action_data: dict[str, str] = field(default_factory=dict)
    logout_url: str | None = None
    success_text: str | None = None
    failure_text: str | None = None
    username_field: str | None = None
    password_field: str | None = None
    form_index: int = 0
    timeout: float = 15.0


def login_succeeded(config: Config, login_url: str, response: Response) -> bool:
    """Decide whether a login POST actually authenticated the session."""
    body = response.text.lower()
    if config.failure_text and config.failure_text.lower() in body:
        return False
    if config.success_text:
        return config.success_text.lower() in body
    lowered = body
    if any(marker in lowered for marker in ("invalid password", "incorrect password",
                                            "login failed", "authentication failed")):
        return False
    if urlparse(response.url).path != urlparse(login_url).path:
        return True
    return not any(form.has_password() for form in parse_forms(response.text))


def run_cycle(config: Config, cycle: int = 1) -> bool:
    """Run one login, action and logout cycle.  Returns True on success."""
    session = Session(config.timeout)
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{started}] cycle {cycle}: {config.login_url}")
    try:
        response = session.request(config.login_url)
        print(f"  GET  login page     {response.status} {response.url}")
        if response.status >= 400:
            raise LoginError(f"login page returned HTTP {response.status}")

        form = choose_login_form(parse_forms(response.text), config.form_index)
        payload, user_field, pass_field = build_login_payload(
            form, config.username, config.password,
            config.username_field, config.password_field)
        target = form.action_url(response.url)
        print(f"  form {target} ({form.method.upper()}, {len(payload)} fields; "
              f"user={user_field!r}, password={pass_field!r})")

        if form.method == "post":
            response = session.request(target, data=payload, method="POST")
        else:
            response = session.request(f"{target}?{urlencode(payload)}")
        print(f"  POST credentials    {response.status} {response.url} — "
              f"{page_title(response.text)!r}")
        if not login_succeeded(config, config.login_url, response):
            raise LoginError(f"login failed: {snippet(response.text)!r}")

        print(f"  login OK: {snippet(response.text, 70)}")

        action_url = urljoin(response.url, config.action_url) if config.action_url \
            else response.url
        action_data = config.action_data if config.action_method == "POST" else None
        if config.action_method == "POST" and not config.action_data:
            action_data = {}
        action = session.request(action_url, data=action_data,
                                 method=config.action_method)
        print(f"  {config.action_method:<4} action         {action.status} {action.url} — "
              f"{page_title(action.text)!r}")
        action_ok = action.status < 400
        if not action_ok:
            print(f"  action failed: HTTP {action.status}", file=sys.stderr)

        logout_url = urljoin(action.url, config.logout_url) if config.logout_url else None
        logout_url = (logout_url or find_logout_link(action.text, action.url)
                      or find_logout_link(response.text, response.url))
        if logout_url:
            logged_out = session.request(logout_url)
            print(f"  GET  logout         {logged_out.status} {logged_out.url} — "
                  f"{page_title(logged_out.text)!r}")
            logout_ok = logged_out.status < 400
        else:
            print("  logout              no link found; clearing session cookies locally")
            session.logout_locally()
            logout_ok = True
        return action_ok and logout_ok
    except LoginError as exc:
        print(f"  error: {exc}", file=sys.stderr)
        return False
    finally:
        session.logout_locally()


def run_schedule(config: Config, interval: float, count: int) -> int:
    """Run cycles according to the schedule; ``count=0`` means forever."""
    completed = 0
    failures = 0
    try:
        while count == 0 or completed < count:
            completed += 1
            if not run_cycle(config, completed):
                failures += 1
            if count != 0 and completed >= count:
                break
            print(f"  sleeping {interval:g}s until the next cycle\n")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    print(f"\nCycles: {completed}, failures: {failures}")
    return 0 if failures == 0 else 1


def parse_pairs(values: list[str] | None) -> dict[str, str]:
    """Parse repeated ``KEY=VALUE`` options into a dictionary."""
    result: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"expected KEY=VALUE, got {value!r}")
        key, item = value.split("=", 1)
        if not key:
            raise ValueError(f"empty key in {value!r}")
        result[key] = item
    return result


# --------------------------------------------------------------------------- demo

class MockSiteHandler(BaseHTTPRequestHandler):
    """A minimal site with a CSRF-protected login, report and logout."""

    csrf_token = "demo-csrf-token"
    username = "demo"
    password = "demo123"
    sessions: set[str] = set()

    def log_message(self, format: str, *args: object) -> None:
        """Keep demo output clean."""

    def _send(self, status: int, body: str, headers: dict[str, str] | None = None) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def _logged_in(self) -> bool:
        cookie = self.headers.get("Cookie", "")
        for chunk in cookie.split(";"):
            name, _, value = chunk.strip().partition("=")
            if name == "session" and value in self.sessions:
                return True
        return False

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        path = urlparse(self.path).path
        if path == "/login":
            self._send(200, f"""<!doctype html><html><head><title>Sign in</title></head>
                <body><h1>Mock login</h1>
                <form method="post" action="/login">
                  <input type="hidden" name="csrf_token" value="{self.csrf_token}">
                  <label>Username <input type="text" name="username"></label>
                  <label>Password <input type="password" name="password"></label>
                  <button type="submit" name="commit" value="signin">Sign in</button>
                </form></body></html>""")
        elif path == "/dashboard":
            if not self._logged_in():
                self._send(403, "<html><head><title>Denied</title></head>"
                                "<body>Please sign in</body></html>")
                return
            self._send(200, """<html><head><title>Dashboard</title></head><body>
                <h1>Welcome, demo</h1>
                <a href="/reports/summary">Weekly report</a> ·
                <a href="/logout">Log out</a></body></html>""")
        elif path == "/reports/summary":
            if not self._logged_in():
                self._send(403, "<html><head><title>Denied</title></head>"
                                "<body>Please sign in</body></html>")
                return
            self._send(200, """<html><head><title>Weekly report</title></head><body>
                <h1>Weekly report</h1><p>Orders: 42 · Revenue: $1,260</p>
                <a href="/logout">Log out</a></body></html>""")
        elif path == "/logout":
            self.sessions.discard(self._cookie_value())
            self._send(200, """<html><head><title>Signed out</title></head><body>
                <h1>Signed out</h1><p>Your session has ended.</p></body></html>""",
                        {"Set-Cookie": "session=; Path=/; Max-Age=0"})
        else:
            self._send(404, "<html><head><title>Not found</title></head>"
                            "<body>Not found</body></html>")

    def _cookie_value(self) -> str:
        for chunk in self.headers.get("Cookie", "").split(";"):
            name, _, value = chunk.strip().partition("=")
            if name == "session":
                return value
        return ""

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        path = urlparse(self.path).path
        if path != "/login":
            self._send(404, "<html><head><title>Not found</title></head>"
                            "<body>Not found</body></html>")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            form = parse_qs(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send(400, "<html><head><title>Bad request</title></head>"
                            "<body>Bad request</body></html>")
            return
        supplied_csrf = (form.get("csrf_token") or [""])[0]
        username = (form.get("username") or [""])[0]
        password = (form.get("password") or [""])[0]
        if supplied_csrf != self.csrf_token:
            self._send(400, "<html><head><title>Bad CSRF</title></head>"
                            "<body>Invalid form token</body></html>")
            return
        if username != self.username or password != self.password:
            self._send(200, """<html><head><title>Sign in</title></head><body>
                <p>Invalid username or password</p>
                <form method="post" action="/login">
                  <input type="hidden" name="csrf_token" value="demo-csrf-token">
                  <input type="text" name="username">
                  <input type="password" name="password">
                </form></body></html>""")
            return
        import secrets
        token = secrets.token_hex(8)
        self.sessions.add(token)
        self._send(303, "<html><body>Redirecting</body></html>",
                   {"Location": "/dashboard", "Set-Cookie": f"session={token}; Path=/; HttpOnly"})


def run_demo() -> int:
    """Start the mock site and perform a real end-to-end login cycle."""
    server = ThreadingHTTPServer((LOCALHOST, 0), MockSiteHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{LOCALHOST}:{server.server_address[1]}"
    print("Scheduled Auto Login demo (offline: mock site served from this process)")
    print(f"Mock site: {base}\n")
    ok = False
    try:
        config = Config(
            login_url=base + "/login",
            username="demo",
            password="demo123",
            action_url=base + "/reports/summary",
            logout_url=base + "/logout",
            success_text="Welcome",
            timeout=5.0,
        )
        ok = run_cycle(config)
        session = Session(5.0)
        after = session.request(base + "/dashboard")
        print(f"\nPost-logout access check: GET /dashboard -> {after.status} "
              f"({'denied as expected' if after.status == 403 else 'unexpected'})")
        ok = ok and after.status == 403
    finally:
        server.shutdown()
        server.server_close()
    print("\nDemo complete: CSRF token preserved, cookies logged in and out, "
          f"action fetched — {'PASS' if ok else 'FAIL'}.")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Log into a site on a schedule, perform an action, then log out.",
        epilog="Examples:\n"
               "  AUTO_LOGIN_PASSWORD=secret python3 solution.py \\\n"
               "      --login-url https://example.com/login --username alice \\\n"
               "      --action-url https://example.com/reports --once\n"
               "  python3 solution.py --login-url https://example.com/login \\\n"
               "      --username alice --interval 3600 --count 0\n"
               "  python3 solution.py --demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--login-url", help="page containing the login form")
    parser.add_argument("--username", help="username (default: $AUTO_LOGIN_USERNAME)")
    parser.add_argument("--password-env", default="AUTO_LOGIN_PASSWORD",
                        help="environment variable holding the password "
                             "(default: AUTO_LOGIN_PASSWORD)")
    parser.add_argument("--action-url", help="page to fetch after login (default: post-login page)")
    parser.add_argument("--action-method", choices=("GET", "POST"), default="GET",
                        help="HTTP method for the action (default: GET)")
    parser.add_argument("--action-data", action="append", metavar="KEY=VALUE",
                        help="form field for a POST action (repeatable)")
    parser.add_argument("--logout-url", help="logout URL (default: auto-detected link)")
    parser.add_argument("--success-text", help="text that proves login succeeded")
    parser.add_argument("--failure-text", help="text that proves login failed")
    parser.add_argument("--username-field", help="override the username input name")
    parser.add_argument("--password-field", help="override the password input name")
    parser.add_argument("--form-index", type=int, default=0,
                        help="which password form to use, zero-based (default: 0)")
    parser.add_argument("--timeout", type=float, default=15.0,
                        help="HTTP timeout in seconds (default: 15)")
    parser.add_argument("--interval", type=float, default=3600.0,
                        help="seconds between cycles (default: 3600)")
    parser.add_argument("--count", type=int, default=1,
                        help="number of cycles; 0 runs forever (default: 1)")
    parser.add_argument("--once", action="store_true",
                        help="run exactly one cycle and exit")
    parser.add_argument("--demo", action="store_true",
                        help="run a self-contained offline demonstration")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Program entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()
    if not args.login_url:
        parser.error("--login-url is required (or use --demo)")
    if args.count < 0:
        parser.error("--count cannot be negative")
    if args.interval < 0:
        parser.error("--interval cannot be negative")
    if args.count == 0 and args.interval <= 0 and not args.once:
        parser.error("--interval must be positive when running forever")
    if args.form_index < 0:
        parser.error("--form-index cannot be negative")

    username = args.username or os.environ.get("AUTO_LOGIN_USERNAME", "")
    if not username:
        if not sys.stdin.isatty():
            print("error: provide --username or set AUTO_LOGIN_USERNAME", file=sys.stderr)
            return 2
        try:
            username = input("Username: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 2
    password = os.environ.get(args.password_env, "")
    if not password:
        if not sys.stdin.isatty():
            print(f"error: set the {args.password_env} environment variable", file=sys.stderr)
            return 2
        try:
            password = getpass.getpass("Password: ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 2
    try:
        action_data = parse_pairs(args.action_data)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    config = Config(
        login_url=args.login_url,
        username=username,
        password=password,
        action_url=args.action_url,
        action_method=args.action_method,
        action_data=action_data,
        logout_url=args.logout_url,
        success_text=args.success_text,
        failure_text=args.failure_text,
        username_field=args.username_field,
        password_field=args.password_field,
        form_index=args.form_index,
        timeout=args.timeout,
    )
    count = 1 if args.once else args.count
    return run_schedule(config, args.interval, count)


if __name__ == "__main__":
    raise SystemExit(main())
