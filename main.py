import os
import sys
import time
import re
import json
import random
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
logger = logging.getLogger("real-ai-shorts")

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

if not GEMINI_API_KEY:
    logger.error("❌ GEMINI_API_KEY zorunludur!")
    sys.exit(1)

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="ai-shorts-"))


# 1. GERÇEK ZAMANLI YOUTUBE MOST POPULAR TRENDLERİNİ ÇEKME
def fetch_youtube_trends():
    logger.info("🔍 YouTube'da o an en çok izlenen GERÇEK trend videolar çekiliyor...")
    titles = []
    try:
        youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
        res = youtube.videos().list(
            chart='mostPopular',
            regionCode='US',
            maxResults=10,
            part='snippet'
        ).execute()

        for item in res.get('items', []):
            titles.append(item['snippet']['title'])
    except Exception as e:
        logger.warning(f"⚠️ YouTube API MostPopular arama uyarısı: {e}. Arama yöntemine geçiliyor...")
        try:
            youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
            res = youtube.search().list(
                q='viral trending shorts',
                type='video',
                videoDuration='short',
                order='viewCount',
                maxResults=10,
                part='snippet'
            ).execute()
            for item in res.get('items', []):
                titles.append(item['snippet']['title'])
        except Exception as err:
            logger.error(f"❌ YouTube API tamamen başarısız: {err}")

    if not titles:
        raise RuntimeError("❌ YouTube trendleri çekilemedi! Lütfen YT_API_KEY kontrol edin.")

    logger.info(f"📈 Bulunan Trend Başlıklar: {titles[:3]}")
    return titles


# 2. DİNAMİK GEMINI MODEL TESPİTİ VE SENARYO ÜRETİMİ
def generate_story_with_gemini(trends):
    logger.info("🧠 Gemini AI trendleri analiz ediyor ve %100 özgün gerçekçi senaryo üretiyor...")
    
    genai.configure(api_key=GEMINI_API_KEY)
    
    selected_model = None
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        logger.info(f"📋 Kullanılabilir Gemini Modelleri: {available_models}")
        
        for pref in ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-2.0-flash', 'gemini-1.0-pro']:
            for am in available_models:
                if pref in am:
                    selected_model = am
                    break
            if selected_model:
                break
                
        if not selected_model and available_models:
            selected_model = available_models[0]
    except Exception as e:
        logger.warning(f"Modeller listelenemedi, varsayılan deneniyor: {e}")
        selected_model = "models/gemini-1.5-flash"

    logger.info(f"🎯 Kullanılan Gemini Modeli: {selected_model}")
    model = genai.GenerativeModel(selected_model)

    prompt_instruction = f"""
    You are a professional YouTube Shorts content creator.
    Analyze these REAL trending topic titles from YouTube right now: {json.dumps(trends)}

    Pick the most interesting trend topic among them and create an engaging, realistic, factual or captivating 4-scene YouTube Shorts script.
    
    IMPORTANT:
    - NO cartoon or Pixar style.
    - Style MUST be realistic, cinematic photorealistic, and highly engaging.
    - Keep each scene's spoken sentence short and powerful (MAX 4 to 6 words).

    For each scene provide:
    1. 'text': Spoken voiceover sentence (MAX 4-6 words).
    2. 'prompt': Detailed photorealistic image prompt (Must include: cinematic lighting, 8k resolution, photorealistic photography, 35mm camera lens, 9:16 vertical ratio, highly detailed, no text on image).

    Return ONLY a valid JSON object in this exact format:
    {{
      "title": "Catchy YouTube Shorts Title with #shorts #viral #trending",
      "scenes": [
        {{"text": "Short spoken sentence 1", "prompt": "Photorealistic image prompt 1"}},
        {{"text": "Short spoken sentence 2", "prompt": "Photorealistic image prompt 2"}},
        {{"text": "Short spoken sentence 3", "prompt": "Photorealistic image prompt 3"}},
        {{"text": "Short spoken sentence 4", "prompt": "Photorealistic image prompt 4"}}
      ]
    }}
    Do NOT wrap in markdown or add extra text.
    """

    response = model.generate_content(prompt_instruction)
    raw_text = response.text.strip()
    
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if not match:
        raise ValueError(f"❌ Gemini geçerli bir JSON üretmedi. Gelen yanıt: {raw_text}")
        
    data = json.loads(match.group(0))
    
    if "scenes" not in data or len(data["scenes"]) < 4:
        raise ValueError("❌ Gemini senaryosu eksik sahneler içeriyor.")

    logger.info("✅ Gemini AI Özgün Gerçekçi Senaryoyu Başarıyla Oluşturdu!")
    return data["scenes"], data.get("title", "Viral Trend Shorts #shorts #viral")


# 3. GERÇEKÇİ FOTOĞRAF KALİTESİNDE GÖRSEL ÜRETİMİ (FLUX ENGINE)
def generate_realistic_image(prompt: str, index: int) -> str:
    output_path = TMP_DIR / f"scene_{index}.jpg"
    logger.info(f"🎨 Sahne #{index+1} Gerçekçi AI Görseli Çiziliyor...")

    encoded_p = urllib.parse.quote(prompt)
    seed = random.randint(100000, 999999)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_p}?width=1080&height=1920&model=flux&seed={seed}&nologo=true"

    response = requests.get(image_url, timeout=90)
    if response.status_code == 200:
        with open(output_path, 'wb') as f:
            f.write(response.content)
        logger.info(f"✅ Görsel Hazır: {output_path}")
        return str(output_path)
    else:
        image_url_alt = f"https://image.pollinations.ai/prompt/{encoded_p}?width=1080&height=1920&model=turbo&seed={seed}&nologo=true"
        res_alt = requests.get(image_url_alt, timeout=90)
        if res_alt.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(res_alt.content)
            return str(output_path)
        raise RuntimeError(f"❌ Görsel Motoru Yanıt Vermedi (Status: {response.status_code})")


# 4. MONTAJ VE YOUTUBE'A YÜKLEME
def main():
    trends = fetch_youtube_trends()
    scenes, video_title = generate_story_with_gemini(trends)
    video_clips = []

    for idx, scene in enumerate(scenes):
        logger.info(f"🎬 Sahne {idx+1}/{len(scenes)}: '{scene['text']}'")
        image_file = generate_realistic_image(scene["prompt"], idx)

        tts_path = TMP_DIR / f"tts_{idx}.mp3"
        gTTS(text=scene["text"], lang='en').save(str(tts_path))
        audio_clip = AudioFileClip(str(tts_path))
        
        duration = max(3.0, audio_clip.duration + 0.5)

        img_clip = ImageClip(image_file).resized((1080, 1920)).with_duration(duration)

        txt_clip = TextClip(
            text=scene["text"],
            font="DejaVuSans-Bold",
            font_size=38,
            color='yellow',
            stroke_color='black',
            stroke_width=4,
            method='caption',
            size=(920, 200)
        ).with_duration(duration).with_position(('center', 0.80), relative=True)

        composite = CompositeVideoClip([img_clip, txt_clip], size=(1080, 1920)).with_audio(audio_clip)
        video_clips.append(composite)

    logger.info("🎬 Video İşleniyor (1080x1920 Full HD)...")
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
        'snippet': {'title': video_title, 'description': f"{video_title}\n\n#shorts #viral #trending #ai"},
        'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False, 'containsSyntheticMedia': True}
    }
    media = MediaFileUpload(str(output_file), chunksize=-1, resumable=True, mimetype='video/mp4')
    
    upload_response = youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
    video_id = upload_response.get('id')
    logger.info(f"🎉 Başarıyla yüklendi! Video ID: {video_id}")

    # OTOMATİK BEĞENİ VE YORUM (BEKLEME SÜRESİ EKLENDİ)
    if video_id:
        logger.info("⏳ Videonun YouTube sunucularında tam aktifleşmesi için 15 saniye bekleniyor...")
        time.sleep(15)

        try:
            youtube.videos().rate(id=video_id, rating='like').execute()
            logger.info("👍 Video otomatik beğenildi!")
        except Exception as e:
            logger.warning(f"⚠️ Beğeni hatası (Token yetkisini kontrol edin): {e}")

        try:
            comment_body = {
                'snippet': {
                    'videoId': video_id,
                    'topLevelComment': {
                        'snippet': {
                            'textOriginal': 'Subscribe and hit the bell for daily viral shorts! 🔔'
                        }
                    }
                }
            }
            youtube.commentThreads().insert(part='snippet', body=comment_body).execute()
            logger.info("💬 Otomatik yorum sabitlendi!")
        except Exception as e:
            logger.warning(f"⚠️ Yorum hatası (Token yetkisini kontrol edin): {e}")


if __name__ == "__main__":
    main()
