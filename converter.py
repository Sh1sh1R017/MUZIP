"""
converter.py - High-Performance Audio Conversion & ytmdl ID3 Tagging Engine
Extracts YouTube audio (320kbps MP3), queries iTunes metadata API,
and embeds rich ID3 tags (artist, album, high-res cover art, release date).
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import re
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional
import urllib.request
import urllib.parse
import json
import yt_dlp

# Mutagen for ID3 tag embedding
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, APIC, ID3NoHeaderError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

YOUTUBE_INPUT_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:m\.)?(?:music\.)?(?:youtube\.com|youtu\.be)/",
    re.IGNORECASE,
)

# Max worker threads for parallel track downloads
MAX_WORKER_THREADS = 4
executor = ThreadPoolExecutor(max_workers=MAX_WORKER_THREADS)

# In-memory metadata cache with TTL (timestamp, data)
_METADATA_CACHE: Dict[str, tuple[float, Dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour cache TTL


def _build_ydl_auth_options() -> Dict[str, Any]:
    """Build yt-dlp authentication options from environment variables."""
    cookie_file = os.getenv("YTDLP_COOKIES_FILE", "").strip()
    cookies_from_browser = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "").strip()

    auth_options: Dict[str, Any] = {}

    if cookie_file:
        auth_options["cookiefile"] = os.path.expanduser(cookie_file)
    elif cookies_from_browser:
        auth_options["cookiesfrombrowser"] = cookies_from_browser

    return auth_options


def _build_ydl_options(base_options: Dict[str, Any]) -> Dict[str, Any]:
    """Merge shared yt-dlp options with authentication settings."""
    merged_options = dict(base_options)
    merged_options.update(_build_ydl_auth_options())
    return merged_options


def sanitize_filename(name: str) -> str:
    """Sanitize string for clean, safe filenames across platforms."""
    clean = re.sub(r'[\\/*?:"<>|]', "_", name)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean or "audio_track"


def normalize_media_query(value: str) -> str:
    """Convert pasted YouTube URLs without a scheme into a fetchable form."""
    cleaned = (value or "").strip()
    if not cleaned:
        return cleaned

    if cleaned.startswith("ytsearch"):
        return cleaned

    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned

    if YOUTUBE_INPUT_RE.match(cleaned):
        return f"https://{cleaned.lstrip('/')}"

    return f"ytsearch1:{cleaned}"


def clean_search_term(title: str) -> str:
    """Clean video titles to extract core song and artist names for iTunes searching."""
    # Remove common video noise like (Official Music Video), [Lyrics], 4K, HD, etc.
    patterns = [
        r"\(official\s*(music\s*)?video\)",
        r"\[official\s*(music\s*)?video\]",
        r"\(lyrics?\)",
        r"\[lyrics?\]",
        r"\(audio\)",
        r"\[audio\]",
        r"\(hd\)",
        r"\[hd\]",
        r"\(4k\)",
        r"\[4k\]",
        r"ft\..*",
        r"feat\..*",
    ]
    cleaned = title
    for p in patterns:
        cleaned = re.sub(p, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or title


def fetch_itunes_metadata(song_title: str) -> Optional[Dict[str, Any]]:
    """
    Queries iTunes API (ytmdl style) for official song metadata,
    artist, album name, release year, and high-res cover art.
    """
    try:
        search_query = clean_search_term(song_title)
        url = f"https://itunes.apple.com/search?term={urllib.parse.quote(search_query)}&entity=song&limit=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("results", [])
                if results:
                    item = results[0]
                    # Upgrade thumbnail to high-resolution 600x600
                    artwork = item.get("artworkUrl100", "").replace("100x100bb", "600x600bb")
                    release_year = item.get("releaseDate", "")[:4] if item.get("releaseDate") else ""
                    return {
                        "track": item.get("trackName", song_title),
                        "artist": item.get("artistName", "Unknown Artist"),
                        "album": item.get("collectionName", "Single"),
                        "year": release_year,
                        "artwork_url": artwork,
                    }
    except Exception as e:
        logger.warning("iTunes metadata fetch skipped for '%s': %s", song_title, e)
    return None


def embed_id3_tags(mp3_path: str, meta: Dict[str, Any]) -> None:
    """Embeds ID3v2.3 tags (title, artist, album, year, artwork) into MP3 using mutagen."""
    if not os.path.exists(mp3_path):
        return

    try:
        try:
            tags = ID3(mp3_path)
        except ID3NoHeaderError:
            tags = ID3()

        if meta.get("track"):
            tags.add(TIT2(encoding=3, text=meta["track"]))
        if meta.get("artist"):
            tags.add(TPE1(encoding=3, text=meta["artist"]))
        if meta.get("album"):
            tags.add(TALB(encoding=3, text=meta["album"]))
        if meta.get("year"):
            tags.add(TDRC(encoding=3, text=str(meta["year"])))

        # Fetch and embed cover image if available
        artwork_url = meta.get("artwork_url")
        if artwork_url:
            try:
                req = urllib.request.Request(artwork_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as img_resp:
                    img_data = img_resp.read()
                    tags.add(
                        APIC(
                            encoding=3,
                            mime="image/jpeg",
                            type=3,  # Front cover
                            desc="Cover",
                            data=img_data,
                        )
                    )
            except Exception as ie:
                logger.warning("Could not download artwork for ID3 tag: %s", ie)

        tags.save(mp3_path)
        logger.info("Successfully embedded ID3 tags into '%s'", mp3_path)
    except Exception as e:
        logger.error("Failed to embed ID3 tags for '%s': %s", mp3_path, e)


def format_duration(seconds: Optional[int]) -> str:
    """Format duration in seconds into MM:SS or HH:MM:SS format."""
    if not seconds or seconds <= 0:
        return "00:00"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def get_cached_metadata(url: str) -> Optional[Dict[str, Any]]:
    """Retrieve metadata from in-memory LRU cache if valid."""
    if url in _METADATA_CACHE:
        timestamp, data = _METADATA_CACHE[url]
        if time.time() - timestamp < CACHE_TTL_SECONDS:
            logger.info("Serving cached metadata for URL: %s", url)
            return data
        else:
            del _METADATA_CACHE[url]
    return None


def set_cached_metadata(url: str, data: Dict[str, Any]) -> None:
    """Store metadata in in-memory LRU cache."""
    _METADATA_CACHE[url] = (time.time(), data)


async def extract_url_info(url: str) -> Dict[str, Any]:
    """
    Extract structured metadata from YouTube URL (video or playlist).
    Queries iTunes API to enrich artist, album, and high-res cover art.
    """
    source = normalize_media_query(url)
    cached = get_cached_metadata(source)
    if cached:
        return cached

    def _fetch():
        ydl_opts = _build_ydl_options({
            "extract_flat": "in_playlist",
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
            "nocheckcertificate": True,
        })
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(source, download=False)
            if not info:
                raise ValueError("Could not fetch metadata for the provided URL.")
            return info

    raw_info = await asyncio.to_thread(_fetch)
    
    is_playlist = raw_info.get("_type") == "playlist" or "entries" in raw_info

    if is_playlist:
        entries = raw_info.get("entries", [])
        tracks = []
        total_duration = 0
        for idx, entry in enumerate(entries, start=1):
            if not entry:
                continue
            title = entry.get("title") or f"Track {idx}"
            duration = entry.get("duration", 0) or 0
            total_duration += duration
            
            uploader = entry.get("uploader") or entry.get("channel") or "Unknown Artist"
            thumbnail = entry.get("thumbnail") or (
                entry.get("thumbnails")[-1]["url"] if entry.get("thumbnails") else ""
            )

            tracks.append({
                "index": idx,
                "id": entry.get("id", ""),
                "title": title,
                "uploader": uploader,
                "duration": duration,
                "duration_formatted": format_duration(duration),
                "thumbnail": thumbnail,
                "url": f"https://www.youtube.com/watch?v={entry.get('id')}" if entry.get("id") else url,
            })
        
        playlist_title = raw_info.get("title") or "YouTube Playlist"
        playlist_uploader = raw_info.get("uploader") or raw_info.get("playlist_uploader") or "Various Artists"
        playlist_thumb = raw_info.get("thumbnails")[-1]["url"] if raw_info.get("thumbnails") else (tracks[0]["thumbnail"] if tracks else "")

        result = {
            "is_playlist": True,
            "id": raw_info.get("id", ""),
            "title": playlist_title,
            "uploader": playlist_uploader,
            "thumbnail": playlist_thumb,
            "total_tracks": len(tracks),
            "total_duration": total_duration,
            "total_duration_formatted": format_duration(total_duration),
            "tracks": tracks,
        }
    else:
        title = raw_info.get("title") or "YouTube Audio Track"
        duration = raw_info.get("duration", 0) or 0
        uploader = raw_info.get("uploader") or raw_info.get("channel") or "Unknown Artist"
        thumbnail_url = raw_info.get("thumbnail", "")
        if not thumbnail_url and raw_info.get("thumbnails"):
            thumbnail_url = raw_info.get("thumbnails")[-1]["url"]
            
        # iTunes Enrichment
        itunes_data = fetch_itunes_metadata(title)
        if itunes_data:
            if itunes_data.get("artwork_url"):
                thumbnail_url = itunes_data["artwork_url"]
            if itunes_data.get("artist"):
                uploader = itunes_data["artist"]

        track_data = {
            "index": 1,
            "id": raw_info.get("id", ""),
            "title": title,
            "uploader": uploader,
            "duration": duration,
            "duration_formatted": format_duration(duration),
            "thumbnail": thumbnail_url,
            "url": raw_info.get("webpage_url") or url,
        }
        
        result = {
            "is_playlist": False,
            "id": raw_info.get("id", ""),
            "title": title,
            "uploader": uploader,
            "thumbnail": thumbnail_url,
            "total_tracks": 1,
            "total_duration": duration,
            "total_duration_formatted": format_duration(duration),
            "tracks": [track_data],
        }

    set_cached_metadata(source, result)
    return result


class DownloadProgressHook:
    """yt-dlp progress hook wrapper to publish live telemetry to callbacks."""
    def __init__(
        self,
        track_index: int,
        total_tracks: int,
        track_title: str,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        self.track_index = track_index
        self.total_tracks = total_tracks
        self.track_title = track_title
        self.callback = callback

    def update_title(self, new_title: str):
        if new_title:
            self.track_title = new_title

    def __call__(self, d: Dict[str, Any]):
        if not self.callback:
            return

        status_str = d.get("status")
        if status_str == "downloading":
            total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
            downloaded_bytes = d.get("downloaded_bytes", 0)
            track_pct = round((downloaded_bytes / total_bytes) * 100, 1)
            
            overall_pct = round(
                ((self.track_index - 1) / self.total_tracks * 100) + (track_pct / self.total_tracks),
                1
            )
            
            speed = d.get("speed") or 0.0
            speed_mbps = round(speed / (1024 * 1024), 2)
            eta = d.get("eta") or 0

            self.callback({
                "type": "PROGRESS_UPDATE",
                "payload": {
                    "current_track_index": self.track_index,
                    "total_tracks": self.total_tracks,
                    "track_title": self.track_title,
                    "status": "DOWNLOADING",
                    "track_progress_pct": min(track_pct, 100.0),
                    "overall_progress_pct": min(overall_pct, 100.0),
                    "speed_mbps": speed_mbps,
                    "eta_seconds": eta,
                }
            })
        elif status_str == "finished":
            self.callback({
                "type": "PROGRESS_UPDATE",
                "payload": {
                    "current_track_index": self.track_index,
                    "total_tracks": self.total_tracks,
                    "track_title": self.track_title,
                    "status": "ENCODING_MP3",
                    "track_progress_pct": 100.0,
                    "overall_progress_pct": round((self.track_index / self.total_tracks) * 100, 1),
                    "speed_mbps": 0.0,
                    "eta_seconds": 0,
                }
            })


def download_single_track_sync(
    url: str,
    output_dir: str,
    filename_prefix: str = "",
    track_index: int = 1,
    total_tracks: int = 1,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    track_title_hint: str = "",
) -> str:
    """
    Synchronously download a single YouTube track, convert to 320kbps MP3,
    queries iTunes metadata, and embeds ID3 tags.
    """
    os.makedirs(output_dir, exist_ok=True)
    out_template = os.path.join(output_dir, f"{filename_prefix}%(title)s.%(ext)s")

    initial_title = track_title_hint or filename_prefix or "Audio Track"
    hook = DownloadProgressHook(
        track_index=track_index,
        total_tracks=total_tracks,
        track_title=initial_title,
        callback=progress_callback,
    )

    ydl_opts = _build_ydl_options({
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "nocheckcertificate": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            },
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
            }
        ],
        "postprocessor_args": [
            "-threads", "0",
            "-q:a", "0",
        ],
        "progress_hooks": [hook],
    })

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        real_title = info.get("title") or initial_title
        hook.update_title(real_title)

        filename = ydl.prepare_filename(info)
        base_name, _ = os.path.splitext(filename)
        mp3_path = base_name + ".mp3"
        
        if not os.path.exists(mp3_path):
            for f in os.listdir(output_dir):
                if f.endswith(".mp3"):
                    mp3_path = os.path.join(output_dir, f)
                    break
        
        # Query iTunes & Embed ID3 metadata tags
        itunes_meta = fetch_itunes_metadata(real_title)
        if itunes_meta:
            embed_id3_tags(mp3_path, itunes_meta)

        return mp3_path


async def download_track_async(
    url: str,
    output_dir: str,
    filename_prefix: str = "",
    track_index: int = 1,
    total_tracks: int = 1,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    track_title_hint: str = "",
) -> str:
    """Asynchronous thread-pool wrapper around download_single_track_sync."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        executor,
        download_single_track_sync,
        url,
        output_dir,
        filename_prefix,
        track_index,
        total_tracks,
        progress_callback,
        track_title_hint,
    )
