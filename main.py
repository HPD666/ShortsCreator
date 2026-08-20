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


# 1. TREND VİDEOLARI İZLEME VE METİN VERİLERİNİ ÇEKME
def extract_trend_video_data():
    logger.info("🔍 Trend videolar izleniyor, açıklamalar ve ekran yazıları taranıyor...")
    
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
        
        # A) EKRANDA YAZAN YAZI (Video Başlığı)
        screen_text = snippet.get('title', '')
        screen_words = [w for w in screen_text.split() if not w.startswith('#')]
        clean_screen_text = " ".join(screen_words)

        # B) AÇIKLAMADAKİ # İLE BAŞLAMAYAN KELİMELERİ SIRAYLA AL
        description = snippet.get('description', '')
        desc_words = [word for word in description.split() if not word.startswith('#')]
        clean_desc_text = " ".join(desc_words)

        all_non_hashtag_words.extend(desc_words)
        
        combined_text = f"Ekran Yazısı: {clean_screen_text} | Açıklama: {clean_desc_text}"
        extracted_sentences.append(combined_text)

    logger.info(f"📊 Toplam {len(all_non_hashtag_words)} adet # ile başlamayan kelime sırayla toplandı.")
    return extracted_sentences, all_non_hashtag_words


# 2. YEDEK PROGRAM (COPILOT/AI ÇALIŞMAZSA DEVREYE GİREN SAF PYTHON KODU)
def programmatic_fallback_engine(all_words):
    logger.info("⚡ YEDEK PROGRAM DEVREDE: AI çalışmadığı için saf kod (program) senaryoyu üretiyor...")
    
    clean_words = [re.sub(r'[^\w\s]', '', w) for w in all_words if len(w) > 2]
    if len(clean_words) < 16:
        clean_words = ["viral", "trending", "amazing", "watch", "this", "moment", "incredible", "secret", "mindblowing", "today", "popular", "shorts", "video", "content", "best", "trend"]

    chunk_size = max(3, len(clean_words) // 4)
    scene1_text = " ".join(clean_words[0:chunk_size])[:30]
    scene2_text = " ".join(clean_words[chunk_size:chunk_size*2])[:30]
    scene3_text = " ".join(clean_words[chunk_size*2:chunk_size*3])[:30]
    scene4_text = " ".join(clean_words[chunk_size*3:chunk_size*4])[:30]

    scenes = [
        {"text": scene1_text, "prompt": f"cinematic moving video of {scene1_text}, photorealistic 8k vertical"},
        {"text": scene2_text, "prompt": f"cinematic dynamic video of {scene2_text}, photorealistic 8k vertical"},
        {"text": scene3_text, "prompt": f"cinematic action video of {scene3_text}, photorealistic 8k vertical"},
        {"text": scene4_text, "prompt": f"cinematic dramatic climax video of {scene4_text}, photorealistic 8k vertical"}
    ]
    
    title = f"{clean_words[0].capitalize()} {clean_words[1].capitalize()} #trend #viral"
    return scenes, title


# 3. GEMINI AI ÇAĞRICI (AKILLI MODEL SEÇİMLİ)
def call_gemini_smart(prompt_instruction):
    genai.configure(api_key=GEMINI_API_KEY)
    
    candidate_models = ["gemini-2.0-flash", "gemini-1.5-flash-latest", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
    
    try:
        available = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for m in available:
            if m not in candidate_models:
                candidate_models.insert(0, m)
    except Exception as e:
        logger.warning(f"⚠️ Model listesi taranamadı: {e}")

    for m_name in candidate_models:
        try:
            logger.info(f"🧠 Gemini modeli deneniyor: {m_name}")
            model = genai.GenerativeModel(m_name)
            res = model.generate_content(prompt_instruction)
            if res and res.text:
                return res.text
        except Exception as e:
            logger.warning(f"⚠️ Model '{m_name}' çalışmadı: {e}")

    raise RuntimeError("Gemini AI yanıt vermedi.")


# 4. SENARYO OLUŞTURUCU
def generate_story(extracted_sentences, all_words):
    logger.info("🧠 AI ile senaryo oluşturuluyor...")
    
    prompt_instruction = f"""
    You are an AI video producer. Here are extracted texts from trending videos:
    {json.dumps(extracted_sentences[:5])}

    Create a 4-scene viral script based strictly on these trend inputs.
    
    RULES:
    - Spoken sentence in each scene MUST be 4 to 6 words maximum.
    - Video prompts must describe dynamic cinematic moving 8k vertical 9:16 video scenes.
    - Title MUST ONLY use hashtags #trend #viral. Do NOT use weekly trend words.

    Return ONLY a JSON:
    {{
      "title": "Catchy Title #trend #viral",
      "scenes": [
        {{"text": "Short spoken sentence 1", "prompt": "Dynamic moving cinematic text-to-video scene 1"}},
        {{"text": "Short spoken sentence 2", "prompt": "Dynamic moving cinematic text-to-video scene 2"}},
        {{"text": "Short spoken sentence 3", "prompt": "Dynamic moving cinematic text-to-video scene 3"}},
        {{"text": "Short spoken sentence 4", "prompt": "Dynamic moving cinematic text-to-video scene 4"}}
      ]
    }}
    """
    try:
        response_text = call_gemini_smart(prompt_instruction)
        match = re.search(r'\{.*\}', response_text.strip(), re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            return data["scenes"], data.get("title", "Trending Shorts #trend #viral")
        else:
            raise ValueError("AI geçerli JSON üretmedi.")
    except Exception as e:
        logger.warning(f"⚠️ AI çalışmadı ({e}). Yedek Program (Kod Algoritması) tetikleniyor...")
        return programmatic_fallback_engine(all_words)


# 5. GERÇEK VİDEO AI SERVİSLERİ (SIRA BEKLEME - UZUN TIMEOUT & RETRY)
def fetch_real_video_ai(prompt: str, index: int) -> str:
    logger.info(f"🎥 Sahne #{index+1} için GERÇEK VİDEO AI çağrılıyor...")

    # Aktif çalışan Gerçek Text-to-Video Yapay Zeka Sunucuları
    video_spaces = [
        ("ByteDance/AnimateDiff-Lightning", "/generate"),
        ("guoyww/AnimateDiff", "/generate"),
        ("ali-vilab/modelscope-text-to-video-synthesis", "/predict"),
        ("CiroGarcía/ZeroScope_v2_dark", "/predict")
    ]

    for space_name, api_endpoint in video_spaces:
        for attempt in range(1, 3):  # Her servisi 2 kere dene
            try:
                logger.info(f"⏳ [{attempt}/2] HF Video AI Kuyruğuna Giriliyor: '{space_name}' (Sıra bekleniyor...)")
                
                # Timeout süresi 600 saniye (10 DAKİKA). Kuyrukta sırasını bekler, erken vazgeçmez.
                client = Client(space_name, timeout=600)
                
                result = client.predict(prompt, api_name=api_endpoint)
                if result and os.path.exists(str(result)):
                    logger.info(f"✅ GERÇEK VİDEO BÜTÜNÜYLE ÜRETİLDİ VE İNDİRİLDİ: {space_name}")
                    return str(result)
            except Exception as e:
                logger.warning(f"⚠️ '{space_name}' (Deneme {attempt}) sıra beklenirken meşgul/hata verdi: {e}")
                time.sleep(5)

    raise RuntimeError(f"❌ Sahne #{index+1} için Video AI sunucuları meşguldü.")


# 6. MONTAJ VE YOUTUBE SHORTS YÜKLEME
def main():
    extracted_sentences, all_words = extract_trend_video_data()
    scenes, video_title = generate_story(extracted_sentences, all_words)
    video_clips = []

    for idx, scene in enumerate(scenes):
        logger.info(f"🎬 Sahne {idx+1}/{len(scenes)} hazırlanıyor: '{scene['text']}'")
        
        # SADECE GERÇEK VİDEO AI KULLANILIR
        raw_video_path = fetch_real_video_ai(scene["prompt"], idx)

        # Seslendirme (gTTS)
        tts_path = TMP_DIR / f"tts_{idx}.mp3"
        gTTS(text=scene["text"], lang='en').save(str(tts_path))
        audio_clip = AudioFileClip(str(tts_path))

        # Video İşleme (9:16 Dikey Format)
        clip = VideoFileClip(raw_video_path)
        clip = clip.resized(height=1920)
        if clip.width < 1080:
            clip = clip.resized(width=1080)
        clip = clip.cropped(x_center=clip.width/2, y_center=clip.height/2, width=1080, height=1920)

        duration = max(clip.duration, audio_clip.duration)
        clip = clip.with_duration(duration)

        # Ekran Sarı Altyazısı
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

    logger.info("🎬 Shorts Videosu Birleştiriliyor...")
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
    logger.info(f"🎉 Video Yüklendi! ID: {video_id}")

    # Otomatik Beğeni ve Sabitlenmiş Yorum
    if video_id:
        time.sleep(15)
        try:
            youtube.videos().rate(id=video_id, rating='like').execute()
            logger.info("👍 Otomatik beğenildi!")
        except Exception as e:
            logger.warning(f"⚠️ Auto-like uyarısı: {e}")

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
            logger.info("💬 Otomatik yorum eklendi!")
        except Exception as e:
            logger.warning(f"⚠️ Auto-comment uyarısı: {e}")


if __name__ == "__main__":
    main()
