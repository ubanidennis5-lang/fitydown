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
        # ADD THIS LINE HERE SO FETCHING NEVER CRASHES:
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
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
