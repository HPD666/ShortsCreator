import os
import sys
import time
import re
import logging
import tempfile
import requests
import warnings
from pathlib import Path

# Stream logs continuously in GitHub Actions
sys.stdout.reconfigure(line_buffering=True)

# Suppress unnecessary SDK warnings
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
logger = logging.getLogger("zero-cost-full-auto")

# Credentials & Tokens Check
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
TMP_DIR = Path(tempfile.mkdtemp(prefix="free-auto-t2v-"))


# 1. CANLI YOUTUBE TREND ANALİZİ
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
        logger.warning(f"⚠️ YouTube API uyarısı: {e}")

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


# 2. ÜCRETSİZ HUGGING FACE GPU (KUYRUK DESTEKLİ)
def render_video_free_queue(prompt: str) -> str:
    logger.info(f"⚡ Hugging Face GPU kuyruğuna giriliyor: '{prompt[:35]}...'")
    
    # 0$ LTX Video Hugging Face Alanı
    space_name = "Lightricks/LTX-Video-Demo"
    
    try:
        client = Client(space_name, verbose=False)
        
        # Submit ile istek atıp kuyruğu sabırla bekler
        job = client.submit(
            prompt=prompt,
            negative_prompt="worst quality, low quality, anime, cartoon, deformed, blurry",
            height=480,
            width=704,
            num_frames=121,
            frame_rate=25,
            api_name="/generate_video_1"
        )
        
        logger.info("⏳ Hugging Face ücretsiz sunucu kuyruğu bekleniyor (Bu işlem birkaç dakika sürebilir)...")
        
        while not job.done():
            time.sleep(10)
            
        result = job.result()
        video_path = result if isinstance(result, str) else result[0]
        logger.info("✅ Hugging Face kuyruğundan video başarıyla çekildi!")
        return video_path

    except Exception as e:
        logger.warning(f"⚠️ HF Space yoğun veya yanıt vermedi, ücretsiz Pollinations motoruna geçiliyor: {e}")
        # Ücretsiz fallback görsel-video akışı
        url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}?width=704&height=480&model=flux"
        img_data = requests.get(url).content
        tmp_img = TMP_DIR / f"fallback_{time.time()}.jpg"
        with open(tmp_img, "wb") as f:
            f.write(img_data)
        return str(tmp_img)


# 3. NİHAİ MONTAJ, YÜKLEME VE OTOMATİK BEĞENİ
def main():
    scenes, video_title = analyze_live_trends()
    video_clips = []

    for idx, scene in enumerate(scenes):
        logger.info(f"🎬 Processing Clip {idx+1}/{len(scenes)}...")
        generated_file = render_video_free_queue(scene["prompt"])
        
        if generated_file.endswith(".jpg"):
            from moviepy import ImageClip
            clip = ImageClip(generated_file).with_duration(3.0)
        else:
            clip = VideoFileClip(generated_file)
            
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
        logger.error("❌ Hiçbir video klibi işlenemedi.")
        sys.exit(1)

    try:
        logger.info("🎬 Stitching video clips & finalizing MP4...")
        final_video = concatenate_videoclips(video_clips, method="compose")
        output_file = OUT_DIR / "short_video.mp4"
        final_video.write_videofile(str(output_file), fps=24, codec="libx264", audio_codec="aac", logger=None)
        logger.info(f"✅ Final video saved: {output_file}")

        # 🚀 YOUTUBE SHORTS UPLOAD & AUTOMATIC LIKE
        if os.path.exists('token.json'):
            logger.info("🚀 Uploading to YouTube Shorts...")
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
            logger.info(f"🎉 Successfully uploaded! Video ID: {video_id}")

            # AUTOMATIC LIKE
            if video_id:
                try:
                    youtube.videos().rate(id=video_id, rating='like').execute()
                    logger.info("👍 Auto-liked successfully!")
                except Exception as like_error:
                    logger.warning(f"⚠️ Auto-like skipped: {like_error}")

    except Exception as e:
        logger.error(f"Render/Upload Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
