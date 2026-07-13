import os
import uuid
import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
import yt_dlp
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
    format_id: str = "best"
    start_time: str = None
    end_time: str = None

EXPLORE_CACHE = {}
CACHE_TTL = 900  

@app.get("/explore")
async def explore_live(category: str = "music"):
    return {"category": category, "streams": []}

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
            return {
                "title": info.get('title'),
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "is_live": info.get('is_live', False),
                "id": info.get('id'),
                "extractor": info.get('extractor'),
                "formats": []
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/download")
async def download_video(req: VideoRequest):
    out_filename = f"dl_{uuid.uuid4().hex}"
    
    ydl_opts = {
        'cookiefile': os.path.abspath('cookies.txt'),
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        # Extremely robust fallback: tries to get highest MP4, otherwise just grabs the absolute best single file available
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
            filename = ydl.prepare_filename(info)
            if not os.path.exists(filename):
                filename = f"{out_filename}.mp4"
            
            return FileResponse(filename, media_type='application/octet-stream', filename=os.path.basename(filename))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
