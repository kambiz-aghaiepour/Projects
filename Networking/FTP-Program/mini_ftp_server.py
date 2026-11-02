"""A deliberately small FTP server used by the FTP client demo.

It implements just enough of RFC 959 (USER, PASS, PASV/EPSV, LIST, NLST,
RETR, STOR, SIZE, MKD, RMD, DELE, CWD, PWD, TYPE, SYST, FEAT, QUIT) for the
standard-library ``ftplib`` client to exercise the full upload/download path.
Files are confined to a temporary root directory.  This is a demo helper, not
a production server: there is no authentication, TLS or rate limiting.
"""

from __future__ import annotations

import socket
import socketserver
import threading
import time
from pathlib import Path, PurePosixPath
from typing import cast


def _listing_line(path: Path) -> str:
    """Render one ls-style directory entry."""
    stat = path.stat()
    kind = "d" if path.is_dir() else "-"
    permissions = "rwxr-xr-x" if path.is_dir() else "rw-r--r--"
    stamp = time.strftime("%b %d %H:%M", time.localtime(stat.st_mtime))
    return f"{kind}{permissions} 1 owner group {stat.st_size:>10} {stamp} {path.name}\r\n"


class FTPHandler(socketserver.StreamRequestHandler):
    """Per-connection FTP command handler."""

    def setup(self) -> None:
        super().setup()
        self.cwd = PurePosixPath("/")
        self.username = ""
        self.authenticated = False
        self.passive: socket.socket | None = None

    def handle(self) -> None:
        self.reply("220 Mini FTP server ready")
        while True:
            raw = self.rfile.readline(8192)
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            command, _, argument = line.partition(" ")
            command = command.upper()
            handler = getattr(self, f"ftp_{command.lower()}", None)
            if handler is None:
                self.reply("502 Command not implemented")
                continue
            if not self.authenticated and command not in {"USER", "PASS", "QUIT",
                                                          "FEAT", "NOOP"}:
                self.reply("530 Please login with USER and PASS")
                continue
            try:
                stop = handler(argument.strip())
            except (OSError, ValueError) as exc:
                self.reply(f"550 {exc}")
                stop = False
            if stop:
                break
        self.close_passive()

    # -- plumbing ---------------------------------------------------------
    def reply(self, text: str) -> None:
        try:
            self.wfile.write((text + "\r\n").encode("utf-8"))
            self.wfile.flush()
        except OSError:
            pass

    def close_passive(self) -> None:
        if self.passive is not None:
            try:
                self.passive.close()
            except OSError:
                pass
            self.passive = None

    def virtual_path(self, argument: str) -> PurePosixPath:
        """Resolve an FTP path against the virtual cwd, clamping at root."""
        current = PurePosixPath("/") if argument.startswith("/") else self.cwd
        for part in argument.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if len(current.parts) > 1:
                    current = current.parent
            else:
                current = current / part
        return current

    def local_path(self, argument: str) -> Path:
        virtual = self.virtual_path(argument)
        relative = virtual.relative_to("/")
        candidate = (cast("MiniFTPServer", self.server).root / str(relative)).resolve()
        root = cast("MiniFTPServer", self.server).root
        if candidate != root and root not in candidate.parents:
            raise ValueError("path escapes the server root")
        return candidate

    def open_passive(self) -> socket.socket:
        self.close_passive()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(10)
        self.passive = listener
        return listener

    def begin_transfer(self) -> socket.socket | None:
        """Send 150 and accept the pending passive connection."""
        if self.passive is None:
            self.reply("425 Use PASV or EPSV first")
            return None
        self.reply("150 Opening data connection")
        try:
            connection, _ = self.passive.accept()
        except OSError:
            self.close_passive()
            self.reply("425 Cannot open data connection")
            return None
        self.close_passive()
        return connection

    # -- session commands -------------------------------------------------
    def ftp_user(self, argument: str) -> None:
        self.username = argument or "anonymous"
        self.reply("331 Password required")

    def ftp_pass(self, argument: str) -> None:
        if not self.username:
            self.reply("503 Login with USER first")
            return
        self.authenticated = True
        self.reply("230 Logged in")

    def ftp_syst(self, argument: str) -> None:
        self.reply("215 UNIX Type: L8")

    def ftp_feat(self, argument: str) -> None:
        self.reply("211-Features:\r\n SIZE\r\n UTF8\r\n PASV\r\n211 End")

    def ftp_opts(self, argument: str) -> None:
        self.reply("200 Always in UTF8 mode")

    def ftp_type(self, argument: str) -> None:
        self.reply("200 Type set")

    def ftp_noop(self, argument: str) -> None:
        self.reply("200 OK")

    def ftp_pwd(self, argument: str) -> None:
        self.reply(f'257 "{self.cwd}" is the current directory')

    def ftp_cwd(self, argument: str) -> None:
        target = self.local_path(argument or "/")
        if not target.is_dir():
            raise ValueError("not a directory")
        self.cwd = self.virtual_path(argument or "/")
        self.reply("250 Directory changed")

    def ftp_cdup(self, argument: str) -> None:
        self.ftp_cwd("..")

    def ftp_pasv(self, argument: str) -> None:
        listener = self.open_passive()
        port = listener.getsockname()[1]
        self.reply(f"227 Entering Passive Mode (127,0,0,1,{port >> 8},{port & 0xFF})")

    def ftp_epsv(self, argument: str) -> None:
        listener = self.open_passive()
        port = listener.getsockname()[1]
        self.reply(f"229 Entering Extended Passive Mode (|||{port}|)")

    def ftp_quit(self, argument: str) -> bool:
        self.reply("221 Goodbye")
        return True

    # -- directory and file commands --------------------------------------
    def ftp_list(self, argument: str) -> None:
        target = self.local_path(argument or ".")
        if target.is_file():
            entries = [target]
        elif target.is_dir():
            entries = sorted(target.iterdir(), key=lambda item: item.name.lower())
        else:
            raise ValueError("no such directory")
        connection = self.begin_transfer()
        if connection is None:
            return
        try:
            for entry in entries:
                try:
                    connection.sendall(_listing_line(entry).encode("utf-8"))
                except OSError:
                    break
        finally:
            connection.close()
        self.reply("226 Transfer complete")

    def ftp_nlst(self, argument: str) -> None:
        target = self.local_path(argument or ".")
        if target.is_file():
            names = [target.name]
        elif target.is_dir():
            names = sorted(item.name for item in target.iterdir())
        else:
            raise ValueError("no such directory")
        connection = self.begin_transfer()
        if connection is None:
            return
        try:
            connection.sendall("".join(name + "\r\n" for name in names).encode("utf-8"))
        finally:
            connection.close()
        self.reply("226 Transfer complete")

    def ftp_size(self, argument: str) -> None:
        target = self.local_path(argument)
        if not target.is_file():
            raise ValueError("not a regular file")
        self.reply(f"213 {target.stat().st_size}")

    def ftp_retr(self, argument: str) -> None:
        target = self.local_path(argument)
        if not target.is_file():
            raise ValueError("no such file")
        connection = self.begin_transfer()
        if connection is None:
            return
        try:
            with target.open("rb") as handle:
                while chunk := handle.read(65536):
                    connection.sendall(chunk)
        finally:
            connection.close()
        self.reply("226 Transfer complete")

    def ftp_stor(self, argument: str) -> None:
        target = self.local_path(argument)
        if not target.parent.is_dir():
            raise ValueError("destination directory does not exist")
        connection = self.begin_transfer()
        if connection is None:
            return
        try:
            with target.open("wb") as handle:
                while chunk := connection.recv(65536):
                    handle.write(chunk)
        finally:
            connection.close()
        self.reply("226 Transfer complete")

    def ftp_mkd(self, argument: str) -> None:
        target = self.local_path(argument)
        target.mkdir(parents=False, exist_ok=False)
        self.reply(f'257 "{self.virtual_path(argument)}" created')

    def ftp_rmd(self, argument: str) -> None:
        target = self.local_path(argument)
        target.rmdir()
        self.reply("250 Directory removed")

    def ftp_dele(self, argument: str) -> None:
        target = self.local_path(argument)
        target.unlink()
        self.reply("250 File deleted")


class MiniFTPServer(socketserver.ThreadingTCPServer):
    """Threaded FTP server rooted at a directory."""

    allow_reuse_address = True
    daemon_threads = True
    address_family = socket.AF_INET

    def __init__(self, root: str | Path, host: str = "127.0.0.1", port: int = 0) -> None:
        self.root = Path(root).resolve()
        super().__init__((host, port), FTPHandler)
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    def start(self) -> "MiniFTPServer":
        self._thread = threading.Thread(target=self.serve_forever,
                                        kwargs={"poll_interval": 0.05}, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self.shutdown()
        self.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
