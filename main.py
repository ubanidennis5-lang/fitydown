import os
import uuid
import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
import yt_dlp
import re
import urllib.request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.cors import CORSMiddleware

import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class VideoRequest(BaseModel):
    url: str
    format_id: str = "bestvideo+bestaudio/best"
    start_time: str = None
    end_time: str = None

EXPLORE_CACHE = {}
CACHE_TTL = 900  # 15 minutes in seconds

@app.get("/explore")
async def explore_live(category: str = "music"):
    current_time = time.time()
    
    # Check cache
    if category in EXPLORE_CACHE:
        cache_entry = EXPLORE_CACHE[category]
        if current_time - cache_entry['timestamp'] < CACHE_TTL:
            return {"category": category, "streams": cache_entry['data']}
    
    ydl_opts = {
        'extract_flat': 'in_playlist',
        'quiet': True,
        'no_warnings': True,
        'simulate': True,
    }
    
    search_query = f"ytsearch20:live stream {category}"
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
            entries = info.get('entries', [])
            
            streams = []
            for entry in entries:
                if entry:
                    streams.append({
                        "id": entry.get('id'),
                        "title": entry.get('title'),
                        "thumbnail": entry.get('thumbnails', [{}])[-1].get('url', f"https://i.ytimg.com/vi/{entry.get('id')}/hqdefault.jpg"),
                        "channel": entry.get('uploader'),
                        "url": entry.get('url'),
                    })
            
            # Save to cache
            EXPLORE_CACHE[category] = {
                "timestamp": current_time,
                "data": streams
            }
            
            return {"category": category, "streams": streams}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/info")
async def get_info(req: VideoRequest):
    ydl_opts = {
        'cookiefile': os.path.abspath('cookies.txt'),
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
            formats = info.get('formats', [])
            clean_formats = []
            for f in formats:
                if f.get('format_id') and (f.get('height') or f.get('ext') == 'm4a'):
                    res = f"{f.get('height')}p" if f.get('height') else "Audio Only"
                    clean_formats.append({
                        "format_id": f.get('format_id'),
                        "resolution": res,
                        "ext": f.get('ext')
                    })
            return {
                "title": info.get('title'),
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "is_live": info.get('is_live', False),
                "id": info.get('id'),
                "extractor": info.get('extractor'),
                "formats": clean_formats
            }
    except Exception as e:
        error_msg = str(e)
        if "There is no video in this post" in error_msg and "instagram.com" in req.url.lower():
            try:
                import instaloader
                L = instaloader.Instaloader(quiet=True)
                match = re.search(r'/(?:p|reel|tv)/([^/?]+)', req.url)
                if match:
                    shortcode = match.group(1)
                    post = instaloader.Post.from_shortcode(L.context, shortcode)
                    return {
                        "title": post.caption and post.caption[:50] or f"Instagram Photo {shortcode}",
                        "thumbnail": post.url,
                        "duration": 0,
                        "is_live": False,
                        "id": shortcode,
                        "extractor": "instaloader",
                        "formats": [{
                            "format_id": "photo",
                            "resolution": "Photo (High Res)",
                            "ext": "jpg"
                        }]
                    }
            except Exception as inst_e:
                raise HTTPException(status_code=400, detail=f"Failed to fetch photo: {str(inst_e)}")
        
        raise HTTPException(status_code=400, detail=error_msg)

@app.post("/download")
async def download_video(req: VideoRequest):
    out_filename = f"dl_{uuid.uuid4().hex}"
    
    ydl_opts = {
        'cookiefile': os.path.abspath('cookies.txt'),
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': f'{out_filename}.%(ext)s',
        'quiet': True,
    }
    
    if req.start_time and req.end_time:
        ydl_opts['download_ranges'] = yt_dlp.utils.download_range_func(None, [(yt_dlp.utils.parse_duration(req.start_time), yt_dlp.utils.parse_duration(req.end_time))])
        ydl_opts['force_keyframes_at_cuts'] = True

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=True)
            import glob
            downloaded_files = glob.glob(f"{out_filename}.*")
            if not downloaded_files:
                raise HTTPException(status_code=404, detail="Video file not found after downloading.")
            actual_filename = downloaded_files[0]
            
            return FileResponse(actual_filename, media_type='application/octet-stream', filename=os.path.basename(actual_filename))
    except Exception as e:
        error_msg = str(e)
        if "There is no video in this post" in error_msg and "instagram.com" in req.url.lower():
            try:
                import instaloader
                L = instaloader.Instaloader(quiet=True)
                match = re.search(r'/(?:p|reel|tv)/([^/?]+)', req.url)
                if match:
                    shortcode = match.group(1)
                    post = instaloader.Post.from_shortcode(L.context, shortcode)
                    img_url = post.url
                    # Download the image
                    urllib.request.urlretrieve(img_url, f"{out_filename}.jpg")
                    return FileResponse(f"{out_filename}.jpg", media_type='image/jpeg', filename=f"{shortcode}.jpg")
            except Exception as inst_e:
                raise HTTPException(status_code=400, detail=f"Failed to fetch photo: {str(inst_e)}")
                
        raise HTTPException(status_code=400, detail=error_msg)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
