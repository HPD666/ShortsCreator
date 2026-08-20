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
    
    video_items = []
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
        video_items = res.get('items', [])
    except Exception as e:
        logger.warning(f"⚠️ Trend arama uyarısı: {e}")

    extracted_sentences = []
    all_non_hashtag_words = []

    for item in video_items:
        snippet = item.get('snippet', {})
        screen_text = snippet.get('title', '')
        screen_words = [w for w in screen_text.split() if not w.startswith('#')]
        clean_screen_text = " ".join(screen_words)

        description = snippet.get('description', '')
        desc_words = [word for word in description.split() if not word.startswith('#')]
        clean_desc_text = " ".join(desc_words)

        all_non_hashtag_words.extend(desc_words)
        extracted_sentences.append(f"Ekran: {clean_screen_text} | Açıklama: {clean_desc_text}")

    return extracted_sentences, all_non_hashtag_words


# 2. YEDEK PROGRAM SENARYOSU
def programmatic_fallback_engine(all_words):
    logger.info("⚡ YEDEK PROGRAM DEVREDE: Kod senaryosu oluşturuluyor...")
    clean_words = [re.sub(r'[^\w\s]', '', w) for w in all_words if len(w) > 2]
    if len(clean_words) < 16:
        clean_words = ["viral", "trending", "amazing", "watch", "this", "moment", "incredible", "secret", "mindblowing", "today", "popular", "shorts", "video", "content", "best", "trend"]

    chunk_size = max(3, len(clean_words) // 4)
    scenes = [
        {"text": " ".join(clean_words[0:chunk_size])[:30], "prompt": f"cinematic vertical video of {clean_words[0]}, 8k, realistic"},
        {"text": " ".join(clean_words[chunk_size:chunk_size*2])[:30], "prompt": f"action dramatic vertical video of {clean_words[1]}, 8k, realistic"},
        {"text": " ".join(clean_words[chunk_size*2:chunk_size*3])[:30], "prompt": f"aesthetic vertical video of {clean_words[2]}, 8k, realistic"},
        {"text": " ".join(clean_words[chunk_size*3:chunk_size*4])[:30], "prompt": f"epic climax vertical video of {clean_words[3]}, 8k, realistic"}
    ]
    title = f"{clean_words[0].capitalize()} {clean_words[1].capitalize()} #trend #viral"
    return scenes, title


# 3. GEMINI AI METİN ÜRETİCİ
def call_gemini_smart(prompt_instruction):
    genai.configure(api_key=GEMINI_API_KEY)
    valid_models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name = m.name.replace('models/', '')
                if any(k in name for k in ['flash', 'pro']) and not any(x in name for x in ['research', 'computer']):
                    valid_models.append(name)
    except Exception:
        pass

    valid_models.extend(["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"])

    for m_name in valid_models:
        try:
            logger.info(f"🧠 Gemini deneniyor: {m_name}")
            model = genai.GenerativeModel(m_name)
            res = model.generate_content(prompt_instruction)
            if res and res.text:
                return res.text
        except Exception as e:
            logger.warning(f"⚠️ Gemini model uyarısı ({m_name}): {e}")

    raise RuntimeError("Gemini yanıt vermedi.")


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


# 5. SAF TEXT-TO-VIDEO AI MOTORU (DİNAMİK GRADIO ÇAĞRISI)
def fetch_pure_text_to_video_ai(prompt: str, index: int) -> str:
    logger.info(f"🎥 Sahne #{index+1} için SAF TEXT-TO-VIDEO AI çağrılıyor...")

    # Aktif çalışan Text-To-Video AI sunucu listesi
    video_spaces = [
        "THUDM/CogVideoX-5B-Space",
        "CiroGarcía/ZeroScope_v2_dark",
        "fffiloni/zeroscope",
        "KingNish/Video-Generator"
    ]

    for space in video_spaces:
        for attempt in range(1, 3):
            try:
                logger.info(f"⏳ [{attempt}/2] Text-To-Video deneniyor: '{space}'")
                client = Client(space)
                
                # Dinamik olarak sunucunun API yapısını saptama ve çalıştırma
                try:
                    result = client.predict(prompt, api_name="/predict")
                except Exception:
                    try:
                        result = client.predict(prompt, api_name="/generate")
                    except Exception:
                        result = client.predict(prompt)

                if result and os.path.exists(str(result)):
                    logger.info(f"✅ GERÇEK TEXT-TO-VIDEO BAŞARIYLA ÜRETİLDİ: {space}")
                    return str(result)

            except Exception as e:
                logger.warning(f"⚠️ Sunucu meşgul ({space}): {e}")
                time.sleep(5)

    raise RuntimeError(f"❌ Sahne #{index+1} için tüm Text-to-Video AI sunucuları meşguldü. Lütfen tekrar çalıştırın.")


# 6. MONTAJ VE YOUTUBE SHORTS YÜKLEME
def main():
    extracted_sentences, all_words = extract_trend_video_data()
    scenes, video_title = generate_story(extracted_sentences, all_words)
    video_clips = []

    for idx, scene in enumerate(scenes):
        logger.info(f"🎬 Sahne {idx+1}/{len(scenes)} hazırlanıyor: '{scene['text']}'")
        
        # Sadece gerçek Text-to-Video yapay zekası kullanılır
        raw_video_path = fetch_pure_text_to_video_ai(scene["prompt"], idx)

        # Seslendirme
        tts_path = TMP_DIR / f"tts_{idx}.mp3"
        gTTS(text=scene["text"], lang='en').save(str(tts_path))
        audio_clip = AudioFileClip(str(tts_path))

        # Video Dikey (9:16) Ayarları
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

    logger.info("🎬 Shorts Bütünleştiriliyor...")
    final_video = concatenate_videoclips(video_clips, method="compose")
    output_file = OUT_DIR / "short_video.mp4"
    final_video.write_videofile(str(output_file), fps=24, codec="libx264", audio_codec="aac", logger=None)

    # YouTube Otomatik Yükleme
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
    logger.info(f"🎉 Video Başarıyla Yüklendi! ID: {video_id}")

    if video_id:
        time.sleep(15)
        try:
            youtube.videos().rate(id=video_id, rating='like').execute()
            logger.info("👍 Otomatik beğenildi.")
        except Exception as e:
            logger.warning(f"⚠️ Beğeni eklenemedi: {e}")

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
        except Exception as e:
            logger.warning(f"⚠️ Yorum eklenemedi: {e}")


if __name__ == "__main__":
    main()
