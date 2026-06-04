import sys
import re
import json
import time
import requests
import yt_dlp
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


def _ffmpeg_path() -> str | None:
    exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    local = SCRIPT_DIR / "ffmpeg" / exe
    if local.exists():
        return str(SCRIPT_DIR / "ffmpeg")
    return None

AUDIO_EXTENSIONS = {"mp3", "flac", "wav", "m4a", "ogg", "opus", "mp4", "webm", "aac", "wma"}
THUMB_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

_ANON_TOKEN: str | None = None
_TOKEN_EXPIRY: float = 0.0

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()


def detect_platform(url: str) -> str:
    u = url.lower()
    if "spotify.com" in u:
        return "spotify"
    if "music.apple.com" in u:
        return "apple_music"
    return "youtube"


def _extract_spotify_id(url: str) -> tuple[str, str]:
    m = re.search(
        r"spotify\.com/(?:[a-z]{2}/)?(?:intl-[a-z]+/)?(track|album|playlist)/([A-Za-z0-9]+)",
        url,
    )
    return (m.group(1), m.group(2)) if m else ("", "")


# --- anonymous token path ---

def _get_anon_token() -> str:
    global _ANON_TOKEN, _TOKEN_EXPIRY
    if _ANON_TOKEN and time.time() < _TOKEN_EXPIRY:
        return _ANON_TOKEN
    resp = requests.get(
        "https://open.spotify.com/get_access_token?reason=transport&productType=web_player",
        headers={"User-Agent": _UA, "app-platform": "WebPlayer"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _ANON_TOKEN = data["accessToken"]
    _TOKEN_EXPIRY = data.get("accessTokenExpirationTimestampMs", 0) / 1000 - 30
    return _ANON_TOKEN


def _api(path: str) -> dict:
    token = _get_anon_token()
    resp = requests.get(
        f"https://api.spotify.com/v1/{path}",
        headers={"Authorization": f"Bearer {token}", "User-Agent": _UA},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _parse_api_track(track: dict, album_override: dict | None = None) -> dict:
    album = album_override or track.get("album") or {}
    images = album.get("images") or []
    cover = images[0]["url"] if images else None
    artists = track.get("artists") or []
    artist = ", ".join(a["name"] for a in artists)
    title = track.get("name", "")
    return {
        "title": title,
        "artist": artist,
        "album": album.get("name"),
        "year": (album.get("release_date") or "")[:4],
        "track_number": track.get("track_number"),
        "cover_url": cover,
        "search_query": f"{artist} - {title} audio",
        "duration": (track.get("duration_ms") or 0) // 1000,
    }


def _get_via_api(kind: str, sid: str) -> list:
    if kind == "track":
        return [_parse_api_track(_api(f"tracks/{sid}"))]

    if kind == "album":
        album = _api(f"albums/{sid}")
        results = []
        page = album.get("tracks", {})
        while True:
            for t in page.get("items", []):
                results.append(_parse_api_track(t, album))
            nxt = page.get("next")
            if not nxt:
                break
            token = _get_anon_token()
            page = requests.get(nxt, headers={"Authorization": f"Bearer {token}", "User-Agent": _UA}, timeout=10).json()
        return results

    if kind == "playlist":
        results = []
        page = _api(f"playlists/{sid}/tracks?limit=50")
        while True:
            for item in page.get("items", []):
                t = item.get("track")
                if t:
                    results.append(_parse_api_track(t))
            nxt = page.get("next")
            if not nxt:
                break
            token = _get_anon_token()
            page = requests.get(nxt, headers={"Authorization": f"Bearer {token}", "User-Agent": _UA}, timeout=10).json()
        return results

    return []


# --- embed page scraping fallback ---

def _embed_url(kind: str, sid: str) -> str:
    return f"https://open.spotify.com/embed/{kind}/{sid}"


def _scrape_embed(kind: str, sid: str) -> dict:
    resp = requests.get(
        _embed_url(kind, sid),
        headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"},
        timeout=12,
    )
    resp.raise_for_status()
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        resp.text,
        re.DOTALL,
    )
    if not m:
        raise RuntimeError("Could not parse Spotify embed page")
    return json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"]


def _best_cover(images: list) -> str | None:
    if not images:
        return None
    return sorted(images, key=lambda x: x.get("maxWidth", 0), reverse=True)[0]["url"]


def _get_via_embed(kind: str, sid: str) -> list:
    entity = _scrape_embed(kind, sid)

    if kind == "track":
        artists = entity.get("artists") or []
        artist = ", ".join(a["name"] for a in artists)
        title = entity.get("name") or entity.get("title", "")
        year = (entity.get("releaseDate") or {}).get("isoString", "")[:4]
        cover = _best_cover(entity.get("visualIdentity", {}).get("image", []))
        return [
            {
                "title": title,
                "artist": artist,
                "album": None,
                "year": year,
                "track_number": None,
                "cover_url": cover,
                "search_query": f"{artist} - {title} audio",
                "duration": (entity.get("duration") or 0) // 1000,
            }
        ]

    if kind in ("album", "playlist"):
        album_name = entity.get("name") or entity.get("title", "")
        album_artist = entity.get("subtitle", "")
        year = (entity.get("releaseDate") or {}).get("isoString", "")[:4]
        cover = _best_cover(entity.get("visualIdentity", {}).get("image", []))
        track_list = entity.get("trackList") or []
        results = []
        for t in track_list:
            title = t.get("title") or t.get("name", "")
            artist = t.get("subtitle") or album_artist
            results.append(
                {
                    "title": title,
                    "artist": artist,
                    "album": album_name if kind == "album" else None,
                    "year": year,
                    "track_number": None,
                    "cover_url": cover,
                    "search_query": f"{artist} - {title} audio",
                    "duration": (t.get("duration") or 0) // 1000,
                }
            )
        return results

    return []


def get_spotify_metadata(url: str) -> list:
    kind, sid = _extract_spotify_id(url)
    if not sid:
        raise RuntimeError(f"Cannot parse Spotify URL: {url}")

    try:
        return _get_via_api(kind, sid)
    except Exception:
        pass

    return _get_via_embed(kind, sid)


# --- Apple Music ---

def _itunes_track(row: dict, album_name=None, artist_fallback=None, cover_fallback=None, year_fallback=None) -> dict:
    cover = (row.get("artworkUrl100") or cover_fallback or "").replace("100x100bb", "600x600bb")
    artist = row.get("artistName") or artist_fallback or ""
    title = row.get("trackName") or row.get("collectionName") or ""
    return {
        "title": title,
        "artist": artist,
        "album": row.get("collectionName") or album_name,
        "year": (row.get("releaseDate") or year_fallback or "")[:4],
        "track_number": row.get("trackNumber"),
        "cover_url": cover,
        "search_query": f"{artist} - {title} audio",
        "duration": (row.get("trackTimeMillis") or 0) // 1000,
    }


def _itunes_lookup(track_id: str) -> list:
    try:
        resp = requests.get(f"https://itunes.apple.com/lookup?id={track_id}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("resultCount"):
            return [_itunes_track(data["results"][0])]
    except Exception:
        pass
    return []


def _itunes_album(album_id: str) -> list:
    try:
        resp = requests.get(f"https://itunes.apple.com/lookup?id={album_id}&entity=song", timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    album_name = artist_name = cover_url = year = None
    results = []
    for r in data.get("results", []):
        if r.get("wrapperType") == "collection":
            album_name = r.get("collectionName")
            artist_name = r.get("artistName")
            cover_url = (r.get("artworkUrl100") or "").replace("100x100bb", "600x600bb")
            year = (r.get("releaseDate") or "")[:4]
        elif r.get("wrapperType") == "track":
            results.append(_itunes_track(r, album_name, artist_name, cover_url, year))
    return results


def _itunes_search_from_url(url: str) -> list:
    path = re.sub(r"https?://[^/]+", "", url.split("?")[0])
    parts = [p for p in path.split("/") if p and not re.fullmatch(r"\d+", p) and p not in ("us","ru","gb","de","fr","jp","kr","cn","au","ca","it","es","pl","tr","ua","kz","by","am","ge","az","uz")]
    query = " ".join(parts[-3:]).replace("-", " ")
    if not query.strip():
        return []
    try:
        resp = requests.get(
            f"https://itunes.apple.com/search?term={requests.utils.quote(query)}&media=music&limit=1",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("resultCount"):
            return [_itunes_track(data["results"][0])]
    except Exception:
        pass
    return []


def get_apple_music_metadata(url: str) -> list:
    m = re.search(r"[?&]i=(\d+)", url)
    if m:
        r = _itunes_lookup(m.group(1))
        if r:
            return r

    for pattern in (r"/song/[^/?#]+/(\d+)", r"/music-video/[^/?#]+/(\d+)", r"/album/[^/?#]+/(\d+)"):
        m = re.search(pattern, url)
        if m:
            sid = m.group(1)
            if "/album/" in pattern:
                r = _itunes_album(sid)
            else:
                r = _itunes_lookup(sid)
            if r:
                return r

    for m in re.finditer(r"/(\d{6,12})(?:[/?#]|$)", url):
        r = _itunes_lookup(m.group(1))
        if r:
            return r
        r = _itunes_album(m.group(1))
        if r:
            return r

    return _itunes_search_from_url(url)


# --- yt-dlp options ---

def _build_opts(fmt: str, quality: str, output_dir: str, meta: dict | None = None, embed_thumb: bool = True) -> dict:
    if meta and meta.get("title") and meta.get("artist"):
        stem = f"{_sanitize_filename(meta['artist'])} - {_sanitize_filename(meta['title'])}"
    else:
        stem = "%(title)s"

    base = {
        "outtmpl": str(Path(output_dir) / f"{stem}.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
    }

    ffmpeg = _ffmpeg_path()
    if ffmpeg:
        base["ffmpeg_location"] = ffmpeg

    if fmt == "mp4":
        base.update(
            {
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
                "writethumbnail": embed_thumb,
                "postprocessors": [
                    {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
                    {"key": "FFmpegMetadata"},
                ]
                + ([{"key": "EmbedThumbnail"}] if embed_thumb else []),
            }
        )
    else:
        codec_map = {"mp3": "mp3", "flac": "flac", "wav": "wav", "m4a": "m4a", "alac": "alac", "ogg": "vorbis", "opus": "opus"}
        quality_map = {"320": "320", "256": "256", "192": "192", "128": "128", "best": "0", "lossless": "0"}
        codec = codec_map.get(fmt, "mp3")
        q = quality_map.get(quality, "0")
        ytdl_embed = embed_thumb and fmt in ("mp3", "m4a", "opus")
        base.update(
            {
                "format": "bestaudio/best",
                "writethumbnail": embed_thumb,
                "postprocessors": [
                    {"key": "FFmpegExtractAudio", "preferredcodec": codec, "preferredquality": q},
                    {"key": "FFmpegMetadata"},
                ]
                + ([{"key": "EmbedThumbnail"}] if ytdl_embed else []),
            }
        )

    return base


# --- download helpers ---

def _snapshot_dir(directory: str) -> set:
    result = set()
    p = Path(directory)
    if not p.exists():
        return result
    for f in p.iterdir():
        if f.is_file() and f.suffix.lstrip(".").lower() in AUDIO_EXTENSIONS:
            result.add(str(f))
    return result


def _apply_thumb_file(audio_file: str, thumb_path: str):
    import io
    from PIL import Image

    try:
        img = Image.open(thumb_path).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        cover_data = buf.getvalue()
    except Exception:
        return

    ext = Path(audio_file).suffix.lower()
    try:
        if ext == ".flac":
            from mutagen.flac import FLAC, Picture
            audio = FLAC(audio_file)
            audio.clear_pictures()
            pic = Picture()
            pic.type = 3
            pic.mime = "image/jpeg"
            pic.data = cover_data
            audio.add_picture(pic)
            audio.save()
        elif ext == ".wav":
            from mutagen.id3 import ID3, APIC, ID3NoHeaderError
            try:
                tags = ID3(audio_file)
            except ID3NoHeaderError:
                tags = ID3()
            tags.delall("APIC")
            tags["APIC"] = APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_data)
            tags.save(audio_file)
        elif ext == ".ogg":
            import base64
            from mutagen.oggvorbis import OggVorbis
            from mutagen.flac import Picture
            audio = OggVorbis(audio_file)
            pic = Picture()
            pic.type = 3
            pic.mime = "image/jpeg"
            pic.data = cover_data
            audio["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]
            audio.save()
    except Exception:
        pass


def _cleanup_thumbs(output_dir: str):
    p = Path(output_dir)
    if not p.exists():
        return
    for f in p.iterdir():
        if f.is_file() and f.suffix.lstrip(".").lower() in THUMB_EXTENSIONS:
            try:
                f.unlink()
            except Exception:
                pass


def _embed_saved_thumb(audio_file: str, output_dir: str):
    stem = Path(audio_file).stem
    for ext in THUMB_EXTENSIONS:
        thumb = Path(output_dir) / f"{stem}.{ext}"
        if thumb.exists():
            _apply_thumb_file(audio_file, str(thumb))
            try:
                thumb.unlink()
            except Exception:
                pass
            return


def _download_url(url: str, opts: dict, output_dir: str, fmt: str = "") -> list:
    before = _snapshot_dir(output_dir)
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            ydl.download([url])
        except yt_dlp.utils.DownloadError as e:
            if "Postprocessing" not in str(e):
                raise RuntimeError(str(e)) from e
    after = _snapshot_dir(output_dir)
    new_files = list(after - before)

    if fmt in ("flac", "wav", "ogg"):
        for f in new_files:
            _embed_saved_thumb(f, output_dir)

    _cleanup_thumbs(output_dir)
    return new_files


# --- public API ---

def download_track(url: str, fmt: str, quality: str, output_dir: str, progress_callback=None) -> list:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    platform = detect_platform(url)

    if platform == "spotify":
        tracks = get_spotify_metadata(url)
        if not tracks:
            raise RuntimeError("Could not retrieve Spotify metadata.")
        return _download_tracks_list(tracks, fmt, quality, output_dir, progress_callback)

    if platform == "apple_music":
        tracks = get_apple_music_metadata(url)
        if not tracks:
            raise RuntimeError("Could not retrieve Apple Music metadata.")
        return _download_tracks_list(tracks, fmt, quality, output_dir, progress_callback)

    opts = _build_opts(fmt, quality, output_dir, embed_thumb=True)
    if progress_callback:
        opts["progress_hooks"] = [progress_callback]
    return _download_url(url, opts, output_dir, fmt)


def _download_tracks_list(tracks: list, fmt: str, quality: str, output_dir: str, progress_callback=None) -> list:
    from converter import embed_cover_and_metadata

    downloaded = []
    for track in tracks:
        opts = _build_opts(fmt, quality, output_dir, meta=track, embed_thumb=False)
        if progress_callback:
            opts["progress_hooks"] = [progress_callback]
        new_files = _download_url(f"ytsearch1:{track['search_query']}", opts, output_dir, fmt)
        for f in new_files:
            embed_cover_and_metadata(f, track)
            downloaded.append(f)

    return downloaded
