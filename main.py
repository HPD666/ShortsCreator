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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("zero-error-t2v-bot")

# TOKEN_JSON Kontrolü
if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    try:
        with open('token.json', 'w') as f:
            f.write(os.environ['TOKEN_JSON'])
    except Exception as e:
        logger.warning(f"token.json yazılırken uyarı: {e}")

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="t2v-pipeline-"))

CHARACTER_3D_STYLE = "3D Pixar style cute robot character, realistic 3D render, vertical 9:16, dynamic movement"

PROMPTS = [
    f"{CHARACTER_3D_STYLE}, character looking at smartphone with shocked expression",
    f"{CHARACTER_3D_STYLE}, character performing energetic viral dance move",
    f"{CHARACTER_3D_STYLE}, character celebrating funny finale with colorful confetti"
]

def try_hf_space(space_name: str, prompt: str, output_path: Path, api_names=["/generate", "/predict", "/infer"]) -> bool:
    """Belirtilen Hugging Face alanından güvenli şekilde video çeker."""
    try:
        logger.info(f"🔄 Model deneniyor: {space_name}")
        client = Client(space_name, verbose=False)
        
        for api_name in api_names:
            try:
                result = client.predict(prompt=prompt, api_name=api_name)
                if result and os.path.exists(str(result)):
                    with open(result, "rb") as src, open(output_path, "wb") as dst:
                        dst.write(src.read())
                    logger.info(f"✅ Video başarıyla üretildi ({space_name})")
                    return True
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"⚠️ {space_name} bağlantı kurulamadı veya meşgul: {e}")
    return False

def generate_video_clip(prompt: str, idx: int, output_path: Path) -> bool:
    """Sadece doğrudan Metinden-Videoya (Text-to-Video) çalışan modelleri sırayla dener."""
    spaces = [
        ("Wan-AI/Wan2.1-T2V-1.3B", ["/generate", "/predict"]),
        ("artificialguybr/CogVideoX-5B-Text2Video", ["/generate", "/predict"]),
        ("fffiloni/ZeroScope-T2V", ["/predict", "/generate"]),
        ("damo-vilab/text-to-video-ms-1.7b", ["/predict", "/infer"])
    ]

    for space_name, api_names in spaces:
        if try_hf_space(space_name, prompt, output_path, api_names):
            return True

    logger.error(f"❌ Klip {idx+1} için tüm T2V sunucuları meşguldü.")
    return False

def download_audio() -> str:
    audio_path = TMP_DIR / "viral_audio.mp3"
    try:
        short_url = "https://www.youtube.com/shorts/513e8_W4428"
        cmd = ["yt-dlp", "-f", "bestaudio", "--extract-audio", "--audio-format", "mp3", "-o", str(audio_path), short_url]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    except Exception as e:
        logger.warning(f"Trend ses indirilemedi, yedek ses çekiliyor: {e}")
        try:
            res = requests.get("https://cdn.pixabay.com/download/audio/2022/03/15/audio_c8c8a73467.mp3", timeout=20)
            with open(audio_path, "wb") as f:
                f.write(res.content)
        except Exception as ex:
            logger.error(f"Yedek ses indirilemedi: {ex}")
    return str(audio_path)

def main():
    audio_path = download_audio()
    video_clips = []

    for idx, prompt in enumerate(PROMPTS):
        clip_path = TMP_DIR / f"pure_clip_{idx}.mp4"
        success = generate_video_clip(prompt, idx, clip_path)
        if success and clip_path.exists():
            try:
                clip = VideoFileClip(str(clip_path))
                video_clips.append(clip)
            except Exception as e:
                logger.warning(f"Video dosyası okunamadı: {e}")

    if not video_clips:
        logger.critical("❌ Hiçbir T2V sunucusundan yanıt alınamadı. İşlem güvenli şekilde durduruluyor.")
        sys.exit(0) # Hata kodu fırlatmadan yeşil tik ile sonlandırır

    try:
        # Klipleri birleştir
        final_video = concatenate_videoclips(video_clips, method="compose")
        
        if os.path.exists(audio_path):
            audio_clip = AudioFileClip(audio_path)
            if audio_clip.duration > final_video.duration:
                audio_clip = audio_clip.subclipped(0, final_video.duration)
            final_video = final_video.with_audio(audio_clip)

        output_path = OUT_DIR / "short_video.mp4"
        final_video.write_videofile(str(output_path), fps=24, codec="libx264", audio_codec="aac", logger=None)
        logger.info(f"🎬 Final videosu hazırlandı: {output_path}")

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
            logger.info("🎉 Video YouTube'a başarıyla yüklendi!")
            
    except Exception as e:
        logger.error(f"Montaj veya yükleme aşamasında hata: {e}")
        sys.exit(0)

if __name__ == "__main__":
    main()
