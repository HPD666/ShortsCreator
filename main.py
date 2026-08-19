import os
import sys
import logging
import tempfile
import requests
import shutil
import urllib.parse
from pathlib import Path

from gradio_client import Client
from moviepy import VideoFileClip, ImageClip, AudioFileClip, concatenate_videoclips
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("pure-t2v-bot")

# Token Kontrolleri
if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    try:
        with open('token.json', 'w') as f:
            f.write(os.environ['TOKEN_JSON'])
    except Exception as e:
        logger.warning(f"token.json yazılamadı: {e}")

HF_TOKEN = os.environ.get("HF_TOKEN", None)

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="t2v-pipeline-"))

CHARACTER_3D_STYLE = "3D Pixar style cute robot character, realistic 3D render, vertical 9:16"

PROMPTS = [
    f"{CHARACTER_3D_STYLE}, robot looking at smartphone shocked",
    f"{CHARACTER_3D_STYLE}, robot dancing energetic viral dance",
    f"{CHARACTER_3D_STYLE}, robot celebrating with colorful confetti"
]

def generate_t2v_video(prompt: str, idx: int, output_path: Path) -> bool:
    """Yedekli ve Garantili Metinden-Videoya (T2V) üretim fonksiyonu."""
    logger.info(f"🎬 Klip {idx+1} üretiliyor: '{prompt[:30]}...'")

    # 1. YÖNTEM: Aktif Hugging Face Spaces
    spaces_config = [
        {"space": "damo-vilab/ModelScope-Text-To-Video-Synthesis", "api_name": "/predict"},
        {"space": "fffiloni/ZeroScope-T2V", "api_name": "/predict"}
    ]

    for config in spaces_config:
        space_name = config["space"]
        api_name = config["api_name"]
        try:
            logger.info(f"🔄 HF Space deneniyor: {space_name}")
            client = Client(space_name, token=HF_TOKEN, verbose=False) if HF_TOKEN else Client(space_name, verbose=False)
            
            result = client.predict(prompt, api_name=api_name)
            
            video_file = None
            if isinstance(result, str) and os.path.exists(result):
                video_file = result
            elif isinstance(result, (list, tuple)) and len(result) > 0:
                item = result[0]
                if isinstance(item, str) and os.path.exists(item):
                    video_file = item
                elif isinstance(item, dict) and "video" in item:
                    video_file = item["video"]

            if video_file and os.path.exists(video_file):
                shutil.copy(video_file, str(output_path))
                logger.info(f"✅ Klip {idx+1} HF sunucusundan başarıyla alındı.")
                return True
        except Exception as e:
            logger.warning(f"⚠️ {space_name} geçildi: {e}")

    # 2. YÖNTEM (YEDEK): HF başarısız olursa Görsel/Video Üretip MP4'e Dönüştürme
    try:
        logger.info("⚡ HF sunucuları meşgul, yedek API devreye giriyor...")
        encoded_prompt = urllib.parse.quote(prompt)
        img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=576&height=1024&seed={idx+42}"
        
        response = requests.get(img_url, timeout=60)
        if response.status_code == 200 and len(response.content) > 5000:
            temp_img = TMP_DIR / f"temp_{idx}.jpg"
            with open(temp_img, "wb") as f:
                f.write(response.content)
            
            # İndirilen görseli 3 saniyelik MP4 klibine dönüştür
            img_clip = ImageClip(str(temp_img)).with_duration(3)
            img_clip.write_videofile(str(output_path), fps=24, codec="libx264", logger=None)
            img_clip.close()
            
            logger.info(f"✅ Klip {idx+1} görselden 3s videoya başarıyla dönüştürüldü.")
            return True
    except Exception as e:
        logger.error(f"❌ Yedek API hatası: {e}")

    return False

def download_audio() -> str:
    audio_path = TMP_DIR / "viral_audio.mp3"
    pixabay_url = "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3"
    try:
        res = requests.get(pixabay_url, timeout=30)
        if res.status_code == 200:
            with open(audio_path, "wb") as f:
                f.write(res.content)
            logger.info("🎵 Arka plan müziği indirildi.")
    except Exception as e:
        logger.warning(f"Müzik indirilemedi: {e}")
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
        logger.error("❌ Hiçbir sunucudan klip alınamadı.")
        sys.exit(0)

    try:
        final_video = concatenate_videoclips(video_clips, method="compose")
        
        if os.path.exists(audio_path):
            try:
                audio_clip = AudioFileClip(audio_path)
                if audio_clip.duration > final_video.duration:
                    audio_clip = audio_clip.subclipped(0, final_video.duration)
                final_video = final_video.with_audio(audio_clip)
                logger.info("🔊 Ses eklendi.")
            except Exception as e:
                logger.warning(f"Ses eklenemedi: {e}")

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
            logger.info("🎉 Videolu ve Sesli Short YouTube'a yüklendi!")

    except Exception as e:
        logger.error(f"İşlem hatası: {e}")
        sys.exit(0)

if __name__ == "__main__":
    main()
