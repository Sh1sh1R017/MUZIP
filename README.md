# MUZIP 🎵⚡ — YouTube Audio & Instant Playlist ZIP Downloader

> **MUZIP** stands for **Music Zipped** — an ultra-fast, production-grade RESTful API, WebSocket service, and minimalist web application designed to convert YouTube videos and playlists into high-fidelity **320kbps MP3s** and stream them as **instant dynamically compressed `.zip` archives** without disk pre-staging.

Inspired by the clean, trustworthy design systems of **Vercel, Linear, Stripe, Raycast, and Notion**.

---

## ✨ Key Features & Technical Highlights

- **⚡ Zero-Disk In-Flight Zip Streaming**: Uses `zipstream` chunked HTTP generator streaming. Browser downloads start within milliseconds of the first track completing download/encoding without staging multi-gigabyte ZIP files on disk.
- **🏷️ `ytmdl` iTunes Metadata Enrichment**: Automatically queries the iTunes Search API to fetch official song titles, artist names, album titles, release dates, and high-resolution **600x600 album artwork**.
- **🎧 ID3 Tag Embedding**: Uses `mutagen` to embed ID3v2.3 tags (`TIT2`, `TPE1`, `TALB`, `TDRC`, `APIC`) directly into exported 320kbps MP3 files.
- **🎯 Dual Explicit Action Buttons**: Separate buttons for **`Download 320kbps MP3`** and **`Download ZIP Archive (.zip)`**.
- **📡 WebSocket Progress Telemetry**: Pushes live execution updates (`/ws/progress/{client_id}`) for track status (`QUEUED`, `DOWNLOADING`, `ENCODING_MP3`, `COMPLETE`), download throughput (`MB/s`), and `ETA`.
- **☀️ Light & Dark Mode Toggle**: Instant theme switching with `localStorage` persistence and accessible high-contrast colors.
- **📜 Local History Drawer**: Saves recent downloads in `localStorage` for instant re-inspection and re-downloading.
- **📱 Mobile-First Thumb-Zone Design**: Input bar and primary actions anchored for easy one-handed mobile operation with drag-and-drop link support.
- **💰 Ad Revenue Banner Containers**: Responsive ad banner placeholders (`970x250` and `970x280`) integrated seamlessly for maximum monetization.

---

## 🛠️ Project Structure

```
MUZIP/
├── main.py          # FastAPI application, REST routes, WebSocket manager, background cleanup
├── converter.py     # yt-dlp & ffmpeg engine, iTunes metadata lookup, mutagen ID3 tagger
├── zipper.py        # zipstream chunked in-flight HTTP ZIP streaming generator
├── index.html       # Entry HTML with Inter Google Font configuration
├── src/
│   ├── App.jsx      # React Single Page Application (Vercel/Linear UI design)
│   └── index.css    # Tailwind CSS v4 custom styling & Dark/Light mode theme rules
├── requirements.txt # Python package manifest
├── package.json     # Node.js dependencies & scripts (Vite, React, Tailwind CSS)
├── Dockerfile       # Production multi-stage Docker deployment build
└── README.md        # Project documentation
```

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.11+**
- **Node.js 18+** & `npm`
- **FFmpeg** installed and added to system `PATH`
  - *Ubuntu/Debian*: `sudo apt install ffmpeg`
  - *macOS*: `brew install ffmpeg`
  - *Windows*: Download from [ffmpeg.org](https://ffmpeg.org/) or run `winget install FFmpeg`

### 1. Local Setup

```bash
# Clone the repository
git clone https://github.com/Sh1sh1R017/MUZIP.git
cd MUZIP

# Install Python backend dependencies
pip install -r requirements.txt

# Install Frontend Node dependencies
npm install
```

### 2. Running the Application

Start the FastAPI backend server (Port 8000):
```bash
python main.py
```

In a separate terminal, start the Vite frontend development server (Port 5173):
```bash
npm run dev
```

Open your browser at `http://localhost:5173`.

### Azure Container Apps: Single-Container Setup

If you deploy MUZIP as a single Azure Container App, the frontend now talks to the FastAPI backend on the same origin by default, so you do not need to set `VITE_API_URL`.

The app also normalizes pasted YouTube links that are missing `https://`, so `youtube.com/watch?...` and `youtu.be/...` inputs are handled correctly instead of being treated as search queries.

---

## 🐳 Docker Deployment

Build and run using the production multi-stage `Dockerfile`:

```bash
# Build Docker image
docker build -t muzip .

# Run container
docker run -d -p 8000:8000 --name muzip-app muzip
```

Access system health at `http://localhost:8000/health`.

---

## 🔌 API & WebSocket Documentation

### 1. System Health Checklist
- **`GET /health`**
- **Response**:
```json
{
  "status": "healthy",
  "ram_usage_pct": 28.4,
  "ram_used_mb": 2248.15,
  "ram_total_mb": 8032.0,
  "active_jobs": 0,
  "ffmpeg": {
    "installed": true,
    "binary_path": "/usr/bin/ffmpeg"
  }
}
```

### 2. URL / Song Metadata Extraction
- **`POST /api/v1/info`**
- **Body**: `{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}`
- **Response**: Returns structured JSON with title, artist, duration, high-res thumbnail, and track listing.

### 3. Single Track MP3 Download
- **`POST /api/v1/download/single`**
- **Body**: `{"url": "https://www.youtube.com/watch?v=...", "client_id": "uuid-v4"}`
- **Response**: Streams `.mp3` file with `Content-Disposition` attachment headers and embedded ID3 tags.

### 4. Playlist ZIP Stream Download
- **`POST /api/v1/download/playlist`**
- **Body**: `{"url": "https://www.youtube.com/playlist?list=...", "client_id": "uuid-v4"}`
- **Response**: Streams dynamically compressed `.zip` archive chunk-by-chunk over HTTP.

### 5. Telemetry WebSocket
- **`WS /ws/progress/{client_id}`**
- **Telemetry Event**:
```json
{
  "type": "PROGRESS_UPDATE",
  "payload": {
    "current_track_index": 2,
    "total_tracks": 10,
    "track_title": "Track Name",
    "status": "DOWNLOADING",
    "track_progress_pct": 65.4,
    "overall_progress_pct": 16.5,
    "speed_mbps": 18.4,
    "eta_seconds": 8
  }
}
```

---

## 📄 License

MIT License. Created for fast audio conversion, in-flight ZIP streaming, and clean web application design.
