import os
import imageio_ffmpeg
os.environ["PATH"] += os.pathsep + os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import yt_dlp
import uuid

app = FastAPI()

# Allow our Next.js frontend to talk to this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DownloadRequest(BaseModel):
    url: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None

def parse_time_to_seconds(time_str: str) -> int:
    if not time_str: return 0
    parts = time_str.split(':')
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + int(part)
    return seconds

def cleanup_file(filepath: str):
    if os.path.exists(filepath):
        os.remove(filepath)

@app.post("/download")
async def download_video(req: DownloadRequest, background_tasks: BackgroundTasks):
    start_sec = parse_time_to_seconds(req.start_time) if req.start_time else None
    end_sec = parse_time_to_seconds(req.end_time) if req.end_time else None

    # Generate a unique filename for this user's download
    filename = f"/tmp/{uuid.uuid4()}.mp4"

    ydl_opts = {
        'format': 'best',
        'outtmpl': filename,
        'quiet': True,
        'no_warnings': True,
    }

    # If the user provided timestamps, tell yt-dlp to slice the video!
    if start_sec is not None and end_sec is not None:
        def download_range_func(info_dict, ydl):
            return [{'start_time': start_sec, 'end_time': end_sec}]
        ydl_opts['download_ranges'] = download_range_func

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([req.url])
            
        if not os.path.exists(filename):
            raise HTTPException(status_code=500, detail="Failed to process video.")
            
        # Tell FastAPI to delete the file from the server AFTER sending it to the user
        background_tasks.add_task(cleanup_file, filename)
        
        return FileResponse(path=filename, media_type='video/mp4', filename="video_clip.mp4")

    except Exception as e:
        cleanup_file(filename)
        raise HTTPException(status_code=400, detail=str(e))
