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

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="3d-ai-"))


# 1. YOUTUBE TRENDLERİNİ GERÇEK ZAMANLI ÇEKME
def fetch_youtube_trends():
    logger.info("🔍 Güncel YouTube Shorts trendleri ve viral konular çekiliyor...")
    titles = []
    queries = ['viral shorts challenge 2026', 'unbelievable life hack trending', 'mind blowing technology shorts', 'satisfying scientific experiment']
    q = random.choice(queries)
    
    try:
        youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
        res = youtube.search().list(
            q=q,
            type='video',
            videoDuration='short',
            order='viewCount',
            maxResults=8,
            part='snippet'
        ).execute()

        for item in res.get('items', []):
            titles.append(item['snippet']['title'])
    except Exception as e:
        logger.warning(f"⚠️ YouTube API okuma uyarısı: {e}")

    return titles if titles else ["Unbelievable Tech Gadgets", "Mind Blowing Physics Hacks", "Future AI Secrets"]


# 2. GEMINI VEYA YEDEK AI İLE %100 DİNAMİK & GERÇEKÇİ SENARYO ÜRETİMİ
def generate_story_with_gemini(trends):
    logger.info("🧠 AI trendleri analiz ediyor ve gerçekçi viral senaryo yazıyor...")
    
    prompt_instruction = f"""
    You are an expert viral YouTube Shorts content creator.
    Analyze these trending topic titles: {json.dumps(trends)}

    Create a realistic, intriguing, 4-scene short story/fact based on these trends.
    Style MUST be realistic, cinematic, and captivating (NOT cartoon/Pixar).

    For each scene:
    1. 'text': A catchy spoken sentence for voiceover (MAX 4 to 6 words per scene).
    2. 'prompt': A detailed photorealistic image prompt describing the scene. (Include: photorealistic, 8k resolution, cinematic lighting, shot on 35mm lens, highly detailed, vertical 9:16 aspect ratio, no text or overlays).

    Return ONLY a valid JSON object formatted exactly like this:
    {{
      "title": "Viral Catchy Title with #shorts #viral #trending",
      "scenes": [
        {{"text": "Spoken text scene 1", "prompt": "Photorealistic prompt scene 1"}},
        {{"text": "Spoken text scene 2", "prompt": "Photorealistic prompt scene 2"}},
        {{"text": "Spoken text scene 3", "prompt": "Photorealistic prompt scene 3"}},
        {{"text": "Spoken text scene 4", "prompt": "Photorealistic prompt scene 4"}}
      ]
    }}
    Do not add markdown formatting or extra text outside JSON.
    """

    data = None

    # GEMINI DENEMESİ
    if GEMINI_API_KEY:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            
            # Dinamik Model Seçimi (404 önleme)
            selected_model_name = 'gemini-1.5-flash'
            try:
                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                for candidate in ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-2.0-flash']:
                    if candidate in available_models:
                        selected_model_name = candidate
                        break
            except Exception:
                pass

            model = genai.GenerativeModel(selected_model_name)
            response = model.generate_content(prompt_instruction)
            raw_text = response.text.strip()
            
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                logger.info("✅ Gemini AI Özgün Senaryoyu Başarıyla Oluşturdu!")
        except Exception as e:
            logger.warning(f"⚠️ Gemini API Hatası: {e}")

    # YEDEK POLLINATIONS LLM DENEMESİ
    if not data or "scenes" not in data:
        try:
            logger.info("🔄 Yedek AI motoruna bağlanılıyor...")
            url = "https://text.pollinations.ai/"
            res = requests.post(url, json={"messages": [{"role": "user", "content": prompt_instruction}], "model": "openai"}, timeout=30)
            raw_text = res.text.strip()
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                logger.info("✅ Yedek AI Özgün Senaryoyu Oluşturdu!")
        except Exception as e:
            logger.warning(f"⚠️ Yedek AI Hatası: {e}")

    # DİNAMİK YEDEK MOTORU (ASLA MYStery BOX TEKRARI YAPMAZ!)
    if not data or "scenes" not in data or len(data.get("scenes", [])) < 4:
        logger.info("🎲 Tamamen dinamik rastgele viral içerik motoru devreye giriyor...")
        topics = [
            ("The Secret AI Gadget", "This invisible device changes everything.", "It scans objects in real time.", "You can control it with mind.", "The future is already here!"),
            ("Deep Ocean Mystery", "Scientists found something glowing underwater.", "It responded to sound waves.", "A strange light burst forth.", "We are not alone down there."),
            ("Quantum Physics Hack", "This simple trick defies gravity.", "Light splits into infinite beams.", "Objects float in mid air.", "Reality is an illusion!"),
            ("Futuristic Supercars", "Engineers built a transparent engine.", "It runs purely on water.", "Top speed reaches unbelievable limits.", "Transportation changed forever.")
        ]
        chosen = random.choice(topics)
        data = {
            "title": f"{chosen[0]} 😱 #shorts #viral #trending #facts",
            "scenes": [
                {"text": chosen[1], "prompt": f"Photorealistic cinematic image of {chosen[0]}, 8k resolution, ultra detailed, 9:16 vertical, shot on 35mm lens, no text"},
                {"text": chosen[2], "prompt": f"Hyper-detailed close up photo representing {chosen[0]}, futuristic atmosphere, dramatic lighting, 9:16 vertical, no text"},
                {"text": chosen[3], "prompt": f"Photorealistic wide shot of {chosen[0]} in action, neon glowing reflections, 8k render, 9:16 vertical, no text"},
                {"text": chosen[4], "prompt": f"High resolution realistic photography of {chosen[0]} finale, epic background, studio quality, 9:16 vertical, no text"}
            ]
        }

    return data["scenes"], data.get("title", "Unbelievable Viral Shorts #shorts #viral")


# 3. GERÇEKÇİ GÖRSEL ÜRETME (POLLINATIONS FLUX / TURBO MOTORU)
def generate_3d_image(prompt: str, index: int) -> str:
    output_path = TMP_DIR / f"scene_{index}.jpg"
    logger.info(f"🎨 Sahne #{index+1} Gerçekçi AI Görseli Çiziliyor...")

    encoded_p = urllib.parse.quote(prompt)
    seed = random.randint(100000, 999999)
    # model=flux kullanarak hyper-realistic sonuçlar elde ediyoruz
    image_url = f"https://image.pollinations.ai/prompt/{encoded_p}?width=1080&height=1920&model=flux&seed={seed}&nologo=true"

    response = requests.get(image_url, timeout=90)
    if response.status_code == 200:
        with open(output_path, 'wb') as f:
            f.write(response.content)
        logger.info(f"✅ Gerçekçi Görsel Oluşturuldu: {output_path}")
        return str(output_path)
    else:
        # Görsel servisinde sorun olursa alternatif turbo motorunu dener
        image_url_alt = f"https://image.pollinations.ai/prompt/{encoded_p}?width=1080&height=1920&model=turbo&seed={seed}&nologo=true"
        response_alt = requests.get(image_url_alt, timeout=90)
        if response_alt.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response_alt.content)
            return str(output_path)
        raise RuntimeError(f"❌ Görsel Motoru Yanıt Vermedi (Status: {response.status_code})")


# 4. SES, ALTYAZI VE VİDEO KURGUSU (1080x1920 TAM EKRAN SHORTS)
def main():
    trends = fetch_youtube_trends()
    scenes, video_title = generate_story_with_gemini(trends)
    video_clips = []

    for idx, scene in enumerate(scenes):
        logger.info(f"🎬 Sahne {idx+1}/{len(scenes)}: '{scene['text']}'")
        image_file = generate_3d_image(scene["prompt"], idx)

        # Seslendirme (gTTS)
        tts_path = TMP_DIR / f"tts_{idx}.mp3"
        gTTS(text=scene["text"], lang='en').save(str(tts_path))
        audio_clip = AudioFileClip(str(tts_path))
        
        duration = max(3.0, audio_clip.duration + 0.5)

        # Görseli tam 1080x1920 boyutuna oturtma
        img_clip = ImageClip(image_file).resized((1080, 1920)).with_duration(duration)

        # Ekrandan Taşmayan, Okunabilir Şık Sarı Altyazı
        txt_clip = TextClip(
            text=scene["text"],
            font="DejaVuSans-Bold",
            font_size=42,
            color='yellow',
            stroke_color='black',
            stroke_width=4,
            method='caption',
            size=(900, 180)
        ).with_duration(duration).with_position(('center', 0.82), relative=True)

        composite = CompositeVideoClip([img_clip, txt_clip], size=(1080, 1920)).with_audio(audio_clip)
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
        'snippet': {'title': video_title, 'description': f"{video_title}\n\n#shorts #viral #trending #facts #ai"},
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
                            'textOriginal': 'Subscribe and turn on notifications for more daily shorts! 🔔'
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
