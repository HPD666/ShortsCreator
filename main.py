import os
import sys
import time
import logging
import tempfile
import requests
import subprocess
from pathlib import Path

from gradio_client import Client
from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hf-free-video-bot")

# Secrets ve YouTube Token Kontrolü
if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    with open('token.json', 'w') as f:
        f.write(os.environ['TOKEN_JSON'])

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="hf-pipeline-"))

# Sabit 3D Karakter Stil Tanımı
CHARACTER_3D_STYLE = "3D Pixar style cute robot character, realistic 3D render, vertical 9:16, dynamic movement"

PROMPTS = [
    f"{CHARACTER_3D_STYLE}, character looking at smartphone with shocked expression, zoom in",
    f"{CHARACTER_3D_STYLE}, character performing energetic viral dance move, dynamic motion",
    f"{CHARACTER_3D_STYLE}, character celebrating funny finale, colorful confetti"
]

def generate_video_from_hf(prompt: str, output_path: Path) -> bool:
    """Hugging Face ZeroGPU üzerindeki açık kaynak video modeliyle ücretsiz .mp4 üretir."""
    logger.info(f"🎬 Open-Source HF Space ile video üretiliyor: {prompt[:40]}...")
    
    # 1. Öncelikli Model (LTX-Video)
    try:
        client = Client("Lightricks/LTX-Video")
        result = client.predict(
            prompt=prompt,
            negative_prompt="worst quality, low quality, blurry",
            frame_rate=25,
            api_name="/generate"
        )
        if result and os.path.exists(result):
            with open(result, "rb") as src, open(output_path, "wb") as dst:
                dst.write(src.read())
            return True
    except Exception as e:
        logger.warning(f"LTX-Video yoğun, yedek açık kaynak model deneniyor: {e}")

    # 2. Yedek Model (CogVideoX)
    try:
        client = Client("THUDM/CogVideoX-5B-Space")
        result = client.predict(
            prompt=prompt,
            api_name="/generate"
        )
        if result and os.path.exists(result):
            with open(result, "rb") as src, open(output_path, "wb") as dst:
                dst.write(src.read())
            return True
    except Exception as ex:
        logger.error(f"Hugging Face Video Üretim Hatası: {ex}")

    return False

def download_audio() -> str:
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
    audio_path = download_audio()
    video_clips = []

    for idx, prompt in enumerate(PROMPTS):
        clip_path = TMP_DIR / f"hf_clip_{idx}.mp4"
        success = generate_video_from_hf(prompt, clip_path)
        if success and clip_path.exists():
            video_clips.append(VideoFileClip(str(clip_path)))

    if not video_clips:
        logger.error("Video klipleri oluşturulamadı.")
        sys.exit(1)

    # Hareketli video kliplerini birleştir ve sesi ekle
    final_video = concatenate_videoclips(video_clips, method="compose")
    audio_clip = AudioFileClip(audio_path)
    
    if audio_clip.duration > final_video.duration:
        audio_clip = audio_clip.subclipped(0, final_video.duration)
        
    final_video = final_video.with_audio(audio_clip)
    output_path = OUT_DIR / "short_video.mp4"
    final_video.write_videofile(str(output_path), fps=24, codec="libx264", audio_codec="aac", logger=None)

    # YouTube Otomatik Yükleme
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json')
        youtube = build('youtube', 'v3', credentials=creds)

        body = {
            'snippet': {'title': '#shorts #3d #viral #trending', 'description': '#shorts #3d #viral', 'categoryId': '22'},
            'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
        }
        media = MediaFileUpload(str(output_path), chunksize=-1, resumable=True, mimetype='video/mp4')
        youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
        logger.info("🎉 HF Açık Kaynak Video Altyapısı ile üretilen Short yüklendi!")

if __name__ == "__main__":
    main()
