import io
import os
import requests
from pathlib import Path
from PIL import Image

try:
    from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TRCK, TDRC
    from mutagen.id3 import ID3NoHeaderError
    from mutagen.flac import FLAC, Picture
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen.oggvorbis import OggVorbis
    from mutagen.oggopus import OggOpus
    MUTAGEN_OK = True
except ImportError:
    MUTAGEN_OK = False


def _fetch_cover(url: str) -> bytes | None:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
    except Exception:
        return None


def _sanitize(value) -> str:
    return str(value) if value is not None else ""


def embed_cover_and_metadata(file_path: str, meta: dict):
    if not MUTAGEN_OK or not os.path.exists(file_path):
        return

    cover_data = _fetch_cover(meta.get("cover_url"))
    ext = Path(file_path).suffix.lower()

    try:
        if ext == ".mp3":
            _embed_mp3(file_path, meta, cover_data)
        elif ext == ".flac":
            _embed_flac(file_path, meta, cover_data)
        elif ext in (".m4a", ".mp4"):
            _embed_m4a(file_path, meta, cover_data)
        elif ext == ".wav":
            _embed_wav(file_path, meta, cover_data)
        elif ext == ".ogg":
            _embed_ogg(file_path, meta, cover_data)
        elif ext == ".opus":
            _embed_opus(file_path, meta, cover_data)
    except Exception:
        pass


def _embed_mp3(path: str, meta: dict, cover: bytes | None):
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()

    if meta.get("title"):
        tags["TIT2"] = TIT2(encoding=3, text=_sanitize(meta["title"]))
    if meta.get("artist"):
        tags["TPE1"] = TPE1(encoding=3, text=_sanitize(meta["artist"]))
    if meta.get("album"):
        tags["TALB"] = TALB(encoding=3, text=_sanitize(meta["album"]))
    if meta.get("track_number"):
        tags["TRCK"] = TRCK(encoding=3, text=_sanitize(meta["track_number"]))
    if meta.get("year"):
        tags["TDRC"] = TDRC(encoding=3, text=_sanitize(meta["year"]))
    if cover:
        tags.delall("APIC")
        tags["APIC"] = APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover)

    tags.save(path)


def _embed_flac(path: str, meta: dict, cover: bytes | None):
    audio = FLAC(path)

    if meta.get("title"):
        audio["title"] = _sanitize(meta["title"])
    if meta.get("artist"):
        audio["artist"] = _sanitize(meta["artist"])
    if meta.get("album"):
        audio["album"] = _sanitize(meta["album"])
    if meta.get("track_number"):
        audio["tracknumber"] = _sanitize(meta["track_number"])
    if meta.get("year"):
        audio["date"] = _sanitize(meta["year"])

    if cover:
        audio.clear_pictures()
        pic = Picture()
        pic.type = 3
        pic.mime = "image/jpeg"
        pic.data = cover
        audio.add_picture(pic)

    audio.save()


def _embed_m4a(path: str, meta: dict, cover: bytes | None):
    audio = MP4(path)

    if meta.get("title"):
        audio["\xa9nam"] = [_sanitize(meta["title"])]
    if meta.get("artist"):
        audio["\xa9ART"] = [_sanitize(meta["artist"])]
    if meta.get("album"):
        audio["\xa9alb"] = [_sanitize(meta["album"])]
    if meta.get("year"):
        audio["\xa9day"] = [_sanitize(meta["year"])]
    if meta.get("track_number"):
        audio["trkn"] = [(int(meta["track_number"]), 0)]
    if cover:
        audio["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]

    audio.save()


def _embed_wav(path: str, meta: dict, cover: bytes | None):
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()

    if meta.get("title"):
        tags["TIT2"] = TIT2(encoding=3, text=_sanitize(meta["title"]))
    if meta.get("artist"):
        tags["TPE1"] = TPE1(encoding=3, text=_sanitize(meta["artist"]))
    if meta.get("album"):
        tags["TALB"] = TALB(encoding=3, text=_sanitize(meta["album"]))
    if cover:
        tags.delall("APIC")
        tags["APIC"] = APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover)

    tags.save(path)


def _embed_ogg(path: str, meta: dict, cover: bytes | None):
    audio = OggVorbis(path)

    if meta.get("title"):
        audio["title"] = _sanitize(meta["title"])
    if meta.get("artist"):
        audio["artist"] = _sanitize(meta["artist"])
    if meta.get("album"):
        audio["album"] = _sanitize(meta["album"])
    if meta.get("year"):
        audio["date"] = _sanitize(meta["year"])

    if cover:
        import base64
        pic = Picture()
        pic.type = 3
        pic.mime = "image/jpeg"
        pic.data = cover
        pic_data = base64.b64encode(pic.write()).decode("ascii")
        audio["metadata_block_picture"] = [pic_data]

    audio.save()


def _embed_opus(path: str, meta: dict, cover: bytes | None):
    audio = OggOpus(path)

    if meta.get("title"):
        audio["title"] = _sanitize(meta["title"])
    if meta.get("artist"):
        audio["artist"] = _sanitize(meta["artist"])
    if meta.get("album"):
        audio["album"] = _sanitize(meta["album"])
    if meta.get("year"):
        audio["date"] = _sanitize(meta["year"])

    if cover:
        import base64
        pic = Picture()
        pic.type = 3
        pic.mime = "image/jpeg"
        pic.data = cover
        pic_data = base64.b64encode(pic.write()).decode("ascii")
        audio["metadata_block_picture"] = [pic_data]

    audio.save()
