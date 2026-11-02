# Online White Board

**Category:** Web · **Project:** Online-White-Board

## Problem

Create an application which allows you to draw pictures, write notes and use
various colors to flesh out ideas for projects.

## Features

- HTML5 canvas with freehand drawing via mouse, touch or stylus.
- Twelve-colour palette plus a custom colour picker, and brush sizes from 1 to
  32 px.
- Pen and eraser tools; "Save as PNG" exports the current canvas.
- Named boards: create, switch, clear and delete boards from the sidebar.
- SQLite persistence — boards and every stroke survive a server restart.
- Polling collaboration: clients fetch strokes newer than their last sequence
  number every 1.5 seconds, so another viewer's drawing appears without a
  reload.
- JSON HTTP API for boards, incremental strokes, clearing and deletion.
- `--demo` starts the server on an ephemeral loopback port and drives the API
  with `urllib` (create board, add strokes, incremental fetch, persistence,
  clear, HTML check) — no browser or internet needed.

## Requirements

Python 3.10+ and the standard library (`http.server`, `sqlite3`). A modern
browser is needed only to use the drawing UI; the server and demo are headless.

## Usage

```bash
python3 solution.py --demo
python3 solution.py --port 8000
python3 solution.py --port 0 --db boards.db
```

Then open the printed URL, for example <http://127.0.0.1:8000/>. With
`--port 0` the operating system chooses a free port.

| Option | Meaning |
| --- | --- |
| `--host ADDR` | Bind address (default `127.0.0.1`, loopback only). |
| `--port N` | Listen port; `0` chooses a free port (default 8000). |
| `--db PATH` | SQLite database file (default `whiteboard.db`). |
| `--demo` | Run the offline API demonstration. |

### HTTP API

| Method and path | Purpose |
| --- | --- |
| `GET /api/boards` | List boards with stroke counts, newest first. |
| `POST /api/boards` | Create a board: `{"name": "Sprint plan"}`. |
| `GET /api/boards/{id}` | Board metadata plus all strokes. |
| `GET /api/boards/{id}/strokes?since=N` | Strokes with `seq > N` and `last_seq`. |
| `POST /api/boards/{id}/strokes` | Append `{"strokes": [...]}`; returns assigned sequences. |
| `POST /api/boards/{id}/clear` | Delete all strokes on a board. |
| `DELETE /api/boards/{id}` | Delete a board and its strokes. |

A stroke is
`{"tool": "pen"|"eraser", "color": "#rrggbb", "size": 1-64, "points": [[x, y], ...]}`.

## Example Output

```
Online White Board demo (offline: local server + disposable SQLite database)
Server: http://127.0.0.1:45405

1. GET  /api/boards            -> 200, 0 board(s)
2. POST /api/boards            -> 201, id=9c4c958b8eff, name='Demo brainstorm'
3. POST .../strokes            -> 201, assigned seq=[1, 2, 3]
4. GET  .../boards/9c4c958b8eff -> 200, 3 strokes, last_seq=3
5. GET  .../strokes?since=2    -> 200, 1 new stroke(s), last_seq=3
6. POST one more stroke        -> 201, seq=[4]
7. GET  /api/boards            -> 200, 1 board, 4 strokes in 'Demo brainstorm'
   persistence check           -> OK
8. POST .../clear              -> 200; 0 strokes remain
9. GET  /                      -> 200, 16734 bytes of HTML, canvas=True

Demo complete: API round trip passed; board data persisted in SQLite.
```

## Implementation Notes

The server is a `ThreadingHTTPServer` with a small routing layer. `BoardStore`
owns one SQLite connection guarded by a lock; foreign keys cascade board
deletion to strokes. Each board has a monotonically increasing `seq` per
stroke, computed inside the insert transaction, which makes the
`?since=<last_seq>` polling API cheap and resistant to duplicate delivery.

The client keeps a local stroke list, redraws from white on every accepted
remote batch, and posts a completed stroke on `pointerup`. Canvas coordinates
are stored in the canvas's internal 1200×720 space, so different screen sizes
see the same drawing. Erasing is implemented as a white pen stroke, which keeps
PNG exports opaque and replay deterministic.

Limitations: collaboration is last-writer-wins with no conflict resolution or
presence indicators; polling adds up to 1.5 s latency and one request per
client per interval; a `clear` performed by another client is not announced as
an event, so existing viewers keep their local copy until they switch or reload
the board. The server is intended for a trusted local network — it has no
authentication or TLS and binds loopback by default.
