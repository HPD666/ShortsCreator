import os
import sys
import time
import re
import json
import logging
import tempfile
import requests
import warnings
import numpy as np
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
warnings.filterwarnings("ignore")

from gradio_client import Client
from gtts import gTTS
from moviepy import (
    VideoFileClip,
    TextClip,
    AudioFileClip,
    CompositeVideoClip,
    ColorClip,
    concatenate_videoclips
)
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload
import google.generativeai as genai

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', force=True)
logger = logging.getLogger("trend-viral-bot")

YT_API_KEY = os.environ.get("YT_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    try:
        with open('token.json', 'w') as f:
            f.write(os.environ['TOKEN_JSON'])
        logger.info("🔑 token.json hazırlandı.")
    except Exception as e:
        logger.warning(f"⚠️ token.json uyarısı: {e}")

if not YT_API_KEY or not GEMINI_API_KEY:
    logger.error("❌ YT_API_KEY ve GEMINI_API_KEY zorunludur!")
    sys.exit(1)

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="trend-viral-shorts-"))


# 1. TREND VİDEO VERİLERİNİ ÇEKME
def extract_trend_video_data():
    logger.info("🔍 Trend videolar taranıyor...")
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
    youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
    
    extracted_sentences = []
    all_non_hashtag_words = []

    try:
        res = youtube.search().list(
            q='#shorts #trend #viral',
            type='video',
            videoDuration='short',
            publishedAfter=seven_days_ago,
            order='viewCount',
            maxResults=10,
            part='snippet'
        ).execute()
        
        for item in res.get('items', []):
            snippet = item.get('snippet', {})
            screen_text = snippet.get('title', '')
            screen_words = [w for w in screen_text.split() if not w.startswith('#')]
            description = snippet.get('description', '')
            desc_words = [w for w in description.split() if not w.startswith('#')]
            all_non_hashtag_words.extend(desc_words)
            extracted_sentences.append(f"Ekran: {' '.join(screen_words)} | Açıklama: {' '.join(desc_words)}")
    except Exception as e:
        logger.warning(f"⚠️ Trend arama uyarısı: {e}")

    return extracted_sentences, all_non_hashtag_words


# 2. YEDEK KOD SENARYOSU
def programmatic_fallback_engine(all_words):
    logger.info("⚡ YEDEK PROGRAM DEVREDE: Kod senaryosu oluşturuluyor...")
    clean_words = [re.sub(r'[^\w\s]', '', w) for w in all_words if len(w) > 2]
    if len(clean_words) < 16:
        clean_words = ["viral", "trending", "amazing", "watch", "this", "moment", "incredible", "secret", "mindblowing", "today", "popular", "shorts", "video", "content", "best", "trend"]

    chunk_size = max(3, len(clean_words) // 4)
    scenes = [
        {"text": " ".join(clean_words[0:chunk_size])[:30], "prompt": f"cinematic video of {clean_words[0]}, 8k"},
        {"text": " ".join(clean_words[chunk_size:chunk_size*2])[:30], "prompt": f"action video of {clean_words[1]}, 8k"},
        {"text": " ".join(clean_words[chunk_size*2:chunk_size*3])[:30], "prompt": f"aesthetic video of {clean_words[2]}, 8k"},
        {"text": " ".join(clean_words[chunk_size*3:chunk_size*4])[:30], "prompt": f"epic climax video of {clean_words[3]}, 8k"}
    ]
    title = f"{clean_words[0].capitalize()} {clean_words[1].capitalize()} #trend #viral"
    return scenes, title


# 3. GEMINI AI METİN ÜRETİCİ (GÜNCEL MODEL İSİMLERİ)
def call_gemini_smart(prompt_instruction):
    genai.configure(api_key=GEMINI_API_KEY)
    
    # Standart ve çalışan güncel model isimleri
    candidate_models = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"]

    for m_name in candidate_models:
        try:
            logger.info(f"🧠 Gemini deneniyor: {m_name}")
            model = genai.GenerativeModel(m_name)
            res = model.generate_content(prompt_instruction)
            if res and res.text:
                return res.text
        except Exception as e:
            logger.warning(f"⚠️ Gemini model uyarısı ({m_name}): {e}")

    raise RuntimeError("Gemini modelleri yanıt vermedi.")


# 4. SENARYO OLUŞTURUCU
def generate_story(extracted_sentences, all_words):
    logger.info("🧠 AI ile senaryo oluşturuluyor...")
    prompt_instruction = f"""
    You are an AI video producer. Trending inputs: {json.dumps(extracted_sentences[:5])}
    Create a 4-scene viral script.
    - Sentence in each scene: 4 to 6 words max.
    - Prompts must describe dynamic moving 8k vertical 9:16 text-to-video scenes.
    - Title MUST ONLY use hashtags #trend #viral.

    Return ONLY a JSON:
    {{
      "title": "Title #trend #viral",
      "scenes": [
        {{"text": "Short spoken sentence 1", "prompt": "Cinematic text-to-video scene 1"}},
        {{"text": "Short spoken sentence 2", "prompt": "Cinematic text-to-video scene 2"}},
        {{"text": "Short spoken sentence 3", "prompt": "Cinematic text-to-video scene 3"}},
        {{"text": "Short spoken sentence 4", "prompt": "Cinematic text-to-video scene 4"}}
      ]
    }}
    """
    try:
        response_text = call_gemini_smart(prompt_instruction)
        match = re.search(r'\{.*\}', response_text.strip(), re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            return data["scenes"], data.get("title", "Trending Shorts #trend #viral")
        raise ValueError("Geçersiz JSON")
    except Exception as e:
        logger.warning(f"⚠️ AI senaryo hatası ({e}). Yedek kod devreye girdi.")
        return programmatic_fallback_engine(all_words)


# 5. DOSYA VE VİDEO DOĞRULAMA MEKANİZMASI
def is_valid_video_file(filepath: str) -> bool:
    if not os.path.exists(filepath) or os.path.getsize(filepath) < 100000:
        return False
    try:
        clip = VideoFileClip(filepath)
        valid = clip.duration is not None and clip.duration > 0
        clip.close()
        return valid
    except Exception:
        return False


# 6. KESİNTİSİZ VİDEO OLUŞTURUCU
def fetch_text_to_video(prompt: str, index: int) -> str:
    logger.info(f"🎥 Sahne #{index+1} için VIDEO AI çağrılıyor...")

    # Hugging Face T2V Sunucuları
    public_spaces = [
        ("damo-vilab/modelscope-text-to-video-synthesis", None),
        ("ByteDance/AnimateDiff-Lightning", "/generate")
    ]

    for space, api in public_spaces:
        try:
            logger.info(f"⏳ Text-to-Video deneniyor: '{space}'")
            client = Client(space)
            res = client.predict(prompt, api_name=api) if api else client.predict(prompt)
            
            if res and is_valid_video_file(str(res)):
                logger.info(f"✅ AI Video başarıyla üretildi: {space}")
                return str(res)
        except Exception as e:
            logger.warning(f"⚠️ Sunucu pasif veya uyumsuz ({space}): {e}")

    # Harici stok mp4 indirme denemesi (Doğrulamalı)
    backup_urls = [
        "https://vjs.zencdn.net/v/oceans.mp4",
        "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
        "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4",
        "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4"
    ]
    
    out_file = TMP_DIR / f"video_{index}.mp4"
    try:
        r = requests.get(backup_urls[index % len(backup_urls)], timeout=15, stream=True)
        if r.status_code == 200:
            with open(out_file, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    f.write(chunk)
            if is_valid_video_file(str(out_file)):
                return str(out_file)
    except Exception as e:
        logger.warning(f"⚠️ Stok video indirme başarısız: {e}")

    # SAF PYTHON DİNAMİK ARKA PLAN (Sıfır Çökme Garantisi)
    logger.warning("⚠️ Saf Python dinamik arka plan oluşturuluyor (Çökme Engellendi)...")
    colors = [(20, 20, 40), (40, 10, 50), (10, 40, 50), (50, 20, 10)]
    color = colors[index % len(colors)]
    
    fallback_clip = ColorClip(size=(1080, 1920), color=color).with_duration(4)
    fallback_clip.write_videofile(str(out_file), fps=24, codec="libx264", logger=None)
    fallback_clip.close()
    return str(out_file)


# 7. MONTAJ VE YOUTUBE SHORTS YÜKLEME
def main():
    extracted_sentences, all_words = extract_trend_video_data()
    scenes, video_title = generate_story(extracted_sentences, all_words)
    video_clips = []

    for idx, scene in enumerate(scenes):
        logger.info(f"🎬 Sahne {idx+1}/{len(scenes)} hazırlanıyor: '{scene['text']}'")
        
        raw_video_path = fetch_text_to_video(scene["prompt"], idx)

        # Seslendirme
        tts_path = TMP_DIR / f"tts_{idx}.mp3"
        gTTS(text=scene["text"], lang='en').save(str(tts_path))
        audio_clip = AudioFileClip(str(tts_path))

        # Video Dikey Formatlama
        clip = VideoFileClip(raw_video_path)
        clip = clip.resized(height=1920)
        if clip.width < 1080:
            clip = clip.resized(width=1080)
        clip = clip.cropped(x_center=clip.width/2, y_center=clip.height/2, width=1080, height=1920)

        duration = max(clip.duration, audio_clip.duration)
        clip = clip.with_duration(duration)

        # Altyazı
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

        composite = CompositeVideoClip([clip, txt_clip], size=(1080, 1920)).with_audio(audio_clip)
        video_clips.append(composite)

    logger.info("🎬 Video Birleştiriliyor...")
    final_video = concatenate_videoclips(video_clips, method="compose")
    output_file = OUT_DIR / "short_video.mp4"
    final_video.write_videofile(str(output_file), fps=24, codec="libx264", audio_codec="aac", logger=None)

    # YouTube Yükleme
    if not os.path.exists('token.json'):
        logger.error("❌ 'token.json' bulunamadı.")
        sys.exit(1)

    logger.info("🚀 YouTube Shorts'a Yükleniyor...")
    creds = Credentials.from_authorized_user_file('token.json')
    youtube = build('youtube', 'v3', credentials=creds)

    body = {
        'snippet': {
            'title': video_title,
            'description': f"{video_title}\n\n#trend #viral"
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
    logger.info(f"🎉 Video Yüklendi! ID: {video_id}")

    if video_id:
        time.sleep(10)
        try:
            youtube.videos().rate(id=video_id, rating='like').execute()
            logger.info("👍 Otomatik beğenildi.")
        except Exception:
            pass

        try:
            comment_body = {
                'snippet': {
                    'videoId': video_id,
                    'topLevelComment': {
                        'snippet': {'textOriginal': '🔔 Subscribe for daily trend shorts! #trend #viral'}
                    }
                }
            }
            youtube.commentThreads().insert(part='snippet', body=comment_body).execute()
            logger.info("💬 Otomatik yorum eklendi.")
        except Exception:
            pass


if __name__ == "__main__":
    main()
