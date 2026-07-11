import os
import imageio_ffmpeg
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import yt_dlp
import uuid

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class InfoRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url: str
    format_id: Optional[str] = 'best'
    start_time: Optional[str] = None
    end_time: Optional[str] = None

def get_base_ydl_opts():
    # FORCE absolute paths to guarantee the cookies.txt file is found
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    cookie_path = os.path.join(BASE_DIR, 'cookies.txt')
    
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'ffmpeg_location': imageio_ffmpeg.get_ffmpeg_exe(), # Guarantees audio/video merging works
        'extractor_args': {
            'youtube': ['player_client=android', 'client=android'] # Bypasses YouTube bot checks
        }
    }
    
    if os.path.exists(cookie_path):
        opts['cookiefile'] = cookie_path
    else:
        print(f"WARNING: Could not find cookies at {cookie_path}")
        
    return opts

@app.post("/info")
async def get_video_info(req: InfoRequest):
    ydl_opts = get_base_ydl_opts()
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # We skip downloading, so this just gets the title/thumbnail instantly
            info = ydl.extract_info(req.url, download=False)
            
            formats = []
            for f in info.get('formats', []):
                if f.get('vcodec') != 'none' or f.get('acodec') != 'none':
                    formats.append({
                        'format_id': f.get('format_id'),
                        'ext': f.get('ext'),
                        'resolution': f.get('resolution') or 'Audio/Unknown',
                        'note': f.get('format_note', ''),
                        'filesize': f.get('filesize', 0)
                    })
                    
            return {
                "title": info.get("title", "Unknown Video"),
                "thumbnail": info.get("thumbnail", ""),
                "duration": info.get("duration", 0),
                "formats": formats
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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

    filename = f"/tmp/{uuid.uuid4()}.mp4"

    ydl_opts = get_base_ydl_opts()
    ydl_opts['format'] = req.format_id if req.format_id else 'best'
    ydl_opts['outtmpl'] = filename
    ydl_opts['merge_output_format'] = 'mp4'

    if start_sec is not None and end_sec is not None:
        def download_range_func(info_dict, ydl):
            return [{'start_time': start_sec, 'end_time': end_sec}]
        ydl_opts['download_ranges'] = download_range_func

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([req.url])
            
        actual_file = filename
        if not os.path.exists(actual_file):
            for ext in ['.mp4', '.mkv', '.webm', '.m4a', '.mp3']:
                test_file = f"/tmp/{filename.split('/')[-1].split('.')[0]}{ext}"
                if os.path.exists(test_file):
                    actual_file = test_file
                    break
                    
        if not os.path.exists(actual_file):
            raise HTTPException(status_code=500, detail="Failed to process video.")
            
        background_tasks.add_task(cleanup_file, actual_file)
        return FileResponse(path=actual_file, media_type='application/octet-stream', filename=f"fitydown_video{os.path.splitext(actual_file)[1]}")

    except Exception as e:
        cleanup_file(filename)
        raise HTTPException(status_code=400, detail=str(e))
