#!/usr/bin/env python3
"""Read and write ID3v1 and ID3v2.3/2.4 tags, including embedded album art.

The MP3 audio frames are never re-encoded: the existing ID3v2 tag and ID3v1
trailer are stripped, the new tags are written around the untouched audio,
and the file is replaced atomically.  Frames outside the supported set
(``TIT2``, ``TPE1``, ``TALB``, ``TYER``/``TDRC``, ``TCON``, ``TRCK``,
``COMM`` and ``APIC``) are preserved verbatim.

A "dummy" MP3 (valid-looking MPEG frame headers plus silence) is enough for
tagging; ``--demo`` builds one in a temporary directory and round-trips tags
and a generated PNG cover.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import struct
import sys
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TEXT_FIELDS = {
    "TIT2": "title",
    "TPE1": "artist",
    "TALB": "album",
    "TYER": "year",
    "TDRC": "year",
    "TCON": "genre",
    "TRCK": "track",
}
KNOWN_FRAMES = set(TEXT_FIELDS) | {"COMM", "APIC"}

GENRES = [
    "Blues", "Classic Rock", "Country", "Dance", "Disco", "Funk", "Grunge",
    "Hip-Hop", "Jazz", "Metal", "New Age", "Oldies", "Other", "Pop", "R&B",
    "Rap", "Reggae", "Rock", "Techno", "Industrial", "Alternative", "Ska",
    "Death Metal", "Pranks", "Soundtrack", "Euro-Techno", "Ambient",
    "Trip-Hop", "Vocal", "Jazz+Funk", "Fusion", "Trance", "Classical",
    "Instrumental", "Acid", "House", "Game", "Sound Clip", "Gospel", "Noise",
    "AlternRock", "Bass", "Soul", "Punk", "Space", "Meditative",
    "Instrumental Pop", "Instrumental Rock", "Ethnic", "Gothic", "Darkwave",
    "Techno-Industrial", "Electronic", "Pop-Folk", "Eurodance", "Dream",
    "Southern Rock", "Comedy", "Cult", "Gangsta", "Top 40", "Christian Rap",
    "Pop/Funk", "Jungle", "Native American", "Cabaret", "New Wave",
    "Psychedelic", "Rave", "Showtunes", "Trailer", "Lo-Fi", "Tribal",
    "Acid Punk", "Acid Jazz", "Polka", "Retro", "Musical", "Rock & Roll",
    "Hard Rock",
]
GENRE_INDEX = {name.casefold(): i for i, name in enumerate(GENRES)}


class TagError(Exception):
    """Raised for unsupported or corrupt tag data."""


@dataclass
class Tag:
    """Editable tag fields plus provenance and preserved frames."""

    title: str = ""
    artist: str = ""
    album: str = ""
    year: str = ""
    genre: str = ""
    track: str = ""
    comment: str = ""
    art_mime: str = ""
    art_data: bytes = b""
    version: int = 3
    has_v2: bool = False
    has_v1: bool = False
    extra: list[tuple[bytes, bytes]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(
            [self.title, self.artist, self.album, self.year, self.genre,
             self.track, self.comment, self.art_data]
        )


# --------------------------------------------------------------------------
# Low-level helpers
# --------------------------------------------------------------------------


def syncsafe(value: int) -> bytes:
    """Encode a 28-bit integer as four syncsafe bytes (ID3v2.4)."""
    if not 0 <= value < 1 << 28:
        raise TagError("tag or frame is too large for ID3v2")
    return bytes([(value >> 21) & 0x7F, (value >> 14) & 0x7F,
                  (value >> 7) & 0x7F, value & 0x7F])


def from_syncsafe(data: bytes) -> int:
    if len(data) != 4 or any(b & 0x80 for b in data):
        raise TagError("invalid syncsafe integer")
    return (data[0] << 21) | (data[1] << 14) | (data[2] << 7) | data[3]


def split_audio(data: bytes) -> tuple[bytes, bytes, bytes]:
    """Return (v2_tag_bytes, audio, v1_tag_bytes) with tags removed."""
    v2 = b""
    rest = data
    while rest.startswith(b"ID3") and len(rest) >= 10:
        size = from_syncsafe(rest[6:10])
        total = 10 + size
        if total > len(rest):
            raise TagError("truncated ID3v2 tag")
        if not v2:
            v2 = rest[:total]
        rest = rest[total:]
    v1 = b""
    if len(rest) >= 128 and rest[-128:-125] == b"TAG":
        v1 = rest[-128:]
        rest = rest[:-128]
    return v2, rest, v1


def decode_latin1(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("latin-1", "replace").strip()


def encode_latin1(text: str, width: int) -> bytes:
    raw = text.encode("latin-1", "replace")[:width]
    return raw.ljust(width, b"\x00")


# --------------------------------------------------------------------------
# ID3v1
# --------------------------------------------------------------------------


def parse_v1(raw: bytes) -> dict[str, str]:
    if len(raw) != 128 or raw[:3] != b"TAG":
        raise TagError("not an ID3v1 tag")
    genre_index = raw[127]
    comment = raw[97:127]
    track = ""
    if comment[28] == 0 and comment[29] != 0:
        track = str(comment[29])
        comment = comment[:28]
    return {
        "title": decode_latin1(raw[3:33]),
        "artist": decode_latin1(raw[33:63]),
        "album": decode_latin1(raw[63:93]),
        "year": decode_latin1(raw[93:97]),
        "comment": decode_latin1(comment),
        "track": track,
        "genre": GENRES[genre_index] if genre_index < len(GENRES) else "",
    }


def build_v1(tag: Tag) -> bytes:
    track_no = ""
    if tag.track:
        match = re.match(r"\s*(\d+)", tag.track)
        track_no = match.group(1) if match else ""
    genre_index = GENRE_INDEX.get(tag.genre.casefold(), 255)
    if tag.genre.isdigit():
        genre_index = int(tag.genre) if 0 <= int(tag.genre) < 256 else 255
    comment = encode_latin1(tag.comment, 28)
    track_value = min(255, int(track_no)) if track_no else 0
    return (
        b"TAG"
        + encode_latin1(tag.title, 30)
        + encode_latin1(tag.artist, 30)
        + encode_latin1(tag.album, 30)
        + encode_latin1(tag.year, 4)
        + comment
        + b"\x00"
        + bytes([track_value])
        + bytes([genre_index])
    )


# --------------------------------------------------------------------------
# ID3v2 reading
# --------------------------------------------------------------------------


def decode_text_payload(payload: bytes) -> str:
    """Decode the first text string of a T*** frame."""
    if not payload:
        return ""
    encoding, data = payload[0], payload[1:]
    try:
        if encoding == 0:
            text = data.decode("latin-1")
        elif encoding == 1:
            text = data.decode("utf-16")
        elif encoding == 2:
            text = data.decode("utf-16-be")
        elif encoding == 3:
            text = data.decode("utf-8")
        else:
            return ""
    except UnicodeDecodeError:
        return ""
    return text.split("\x00", 1)[0].strip()


def split_terminated(data: bytes, encoding: int) -> tuple[bytes, bytes]:
    """Split on the encoding's NUL terminator."""
    if encoding in (1, 2):
        for i in range(0, len(data) - 1, 2):
            if data[i:i + 2] == b"\x00\x00":
                return data[:i], data[i + 2:]
        return data, b""
    index = data.find(b"\x00")
    return (data, b"") if index == -1 else (data[:index], data[index + 1:])


def decode_terminated(data: bytes, encoding: int) -> str:
    raw, _ = split_terminated(data, encoding)
    try:
        if encoding == 0:
            return raw.decode("latin-1", "replace")
        if encoding == 1:
            return raw.decode("utf-16", "replace")
        if encoding == 2:
            return raw.decode("utf-16-be", "replace")
        return raw.decode("utf-8", "replace")
    except UnicodeDecodeError:
        return ""


def parse_apic(payload: bytes) -> tuple[str, bytes] | None:
    if len(payload) < 4:
        return None
    encoding = payload[0]
    mime, rest = split_terminated(payload[1:], 0)
    if len(rest) < 1:
        return None
    rest = rest[1:]  # picture type
    _, image = split_terminated(rest, encoding)
    if not image:
        return None
    return mime.decode("latin-1", "replace"), image


def read_v2(raw: bytes) -> Tag:
    if len(raw) < 10 or raw[:3] != b"ID3":
        raise TagError("not an ID3v2 tag")
    major, revision, flags = raw[3], raw[4], raw[5]
    if major not in (3, 4):
        raise TagError(f"unsupported ID3v2.{major}; only 2.3 and 2.4 are handled")
    size = from_syncsafe(raw[6:10])
    body = raw[10:10 + size]
    if flags & 0x80:
        body = body.replace(b"\xff\x00", b"\xff")
    offset = 0
    if flags & 0x40:
        if len(body) < 4:
            raise TagError("truncated extended header")
        ext_size = from_syncsafe(body[:4]) if major == 4 else int.from_bytes(body[:4], "big")
        offset = ext_size if major == 4 else 4 + ext_size
    tag = Tag(version=major, has_v2=True)
    known: set[str] = set()
    while offset + 10 <= len(body):
        frame_id = body[offset:offset + 4]
        if frame_id == b"\x00\x00\x00\x00" or not re.fullmatch(rb"[A-Z0-9]{4}", frame_id):
            break
        frame_size = (
            from_syncsafe(body[offset + 4:offset + 8])
            if major == 4
            else int.from_bytes(body[offset + 4:offset + 8], "big")
        )
        flags_bytes = body[offset + 8:offset + 10]
        offset += 10
        if frame_size <= 0 or offset + frame_size > len(body):
            break
        payload = body[offset:offset + frame_size]
        offset += frame_size
        if major == 3 and flags_bytes[1] & 0xC0:
            continue  # compressed/encrypted frames are skipped
        name = frame_id.decode("ascii")
        if name in TEXT_FIELDS:
            setattr(tag, TEXT_FIELDS[name], decode_text_payload(payload))
            known.add(name)
        elif name == "COMM" and len(payload) > 4:
            encoding = payload[0]
            _, rest = payload[1:4], payload[4:]
            _, text_data = split_terminated(rest, encoding)
            tag.comment = decode_terminated(text_data, encoding).strip()
            known.add(name)
        elif name == "APIC":
            parsed = parse_apic(payload)
            if parsed and not tag.art_data:
                tag.art_mime, tag.art_data = parsed
            known.add(name)
        elif name not in known:
            tag.extra.append((frame_id, payload))
    return tag


# --------------------------------------------------------------------------
# ID3v2 writing
# --------------------------------------------------------------------------


def encode_text(text: str, version: int) -> tuple[int, bytes]:
    if version == 4:
        return 3, text.encode("utf-8")
    return 1, b"\xff\xfe" + text.encode("utf-16-le")


def make_frame(frame_id: bytes, payload: bytes, version: int) -> bytes:
    size = syncsafe(len(payload)) if version == 4 else len(payload).to_bytes(4, "big")
    return frame_id + size + b"\x00\x00" + payload


def text_frame(frame_id: bytes, text: str, version: int) -> bytes:
    encoding, data = encode_text(text, version)
    return make_frame(frame_id, bytes([encoding]) + data, version)


def comm_frame(text: str, version: int) -> bytes:
    encoding, data = encode_text(text, version)
    terminator = b"\x00\x00" if encoding in (1, 2) else b"\x00"
    empty_desc = b"\xff\xfe" + terminator if encoding in (1, 2) else terminator
    return make_frame(b"COMM", bytes([encoding]) + b"eng" + empty_desc + data, version)


def apic_frame(mime: str, data: bytes, version: int) -> bytes:
    # Latin-1 description and MIME keep every player happy.
    mime_bytes = (mime or "image/png").encode("latin-1", "replace")
    return make_frame(
        b"APIC",
        bytes([0]) + mime_bytes + b"\x00" + bytes([3]) + b"\x00" + data,
        version,
    )


def build_v2(tag: Tag, version: int, padding: int = 1024) -> bytes:
    frames = b""
    if tag.title:
        frames += text_frame(b"TIT2", tag.title, version)
    if tag.artist:
        frames += text_frame(b"TPE1", tag.artist, version)
    if tag.album:
        frames += text_frame(b"TALB", tag.album, version)
    if tag.year:
        frames += text_frame(b"TYER" if version == 3 else b"TDRC", tag.year, version)
    if tag.genre:
        frames += text_frame(b"TCON", tag.genre, version)
    if tag.track:
        frames += text_frame(b"TRCK", tag.track, version)
    if tag.comment:
        frames += comm_frame(tag.comment, version)
    if tag.art_data:
        frames += apic_frame(tag.art_mime, tag.art_data, version)
    for frame_id, payload in tag.extra:
        if frame_id not in KNOWN_FRAMES and re.fullmatch(rb"[A-Z0-9]{4}", frame_id):
            frames += make_frame(frame_id, payload, version)
    body = frames + b"\x00" * padding
    header = b"ID3" + bytes([version, 0, 0]) + syncsafe(len(body))
    return header + body


# --------------------------------------------------------------------------
# Public read/write
# --------------------------------------------------------------------------


def read_tags(path: Path) -> Tag:
    """Read ID3v2.3/2.4 and ID3v1 tags, with v2 taking precedence."""
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise TagError(f"file not found: {path}") from exc
    v2_raw, _, v1_raw = split_audio(data)
    tag = Tag()
    if v2_raw:
        tag = read_v2(v2_raw)
    if v1_raw:
        tag.has_v1 = True
        for key, value in parse_v1(v1_raw).items():
            if value and not getattr(tag, key):
                setattr(tag, key, value)
    return tag


def write_tags(
    path: Path,
    tag: Tag,
    version: int = 3,
    write_v1: bool = True,
    strip_v2: bool = False,
) -> None:
    """Rewrite tags around the untouched audio using an atomic replace."""
    if version not in (3, 4):
        raise TagError("tag version must be 3 or 4")
    data = path.read_bytes()
    _, audio, _ = split_audio(data)
    if not audio:
        raise TagError("file contains no audio payload")
    payload = b"" if strip_v2 else build_v2(tag, version)
    if write_v1:
        payload += audio + build_v1(tag)
    else:
        payload += audio
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------
# Demo helpers
# --------------------------------------------------------------------------


def make_dummy_mp3(frames: int = 8) -> bytes:
    """Build an MPEG-1 Layer III-looking stream with silent frame payloads."""
    frame = b"\xff\xfb\x90\x64" + b"\x00" * 413
    return frame * frames


def make_png(width: int = 8, height: int = 8) -> bytes:
    """Create a tiny valid RGB PNG without third-party libraries."""
    raw = b"".join(
        b"\x00" + b"".join(bytes([x * 30 % 256, y * 30 % 256, 160]) for x in range(width))
        for y in range(height)
    )

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


# --------------------------------------------------------------------------
# Demo
# --------------------------------------------------------------------------

DEMO_FIELDS: dict[str, Any] = {
    "title": "Demo Track (Remastered)",
    "artist": "The Standard Library",
    "album": "Batteries Included",
    "year": "2026",
    "genre": "Electronic",
    "track": "7/12",
    "comment": "Round-tripped by the ID3 demo.",
}


def run_demo() -> int:
    """Round-trip ID3v2 tags, album art and the ID3v1 fallback."""
    with tempfile.TemporaryDirectory(prefix="mp3tagger-") as tmp:
        work = Path(tmp)
        song = work / "demo.mp3"
        png = work / "cover.png"
        audio = make_dummy_mp3()
        song.write_bytes(audio)
        png.write_bytes(make_png())
        art = png.read_bytes()
        print(f"Built dummy MP3 ({len(audio)} bytes) and PNG cover ({len(art)} bytes)")

        tag = Tag(art_mime="image/png", art_data=art, **DEMO_FIELDS)
        write_tags(song, tag, version=3)
        print(f"Wrote ID3v2.3 + ID3v1; file is now {song.stat().st_size} bytes")

        read_back = read_tags(song)
        for key, expected in DEMO_FIELDS.items():
            actual = getattr(read_back, key)
            assert actual == expected, f"{key}: {actual!r} != {expected!r}"
        assert read_back.art_data == art and read_back.art_mime == "image/png"
        assert read_back.has_v1 and read_back.has_v2 and read_back.version == 3
        print("ID3v2.3 round-trip: " + ", ".join(
            f"{k}={getattr(read_back, k)!r}" for k in ("title", "artist", "album", "year", "track")
        ))
        print(f"Album art: {read_back.art_mime}, {len(read_back.art_data)} bytes, "
              f"PNG signature={read_back.art_data[:8]!r}")

        header = song.read_bytes()[:6]
        print(f"File starts with {header!r} (ID3v2.3, no flags)")
        assert header == b"ID3\x03\x00\x00"

        # Rewriting with a v2.4 tag must leave the audio bytes identical.
        _, before_audio, _ = split_audio(song.read_bytes())
        write_tags(song, Tag(art_mime="image/png", art_data=art, **DEMO_FIELDS), version=4)
        _, after_audio, _ = split_audio(song.read_bytes())
        assert before_audio == after_audio == audio
        v4 = read_tags(song)
        assert v4.version == 4 and v4.title == DEMO_FIELDS["title"]
        print("ID3v2.4 rewrite preserved the audio payload byte-for-byte.")

        # Strip v2, leaving only ID3v1, and confirm the fallback values.
        write_tags(song, read_back, version=3, write_v1=True, strip_v2=True)
        v1_only = read_tags(song)
        assert v1_only.has_v1 and not v1_only.has_v2
        assert v1_only.title == DEMO_FIELDS["title"]
        assert v1_only.track == "7"
        assert v1_only.genre == "Electronic"
        print(f"ID3v1-only fallback reads: title={v1_only.title!r}, "
              f"track={v1_only.track!r}, genre={v1_only.genre!r}")
        assert len(song.read_bytes()) == len(audio) + 128

        # Art can be extracted independently.
        extracted = work / "extracted.png"
        if read_back.art_data:
            extracted.write_bytes(read_back.art_data)
        assert extracted.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        print(f"Extracted art verified as PNG: {extracted.name}")

        leftover = [p.name for p in work.iterdir() if p.name.startswith("demo.mp3.")]
        assert not leftover, f"temp files left behind: {leftover}"
        print("Atomic write left no temporary files behind.")
        print("\nDemo complete: tags and album art round-trip correctly.")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show or edit ID3v1/ID3v2.3/2.4 tags and album art in MP3 files.",
        epilog="Use --set field=value repeatedly; --demo runs an offline round-trip.",
    )
    parser.add_argument("file", nargs="?", type=Path, help="MP3 file to inspect or edit")
    parser.add_argument("--show", action="store_true", help="print tags (default action)")
    parser.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE",
                        help="set title/artist/album/year/genre/track/comment; empty clears")
    parser.add_argument("--art", type=Path, help="embed this image as the front cover")
    parser.add_argument("--extract-art", type=Path, metavar="PATH", help="write embedded art here")
    parser.add_argument("--remove-art", action="store_true", help="drop embedded album art")
    parser.add_argument("--clear", action="store_true", help="remove all tags")
    parser.add_argument("--tag-version", choices=["2.3", "2.4"], default="2.3",
                        help="ID3v2 version to write (default 2.3)")
    parser.add_argument("--no-v1", action="store_true", help="do not write an ID3v1 trailer")
    parser.add_argument("--v1-only", action="store_true", help="strip ID3v2 and write only ID3v1")
    parser.add_argument("--demo", action="store_true", help="run the offline demo")
    return parser


def print_tag(path: Path, tag: Tag) -> None:
    raw = path.read_bytes()
    v2_raw, audio, v1_raw = split_audio(raw)
    print(f"File      : {path}")
    print(f"Audio     : {len(audio)} bytes")
    print(f"ID3v2     : {'2.' + str(tag.version) if v2_raw else 'none'}"
          + (f" ({len(v2_raw)} bytes)" if v2_raw else ""))
    print(f"ID3v1     : {'yes' if v1_raw else 'no'}")
    for key in ("title", "artist", "album", "year", "genre", "track", "comment"):
        print(f"{key.title():<10}: {getattr(tag, key)}")
    if tag.art_data:
        print(f"Artwork   : {tag.art_mime}, {len(tag.art_data)} bytes")
    else:
        print("Artwork   : none")


def apply_updates(tag: Tag, assignments: list[str]) -> None:
    for assignment in assignments:
        if "=" not in assignment:
            raise TagError(f"expected FIELD=VALUE, got {assignment!r}")
        key, value = assignment.split("=", 1)
        key = key.strip().lower()
        if key not in {"title", "artist", "album", "year", "genre", "track", "comment"}:
            raise TagError(f"unknown field {key!r}")
        setattr(tag, key, value.strip())


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.demo:
        return run_demo()
    if args.file is None:
        build_parser().print_help()
        return 0
    if not args.file.exists():
        print(f"error: file not found: {args.file}", file=sys.stderr)
        return 2

    try:
        tag = read_tags(args.file)
        if args.extract_art:
            if not tag.art_data:
                print("error: no embedded artwork", file=sys.stderr)
                return 1
            args.extract_art.write_bytes(tag.art_data)
            print(f"Wrote {len(tag.art_data)} bytes of {tag.art_mime} to {args.extract_art}")
            return 0

        changing = bool(
            args.set or args.art or args.remove_art or args.clear
            or args.v1_only or args.no_v1
        )
        if not changing:
            print_tag(args.file, tag)
            return 0

        if args.clear:
            tag = Tag()
        else:
            apply_updates(tag, args.set)
            if args.art:
                try:
                    data = args.art.read_bytes()
                except OSError as exc:
                    raise TagError(f"cannot read artwork: {exc}") from exc
                suffix = args.art.suffix.lower()
                tag.art_mime = {
                    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".gif": "image/gif", ".webp": "image/webp",
                }.get(suffix, "application/octet-stream")
                tag.art_data = data
            if args.remove_art:
                tag.art_mime, tag.art_data = "", b""

        version = 4 if args.tag_version == "2.4" else 3
        if args.v1_only and tag.art_data:
            print("error: --v1-only cannot store album art; remove --art or keep ID3v2",
                  file=sys.stderr)
            return 2
        write_tags(
            args.file,
            tag,
            version=version,
            write_v1=not args.no_v1,
            strip_v2=args.v1_only,
        )
        updated = read_tags(args.file)
        print_tag(args.file, updated)
        print("Tags updated.")
        return 0
    except TagError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
