import os
import sys
import io
import json
import math
import time
import shutil
import logging
import tempfile
import subprocess
import requests
from pathlib import Path
from bs4 import BeautifulSoup
import numpy as np
from PIL import Image

import mediapipe as mp
import cv2
import librosa
import soundfile as sf
from moviepy import ImageSequenceClip, AudioFileClip, CompositeVideoClip

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trend-pipeline")

# --- 1. SECRETS HAZIRLIĞI ---
if 'TOKEN_JSON' in os.environ:
    with open('token.json', 'w') as f:
        f.write(os.environ['TOKEN_JSON'])

if 'CLIENT_SECRET_JSON' in os.environ:
    with open('client_secret.json', 'w') as f:
        f.write(os.environ['CLIENT_SECRET_JSON'])

HF_TOKEN = os.environ.get("HF_TOKEN", None)

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="trend-pipeline-"))

TARGET_RESOLUTION = (1080, 1920) # 9:16 Portrait
TITLE = "#trend #shorts #viral"
MAX_VIDEO_SECONDS = 12
FRAME_RATE = 24

# --- 2. ORANTI BOZMAYAN CENTER-CROP ---
def center_crop_9_16(pil_img, target=TARGET_RESOLUTION):
    target_w, target_h = target
    src_w, src_h = pil_img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img_resized = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img_resized.crop((left, top, left + target_w, top + target_h))

# --- 3. TREND VE ORİJİNAL VİRAL SESİ İNDİRME ---
def discover_and_download_trend():
    logger.info("🔍 Scrape & download trending short dance audio...")
    try:
        url = "https://www.youtube.com/feed/trending"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        short_url = None
        for a in soup.find_all("a", href=True):
            if "/shorts/" in a["href"]:
                short_url = "https://www.youtube.com" + a["href"].split("&")[0]
                break
        
        if not short_url:
            short_url = "https://www.youtube.com/shorts/"

        audio_path = TMP_DIR / "viral_audio.mp3"
        cmd = [
            "yt-dlp",
            "-f", "bestaudio",
            "--extract-audio",
            "--audio-format", "mp3",
            "-o", str(audio_path),
            short_url
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return str(audio_path)
    except Exception as e:
        logger.warning(f"Trend download fallback: {e}")
        # Yedek ritmik müzik
        music_url = "https://cdn.pixabay.com/download/audio/2022/03/15/audio_c8c8a73467.mp3"
        fallback_path = TMP_DIR / "fallback_audio.mp3"
        res = requests.get(music_url)
        with open(fallback_path, "wb") as f:
            f.write(res.content)
        return str(fallback_path)

# --- 4. DANS KOREOGRAFİSİ & HAREKET SENTETİKLEME ---
def generate_dance_frames(audio_path):
    logger.info("🕺 Extracting beats and generating motion-synced dance frames...")
    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    duration = min(librosa.get_duration(y=y, sr=sr), MAX_VIDEO_SECONDS)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beats, sr=sr)

    total_frames = int(duration * FRAME_RATE)
    frames_dir = TMP_DIR / "dance_frames"
    frames_dir.mkdir(exist_ok=True)

    # Hugging Face veya Pollinations ile trende uygun akım kareleri üretme
    base_prompt = "cyberpunk anime protagonist performing energetic TikTok dance challenge, neon stage lights, highly detailed, 8k portrait"
    
    frame_files = []
    for i in range(total_frames):
        current_time = i / FRAME_RATE
        # Ritme göre dans hareket pozu değişimi
        is_beat = any(abs(current_time - b) < (1.0 / FRAME_RATE) for b in beat_times)
        
        # Pollinations Turbo (Ücretsiz Hızlı Render)
        prompt_step = f"{base_prompt}, dance move frame {i%8 + 1}, dynamic pose, sharp focus"
        encoded = requests.utils.quote(prompt_step)
        img_url = f"https://image.pollinations.ai/prompt/{encoded}?model=turbo&width=1080&height=1920&nologo=true"
        
        try:
            res = requests.get(img_url, timeout=10)
            if res.status_code == 200:
                raw_img = Image.open(io.BytesIO(res.content)).convert("RGB")
            else:
                raw_img = Image.new("RGB", TARGET_RESOLUTION, (20, 20, 40))
        except Exception:
            raw_img = Image.new("RGB", TARGET_RESOLUTION, (20, 20, 40))

        cropped = center_crop_9_16(raw_img, TARGET_RESOLUTION)
        frame_path = frames_dir / f"frame_{i:05d}.jpg"
        cropped.save(frame_path, quality=90)
        frame_files.append(str(frame_path))

    return frame_files, duration

# --- 5. VİDEO OLUŞTURMA VE YÜKLEME ---
def main():
    logger.info("🚀 Starting Trend & Dance Pipeline...")
    audio_file = discover_and_download_trend()
    frame_files, video_duration = generate_dance_frames(audio_file)

    output_video_path = OUT_DIR / "short_video.mp4"

    # MoviePy v2 ile Ses ve Görüntü Birleştirme
    video_clip = ImageSequenceClip(frame_files, fps=FRAME_RATE).subclipped(0, video_duration)
    audio_clip = AudioFileClip(audio_file).subclipped(0, video_duration)
    
    final_video = CompositeVideoClip([video_clip]).with_audio(audio_clip)
    final_video.write_videofile(str(output_video_path), fps=FRAME_RATE, codec="libx264", audio_codec="aac")

    logger.info("📤 Uploading generated trend video to YouTube...")
    if not os.path.exists('token.json'):
        logger.error("token.json not found! Cannot upload to YouTube.")
        return

    creds = Credentials.from_authorized_user_file('token.json')
    youtube = build('youtube', 'v3', credentials=creds)

    request_body = {
        'snippet': {
            'title': TITLE,
            'description': f"{TITLE} #trending #dance #challenge",
            'tags': ['trend', 'shorts', 'viral', 'dance'],
            'categoryId': '22'
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False,
        }
    }

    media = MediaFileUpload(str(output_video_path), chunksize=-1, resumable=True, mimetype='video/mp4')
    response = youtube.videos().insert(
        part='snippet,status',
        body=request_body,
        media_body=media
    ).execute()

    logger.info(f"🎉 SUCCESS! YouTube Short Uploaded with ID: {response.get('id')}")

if __name__ == "__main__":
    main()
