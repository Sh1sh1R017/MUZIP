import React, { useState, useEffect, useRef } from 'react';
import { 
  Link as LinkIcon, Download, X, Check, Clipboard, 
  History, HelpCircle, Moon, Sun, Loader2,
  FileText, ShieldCheck, Zap, AlertCircle, Music, Archive
} from 'lucide-react';

export default function App() {
  const [url, setUrl] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [metadata, setMetadata] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadMode, setDownloadMode] = useState(null); // 'mp3' | 'zip'
  const [isDragging, setIsDragging] = useState(false);
  
  // Theme State (Dark / Light Mode Toggle)
  const [isDarkMode, setIsDarkMode] = useState(() => {
    try {
      const savedTheme = localStorage.getItem('muzip_theme');
      return savedTheme ? savedTheme === 'dark' : true;
    } catch (e) {
      return true;
    }
  });

  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    try {
      localStorage.setItem('muzip_theme', isDarkMode ? 'dark' : 'light');
    } catch (e) {}
  }, [isDarkMode]);

  // Load download history from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem('muzip_history');
      if (saved) setDownloadHistory(JSON.parse(saved));
    } catch (e) {}
  }, []);

  // Save to history helper
  const saveToHistory = (item) => {
    try {
      const updated = [item, ...downloadHistory.filter(h => h.id !== item.id)].slice(0, 10);
      setDownloadHistory(updated);
      localStorage.setItem('muzip_history', JSON.stringify(updated));
    } catch (e) {}
  };

  // Auto-paste clipboard detection on window focus
  useEffect(() => {
    const handleFocus = async () => {
      try {
        if (!url && navigator.clipboard && navigator.clipboard.readText) {
          const text = await navigator.clipboard.readText();
          if (text && (text.includes('youtube.com/') || text.includes('youtu.be/'))) {
            setUrl(text.trim());
          }
        }
      } catch (e) {}
    };
    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [url]);

  // Paste from Clipboard Action
  const handlePasteClipboard = async () => {
    try {
      if (navigator.clipboard && navigator.clipboard.readText) {
        const text = await navigator.clipboard.readText();
        if (text) {
          setUrl(text.trim());
          handleInspect(text.trim());
        }
      }
    } catch (e) {
      setErrorMsg("Please grant clipboard permission to auto-paste.");
    }
  };

  // Drag & Drop Handlers
  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const text = e.dataTransfer.getData('text');
    if (text) {
      setUrl(text.trim());
      handleInspect(text.trim());
    }
  };

  // Inspect URL via POST /api/v1/info
  const handleInspect = async (overrideUrl) => {
    const targetQuery = (overrideUrl || url).trim();
    if (!targetQuery) return;

    setIsAnalyzing(true);
    setErrorMsg(null);
    setMetadata(null);

    let targetUrl = targetQuery;
    if (!targetQuery.startsWith('http://') && !targetQuery.startsWith('https://')) {
      targetUrl = `ytsearch1:${targetQuery}`;
    }

    try {
      const response = await fetch('/api/v1/info', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: targetUrl })
      });

      const json = await response.json();

      if (!response.ok || !json.success) {
        throw new Error(json.detail || 'Could not extract metadata from YouTube URL.');
      }

      setMetadata(json.data);

    } catch (err) {
      setErrorMsg(err.message || 'Failed to analyze URL. Please verify the YouTube link.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Start Real Audio Download
  const handleStartDownload = async (mode = 'mp3') => {
    if (!metadata || isDownloading) return;

    setIsDownloading(true);
    setDownloadMode(mode);
    setErrorMsg(null);

    const isZip = mode === 'zip';
    const endpoint = isZip ? '/api/v1/download/playlist' : '/api/v1/download/single';
    const downloadQuery = metadata.tracks && metadata.tracks.length > 0 ? metadata.tracks[0].url : url.trim();

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: (isZip && metadata.is_playlist) ? url.trim() : downloadQuery,
          client_id: clientIdRef.current
        })
      });

      if (!response.ok) {
        const errorJson = await response.json().catch(() => ({}));
        throw new Error(errorJson.detail || 'Download failed.');
      }

      const blob = await response.blob();
      const objectUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objectUrl;

      const contentDisposition = response.headers.get('Content-Disposition');
      let fileName = isZip ? `${metadata.title}.zip` : `${metadata.title}.mp3`;
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="?([^"]+)"?/);
        if (match && match[1]) fileName = match[1];
      }

      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(objectUrl);

      // Save to download history
      saveToHistory({
        id: metadata.id || crypto.randomUUID(),
        title: metadata.title,
        uploader: metadata.uploader,
        thumbnail: metadata.thumbnail,
        date: new Date().toLocaleDateString(),
        url: url.trim(),
        format: isZip ? 'ZIP' : 'MP3 320k'
      });

    } catch (err) {
      setErrorMsg(err.message || 'Error occurred during audio download.');
    } finally {
      setIsDownloading(false);
      setDownloadMode(null);
    }
  };

  // Keyboard Enter key trigger
  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (metadata) {
        handleStartDownload('mp3');
      } else {
        handleInspect();
      }
    }
  };

  return (
    <div className="min-h-screen flex flex-col justify-between font-sans antialiased transition-colors duration-200">
      
      {/* 1. TOP NAVIGATION (Height 72px, thin border bottom #27272A) */}
      <nav className="h-[72px] w-full border-b border-[#27272A] bg-[#080B0E] sticky top-0 z-40 px-6">
        <div className="max-w-6xl mx-auto h-full flex items-center justify-between">
          
          {/* MUZIP Branding Logo */}
          <div className="flex items-center space-x-2">
            <span className="font-extrabold text-xl tracking-tight dark:text-white text-slate-900">
              MUZ<span className="text-[#7CFF00]">IP</span>
            </span>
          </div>

          {/* Right Nav Links */}
          <div className="flex items-center space-x-4 sm:space-x-6 text-sm font-medium dark:text-[#A1A1AA] text-slate-600">
            <button 
              onClick={() => setHistoryOpen(true)}
              className="hover:dark:text-white hover:text-slate-900 transition-colors flex items-center space-x-1.5"
            >
              <History className="w-4 h-4 text-[#7CFF00]" />
              <span>History</span>
            </button>

            <button 
              onClick={() => {
                document.getElementById('faq-section')?.scrollIntoView({ behavior: 'smooth' });
              }}
              className="hover:dark:text-white hover:text-slate-900 transition-colors flex items-center space-x-1.5"
            >
              <HelpCircle className="w-4 h-4" />
              <span>FAQ</span>
            </button>

            <div className="w-px h-4 bg-[#27272A]" />

            {/* DARK / LIGHT MODE TOGGLE BUTTON */}
            <button
              onClick={() => setIsDarkMode(!isDarkMode)}
              title={isDarkMode ? "Switch to Light Mode" : "Switch to Dark Mode"}
              className="p-2 rounded-xl shishir-surface hover:scale-105 active:scale-95 transition-all flex items-center justify-center cursor-pointer"
            >
              {isDarkMode ? (
                <Sun className="w-4 h-4 text-[#7CFF00]" />
              ) : (
                <Moon className="w-4 h-4 text-slate-700" />
              )}
            </button>

          </div>
        </div>
      </nav>

      {/* MAIN CONTAINER */}
      <main className="max-w-5xl mx-auto w-full px-6 flex-1 flex flex-col items-center">
        
        {/* 2. LARGE ADVERTISEMENT AREA (Top ~970x250 Desktop) */}
        <div className="w-full my-8">
          <div className="ad-banner-container w-full h-[180px] md:h-[230px] p-6 text-center">
            <div className="space-y-1">
              <span className="text-xs font-semibold tracking-wider uppercase dark:text-[#6B7280] text-slate-500">
                Advertisement
              </span>
              <p className="text-xs dark:text-[#A1A1AA] text-slate-600">Responsive Ad Banner Placeholder (970 × 250)</p>
            </div>
          </div>
        </div>

        {/* 3. MAIN HERO SECTION */}
        <div className="text-center my-6 space-y-3 max-w-2xl">
          <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight dark:text-white text-slate-900">
            Download YouTube Audio
          </h1>
          <p className="text-base font-normal leading-relaxed dark:text-[#A1A1AA] text-slate-600">
            Paste a YouTube video or playlist URL and instantly download high-quality MP3 files.
          </p>
        </div>

        {/* 4. MAIN SEARCH AREA (Visually Dominant Component) */}
        <div 
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`w-full my-4 transition-all duration-200 ${isDragging ? 'scale-[1.01]' : ''}`}
        >
          <div className="flex flex-col sm:flex-row items-center gap-3">
            
            {/* Input Bar (64px Height, 16px Rounded) */}
            <div className="relative flex-1 w-full flex items-center">
              <div className="absolute left-5 dark:text-[#6B7280] text-slate-400">
                <LinkIcon className="w-5 h-5" />
              </div>

              <input 
                ref={inputRef}
                type="text" 
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Paste YouTube URL here..."
                className="shishir-input w-full h-[64px] pl-14 pr-12 text-sm focus:outline-none"
              />

              {url && (
                <button 
                  onClick={() => { setUrl(''); setMetadata(null); setErrorMsg(null); }}
                  className="absolute right-4 dark:text-[#A1A1AA] text-slate-500 hover:text-black dark:hover:text-white p-1"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            {/* Primary Action Button (#7CFF00, Black text, Bold, Hover 1.02 scale) */}
            <button 
              onClick={() => {
                if (metadata) {
                  handleStartDownload('mp3');
                } else {
                  handleInspect();
                }
              }}
              disabled={isAnalyzing || !url.trim()}
              className="btn-shishir-primary w-full sm:w-auto h-[64px] px-8 text-base font-bold text-black flex items-center justify-center space-x-2 shrink-0 disabled:opacity-50 cursor-pointer"
            >
              {isAnalyzing ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin text-black" />
                  <span>Analyzing...</span>
                </>
              ) : (
                <>
                  <Download className="w-5 h-5 text-black" />
                  <span>Download MP3</span>
                </>
              )}
            </button>

          </div>
        </div>

        {/* 5. SECONDARY ACTION */}
        <div className="my-3 flex justify-center">
          <button 
            onClick={handlePasteClipboard}
            className="btn-shishir-secondary px-4 py-2.5 text-xs flex items-center space-x-2 cursor-pointer"
          >
            <Clipboard className="w-3.5 h-3.5 text-[#7CFF00]" />
            <span>Paste from Clipboard</span>
          </button>
        </div>

        {/* 6. TINY FEATURE ROW */}
        <div className="my-4 flex flex-wrap items-center justify-center gap-6 text-xs font-medium dark:text-[#A1A1AA] text-slate-600">
          <div className="flex items-center space-x-1.5">
            <Check className="w-4 h-4 text-[#7CFF00]" />
            <span>Fast Conversion</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <Check className="w-4 h-4 text-[#7CFF00]" />
            <span>High Quality MP3</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <Check className="w-4 h-4 text-[#7CFF00]" />
            <span>Playlist Support</span>
          </div>
        </div>

        {/* ERROR DISPLAY */}
        {errorMsg && (
          <div className="w-full my-4 p-4 rounded-[16px] shishir-surface border-[#EF4444]/40 text-[#EF4444] text-sm flex items-center space-x-3">
            <AlertCircle className="w-5 h-5 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* EXTRACTED METADATA & DOWNLOAD OPTIONS */}
        {metadata && (
          <div className="w-full shishir-card p-6 my-6 space-y-6">
            <div className="flex flex-col md:flex-row gap-6 items-start">
              {metadata.thumbnail ? (
                <img 
                  src={metadata.thumbnail} 
                  alt="Thumbnail" 
                  className="w-full md:w-48 h-32 object-cover rounded-[14px] border border-[#27272A]" 
                />
              ) : (
                <div className="w-full md:w-48 h-32 rounded-[14px] bg-[#111113] border border-[#27272A] flex items-center justify-center text-[#6B7280]">
                  <Music className="w-8 h-8" />
                </div>
              )}

              <div className="flex-1 space-y-2">
                <div className="flex items-center space-x-2">
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase bg-[#7CFF00]/10 text-[#7CFF00] border border-[#7CFF00]/20">
                    {metadata.is_playlist ? `Playlist (${metadata.total_tracks} Tracks)` : '320kbps MP3'}
                  </span>
                  <span className="text-xs dark:text-[#A1A1AA] text-slate-500">{metadata.total_duration_formatted}</span>
                </div>

                <h2 className="text-xl font-bold dark:text-white text-slate-900 line-clamp-2">{metadata.title}</h2>
                <p className="text-sm dark:text-[#A1A1AA] text-slate-600">{metadata.uploader}</p>

                {/* Explicit Download Buttons */}
                <div className="pt-4 flex flex-wrap gap-3">
                  <button 
                    onClick={() => handleStartDownload('mp3')}
                    disabled={isDownloading}
                    className="btn-shishir-primary px-6 py-3 text-sm font-bold text-black flex items-center space-x-2 disabled:opacity-50 cursor-pointer"
                  >
                    {isDownloading && downloadMode === 'mp3' ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin text-black" />
                        <span>Processing...</span>
                      </>
                    ) : (
                      <>
                        <Music className="w-4 h-4 text-black" />
                        <span>Download 320kbps MP3</span>
                      </>
                    )}
                  </button>

                  <button 
                    onClick={() => handleStartDownload('zip')}
                    disabled={isDownloading}
                    className="btn-shishir-secondary px-6 py-3 text-sm flex items-center space-x-2 disabled:opacity-50 cursor-pointer"
                  >
                    {isDownloading && downloadMode === 'zip' ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin text-white" />
                        <span>Building ZIP...</span>
                      </>
                    ) : (
                      <>
                        <Archive className="w-4 h-4 text-[#7CFF00]" />
                        <span>Download ZIP Archive (.zip)</span>
                      </>
                    )}
                  </button>
                </div>

              </div>
            </div>

            {/* Playlist Track Listing if applicable */}
            {metadata.is_playlist && (
              <div className="space-y-3 pt-4 border-t border-[#27272A]">
                <div className="flex items-center justify-between text-xs font-semibold dark:text-[#A1A1AA] text-slate-600">
                  <span>Playlist Tracks ({metadata.tracks.length})</span>
                  <span>320kbps Audio</span>
                </div>

                <div className="max-h-60 overflow-y-auto space-y-2 pr-1">
                  {metadata.tracks.map((track) => (
                    <div 
                      key={track.id || track.index}
                      className="flex items-center justify-between p-3 rounded-[12px] shishir-surface text-xs"
                    >
                      <div className="flex items-center space-x-3 min-w-0 pr-4">
                        <span className="text-[#7CFF00] font-bold w-5">{String(track.index).padStart(2, '0')}</span>
                        <div className="min-w-0">
                          <p className="font-semibold dark:text-white text-slate-900 truncate">{track.title}</p>
                          <p className="dark:text-[#6B7280] text-slate-500">{track.uploader} • {track.duration_formatted}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 7. MASSIVE ADVERTISEMENT AREA (Bottom ~970x280 Desktop) */}
        <div className="w-full my-12">
          <div className="ad-banner-container w-full h-[200px] md:h-[260px] p-6 text-center">
            <div className="space-y-1">
              <span className="text-xs font-semibold tracking-wider uppercase dark:text-[#6B7280] text-slate-500">
                Advertisement
              </span>
              <p className="text-xs dark:text-[#A1A1AA] text-slate-600">Massive Responsive Ad Container (970 × 280)</p>
            </div>
          </div>
        </div>

        {/* FAQ ACCORDION SECTION WITH MUZIP DEFINITION */}
        <div id="faq-section" className="w-full my-8 space-y-4 max-w-3xl">
          <h2 className="text-2xl font-bold text-center dark:text-white text-slate-900 mb-6">Frequently Asked Questions</h2>

          {[
            {
              id: 'faq-0',
              q: 'What does MUZIP stand for?',
              a: 'MUZIP stands for Music Zipped — an instant high-speed audio converter and dynamic ZIP streaming engine designed for YouTube videos and full playlists.'
            },
            {
              id: 'faq-1',
              q: 'Is MUZIP free to use?',
              a: 'Yes, MUZIP is 100% free with unlimited YouTube video and playlist conversions.'
            },
            {
              id: 'faq-2',
              q: 'What audio quality is exported?',
              a: 'All tracks are converted and exported in maximum high-fidelity 320kbps MP3 audio with embedded ID3 metadata tags (artist, album, cover art).'
            },
            {
              id: 'faq-3',
              q: 'Are YouTube playlists supported?',
              a: 'Yes! Simply paste any YouTube playlist link, and MUZIP streams all tracks dynamically packaged as a single ZIP archive.'
            },
            {
              id: 'faq-4',
              q: 'Do I need to install any software?',
              a: 'No installation required. Everything converts instantly directly inside your web browser.'
            }
          ].map((item) => (
            <div key={item.id} className="shishir-surface p-4 text-sm space-y-2">
              <button 
                onClick={() => setActiveFaq(activeFaq === item.id ? null : item.id)}
                className="w-full flex items-center justify-between font-semibold dark:text-white text-slate-900 text-left focus:outline-none cursor-pointer"
              >
                <span>{item.q}</span>
                <span className="text-[#7CFF00] font-bold text-lg">{activeFaq === item.id ? '−' : '+'}</span>
              </button>
              {activeFaq === item.id && (
                <p className="dark:text-[#A1A1AA] text-slate-600 text-xs leading-relaxed pt-2 border-t border-[#27272A]">
                  {item.a}
                </p>
              )}
            </div>
          ))}
        </div>

      </main>

      {/* HISTORY DRAWER / MODAL */}
      {historyOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md shishir-surface border-l border-[#27272A] p-6 space-y-6 flex flex-col h-full shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#27272A] pb-4">
              <div className="flex items-center space-x-2">
                <History className="w-5 h-5 text-[#7CFF00]" />
                <h3 className="text-lg font-bold dark:text-white text-slate-900">Download History</h3>
              </div>
              <button onClick={() => setHistoryOpen(false)} className="dark:text-[#A1A1AA] text-slate-500 hover:text-black dark:hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-3 pr-1">
              {downloadHistory.length === 0 ? (
                <p className="text-xs dark:text-[#A1A1AA] text-slate-500 text-center py-8">No previous download history found.</p>
              ) : (
                downloadHistory.map((item) => (
                  <div key={item.id} className="shishir-card p-3 space-y-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold dark:text-white text-slate-900 truncate max-w-[220px]">{item.title}</span>
                      <span className="text-[10px] text-[#7CFF00] font-bold">{item.format}</span>
                    </div>
                    <p className="text-[11px] dark:text-[#A1A1AA] text-slate-500">{item.uploader} • {item.date}</p>
                    <button 
                      onClick={() => {
                        setUrl(item.url);
                        setHistoryOpen(false);
                        handleInspect(item.url);
                      }}
                      className="text-xs text-[#7CFF00] hover:underline font-semibold cursor-pointer"
                    >
                      Re-inspect URL →
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* 8. FOOTER (Minimal - Theme aware) */}
      <footer className="w-full border-t border-[#27272A] bg-[#080B0E] py-8 mt-12 text-xs dark:text-[#6B7280] text-slate-500">
        <div className="max-w-5xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
          
          <div className="flex items-center space-x-2">
            <span className="font-extrabold text-sm dark:text-white text-slate-900">
              MUZ<span className="text-[#7CFF00]">IP</span>
            </span>
            <span>© {new Date().getFullYear()} MUZIP (Music Zipped). All rights reserved.</span>
          </div>

          <div className="flex items-center space-x-6 dark:text-[#A1A1AA] text-slate-600">
            <a href="#privacy" className="hover:dark:text-white hover:text-black transition-colors">Privacy Policy</a>
            <a href="#terms" className="hover:dark:text-white hover:text-black transition-colors">Terms of Service</a>
          </div>

        </div>
      </footer>

    </div>
  );
}
