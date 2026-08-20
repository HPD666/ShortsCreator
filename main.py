import os
import sys
import time
import re
import json
import logging
import tempfile
import requests
import warnings
import urllib.parse
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
warnings.filterwarnings("ignore")

from moviepy import (
    ImageClip,
    concatenate_videoclips
)
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', force=True)
logger = logging.getLogger("3d-pure-no-text")

YT_API_KEY = os.environ.get("YT_API_KEY")

if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    try:
        with open('token.json', 'w') as f:
            f.write(os.environ['TOKEN_JSON'])
    except Exception as e:
        logger.warning(f"token.json okunamadı: {e}")

if not YT_API_KEY:
    logger.error("❌ YT_API_KEY zorunludur!")
    sys.exit(1)

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="3d-pure-"))


# 1. TREND ANALİZİ VE YAZISIZ PROMPT
def extract_clean_context():
    logger.info("🔍 YouTube trend içerikleri analiz ediliyor...")
    words, titles = [], []

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

        forbidden = {'shorts', 'video', 'youtube', 'http', 'https', 'subscribe', 'channel'}

        for item in res.get('items', []):
            t = item['snippet']['title']
            d = item['snippet'].get('description', '')
            titles.append(t)
            clean = re.sub(r'[^\w\s]', '', f"{t} {d}")
            for w in clean.split():
                if len(w) > 3 and w.lower() not in forbidden:
                    words.append(w)

    except Exception as e:
        logger.warning(f"⚠️ YouTube API okuma uyarısı: {e}")

    unique_words = list(dict.fromkeys(words))
    main_subject = " ".join(unique_words[:3]) if unique_words else "3D Animated World"

    style_suffix = "3D Pixar Unreal Engine 5 render, highly detailed 3D animation style, vibrant lighting, smooth digital art, 8k resolution, no text, no visual words, no watermark"

    scenes = [
        {"prompt": f"3D animation clip of {main_subject}, {style_suffix}"},
        {"prompt": f"Action 3D scene focusing on {main_subject}, dynamic angles, {style_suffix}"},
        {"prompt": f"Full 3D animated cinematic output of {main_subject}, {style_suffix}"}
    ]

    final_title = f"3D {titles[0][:45]} #shorts #3d #viral" if titles else f"3D {main_subject} #shorts"
    return scenes, final_title


# 2. BULUT ÜZERİNDEN SAF 3D GÖRSEL İNDİRME
def generate_3d_image(prompt: str, index: int) -> str:
    output_path = TMP_DIR / f"3d_scene_{index}.jpg"
    logger.info(f"⚡ 3D Sahne Görseli İndiriliyor... Sahne #{index+1}")

    encoded_p = urllib.parse.quote(prompt)
    seed = int(time.time()) + index
    image_url = f"https://image.pollinations.ai/prompt/{encoded_p}?width=1080&height=1920&model=turbo&seed={seed}&nologo=true"

    response = requests.get(image_url, timeout=90)
    if response.status_code == 200:
        with open(output_path, 'wb') as f:
            f.write(response.content)
        logger.info(f"✅ 3D Sahne İndirildi: {output_path}")
        return str(output_path)
    else:
        raise RuntimeError(f"❌ 3D Motor Yanıt Vermedi (Status: {response.status_code})")


# 3. YAZISIZ VİDEO OLUŞTURMA VE YÜKLEME
def main():
    scenes, video_title = extract_clean_context()
    video_clips = []

    for idx, scene in enumerate(scenes):
        logger.info(f"🎬 Sahne {idx+1}/{len(scenes)} işleniyor...")
        image_file = generate_3d_image(scene["prompt"], idx)

        # Görseli 4 Saniyelik Video Katmanına Dönüştür
        clip = ImageClip(image_file).with_duration(4)
        video_clips.append(clip)

    logger.info("🎬 Saf 3D Sahneler Birleştiriliyor...")
    final_video = concatenate_videoclips(video_clips, method="compose")
    output_file = OUT_DIR / "short_video.mp4"
    
    # Videoyu Ses Olmadan Temiz İşle
    final_video.write_videofile(str(output_file), fps=24, codec="libx264", logger=None)

    if not os.path.exists('token.json'):
        logger.error("❌ 'token.json' bulunamadı.")
        sys.exit(1)

    logger.info("🚀 YouTube Shorts'a Yükleniyor...")
    creds = Credentials.from_authorized_user_file('token.json')
    youtube = build('youtube', 'v3', credentials=creds)

    body = {
        'snippet': {'title': video_title, 'description': video_title, 'categoryId': '1'},
        'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False, 'containsSyntheticMedia': True}
    }
    media = MediaFileUpload(str(output_file), chunksize=-1, resumable=True, mimetype='video/mp4')
    
    upload_response = youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
    video_id = upload_response.get('id')
    logger.info(f"🎉 Başarıyla yüklendi! Video ID: {video_id}")

    # OTOMATİK BEĞENİ
    if video_id:
        try:
            youtube.videos().rate(id=video_id, rating='like').execute()
            logger.info("👍 Video otomatik beğenildi!")
        except Exception as e:
            logger.warning(f"⚠️ Beğeni uyarısı: {e}")

        # OTOMATİK YORUM
        try:
            comment_body = {
                'snippet': {
                    'videoId': video_id,
                    'topLevelComment': {
                        'snippet': {
                            'textOriginal': 'Subscribe for more daily 3D shorts! 🔔'
                        }
                    }
                }
            }
            youtube.commentThreads().insert(part='snippet', body=comment_body).execute()
            logger.info("💬 Otomatik yorum eklendi!")
        except Exception as e:
            logger.warning(f"⚠️ Yorum uyarısı: {e}")


if __name__ == "__main__":
    main()
