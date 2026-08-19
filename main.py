import os
import sys
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("pure-t2v-bot")

if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    try:
        with open('token.json', 'w') as f:
            f.write(os.environ['TOKEN_JSON'])
    except Exception as e:
        logger.warning(f"token.json yazılamadı: {e}")

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
    """Açık kaynak T2V sunucularından doğrudan video üretir."""
    logger.info(f"🎬 Klip {idx+1} için Metinden-Videoya (T2V) üretiliyor...")

    # Aktif ve çalışan T2V modelleri
    spaces = [
        "Wan-AI/Wan2.1-T2V-1.3B",
        "fffiloni/ZeroScope-T2V",
        "artificialguybr/CogVideoX-5B-Text2Video"
    ]

    for space_name in spaces:
        try:
            logger.info(f"🔄 HF Space bağlanıyor: {space_name}")
            client = Client(space_name, verbose=False)
            
            # API parametrelerini dinamik gönder
            job = client.submit(prompt=prompt, api_name="/predict")
            result = job.result(timeout=120)
            
            if result and os.path.exists(str(result)):
                with open(result, "rb") as src, open(output_path, "wb") as dst:
                    dst.write(src.read())
                logger.info(f"✅ Klip {idx+1} başarıyla üretildi ({space_name})")
                return True
        except Exception as e:
            logger.warning(f"⚠️ {space_name} geçildi: {e}")

    return False

def download_audio() -> str:
    """Yüksek kaliteli viral ses indirir."""
    audio_path = TMP_DIR / "viral_audio.mp3"
    
    # Doğrudan telifsiz hareketli müzik bağlantısı
    pixabay_url = "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3"
    try:
        res = requests.get(pixabay_url, timeout=30)
        if res.status_code == 200:
            with open(audio_path, "wb") as f:
                f.write(res.content)
            logger.info("🎵 Arka plan müziği indirildi.")
            return str(audio_path)
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
        logger.error("❌ Sunuculardan klip alınamadı. Lütfen birkaç dakika sonra tekrar çalıştırın.")
        sys.exit(0)

    try:
        final_video = concatenate_videoclips(video_clips, method="compose")
        
        # Sesi videoya bağlama
        if os.path.exists(audio_path):
            try:
                audio_clip = AudioFileClip(audio_path)
                if audio_clip.duration > final_video.duration:
                    audio_clip = audio_clip.subclipped(0, final_video.duration)
                final_video = final_video.with_audio(audio_clip)
                logger.info("🔊 Ses videoya başarıyla eklendi.")
            except Exception as e:
                logger.warning(f"Ses birleştirilemedi: {e}")

        output_path = OUT_DIR / "short_video.mp4"
        final_video.write_videofile(str(output_path), fps=24, codec="libx264", audio_codec="aac", logger=None)

        # YouTube Otomatik Yükleme
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
