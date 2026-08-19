import os
import sys
import io
import json
import logging
import tempfile
import subprocess
import requests
from pathlib import Path
from bs4 import BeautifulSoup
import numpy as np
from PIL import Image

import librosa
import soundfile as sf
from moviepy import ImageSequenceClip, AudioFileClip

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trend-pipeline")

# --- 1. SECRETS VE KLASÖR KURULUMU ---
if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    with open('token.json', 'w') as f:
        f.write(os.environ['TOKEN_JSON'])

if 'CLIENT_SECRET_JSON' in os.environ and os.environ['CLIENT_SECRET_JSON'].strip():
    with open('client_secret.json', 'w') as f:
        f.write(os.environ['CLIENT_SECRET_JSON'])

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="trend-pipeline-"))

TARGET_RESOLUTION = (1080, 1920) # 9:16 Portrait
TITLE = "#trend #shorts #viral"
MAX_VIDEO_SECONDS = 10
FRAME_RATE = 24

# --- 2. CENTER-CROP (9:16 ORANTI KORUMA) ---
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

# --- 3. TREND VİRAL MÜZİK İNDİRME ---
def download_trending_audio():
    logger.info("🔍 Trend YouTube Short müziği indiriliyor...")
    audio_path = TMP_DIR / "viral_audio.mp3"
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
        logger.warning(f"Trend indirme hatası, yedek müzik kullanılıyor: {e}")
        music_url = "https://cdn.pixabay.com/download/audio/2022/03/15/audio_c8c8a73467.mp3"
        res = requests.get(music_url)
        with open(audio_path, "wb") as f:
            f.write(res.content)
        return str(audio_path)

# --- 4. RİTME UYGUN KARE OLUŞTURMA ---
def generate_dance_sequence(audio_path):
    logger.info("🕺 Dans kareleri hazırlanıyor...")
    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    duration = min(librosa.get_duration(y=y, sr=sr), MAX_VIDEO_SECONDS)
    
    total_frames = int(duration * FRAME_RATE)
    frames_dir = TMP_DIR / "dance_frames"
    frames_dir.mkdir(exist_ok=True)

    # 4 Farklı Trend Poz Görseli Oluştur
    poses = []
    base_prompts = [
        "anime character dynamic dance pose 1, neon background",
        "anime character dynamic dance pose 2, neon background",
        "anime character dynamic dance pose 3, neon background",
        "anime character dynamic dance pose 4, neon background"
    ]

    for idx, p in enumerate(base_prompts):
        encoded = requests.utils.quote(p)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&nologo=true"
        try:
            res = requests.get(url, timeout=15)
            if res.status_code == 200:
                img = Image.open(io.BytesIO(res.content)).convert("RGB")
            else:
                img = Image.new("RGB", TARGET_RESOLUTION, (30 * (idx+1), 20, 50))
        except Exception:
            img = Image.new("RGB", TARGET_RESOLUTION, (30 * (idx+1), 20, 50))
        
        cropped = center_crop_9_16(img, TARGET_RESOLUTION)
        poses.append(cropped)

    # Kareleri ritmik geçişle kaydet
    frame_files = []
    for i in range(total_frames):
        # Her 6 karede bir poz değiştir (dans ritmi simülasyonu)
        pose_idx = (i // 6) % len(poses)
        frame_path = frames_dir / f"frame_{i:05d}.jpg"
        poses[pose_idx].save(frame_path, quality=90)
        frame_files.append(str(frame_path))

    return frame_files, duration

# --- 5. VİDEO BİRLEŞTİRME VE YÜKLEME ---
def main():
    logger.info("🚀 Otomasyon başlatıldı...")
    audio_file = download_trending_audio()
    frame_files, video_duration = generate_dance_sequence(audio_file)

    output_video_path = OUT_DIR / "short_video.mp4"

    # En güvenli MoviePy video sentezi
    video_clip = ImageSequenceClip(frame_files, fps=FRAME_RATE)
    audio_clip = AudioFileClip(audio_file)
    
    # Ses uzunluğunu videoya göre kırp
    if audio_clip.duration > video_duration:
        audio_clip = audio_clip.subclipped(0, video_duration)
    
    final_clip = video_clip.with_audio(audio_clip)
    final_clip.write_videofile(
        str(output_video_path), 
        fps=FRAME_RATE, 
        codec="libx264", 
        audio_codec="aac",
        logger=None
    )

    logger.info("📤 YouTube'a yükleniyor...")
    if not os.path.exists('token.json'):
        logger.error("❌ token.json bulunamadı! Yükleme yapılamıyor.")
        sys.exit(1)

    creds = Credentials.from_authorized_user_file('token.json')
    youtube = build('youtube', 'v3', credentials=creds)

    request_body = {
        'snippet': {
            'title': TITLE,
            'description': f"{TITLE} #trending #dance #viral",
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

    logger.info(f"🎉 BAŞARILI! Video Yüklendi. YouTube Video ID: {response.get('id')}")

if __name__ == "__main__":
    main()
