import os
import sys
import logging
import tempfile
from pathlib import Path

from moviepy import (
    TextClip,
    ColorClip,
    CompositeVideoClip,
    AudioFileClip,
    concatenate_videoclips
)
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("shorts-creator")

if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    try:
        with open('token.json', 'w') as f:
            f.write(os.environ['TOKEN_JSON'])
    except Exception as e:
        logger.warning(f"token.json yazılamadı: {e}")

YT_API_KEY = os.environ.get("YT_API_KEY", None)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", None)

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="shorts-pipeline-"))

def get_live_trend_prompts():
    default_scenes = [
        "🔥 DÜNYANIN EN İNANILMAZ 3D GERÇEĞİ!",
        "🚀 TEKNOLOJİ YENİ BİR BOYUTA GEÇTİ!",
        "💡 BU VİDEOYU SAKIN KAÇIRMA!"
    ]
    
    if not YT_API_KEY or not GEMINI_API_KEY or not GENAI_AVAILABLE:
        logger.warning("Eksik API/kütüphane. Varsayılan sahneler kullanılıyor.")
        return default_scenes, "#shorts #viral #trending"

    try:
        logger.info("🔥 YouTube Shorts trendleri çekiliyor...")
        youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
        res = youtube.search().list(q='shorts viral challenge', type='video', videoDuration='short', maxResults=5, part='snippet').execute()
        
        titles = [item['snippet']['title'] for item in res.get('items', [])]
        trend_context = " | ".join(titles)

        client = genai.Client(api_key=GEMINI_API_KEY)
        gemini_prompt = (
            f"YouTube Shorts trendleri: '{trend_context}'. "
            "Bu trende uygun, izleyicinin dikkatini çekecek Türkçe 3 kısa başlık/sahne metni yaz. "
            "Yanıtı aralarında '---' olacak şekilde ver."
        )
        
        response = client.models.generate_content(model='gemini-3.6-flash', contents=gemini_prompt)

        if response and response.text:
            generated_prompts = [p.strip() for p in response.text.split('---') if p.strip()]
            if len(generated_prompts) >= 3:
                clean_tag = titles[0][:15].replace(' ', '').replace('#', '')
                logger.info("✅ Gemini 3.6 Flash ile trend metinleri başarıyla oluşturuldu.")
                return generated_prompts[:3], f"#shorts #trending #{clean_tag}"
    except Exception as e:
        logger.warning(f"Trend çekme hatası: {e}")
        
    return default_scenes, "#shorts #viral"

def create_local_scene_clip(text_content: str, idx: int, duration: float = 4.0) -> str:
    """Dış internet bağlantısına gerek duymadan %100 yerel 9:16 Shorts klibi oluşturur."""
    clip_path = TMP_DIR / f"local_clip_{idx}.mp4"
    logger.info(f"🎬 Yerel Klip {idx+1} oluşturuluyor: '{text_content[:20]}...'")

    # Dinamik renk paleti (Gradient hissi veren renk kombinasyonları)
    bg_colors = [(20, 20, 35), (35, 15, 25), (15, 30, 35)]
    bg_color = bg_colors[idx % len(bg_colors)]

    # 9:16 Shorts arka planı (576x1024)
    bg_clip = ColorClip(size=(576, 1024), color=bg_color, duration=duration)

    try:
        # Metin Katmanı
        txt_clip = TextClip(
            text=text_content,
            font_size=36,
            color='white',
            method='caption',
            size=(500, 400)
        ).with_duration(duration).with_position('center')

        final_scene = CompositeVideoClip([bg_clip, txt_clip])
        final_scene.write_videofile(
            str(clip_path),
            fps=24,
            codec="libx264",
            logger=None
        )
        logger.info(f"✅ Yerel Klip {idx+1} üretildi.")
        return str(clip_path)
    except Exception as e:
        logger.warning(f"Metin katmanı oluşturulamadı, sade renk kullanılıyor: {e}")
        bg_clip.write_videofile(str(clip_path), fps=24, codec="libx264", logger=None)
        return str(clip_path)

def main():
    scenes, video_title = get_live_trend_prompts()
    video_clips = []

    for idx, scene_text in enumerate(scenes):
        clip_file = create_local_scene_clip(scene_text, idx)
        if os.path.exists(clip_file):
            try:
                clip = VideoFileClip(clip_file)
                video_clips.append(clip)
            except Exception as e:
                logger.warning(f"Klip okunamadı: {e}")

    if not video_clips:
        logger.error("❌ Hiçbir video klibi oluşturulamadı. İşlem durduruluyor.")
        sys.exit(1)

    try:
        logger.info("🎬 Klipler kurgulanıyor...")
        final_video = concatenate_videoclips(video_clips, method="compose")

        output_path = OUT_DIR / "short_video.mp4"
        final_video.write_videofile(
            str(output_path), 
            fps=24, 
            codec="libx264", 
            audio_codec="aac", 
            logger=None
        )
        logger.info(f"✅ Final video başarıyla üretildi: {output_path}")

        if os.path.exists('token.json'):
            logger.info("🚀 YouTube Shorts'a yükleniyor...")
            creds = Credentials.from_authorized_user_file('token.json')
            youtube = build('youtube', 'v3', credentials=creds)

            body = {
                'snippet': {
                    'title': video_title,
                    'description': f'{video_title} #viral #shorts',
                    'categoryId': '22'
                },
                'status': {
                    'privacyStatus': 'public',
                    'selfDeclaredMadeForKids': False,
                    'containsSyntheticMedia': False
                }
            }
            media = MediaFileUpload(str(output_path), chunksize=-1, resumable=True, mimetype='video/mp4')
            youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
            logger.info("🎉 Video YouTube Shorts'a başarıyla yüklendi!")

    except Exception as e:
        logger.error(f"Kurgu/Yükleme hatası: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
