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

from gtts import gTTS
from moviepy import (
    ImageClip,
    TextClip,
    AudioFileClip,
    CompositeVideoClip,
    concatenate_videoclips
)
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

import google.generativeai as genai

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', force=True)
logger = logging.getLogger("3d-ai-comic-shorts")

YT_API_KEY = os.environ.get("YT_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

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
TMP_DIR = Path(tempfile.mkdtemp(prefix="3d-ai-"))


# 1. YOUTUBE TRENDLERİNİ ÇEKME
def fetch_youtube_trends():
    logger.info("🔍 Güncel YouTube trend içerikleri çekiliyor...")
    titles = []
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
            titles.append(item['snippet']['title'])
    except Exception as e:
        logger.warning(f"⚠️ YouTube API okuma uyarısı: {e}")

    return titles if titles else ["Mystery Box Challenge", "5 Dollar Challenge", "Futuristic Gadgets"]


# 2. GEMINI AI İLE SINIRSIZ & DİNAMİK HİKAYE VE PROMPT ÜRETİMİ
def generate_story_with_gemini(trends):
    logger.info("🧠 Gemini AI trendleri insan gibi analiz edip dinamik senaryo yazıyor...")
    
    prompt_instruction = f"""
    You are a viral YouTube Shorts scriptwriter and 3D animator.
    Analyze these trending topic titles: {json.dumps(trends)}

    Create a funny, surprising, 4-scene comic-book style story based on the most viral idea among these trends.
    For each scene:
    1. 'text': A very short spoken sentence for voiceover (MAX 3 to 5 words per scene).
    2. 'prompt': A detailed 3D Pixar / Unreal Engine 5 animation prompt describing EXACTLY what is happening in 'text'. (Include parameters: 3D Pixar style, 8k render, vibrant lighting, highly detailed, no text on picture).

    Return ONLY a valid JSON object with this structure:
    {{
      "title": "A catchy YouTube Shorts title with hashtags",
      "scenes": [
        {{"text": "Short spoken sentence", "prompt": "Detailed 3D prompt matching the text"}},
        {{"text": "Short spoken sentence", "prompt": "Detailed 3D prompt matching the text"}},
        {{"text": "Short spoken sentence", "prompt": "Detailed 3D prompt matching the text"}},
        {{"text": "Short spoken sentence", "prompt": "Detailed 3D prompt matching the text"}}
      ]
    }}
    Do not add any Markdown code blocks or extra explanations, output raw JSON only.
    """

    data = None

    if GEMINI_API_KEY:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt_instruction)
            raw_text = response.text.strip()
            raw_text = re.sub(r'```json\s*', '', raw_text)
            raw_text = re.sub(r'```\s*', '', raw_text)
            data = json.loads(raw_text)
            logger.info("✅ Gemini AI Senaryoyu Başarıyla Oluşturdu!")
        except Exception as e:
            logger.warning(f"⚠️ Gemini API hatası, yedek yapay zekaya geçiliyor: {e}")

    if not data or "scenes" not in data:
        # YEDEK YAPAY ZEKA (Pollinations Free LLM)
        try:
            url = "https://text.pollinations.ai/"
            res = requests.post(url, json={"messages": [{"role": "user", "content": prompt_instruction}], "model": "openai"}, timeout=30)
            raw_text = res.text.strip()
            raw_text = re.sub(r'```json\s*', '', raw_text)
            raw_text = re.sub(r'```\s*', '', raw_text)
            data = json.loads(raw_text)
            logger.info("✅ Yedek AI Senaryoyu Başarıyla Oluşturdu!")
        except Exception as e:
            logger.warning(f"⚠️ Yedek AI yanıt veremedi veya geçersiz JSON döndürdü: {e}")

    if not data or "scenes" not in data:
        logger.info("🔄 Varsayılan güvenli 3D senaryosu devreye giriyor...")
        data = {
            "title": "Unbelievable 3D Story! 😱 #shorts #3d #viral",
            "scenes": [
                {"text": "He found a mystery box.", "prompt": "3D Pixar character holding a glowing mystery box, highly detailed 3D Pixar style, 8k render, no text"},
                {"text": "Inside was pure magic!", "prompt": "3D Pixar character looking amazed inside a glowing box with magical particles, vibrant lighting, no text"},
                {"text": "It granted one wish.", "prompt": "3D Pixar character floating with golden magical energy around, epic lighting, no text"},
                {"text": "The best day ever!", "prompt": "3D Pixar character celebrating happily outdoors, 3D animated style, 8k render, no text"}
            ]
        }

    return data["scenes"], data.get("title", "Epic 3D Shorts #shorts #viral")


# 3. 3D SAHNE GÖRSELİ ÜRETME (POLLINATIONS)
def generate_3d_image(prompt: str, index: int) -> str:
    output_path = TMP_DIR / f"3d_scene_{index}.jpg"
    logger.info(f"🎨 Sahne #{index+1} AI Promptu Çiziliyor...")

    encoded_p = urllib.parse.quote(prompt)
    seed = int(time.time()) + (index * 17)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_p}?width=1080&height=1920&model=turbo&seed={seed}&nologo=true"

    response = requests.get(image_url, timeout=90)
    if response.status_code == 200:
        with open(output_path, 'wb') as f:
            f.write(response.content)
        logger.info(f"✅ 3D Sahne Çizildi: {output_path}")
        return str(output_path)
    else:
        raise RuntimeError(f"❌ Görsel Motoru Yanıt Vermedi (Status: {response.status_code})")


# 4. SES, ALTYAZI VE VİDEO KURGUSU
def main():
    trends = fetch_youtube_trends()
    scenes, video_title = generate_story_with_gemini(trends)
    video_clips = []

    for idx, scene in enumerate(scenes):
        logger.info(f"🎬 Sahne {idx+1}/{len(scenes)}: '{scene['text']}'")
        image_file = generate_3d_image(scene["prompt"], idx)

        # Metin Seslendirme (gTTS)
        tts_path = TMP_DIR / f"tts_{idx}.mp3"
        gTTS(text=scene["text"], lang='en').save(str(tts_path))
        audio_clip = AudioFileClip(str(tts_path))
        
        duration = max(3.0, audio_clip.duration + 0.5)

        # Görsel Katmanı
        img_clip = ImageClip(image_file).with_duration(duration)

        # Ubuntu ortamında garanti çalışan DejaVuSans-Bold fontu
        txt_clip = TextClip(
            text=scene["text"],
            font="DejaVuSans-Bold",
            font_size=60,
            color='yellow',
            stroke_color='black',
            stroke_width=5,
            method='caption',
            size=(950, 250)
        ).with_duration(duration).with_position(('center', 0.78), relative=True)

        composite = CompositeVideoClip([img_clip, txt_clip]).with_audio(audio_clip)
        video_clips.append(composite)

    logger.info("🎬 Yapay Zeka Videosu İşleniyor...")
    final_video = concatenate_videoclips(video_clips, method="compose")
    output_file = OUT_DIR / "short_video.mp4"
    final_video.write_videofile(str(output_file), fps=24, codec="libx264", audio_codec="aac", logger=None)

    if not os.path.exists('token.json'):
        logger.error("❌ 'token.json' bulunamadı.")
        sys.exit(1)

    logger.info("🚀 YouTube Shorts'a Yükleniyor...")
    creds = Credentials.from_authorized_user_file('token.json')
    youtube = build('youtube', 'v3', credentials=creds)

    body = {
        'snippet': {'title': video_title, 'description': f"{video_title}\n\n#shorts #3d #ai #animation #viral"},
        'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False, 'containsSyntheticMedia': True}
    }
    media = MediaFileUpload(str(output_file), chunksize=-1, resumable=True, mimetype='video/mp4')
    
    upload_response = youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
    video_id = upload_response.get('id')
    logger.info(f"🎉 Başarıyla yüklendi! Video ID: {video_id}")

    # OTOMATİK LİKE VE YORUM
    if video_id:
        try:
            youtube.videos().rate(id=video_id, rating='like').execute()
            logger.info("👍 Video otomatik beğenildi!")
        except Exception as e:
            logger.warning(f"⚠️ Beğeni uyarısı: {e}")

        try:
            comment_body = {
                'snippet': {
                    'videoId': video_id,
                    'topLevelComment': {
                        'snippet': {
                            'textOriginal': 'Subscribe and drop a comment for Part 2! 🔔'
                        }
                    }
                }
            }
            youtube.commentThreads().insert(part='snippet', body=comment_body).execute()
            logger.info("💬 Otomatik yorum sabitlendi!")
        except Exception as e:
            logger.warning(f"⚠️ Yorum uyarısı: {e}")


if __name__ == "__main__":
    main()
