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
logger = logging.getLogger("pure-dynamic-auto")

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


# 1. DİNAMİK TREND TRACKER & PROMPT LOADER (%100 CANLI VERİ)
def analyze_and_build_dynamic_content():
    logger.info("🔥 Live YouTube Shorts Trend Tracker çalıştırılıyor...")
    extracted_titles = []
    
    try:
        youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
        res = youtube.search().list(
            q='viral shorts challenge trending',
            type='video',
            videoDuration='short',
            order='viewCount',
            maxResults=5,
            part='snippet'
        ).execute()
        
        for item in res.get('items', []):
            raw_title = item['snippet']['title']
            clean_title = re.sub(r'[^\w\s]', '', raw_title)
            if clean_title.strip():
                extracted_titles.append(clean_title.strip())
    except Exception as e:
        logger.warning(f"⚠️ YouTube API uyarısı: {e}")

    # Trend verisi yoksa dinamik güvenlik kelimeleri oluştur
    main_topic = extracted_titles[0] if extracted_titles else "Viral Action Stunt"
    words = [w.upper() for w in main_topic.split() if len(w) > 3 and w.lower() not in ['shorts', 'video', 'http', 'https', 'with']]
    
    # Ekran yazılarını ve promptları canlı trend kelimelerinden üret
    w1 = words[0] if len(words) > 0 else "TRENDING"
    w2 = words[1] if len(words) > 1 else "VIRAL"
    w3 = words[2] if len(words) > 2 else "MUST SEE"

    final_video_title = f"{main_topic[:50]} #shorts #viral #trending"

    # HİÇBİR SABİT METİN YOK: Promptlar ve yazılar trend verisinden türetilir
    scenes = [
        {
            "prompt": f"Cinematic photorealistic 8k movie scene of {main_topic}, highly detailed dynamic action",
            "text": f"{w1} {w2}"
        },
        {
            "prompt": f"Hyper-realistic slow motion video of {w1} {w2} challenge, 4k resolution cinematic lighting",
            "text": f"WAIT FOR {w3}"
        },
        {
            "prompt": f"Photorealistic dynamic close up shot of {w2} {w3} viral moment, action shot",
            "text": f"UNBELIEVABLE {w1}"
        }
    ]

    logger.info(f"📌 Dinamik YouTube Başlığı: '{final_video_title}'")
    for i, s in enumerate(scenes):
        logger.info(f"🎬 Sahne {i+1} Metni: '{s['text']}' | Prompt: '{s['prompt'][:40]}...'")

    return scenes, final_video_title


# 2. HUGGING FACE PUBLIC GPU QUEUE (SIRADA BEKLEME MOTORU)
def render_video_strict_queue(prompt: str) -> str:
    logger.info(f"⚡ HF Public Video GPU alanına bağlanılıyor: '{prompt[:35]}...'")
    
    public_spaces = [
        "cjwbw/damo-vilab-text-to-video-synthesis",
        "artificialguybr/Text-To-Video-Alpha",
        "aipicasso/Text2Video-Zero"
    ]

    for space in public_spaces:
        try:
            logger.info(f"⏳ [{space}] alanında sıra bekleniyor...")
            client = Client(space, verbose=False)
            
            job = client.submit(
                prompt,
                api_name="/predict"
            )

            queue_timer = 0
            while not job.done():
                time.sleep(15)
                queue_timer += 15
                if queue_timer % 30 == 0:
                    logger.info(f"⏳ [{space}] Sıra bekleniyor... ({queue_timer} sn geçti)")

            result = job.result()
            video_path = result if isinstance(result, str) else result[0]
            
            if str(video_path).lower().endswith(('.mp4', '.avi', '.mov', '.webm')):
                logger.info(f"✅ [{space}] AI Video başarıyla üretildi: {video_path}")
                return video_path

        except Exception as e:
            logger.warning(f"⚠️ [{space}] meşgul veya sıra verilemedi: {e}")
            continue

    raise RuntimeError("❌ Kamuya açık Hugging Face video alanları sıra vermedi.")


# 3. OTOMATİK MONTAJ, SHORTS YÜKLEME VE AUTO-LIKE
def main():
    scenes, video_title = analyze_and_build_dynamic_content()
    video_clips = []

    for idx, scene in enumerate(scenes):
        logger.info(f"🎬 Sahne {idx+1}/{len(scenes)} işleniyor...")
        video_file_path = render_video_strict_queue(scene["prompt"])
        
        clip = VideoFileClip(video_file_path)
            
        # 🎬 9:16 VERTICAL CROP
        clip_resized = clip.resized(height=1920)
        vertical_clip = clip_resized.cropped(x_center=clip_resized.w / 2, width=1080)

        # 📝 DYNAMIC TEXT OVERLAY
        txt_clip = TextClip(
            text=scene["text"],
            font_size=50,
            color='yellow',
            stroke_color='black',
            stroke_width=3,
            method='caption',
            size=(900, 300)
        ).with_duration(vertical_clip.duration).with_position(('center', 0.70), relative=True)

        # 🔊 DYNAMIC TTS AUDIO
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
        logger.info("🎬 Video klipler birleştiriliyor...")
        final_video = concatenate_videoclips(video_clips, method="compose")
        output_file = OUT_DIR / "short_video.mp4"
        final_video.write_videofile(str(output_file), fps=24, codec="libx264", audio_codec="aac", logger=None)
        logger.info(f"✅ Final video kaydedildi: {output_file}")

        # 🚀 YOUTUBE SHORTS UPLOAD & AUTO-LIKE
        if not os.path.exists('token.json'):
            logger.error("❌ 'token.json' bulunamadı! Yükleme atlandı.")
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
