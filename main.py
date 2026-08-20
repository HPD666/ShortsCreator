import os
import sys
import time
import re
import logging
import tempfile
import requests
import warnings
from pathlib import Path

# Stream logs live in GitHub Actions
sys.stdout.reconfigure(line_buffering=True)

# Suppress HTTP and SDK noise
warnings.filterwarnings("ignore")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

from gradio_client import Client
from gtts import gTTS
from moviepy import (
    VideoFileClip,
    AudioFileClip,
    TextClip,
    CompositeVideoClip,
    concatenate_videoclips
)
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', force=True)
logger = logging.getLogger("pure-video-queue")

# YouTube API Credentials
YT_API_KEY = os.environ.get("YT_API_KEY")

if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    try:
        with open('token.json', 'w') as f:
            f.write(os.environ['TOKEN_JSON'])
    except Exception as e:
        logger.warning(f"token.json yazılamadı: {e}")

if not YT_API_KEY:
    logger.error("❌ YT_API_KEY zorunludur!")
    sys.exit(1)

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="video-auto-t2v-"))


# 1. LIVE YOUTUBE TREND EXTRACTION
def analyze_live_trends():
    logger.info("🔥 Live YouTube Shorts trends fetching...")
    extracted_keywords = []
    
    try:
        youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
        res = youtube.search().list(
            q='viral shorts trending action challenge',
            type='video',
            videoDuration='short',
            order='viewCount',
            maxResults=5,
            part='snippet'
        ).execute()
        
        for item in res.get('items', []):
            raw_title = item['snippet']['title']
            clean_title = re.sub(r'[^\w\s]', '', raw_title)
            words = [w for w in clean_title.split() if len(w) > 3 and w.lower() not in ['shorts', 'video', 'http', 'https', 'with']]
            extracted_keywords.extend(words)
    except Exception as e:
        logger.warning(f"⚠️ YouTube API warning: {e}")

    unique_words = list(dict.fromkeys(extracted_keywords))[:4]
    trend_phrase = " ".join(unique_words).title() if unique_words else "Epic Extreme Action"
    final_video_title = f"{trend_phrase} Trend #trend #viral #shorts"

    scenes = [
        {
            "prompt": "Cinematic photorealistic dynamic action shot of a real person performing an extreme stunt, 8k movie scene",
            "text": "EPIC ACTION"
        },
        {
            "prompt": "Hyper-realistic slow motion video of a professional athlete completing a viral challenge, 4k resolution",
            "text": "UNREAL SKILL"
        },
        {
            "prompt": "Photorealistic 8k dynamic close up shot of a person high-energy challenge action, cinematic lighting",
            "text": "MUST WATCH"
        }
    ]

    logger.info(f"📌 Generated Title: '{final_video_title}'")
    return scenes, final_video_title


# 2. SADECE GERÇEK VIDEO ÜRETEN SIRA BEKLEMELİ HF MOTORU
def render_video_strict_queue(prompt: str) -> str:
    logger.info(f"⚡ HF Public Video GPU alanına bağlanılıyor: '{prompt[:35]}...'")
    
    # Herkese açık Text-To-Video Gradio alanları
    public_spaces = [
        "fffiloni/LTX-Video",
        "KingNish/LTX-Video",
        "ali-vilab/modelscope-text-to-video-synthesis"
    ]

    for space in public_spaces:
        try:
            logger.info(f"⏳ [{space}] alanına bağlanılıyor ve sıra alınıyor...")
            client = Client(space, verbose=False)
            
            # Kuyruğa isteği bırak
            job = client.submit(
                prompt=prompt,
                negative_prompt="worst quality, low quality, blurry, deformed, static, image",
                api_name="/generate_video" if "LTX" in space else "/predict"
            )

            queue_timer = 0
            while not job.done():
                time.sleep(15)
                queue_timer += 15
                if queue_timer % 30 == 0:
                    logger.info(f"⏳ [{space}] Sunucu kuyruğu bekleniyor... ({queue_timer} saniye geçti)")

            result = job.result()
            video_path = result if isinstance(result, str) else result[0]
            
            # Üretilen dosyanın video formatında olduğundan emin ol
            if str(video_path).lower().endswith(('.mp4', '.avi', '.mov', '.webm')):
                logger.info(f"✅ [{space}] Gerçek AI video üretimi tamamlandı: {video_path}")
                return video_path
            else:
                logger.warning(f"⚠️ [{space}] Video yerine farklı format döndürdü, sonraki alana geçiliyor.")

        except Exception as e:
            logger.warning(f"⚠️ [{space}] alanında sıra beklenirken hata/meşguliyet: {e}")
            continue

    raise RuntimeError("❌ Tüm Hugging Face video alanları meşguldü veya sıra verilmedi. Video üretilemedi.")


# 3. NİHAİ MONTAJ, YÜKLEME VE AUTO-LIKE
def main():
    scenes, video_title = analyze_live_trends()
    video_clips = []

    for idx, scene in enumerate(scenes):
        logger.info(f"🎬 Sahne {idx+1}/{len(scenes)} işleniyor...")
        video_file_path = render_video_strict_queue(scene["prompt"])
        
        # Sadece gerçek video klip yüklenir
        clip = VideoFileClip(video_file_path)
            
        # 🎬 9:16 VERTICAL CROP
        clip_resized = clip.resized(height=1920)
        vertical_clip = clip_resized.cropped(x_center=clip_resized.w / 2, width=1080)

        # 📝 TEXT OVERLAY
        txt_clip = TextClip(
            text=scene["text"],
            font_size=55,
            color='yellow',
            stroke_color='black',
            stroke_width=3,
            method='caption',
            size=(900, 300)
        ).with_duration(vertical_clip.duration).with_position(('center', 0.70), relative=True)

        # 🔊 TTS AUDIO
        tts_path = TMP_DIR / f"tts_{idx}.mp3"
        gTTS(text=scene["text"], lang='en').save(str(tts_path))
        audio_clip = AudioFileClip(str(tts_path))
        if audio_clip.duration > vertical_clip.duration:
            audio_clip = audio_clip.subclipped(0, vertical_clip.duration)

        composite = CompositeVideoClip([vertical_clip, txt_clip]).with_audio(audio_clip)
        video_clips.append(composite)

    if not video_clips:
        logger.error("❌ Hiçbir video işlenemedi.")
        sys.exit(1)

    try:
        logger.info("🎬 Video klips birleştiriliyor...")
        final_video = concatenate_videoclips(video_clips, method="compose")
        output_file = OUT_DIR / "short_video.mp4"
        final_video.write_videofile(str(output_file), fps=24, codec="libx264", audio_codec="aac", logger=None)
        logger.info(f"✅ Final video kaydedildi: {output_file}")

        # 🚀 YOUTUBE SHORTS UPLOAD & AUTO-LIKE
        if not os.path.exists('token.json'):
            logger.error("❌ 'token.json' bulunamadı! Yükleme yapılamıyor.")
            sys.exit(1)

        logger.info("🚀 YouTube Shorts'a yükleniyor...")
        creds = Credentials.from_authorized_user_file('token.json')
        youtube = build('youtube', 'v3', credentials=creds)

        body = {
            'snippet': {
                'title': video_title,
                'description': f'{video_title}',
                'categoryId': '22'
            },
            'status': {
                'privacyStatus': 'public',
                'selfDeclaredMadeForKids': False,
                'containsSyntheticMedia': True
            }
        }
        media = MediaFileUpload(str(output_file), chunksize=-1, resumable=True, mimetype='video/mp4')
        
        upload_response = youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
        video_id = upload_response.get('id')
        logger.info(f"🎉 Başarıyla yüklendi! Video ID: {video_id}")

        # AUTO-LIKE
        if video_id:
            try:
                youtube.videos().rate(id=video_id, rating='like').execute()
                logger.info("👍 Otomatik beğenildi (Auto-liked)!")
            except Exception as like_error:
                logger.warning(f"⚠️ Auto-like adımı atlandı: {like_error}")

    except Exception as e:
        logger.error(f"Render/Upload Hatası: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
