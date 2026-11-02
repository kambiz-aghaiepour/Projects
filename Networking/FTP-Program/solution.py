#!/usr/bin/env python3
"""FTP client for listing, downloading, uploading and managing remote files.

Uses the standard library ``ftplib`` against any FTP/FTPS server, with
timeouts on every operation.  ``--demo`` starts the bundled minimal FTP server
in-process, so a complete login/list/get/put cycle runs offline.
"""

from __future__ import annotations

import argparse
import ftplib
import os
import shlex
import sys
import tempfile
from getpass import getpass
from pathlib import Path

from mini_ftp_server import MiniFTPServer


class FTPClient:
    """Thin, typed wrapper around ftplib with deterministic behaviour."""

    def __init__(self, host: str, port: int = 21, user: str = "anonymous",
                 password: str = "", *, tls: bool = False, passive: bool = True,
                 timeout: float = 15.0) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.tls = tls
        self.passive = passive
        self.timeout = timeout
        self._ftp: ftplib.FTP | None = None

    def connect(self) -> "FTPClient":
        """Open the control connection and log in."""
        factory = ftplib.FTP_TLS if self.tls else ftplib.FTP
        control = factory(timeout=self.timeout)
        control.connect(self.host, self.port)
        control.login(self.user, self.password)
        if self.tls and isinstance(control, ftplib.FTP_TLS):
            control.prot_p()
        control.set_pasv(self.passive)
        self._ftp = control
        return self

    def close(self) -> None:
        if self._ftp is not None:
            try:
                self._ftp.quit()
            except ftplib.all_errors:
                try:
                    self._ftp.close()
                except OSError:
                    pass
            self._ftp = None

    @property
    def ftp(self) -> ftplib.FTP:
        if self._ftp is None:
            raise RuntimeError("not connected")
        return self._ftp

    def pwd(self) -> str:
        return self.ftp.pwd()

    def list_lines(self, path: str = "") -> list[str]:
        """Return detailed LIST output for a path."""
        lines: list[str] = []
        self.ftp.retrlines(f"LIST {path}".strip(), lines.append)
        return lines

    def names(self, path: str = "") -> list[str]:
        """Return bare filenames (NLST)."""
        return [name.rsplit("/", 1)[-1] for name in self.ftp.nlst(path)]

    def download(self, remote: str, local: Path) -> int:
        """Download ``remote`` to ``local``; return bytes written."""
        written = 0

        def sink(chunk: bytes) -> None:
            nonlocal written
            handle.write(chunk)
            written += len(chunk)

        with local.open("wb") as handle:
            self.ftp.retrbinary(f"RETR {remote}", sink)
        return written

    def upload(self, local: Path, remote: str) -> int:
        """Upload ``local`` as ``remote``; return bytes sent."""
        with local.open("rb") as handle:
            self.ftp.storbinary(f"STOR {remote}", handle)
        return local.stat().st_size

    def mkdir(self, path: str) -> None:
        self.ftp.mkd(path)

    def delete(self, path: str) -> None:
        self.ftp.delete(path)

    def rmdir(self, path: str) -> None:
        self.ftp.rmd(path)


def _connect_from_args(args: argparse.Namespace) -> FTPClient:
    password = args.password
    if password is None:
        password = os.environ.get("FTP_PASSWORD")
    if password is None:
        if args.user == "anonymous":
            password = "anonymous@"
        elif sys.stdin.isatty():
            password = getpass(f"Password for {args.user}@{args.host}: ")
        else:
            raise RuntimeError("no password; use --password or set FTP_PASSWORD")
    return FTPClient(args.host, args.port, args.user, password, tls=args.tls,
                     passive=not args.active, timeout=args.timeout).connect()


def _dispatch(client: FTPClient, args: argparse.Namespace) -> int:
    if args.command == "list":
        lines = client.list_lines(args.path)
        print(f"Listing of {args.path or '/'} on {args.host}:")
        for line in lines:
            print("  " + line)
        if not lines:
            print("  (empty)")
    elif args.command == "get":
        local = Path(args.local) if args.local else Path(Path(args.remote).name)
        if not local.parent.is_dir():
            print(f"error: local directory {local.parent} does not exist", file=sys.stderr)
            return 2
        size = client.download(args.remote, local)
        print(f"Downloaded {args.remote} -> {local} ({size} bytes)")
    elif args.command == "put":
        source = Path(args.local)
        if not source.is_file():
            print(f"error: {source} is not a file", file=sys.stderr)
            return 2
        remote = args.remote or source.name
        size = client.upload(source, remote)
        print(f"Uploaded {source} -> {remote} ({size} bytes)")
    elif args.command == "mkdir":
        client.mkdir(args.path)
        print(f"Created remote directory {args.path}")
    elif args.command == "delete":
        client.delete(args.path)
        print(f"Deleted remote file {args.path}")
    elif args.command == "rmdir":
        client.rmdir(args.path)
        print(f"Removed remote directory {args.path}")
    elif args.command == "pwd":
        print(client.pwd())
    return 0


def _interactive(client: FTPClient) -> int:
    print("Interactive FTP session. Type 'help' for commands, 'quit' to exit.")
    while True:
        try:
            line = input("ftp> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        try:
            parts = shlex.split(line)
        except ValueError as exc:
            print(f"error: {exc}")
            continue
        command, arguments = parts[0].lower(), parts[1:]
        try:
            if command in ("quit", "exit", "bye"):
                return 0
            if command == "help":
                print("ls [path] | get REMOTE [LOCAL] | put LOCAL [REMOTE] | "
                      "mkdir PATH | rm PATH | rmdir PATH | pwd | quit")
            elif command in ("ls", "dir"):
                for entry in client.list_lines(arguments[0] if arguments else ""):
                    print("  " + entry)
            elif command == "pwd":
                print(client.pwd())
            elif command == "get" and arguments:
                local = (Path(arguments[1]) if len(arguments) > 1
                         else Path(Path(arguments[0]).name))
                size = client.download(arguments[0], local)
                print(f"{size} bytes -> {local}")
            elif command == "put" and arguments:
                source = Path(arguments[0])
                size = client.upload(source, arguments[1] if len(arguments) > 1 else source.name)
                print(f"{size} bytes uploaded")
            elif command == "mkdir" and arguments:
                client.mkdir(arguments[0])
                print("created")
            elif command in ("rm", "delete") and arguments:
                client.delete(arguments[0])
                print("deleted")
            elif command == "rmdir" and arguments:
                client.rmdir(arguments[0])
                print("removed")
            else:
                print("unknown or incomplete command; type 'help'")
        except ftplib.all_errors as exc:
            print(f"FTP error: {exc}")


def run_demo() -> int:
    """Exercise the client against a temporary local FTP server."""
    with tempfile.TemporaryDirectory(prefix="ftp-server-") as server_dir, \
            tempfile.TemporaryDirectory(prefix="ftp-client-") as client_dir:
        root = Path(server_dir)
        local = Path(client_dir)
        (root / "hello.txt").write_text("Hello from the mini FTP server!\n",
                                        encoding="utf-8")
        (root / "notes.md").write_text("# Demo notes\nOffline FTP demo.\n",
                                       encoding="utf-8")
        server = MiniFTPServer(root).start()
        print(f"Demo: mini FTP server on 127.0.0.1:{server.port} (root: temporary)")
        client = FTPClient("127.0.0.1", server.port, "demo", "demo", timeout=5.0)
        try:
            client.connect()
            print(f"Connected as {client.user}; remote directory: {client.pwd()}")
            print("\nRemote listing:")
            for line in client.list_lines():
                print("  " + line)

            target = local / "hello.txt"
            size = client.download("hello.txt", target)
            print(f"\nDownloaded hello.txt ({size} bytes): {target.read_text().strip()}")

            source = local / "upload.txt"
            source.write_text("Uploaded by the FTP demo.\n", encoding="utf-8")
            sent = client.upload(source, "upload.txt")
            print(f"Uploaded upload.txt ({sent} bytes)")

            client.mkdir("archive")
            print("Created remote directory archive")
            client.upload(source, "archive/upload-copy.txt")
            print("Uploaded a copy into archive/")

            names = sorted(client.names())
            print(f"Remote entries now: {', '.join(names)}")
            stored = (root / "upload.txt").read_text(encoding="utf-8")
            archived = (root / "archive" / "upload-copy.txt").read_text(encoding="utf-8")
            if stored != archived or "Uploaded by the FTP demo" not in stored:
                print("demo: server-side verification failed", file=sys.stderr)
                return 1
            print("\nServer-side verification: upload.txt and archive/upload-copy.txt match.")
        except ftplib.all_errors as exc:
            print(f"demo: FTP failure: {exc}", file=sys.stderr)
            return 1
        finally:
            client.close()
            server.stop()
        print("Demo complete: connect, list, get, put and mkdir all verified offline.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Transfer files to and from an FTP server.",
        epilog="Examples:\n"
               "  python3 solution.py --host ftp.example.com --user me list /pub\n"
               "  python3 solution.py --host ftp.example.com --user me get README.md\n"
               "  python3 solution.py --host ftp.example.com --user me put photo.jpg\n"
               "  python3 solution.py --demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", default=os.environ.get("FTP_HOST", ""),
                        help="FTP server hostname (or FTP_HOST)")
    parser.add_argument("--port", type=int, default=21, help="control port (default: 21)")
    parser.add_argument("--user", default="anonymous", help="username (default: anonymous)")
    parser.add_argument("--password", help="password (prefer FTP_PASSWORD env var)")
    parser.add_argument("--tls", action="store_true", help="use explicit FTPS (FTP_TLS)")
    parser.add_argument("--active", action="store_true", help="use active mode (default: passive)")
    parser.add_argument("--timeout", type=float, default=15.0,
                        help="network timeout in seconds (default: 15)")
    parser.add_argument("--demo", action="store_true",
                        help="run a self-contained offline demonstration")

    commands = parser.add_subparsers(dest="command")
    list_cmd = commands.add_parser("list", help="list a remote directory")
    list_cmd.add_argument("path", nargs="?", default="", help="remote path (default: .)")
    get_cmd = commands.add_parser("get", help="download a file")
    get_cmd.add_argument("remote", help="remote filename")
    get_cmd.add_argument("local", nargs="?", help="local destination (default: basename)")
    put_cmd = commands.add_parser("put", help="upload a file")
    put_cmd.add_argument("local", help="local filename")
    put_cmd.add_argument("remote", nargs="?", help="remote destination (default: basename)")
    mkdir_cmd = commands.add_parser("mkdir", help="create a remote directory")
    mkdir_cmd.add_argument("path")
    delete_cmd = commands.add_parser("delete", help="delete a remote file")
    delete_cmd.add_argument("path")
    rmdir_cmd = commands.add_parser("rmdir", help="remove a remote directory")
    rmdir_cmd.add_argument("path")
    commands.add_parser("pwd", help="print the remote working directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo:
        return run_demo()
    if not args.host:
        if not sys.stdin.isatty():
            print("error: --host is required (or use --demo)", file=sys.stderr)
            return 2
        try:
            args.host = input("FTP host: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 2
        if not args.host:
            print("error: no host entered", file=sys.stderr)
            return 2
    if args.timeout <= 0:
        print("error: --timeout must be positive", file=sys.stderr)
        return 2

    try:
        client = _connect_from_args(args)
    except (ftplib.Error, OSError, EOFError, RuntimeError) as exc:
        print(f"error: cannot connect to {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 1
    try:
        print(f"Connected to {args.host}:{args.port} as {args.user}")
        if args.command is None:
            return _interactive(client)
        return _dispatch(client, args)
    except ftplib.all_errors as exc:
        print(f"error: FTP operation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
