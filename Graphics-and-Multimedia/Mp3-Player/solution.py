#!/usr/bin/env python3
"""A playlist-based music player with metadata, transport controls and real audio.

Features
--------
* Reads ID3v2 tags (title, artist, album, year) with a filename fallback.
* Computes track duration from WAV headers or MP3 frame headers (no mutagen).
* Simulated transport (play / pause / resume / next / prev / seek) that is
  fully testable without a sound card, plus real playback through ``ffplay``,
  ``mpg123`` or ``aplay`` when one is installed and ``--play`` is given.
* Shuffle and repeat modes, playlist persistence as JSON.

Run without arguments for an interactive shell; ``--demo`` scripts a session
against generated silent audio files.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}
TEXT_FRAMES = {b"TIT2": "title", b"TPE1": "artist", b"TALB": "album", b"TYER": "year", b"TDRC": "year"}

MP3_BITRATES = {
    (1, 3): [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    (1, 2): [0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384],
    (1, 1): [0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448],
    (2, 3): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
    (2, 2): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
    (2, 1): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
SAMPLE_RATES = {1: [44100, 48000, 32000], 2: [22050, 24000, 16000], 25: [11025, 12000, 8000]}


def format_time(seconds: float) -> str:
    """Format seconds as ``M:SS.s``."""
    seconds = max(0.0, seconds)
    minutes, remainder = divmod(int(seconds), 60)
    return f"{minutes}:{remainder:02d}.{int((seconds % 1) * 10)}"


def _syncsafe(data: bytes) -> int:
    value = 0
    for byte in data:
        value = (value << 7) | (byte & 0x7F)
    return value


def _decode_text_frame(payload: bytes) -> str:
    if not payload:
        return ""
    encoding = payload[0]
    codec = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}.get(encoding, "latin-1")
    text = payload[1:].decode(codec, errors="replace")
    return text.replace("\x00", " ").strip()


def read_id3(path: Path) -> dict[str, str]:
    """Parse the common ID3v2 text frames; return an empty dict on failure."""
    try:
        with path.open("rb") as handle:
            header = handle.read(10)
            if len(header) < 10 or header[:3] != b"ID3":
                return {}
            major, flags = header[3], header[5]
            size = _syncsafe(header[6:10])
            body = handle.read(size)
    except OSError:
        return {}
    if not body:
        return {}
    if flags & 0x80:  # unsynchronisation
        body = body.replace(b"\xff\x00", b"\xff")
    position = 0
    if flags & 0x40 and len(body) >= 4:
        position = 4 + int.from_bytes(body[:4], "big")
    tags: dict[str, str] = {}
    while position + 10 <= len(body):
        frame_id = body[position : position + 4]
        if frame_id.strip(b"\x00") == b"":
            break
        raw_size = body[position + 4 : position + 8]
        frame_size = _syncsafe(raw_size) if major >= 4 else int.from_bytes(raw_size, "big")
        position += 10
        if frame_size <= 0 or position + frame_size > len(body):
            break
        payload = body[position : position + frame_size]
        position += frame_size
        key = TEXT_FRAMES.get(frame_id)
        if key and key not in tags:
            text = _decode_text_frame(payload)
            if text:
                tags[key] = text
    return tags


def mp3_duration(path: Path) -> float:
    """Walk MPEG audio frames and sum their sample counts."""
    try:
        data = path.read_bytes()
    except OSError:
        return 0.0
    offset = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        offset = 10 + _syncsafe(data[6:10])
    total_samples = 0
    sample_rate = 0
    frames = 0
    cursor = offset
    limit = len(data) - 4
    while cursor < limit:
        b1, b2, b3 = data[cursor], data[cursor + 1], data[cursor + 2]
        if b1 != 0xFF or (b2 & 0xE0) != 0xE0:
            cursor += 1
            continue
        version_bits = (b2 >> 3) & 0x03
        layer_bits = (b2 >> 1) & 0x03
        bitrate_index = (b3 >> 4) & 0x0F
        rate_index = (b3 >> 2) & 0x03
        padding = (b3 >> 1) & 0x01
        version = {3: 1, 2: 2, 0: 25}.get(version_bits)
        layer = {3: 1, 2: 2, 1: 3}.get(layer_bits)
        if not version or not layer:
            cursor += 1
            continue
        table = MP3_BITRATES.get((1 if version == 1 else 2, layer))
        if not table or bitrate_index == 0 or bitrate_index >= len(table):
            cursor += 1
            continue
        rate = SAMPLE_RATES[version][rate_index] if rate_index < 3 else 0
        if not rate:
            cursor += 1
            continue
        bitrate = table[bitrate_index] * 1000
        if layer == 1:
            length = (12 * bitrate // rate + padding) * 4
            samples = 384
        elif layer == 3 and version != 1:
            length = 72 * bitrate // rate + padding
            samples = 576
        else:
            length = 144 * bitrate // rate + padding
            samples = 1152
        if length <= 4 or cursor + length > len(data):
            cursor += 1
            continue
        sample_rate = rate
        total_samples += samples
        frames += 1
        cursor += length
        if frames > 500_000:
            break
    if not frames or not sample_rate:
        return 0.0
    return total_samples / sample_rate


def audio_duration(path: Path) -> float:
    """Return duration for a WAV file (via header) or MP3 (via frames)."""
    suffix = path.suffix.lower()
    if suffix == ".wav":
        try:
            with wave.open(str(path), "rb") as handle:
                rate = handle.getframerate()
                return handle.getnframes() / rate if rate else 0.0
        except (wave.Error, OSError):
            return 0.0
    if suffix == ".mp3":
        return mp3_duration(path)
    return 0.0


@dataclass
class Track:
    """One audio file and the metadata shown in the playlist."""

    path: Path
    title: str
    artist: str
    album: str = ""
    duration: float = 0.0

    @classmethod
    def from_path(cls, path: Path) -> "Track":
        tags = read_id3(path)
        fallback_title, fallback_artist = parse_filename(path.stem)
        return cls(
            path=path,
            title=tags.get("title", fallback_title),
            artist=tags.get("artist", fallback_artist),
            album=tags.get("album", ""),
            duration=audio_duration(path),
        )

    @property
    def label(self) -> str:
        return f"{self.artist} — {self.title}" if self.artist else self.title


def parse_filename(stem: str) -> tuple[str, str]:
    """Derive ``(title, artist)`` from names like ``Artist - Title``."""
    cleaned = re.sub(r"^\d{1,3}[\s._-]+", "", stem).strip()
    if " - " in cleaned:
        artist, title = cleaned.split(" - ", 1)
        return title.strip(), artist.strip()
    return cleaned.replace("_", " ").strip(), "Unknown Artist"


class AudioBackend:
    """Thin wrapper around an external command-line audio player."""

    def __init__(self) -> None:
        self.command = self._detect()
        self.process: subprocess.Popen[bytes] | None = None

    @staticmethod
    def _detect() -> tuple[str, str] | None:
        for name, args in (("ffplay", "ffplay"), ("mpg123", "mpg123"), ("aplay", "aplay")):
            if shutil.which(name):
                return name, args
        return None

    @property
    def name(self) -> str:
        return self.command[0] if self.command else "none"

    def can_play(self, track: Track) -> bool:
        if not self.command:
            return False
        if self.command[0] == "mpg123":
            return track.path.suffix.lower() == ".mp3"
        if self.command[0] == "aplay":
            return track.path.suffix.lower() == ".wav"
        return True

    def play(self, track: Track, start: float = 0.0) -> bool:
        """Start playback in the background; return True when launched."""
        self.stop()
        if not self.can_play(track):
            return False
        if self.command is None:
            return False
        name = self.command[0]
        if name == "ffplay":
            argv = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error"]
            if start > 0:
                argv += ["-ss", f"{start:.3f}"]
            argv.append(str(track.path))
        elif name == "mpg123":
            argv = ["mpg123", "-q", str(track.path)]
        else:
            argv = ["aplay", "-q", str(track.path)]
        try:
            self.process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.process = None
            return False
        return True

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None

    def busy(self) -> bool:
        return self.process is not None and self.process.poll() is None


class Player:
    """Transport state machine over a :class:`Playlist`.

    Time only advances through :meth:`tick`, which keeps the demo deterministic
    and makes every transition testable without sleeping.
    """

    def __init__(self, tracks: Sequence[Track], backend: AudioBackend | None = None, seed: int = 7) -> None:
        self.tracks = list(tracks)
        self.backend = backend
        self.random = random.Random(seed)
        self.order: list[int] = list(range(len(self.tracks)))
        self.index = 0
        self.position = 0.0
        self.playing = False
        self.paused = False
        self.shuffle = False
        self.repeat = "off"  # off | one | all

    @property
    def current(self) -> Track | None:
        if not self.tracks:
            return None
        return self.tracks[self.order[self.index]]

    @property
    def state(self) -> str:
        if not self.playing:
            return "stopped"
        return "paused" if self.paused else "playing"

    def _apply_order(self) -> None:
        current_track = self.current
        if self.shuffle:
            self.order = list(range(len(self.tracks)))
            self.random.shuffle(self.order)
        else:
            self.order = list(range(len(self.tracks)))
        if current_track is not None:
            self.index = self.order.index(self.tracks.index(current_track))

    def play(self, number: int | None = None) -> Track | None:
        """Start (or restart) playback, optionally at a 1-based playlist number."""
        if not self.tracks:
            raise ValueError("playlist is empty")
        if number is not None:
            if not 1 <= number <= len(self.tracks):
                raise ValueError(f"track number must be 1..{len(self.tracks)}")
            if self.shuffle:
                self.index = self.order.index(number - 1)
            else:
                self.order = list(range(len(self.tracks)))
                self.index = number - 1
        self.position = 0.0
        self.playing = True
        self.paused = False
        if self.backend and self.current:
            self.backend.play(self.current)
        return self.current

    def pause(self) -> bool:
        if self.playing and not self.paused:
            self.paused = True
            if self.backend:
                self.backend.stop()
            return True
        return False

    def resume(self) -> bool:
        if self.playing and self.paused:
            self.paused = False
            if self.backend and self.current:
                self.backend.play(self.current, self.position)
            return True
        return False

    def stop(self) -> None:
        self.playing = False
        self.paused = False
        self.position = 0.0
        if self.backend:
            self.backend.stop()

    def seek(self, seconds: float) -> float:
        track = self.current
        if not track:
            return 0.0
        self.position = max(0.0, min(seconds, track.duration))
        if self.playing and not self.paused and self.backend:
            self.backend.play(track, self.position)
        return self.position

    def tick(self, seconds: float) -> bool:
        """Advance simulated time. Returns True when the track changed."""
        track = self.current
        if not track or not self.playing or self.paused:
            return False
        self.position += max(0.0, seconds)
        if self.position < track.duration or track.duration <= 0:
            return False
        overflow = self.position - track.duration
        if self.repeat == "one":
            self.position = 0.0
            if self.backend:
                self.backend.play(track)
            return False
        advanced = self.next(auto=True)
        if advanced:
            self.position = min(overflow, self.current.duration if self.current else 0)
        return advanced

    def next(self, auto: bool = False) -> bool:
        """Move to the next track. Returns False at the end when repeat is off."""
        if not self.tracks:
            return False
        last = self.index >= len(self.order) - 1
        if last:
            if self.repeat == "all":
                self.index = 0
            elif auto:
                self.playing = False
                self.paused = False
                self.position = self.current.duration if self.current else 0
                if self.backend:
                    self.backend.stop()
                return False
            else:
                self.index = 0
        else:
            self.index += 1
        self.position = 0.0
        if self.backend and self.playing and not self.paused and self.current:
            self.backend.play(self.current)
        return True

    def previous(self) -> bool:
        if not self.tracks:
            return False
        self.index = (self.index - 1) % len(self.order)
        self.position = 0.0
        if self.backend and self.playing and not self.paused and self.current:
            self.backend.play(self.current)
        return True

    def set_shuffle(self, enabled: bool) -> None:
        if enabled == self.shuffle:
            return
        self.shuffle = enabled
        self._apply_order()

    def set_repeat(self, mode: str) -> None:
        if mode not in {"off", "one", "all"}:
            raise ValueError("repeat must be off, one or all")
        self.repeat = mode

    def status_line(self) -> str:
        track = self.current
        if not track:
            return "no track"
        total = len(self.tracks)
        return (
            f"[{self.state:<7}] {self.index + 1}/{total}  {track.label}  "
            f"{format_time(self.position)}/{format_time(track.duration)}"
            f"  shuffle={'on' if self.shuffle else 'off'} repeat={self.repeat}"
        )


def load_playlist(path: Path) -> list[Track]:
    """Load track paths from a JSON playlist, skipping missing files."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"cannot read playlist {path}: {exc}") from exc
    entries = data.get("tracks", data) if isinstance(data, dict) else data
    tracks: list[Track] = []
    for entry in entries:
        candidate = Path(entry).expanduser()
        if not candidate.is_absolute():
            candidate = (path.parent / candidate).resolve()
        if candidate.is_file():
            tracks.append(Track.from_path(candidate))
    return tracks


def save_playlist(path: Path, tracks: Iterable[Track]) -> None:
    """Persist the playlist as JSON (relative paths when possible)."""
    base = path.parent.resolve()
    entries = []
    for track in tracks:
        try:
            entries.append(str(track.path.resolve().relative_to(base)))
        except ValueError:
            entries.append(str(track.path.resolve()))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tracks": entries}, indent=2) + "\n", encoding="utf-8")


def add_paths(tracks: list[Track], paths: Sequence[str]) -> int:
    """Add audio files or scan directories; return the number of new tracks."""
    existing = {track.path.resolve() for track in tracks}
    added = 0
    for raw in paths:
        path = Path(raw).expanduser()
        candidates: list[Path]
        if path.is_dir():
            candidates = sorted(p for p in path.rglob("*") if p.suffix.lower() in AUDIO_SUFFIXES)
        elif path.is_file():
            candidates = [path]
        else:
            print(f"warning: not found: {path}", file=sys.stderr)
            continue
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in existing:
                continue
            tracks.append(Track.from_path(resolved))
            existing.add(resolved)
            added += 1
    return added


def print_tracks(tracks: Sequence[Track], active: int | None = None) -> None:
    """Print a numbered playlist table."""
    if not tracks:
        print("  (playlist is empty)")
        return
    for number, track in enumerate(tracks, start=1):
        marker = ">" if active == number else " "
        album = f"  [{track.album}]" if track.album else ""
        print(f" {marker} {number:>2}. {track.label}{album}  ({format_time(track.duration)})")


def make_silent_wav(path: Path, seconds: float, rate: int = 22050) -> None:
    """Write a silent mono 16-bit WAV file."""
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * seconds))


def transcode_with_tags(source: Path, destination: Path, title: str, artist: str, album: str) -> bool:
    """Convert WAV to MP3 with ID3 tags using ffmpeg, if available."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-c:a", "libmp3lame", "-b:a", "64k",
        "-metadata", f"title={title}", "-metadata", f"artist={artist}",
        "-metadata", f"album={album}", "-id3v2_version", "3", str(destination),
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and destination.exists()


def run_demo() -> int:
    """Script a full player session against generated audio files."""
    workdir = Path(tempfile.mkdtemp(prefix="mp3-player-demo-"))
    print("Mp3 Player demo")
    print(f"  workspace: {workdir}")

    wav_specs = [
        ("01 - Neon Skyline - Night Drive.wav", 4.0),
        ("02 - Neon Skyline - Static Bloom.wav", 6.0),
        ("03 - Paper Satellites - Slow Orbit.wav", 3.0),
    ]
    for name, seconds in wav_specs:
        make_silent_wav(workdir / name, seconds)

    tracks: list[Track] = []
    for name, _ in wav_specs:
        tracks.append(Track.from_path(workdir / name))

    mp3 = workdir / "04 - Neon Skyline - Afterglow.mp3"
    if transcode_with_tags(workdir / wav_specs[0][0], mp3, "Afterglow", "Neon Skyline", "Midnight Transit"):
        tracks.append(Track.from_path(mp3))
        print(f"  generated: 3 WAV + 1 MP3 with ID3 tags ({mp3.stat().st_size / 1024:.1f} KiB)")
    else:
        print("  generated: 3 WAV files (ffmpeg not available, MP3/ID3 sample skipped)")

    print("  playlist:")
    print_tracks(tracks)

    backend = AudioBackend()
    print(f"  audio backend detected: {backend.name}")
    player = Player(tracks, backend=None, seed=7)
    player.play(1)
    print(f"  play 1  -> {player.status_line()}")
    player.tick(1.5)
    print(f"  +1.5s   -> {player.status_line()}")
    player.pause()
    print(f"  pause   -> {player.status_line()}")
    player.resume()
    player.tick(1.5)
    print(f"  resume  -> {player.status_line()}")
    print(f"  next    -> {player.next()}; {player.status_line()}")
    player.previous()
    print(f"  prev    -> {player.status_line()}")
    player.set_shuffle(True)
    print(f"  shuffle -> order={[n + 1 for n in player.order]}")
    player.set_shuffle(False)
    player.set_repeat("one")
    player.play(3)
    player.tick(5.0)
    print(f"  repeat one, +5s -> {player.status_line()}")
    player.set_repeat("all")
    last = len(tracks)
    player.play(last)
    player.tick(4.5)
    print(f"  repeat all, +4.5s -> {player.status_line()}")

    playlist_file = workdir / "playlist.json"
    save_playlist(playlist_file, tracks)
    reloaded = load_playlist(playlist_file)
    print(f"  saved playlist: {playlist_file.name} -> {len(reloaded)} tracks reloaded")

    checks = [
        len(tracks) >= 3,
        all(track.duration > 0 for track in tracks),
        tracks[0].artist == "Neon Skyline",
        player.repeat == "all",
        len(reloaded) == len(tracks),
    ]
    print(f"  checks  : {sum(checks)}/{len(checks)} passed")
    print("Demo complete (simulated transport: no audio device required).")
    return 0 if all(checks) else 1


def run_shell(player: Player, playlist_path: Path) -> int:
    """Minimal interactive transport shell."""
    print("Commands: list, play N, pause, resume, next, prev, seek SEC, tick SEC, shuffle on|off,")
    print("          repeat off|one|all, status, quit")
    while True:
        try:
            raw = input("mp3> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not raw:
            continue
        command, _, argument = raw.partition(" ")
        command = command.lower()
        argument = argument.strip()
        try:
            if command in {"quit", "exit", "q"}:
                return 0
            if command in {"list", "ls"}:
                print_tracks(player.tracks, player.index + 1 if player.tracks else None)
            elif command == "play":
                number = int(argument) if argument else None
                player.play(number)
                print(player.status_line())
            elif command == "pause":
                print("paused" if player.pause() else "nothing is playing")
            elif command == "resume":
                print("resumed" if player.resume() else "not paused")
            elif command in {"next", "n"}:
                print(player.status_line() if player.next() else "end of playlist")
            elif command in {"prev", "p"}:
                player.previous()
                print(player.status_line())
            elif command == "seek":
                print(f"position {format_time(player.seek(float(argument)))}")
            elif command == "shuffle":
                player.set_shuffle(argument.lower() in {"on", "1", "yes", "true"})
                print(f"shuffle {'on' if player.shuffle else 'off'}")
            elif command == "repeat":
                player.set_repeat(argument.lower())
                print(f"repeat {player.repeat}")
            elif command == "tick":
                changed = player.tick(float(argument or 1.0))
                print(("track changed; " if changed else "") + player.status_line())
            elif command in {"status", "st"}:
                print(player.status_line())
            elif command in {"save"}:
                save_playlist(playlist_path, player.tracks)
                print(f"saved {len(player.tracks)} tracks to {playlist_path}")
            elif command in {"help", "?"}:
                print("list | play N | pause | resume | next | prev | seek SEC | tick SEC | shuffle on|off")
                print("repeat off|one|all | status | save | quit")
            else:
                print(f"unknown command: {command}")
        except ValueError as exc:
            print(f"error: {exc}")


def real_playback(tracks: Sequence[Track], shuffle: bool, repeat: str) -> int:
    """Play the playlist through an external audio backend."""
    backend = AudioBackend()
    if not backend.command:
        print("Error: no audio backend found (install ffmpeg/ffplay, mpg123 or aplay).", file=sys.stderr)
        return 2
    playable = [track for track in tracks if backend.can_play(track)]
    if not playable:
        print(f"Error: {backend.name} cannot play any of these formats.", file=sys.stderr)
        return 2
    randomizer = random.Random()
    if shuffle:
        randomizer.shuffle(playable)
    print(f"Playing {len(playable)} track(s) with {backend.name}. Press Ctrl+C to stop.")
    try:
        while True:
            for track in playable:
                print(f"  ▶ {track.label} ({format_time(track.duration)})")
                if not backend.play(track):
                    print(f"  ! could not play {track.path.name}", file=sys.stderr)
                    continue
                while backend.busy():
                    time.sleep(0.2)
            if repeat == "one":
                continue
            if repeat != "all":
                break
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        backend.stop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Playlist music player with ID3 metadata, transport controls, shuffle and repeat.",
        epilog="Run without arguments for an interactive session.",
    )
    parser.add_argument("--playlist", default="playlist.json", metavar="FILE", help="playlist JSON (default: playlist.json)")
    parser.add_argument("--add", nargs="+", metavar="PATH", help="add audio files or scan directories")
    parser.add_argument("--list", action="store_true", help="print the playlist and exit")
    parser.add_argument("--play", action="store_true", help="actually play audio through ffplay/mpg123/aplay")
    parser.add_argument("--track", type=int, metavar="N", help="start at track N (1-based) with --play")
    parser.add_argument("--shuffle", action="store_true", help="shuffle playback order")
    parser.add_argument("--repeat", choices=["off", "one", "all"], default="off", help="repeat mode (default: off)")
    parser.add_argument("--demo", action="store_true", help="generate silent audio and simulate a session")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    playlist_path = Path(args.playlist).expanduser()
    try:
        tracks = load_playlist(playlist_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    added = 0
    if args.add:
        added = add_paths(tracks, args.add)
        try:
            save_playlist(playlist_path, tracks)
        except OSError as exc:
            print(f"Error saving playlist: {exc}", file=sys.stderr)
            return 2
        print(f"Added {added} track(s); playlist now has {len(tracks)}.")

    if args.list or added:
        print_tracks(tracks)
        if not args.play:
            return 0

    if args.play:
        if not tracks:
            print("Error: playlist is empty (use --add).", file=sys.stderr)
            return 2
        if args.track is not None:
            if not 1 <= args.track <= len(tracks):
                print(f"Error: --track must be 1..{len(tracks)}", file=sys.stderr)
                return 2
            ordered = tracks[args.track - 1 :] + tracks[: args.track - 1]
        else:
            ordered = tracks
        return real_playback(ordered, args.shuffle, args.repeat)

    if not tracks:
        if not sys.stdin.isatty():
            parser.error("playlist is empty (use --add or --demo)")
        try:
            raw = input("Music folder to scan: ").strip().strip("'\"")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.", file=sys.stderr)
            return 130
        if not raw:
            parser.error("no music folder given")
        add_paths(tracks, [raw])
        if not tracks:
            print("Error: no supported audio files found.", file=sys.stderr)
            return 2
        try:
            save_playlist(playlist_path, tracks)
        except OSError as exc:
            print(f"Error saving playlist: {exc}", file=sys.stderr)
            return 2
        print(f"Saved {len(tracks)} tracks to {playlist_path}")

    player = Player(tracks, backend=None)
    player.set_shuffle(args.shuffle)
    player.set_repeat(args.repeat)
    return run_shell(player, playlist_path)


if __name__ == "__main__":
    raise SystemExit(main())
