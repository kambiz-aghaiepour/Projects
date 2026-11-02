# FTP Program

## Problem

A file transfer program that can transfer files back and forth from a remote
web server.

Part of the **Networking** category in the Mega Project List.

## Features

- Real FTP client built on `ftplib`, with explicit FTPS (`--tls`) support.
- List directories, download, upload, create/remove directories, delete files
  and print the remote working directory.
- Passive mode by default, optional active mode, and timeouts on every socket.
- Non-interactive subcommands for scripting plus an interactive `ftp>` shell
  when no subcommand is given.
- Password via `FTP_PASSWORD`, `--password`, or a secure prompt.
- `--demo` starts the bundled minimal FTP server in-process and verifies a full
  login → list → download → upload → mkdir cycle offline.

## Requirements

Python 3.10+ and its standard library. No third-party packages. The demo uses
only loopback and temporary directories.

## Usage

```bash
python3 solution.py --demo

python3 solution.py --host ftp.example.com --user alice list /pub
python3 solution.py --host ftp.example.com --user alice get README.md
python3 solution.py --host ftp.example.com --user alice get README.md ./docs/README.md
python3 solution.py --host ftp.example.com --user alice put photo.jpg
python3 solution.py --host ftp.example.com --user alice mkdir backups
python3 solution.py --host ftp.example.com --user alice delete old.txt
python3 solution.py --host ftp.example.com --user alice --tls list

FTP_PASSWORD=secret python3 solution.py --host ftp.example.com --user alice
```

| Option | Meaning |
| --- | --- |
| `--host`, `--port` | Server address (or `FTP_HOST`); default port `21`. |
| `--user`, `--password` | Credentials; anonymous is the default user. |
| `--tls` | Use explicit FTPS and protect the data channel. |
| `--active` | Use active mode instead of passive. |
| `--timeout` | Network timeout in seconds (default `15`). |
| `list [path]` | Print a detailed remote directory listing. |
| `get REMOTE [LOCAL]` | Download a file. |
| `put LOCAL [REMOTE]` | Upload a file. |
| `mkdir`, `delete`, `rmdir`, `pwd` | Remote management commands. |
| `--demo` | Run the offline client/server demonstration. |

## Example Output

```
$ python3 solution.py --demo
Demo: mini FTP server on 127.0.0.1:39679 (root: temporary)
Connected as demo; remote directory: /

Remote listing:
  -rw-r--r-- 1 owner group         32 Nov 02 18:52 hello.txt
  -rw-r--r-- 1 owner group         31 Nov 02 18:52 notes.md

Downloaded hello.txt (32 bytes): Hello from the mini FTP server!
Uploaded upload.txt (26 bytes)
Created remote directory archive
Uploaded a copy into archive/
Remote entries now: archive, hello.txt, notes.md, upload.txt

Server-side verification: upload.txt and archive/upload-copy.txt match.
Demo complete: connect, list, get, put and mkdir all verified offline.
```

## Implementation Notes

`solution.py` wraps `ftplib.FTP`/`FTP_TLS` in a small `FTPClient` that always
sets a socket timeout, logs in explicitly, and uses binary mode (`RETR`/`STOR`)
for transfers. Downloads stream chunks to disk instead of buffering whole files
in memory. Errors from `ftplib` are caught at the command boundary and turned
into a single clear message and non-zero exit status.

`mini_ftp_server.py` is a deliberately small RFC 959 subset: USER/PASS (any
credentials accepted), PASV/EPSV, LIST/NLST, RETR/STOR, SIZE, MKD/RMD/DELE,
CWD/PWD, TYPE, SYST, FEAT and QUIT. Paths are resolved inside a temporary root
and traversal outside it is rejected. It is a demo fixture, not a hardened
server: there is no real authentication, TLS, chroot isolation or concurrency
limit. The client itself speaks ordinary FTP/FTPS and works against real
servers; it is not SFTP (which uses SSH and a different protocol).
