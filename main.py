import os
import sys
import time
import logging
import tempfile
import requests
import subprocess
from pathlib import Path

from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("pure-t2v-bot")

if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    with open('token.json', 'w') as f:
        f.write(os.environ['TOKEN_JSON'])

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="t2v-pipeline-"))

CHARACTER_3D_STYLE = "3D Pixar style cute robot character, realistic render, 9:16 vertical"

PROMPTS = [
    f"{CHARACTER_3D_STYLE}, robot looking at smartphone shocked",
    f"{CHARACTER_3D_STYLE}, robot dancing energetic viral dance",
    f"{CHARACTER_3D_STYLE}, robot celebrating with colorful confetti"
]

def generate_t2v_video(prompt: str, idx: int, output_path: Path) -> bool:
    """Doğrudan Metinden-Videoya (Text-to-Video) API servislerini dener."""
    logger.info(f"🎬 Klip {idx+1} için Metinden-Videoya (T2V) istek atılıyor...")

    # 1. Yöntem: Pollinations T2V Direct Video API
    try:
        encoded_prompt = requests.utils.quote(prompt)
        video_url = f"https://video.pollinations.ai/prompt/{encoded_prompt}?width=720&height=1280&seed={200 + idx}"
        
        response = requests.get(video_url, timeout=120)
        if response.status_code == 200 and len(response.content) > 100000:
            with open(output_path, "wb") as f:
                f.write(response.content)
            logger.info(f"✅ Klip {idx+1} doğrudan T2V servisi ile üretildi!")
            return True
    except Exception as e:
        logger.warning(f"Pollinations T2V yanıt vermedi: {e}")

    # 2. Yöntem: ModelScope / HF Public T2V Endpoint
    try:
        from gradio_client import Client
        client = Client("damo-vilab/modelscope-text-to-video-synthesis", verbose=False)
        result = client.predict(prompt, api_name="/predict")
        if result and os.path.exists(str(result)):
            with open(result, "rb") as src, open(output_path, "wb") as dst:
                dst.write(src.read())
            logger.info(f"✅ Klip {idx+1} ModelScope T2V ile üretildi!")
            return True
    except Exception as e:
        logger.warning(f"ModelScope T2V meşgul: {e}")

    return False

def download_audio() -> str:
    audio_path = TMP_DIR / "viral_audio.mp3"
    try:
        short_url = "https://www.youtube.com/shorts/513e8_W4428"
        cmd = ["yt-dlp", "-f", "bestaudio", "--extract-audio", "--audio-format", "mp3", "-o", str(audio_path), short_url]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    except Exception:
        res = requests.get("https://cdn.pixabay.com/download/audio/2022/03/15/audio_c8c8a73467.mp3", timeout=20)
        with open(audio_path, "wb") as f:
            f.write(res.content)
    return str(audio_path)

def main():
    audio_path = download_audio()
    video_clips = []

    for idx, prompt in enumerate(PROMPTS):
        clip_path = TMP_DIR / f"pure_clip_{idx}.mp4"
        success = generate_t2v_video(prompt, idx, clip_path)
        if success and clip_path.exists():
            try:
                clip = VideoFileClip(str(clip_path))
                video_clips.append(clip)
            except Exception as e:
                logger.warning(f"Klip okunamadı: {e}")

    if not video_clips:
        logger.error("❌ Hiçbir video klibi üretilemedi.")
        sys.exit(1)

    final_video = concatenate_videoclips(video_clips, method="compose")
    if os.path.exists(audio_path):
        audio_clip = AudioFileClip(audio_path)
        if audio_clip.duration > final_video.duration:
            audio_clip = audio_clip.subclipped(0, final_video.duration)
        final_video = final_video.with_audio(audio_clip)

    output_path = OUT_DIR / "short_video.mp4"
    final_video.write_videofile(str(output_path), fps=24, codec="libx264", audio_codec="aac", logger=None)

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json')
        youtube = build('youtube', 'v3', credentials=creds)

        body = {
            'snippet': {
                'title': '#shorts #3d #viral #trending',
                'description': '#shorts #3d #viral',
                'categoryId': '22'
            },
            'status': {
                'privacyStatus': 'public',
                'selfDeclaredMadeForKids': False,
                'containsSyntheticMedia': True
            }
        }
        media = MediaFileUpload(str(output_path), chunksize=-1, resumable=True, mimetype='video/mp4')
        youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
        logger.info("🎉 Video YouTube'a yüklendi!")

if __name__ == "__main__":
    main()
