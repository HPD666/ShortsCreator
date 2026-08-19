import os
import sys
import time
import logging
import tempfile
import requests
from pathlib import Path
import subprocess

from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kling-video-bot")

# --- SECRETS HAZIRLIĞI ---
if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    with open('token.json', 'w') as f:
        f.write(os.environ['TOKEN_JSON'])

KLING_API_KEY = os.environ.get("KLING_API_KEY", "")
OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="kling-pipeline-"))

# Sabit 3D Karakter ve Görsel Stil Tanımı
CHARACTER_3D_STYLE = "3D Pixar style cute robot character, realistic 3D camera movement, cinematic lighting, vertical 9:16"

SCENARIO_PROMPTS = [
    f"{CHARACTER_3D_STYLE}, character looking at smartphone with shocked expression, camera zoom in",
    f"{CHARACTER_3D_STYLE}, character doing viral trend dance move, energetic movement, dynamic camera shot",
    f"{CHARACTER_3D_STYLE}, character celebrating funny finale, colorful confetti, cinematic motion blur"
]

def generate_kling_video(prompt: str, output_path: Path) -> bool:
    """Kling AI API kullanarak gerçek video (.mp4) üretir."""
    logger.info(f"🎬 Kling AI ile video üretiliyor: {prompt[:40]}...")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KLING_API_KEY}"
    }
    
    # 1. Video Üretim Görevi Başlat
    payload = {
        "model_name": "kling-v1",
        "prompt": prompt,
        "aspect_ratio": "9:16",
        "duration": "5"
    }
    
    try:
        response = requests.post("https://api.klingai.com/v1/videos/text2video", json=payload, headers=headers, timeout=30)
        res_data = response.json()
        
        if res_data.get("code") != 0:
            logger.error(f"Kling API Hata: {res_data}")
            return False
            
        task_id = res_data["data"]["task_id"]
        logger.info(f"Task oluşturuldu: {task_id}, işleniyor...")

        # 2. Video Hazır Olana Kadar Bekle (Polling)
        for _ in range(30):
            time.sleep(10)
            status_res = requests.get(f"https://api.klingai.com/v1/videos/text2video/{task_id}", headers=headers, timeout=15)
            status_data = status_res.json()
            
            task_status = status_data.get("data", {}).get("task_status")
            if task_status == "succeed":
                video_url = status_data["data"]["task_result"]["videos"][0]["url"]
                video_data = requests.get(video_url, timeout=60).content
                with open(output_path, "wb") as f:
                    f.write(video_data)
                return True
            elif task_status == "failed":
                logger.error("Kling Video üretimi başarısız oldu.")
                return False
                
    except Exception as e:
        logger.error(f"Kling API İstek Hatası: {e}")
        
    return False

def download_trend_audio() -> str:
    audio_path = TMP_DIR / "viral_audio.mp3"
    try:
        short_url = "https://www.youtube.com/shorts/513e8_W4428"
        cmd = ["yt-dlp", "-f", "bestaudio", "--extract-audio", "--audio-format", "mp3", "-o", str(audio_path), short_url]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception:
        res = requests.get("https://cdn.pixabay.com/download/audio/2022/03/15/audio_c8c8a73467.mp3")
        with open(audio_path, "wb") as f:
            f.write(res.content)
    return str(audio_path)

def main():
    if not KLING_API_KEY:
        logger.error("KLING_API_KEY bulunamadı! Secrets kısmına ekleyin.")
        sys.exit(1)

    audio_path = download_trend_audio()
    video_clips = []

    # Her senaryo adımı için Kling AI ile ayrı video üret
    for idx, prompt in enumerate(SCENARIO_PROMPTS):
        clip_path = TMP_DIR / f"kling_clip_{idx}.mp4"
        success = generate_kling_video(prompt, clip_path)
        
        if success and clip_path.exists():
            video_clips.append(VideoFileClip(str(clip_path)))

    if not video_clips:
        logger.error("Hiçbir video klibi oluşturulamadı.")
        sys.exit(1)

    # Videoları uç uca birleştir ve sesi ekle
    final_video = concatenate_videoclips(video_clips, method="compose")
    audio_clip = AudioFileClip(audio_path)
    
    if audio_clip.duration > final_video.duration:
        audio_clip = audio_clip.subclipped(0, final_video.duration)
        
    final_video = final_video.with_audio(audio_clip)
    output_path = OUT_DIR / "short_video.mp4"
    final_video.write_videofile(str(output_path), fps=24, codec="libx264", audio_codec="aac", logger=None)

    # YouTube Yükleme
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json')
        youtube = build('youtube', 'v3', credentials=creds)

        body = {
            'snippet': {'title': '#trend #shorts #kling #3d', 'description': '#shorts #viral #3d', 'categoryId': '22'},
            'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
        }
        media = MediaFileUpload(str(output_path), chunksize=-1, resumable=True, mimetype='video/mp4')
        youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
        logger.info("🎉 Kling AI ile üretilen 3D Trend videosu YouTube'a yüklendi!")

if __name__ == "__main__":
    main()
