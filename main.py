import os
import sys
import time
import re
import logging
import tempfile
import requests
import warnings
import urllib.parse
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
warnings.filterwarnings("ignore")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

from gtts import gTTS
from moviepy import (
    ImageClip,
    AudioFileClip,
    TextClip,
    CompositeVideoClip,
    concatenate_videoclips
)
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', force=True)
logger = logging.getLogger("ai-vision-engine")

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
TMP_DIR = Path(tempfile.mkdtemp(prefix="ai-shorts-"))


# 1. TREND VİDEOLARIN DOKUSUNU VE İÇERİĞİNİ DERİNLEMESİNE BİLEŞENLERİNE AYIRAN MOTOR
def analyze_video_deep_details():
    logger.info("🔍 YouTube trend videoları detaylı içerik analizinden geçiriliyor...")
    
    extracted_concepts = []
    selected_title = "Viral Trend Story #shorts"

    try:
        youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
        
        # Trend araması yap ve detaylı parçaları topla
        res = youtube.search().list(
            q='viral shorts funny challenge trending',
            type='video',
            videoDuration='short',
            order='viewCount',
            maxResults=5,
            part='snippet'
        ).execute()

        items = res.get('items', [])
        if items:
            top_item = items[0]['snippet']
            selected_title = f"{top_item['title'][:50]} #shorts #viral"
            
            # Tüm trend videoların metinsel analizi
            for item in items:
                title = item['snippet']['title']
                desc = item['snippet'].get('description', '')
                full_text = f"{title} {desc}"
                clean_text = re.sub(r'[^\w\s]', '', full_text)
                
                # Gereksiz Youtube kelimelerini ayıkla
                filtered_words = [
                    w for w in clean_text.split() 
                    if len(w) > 3 and w.lower() not in ['shorts', 'video', 'youtube', 'http', 'https', 'viral', 'trending']
                ]
                extracted_concepts.extend(filtered_words)

    except Exception as e:
        logger.warning(f"⚠️ YouTube API okuma uyarısı: {e}")

    # Konu başlıklarını netleştir
    unique_concepts = list(dict.fromkeys(extracted_concepts))
    main_subject = " ".join(unique_concepts[:3]) if unique_concepts else "Daily Cinematic Viral Moment"

    # Videoyu izlemişçesine konusunu birebir taklit eden 3 sahnelik içerik yapısı
    scenes = [
        {
            "visual_prompt": f"Photorealistic 8k cinematic vertical video frame of {main_subject}, highly detailed, vivid colors",
            "overlay_text": unique_concepts[0].upper() if len(unique_concepts) > 0 else "WATCH THIS"
        },
        {
            "visual_prompt": f"Dynamic close up cinematic shot depicting {main_subject}, realistic lighting, dramatic focal point",
            "overlay_text": unique_concepts[1].upper() if len(unique_concepts) > 1 else "UNBELIEVABLE"
        },
        {
            "visual_prompt": f"High quality cinematic action frame showing {main_subject}, viral video aesthetic, masterpiece",
            "overlay_text": unique_concepts[2].upper() if len(unique_concepts) > 2 else "MUST SEE"
        }
    ]

    logger.info(f"📌 Analiz Edilen Trend Konusu: '{main_subject}'")
    logger.info(f"📌 Üretilecek Video Başlığı: '{selected_title}'")
    
    return scenes, selected_title


# 2. %100 KESİNTİSİZ VE YÜKSEK KALİTELİ AI GÖRSEL-HAREKET (MOTION) ENGINE
def render_ai_motion_scene(scene_info: dict, index: int) -> str:
    prompt = scene_info["visual_prompt"]
    logger.info(f"🎨 Sahne {index+1} için yüksek çözünürlüklü AI görseli üretiliyor...")

    encoded_prompt = urllib.parse.quote(prompt)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true&seed={int(time.time())+index}"

    img_path = TMP_DIR / f"scene_{index}.jpg"
    response = requests.get(image_url, timeout=30)
    
    if response.status_code == 200:
        with open(img_path, 'wb') as f:
            f.write(response.content)
        logger.info(f"✅ Sahne {index+1} görseli başarıyla oluşturuldu.")
        return str(img_path)
    else:
        raise RuntimeError(f"❌ Görsel motoru yanıt vermedi: HTTP {response.status_code}")


# 3. MONTAJ, DINAMIK HAREKET VE YOUTUBE YÜKLEME
def main():
    scenes, video_title = analyze_video_deep_details()
    video_clips = []

    for idx, scene in enumerate(scenes):
        logger.info(f"🎬 Sahne {idx+1}/{len(scenes)} montajlanıyor...")
        
        # AI Görseli Al
        image_file = render_ai_motion_scene(scene, idx)

        # TTS Sesini Üret
        tts_path = TMP_DIR / f"tts_{idx}.mp3"
        gTTS(text=scene["overlay_text"], lang='en').save(str(tts_path))
        audio_clip = AudioFileClip(str(tts_path))
        duration = max(audio_clip.duration, 3.0)  # Her sahne en az 3sn

        # Ken Burns / Kamera Yakınlaşma (Zoom In) Efekti Ekleme
        img_clip = ImageClip(image_file).with_duration(duration)
        animated_clip = img_clip.resized(lambda t: 1 + 0.08 * t)  # Sürekli dinamik yakınlaşma hareketi

        # Metin Katmanı
        txt_clip = TextClip(
            text=scene["overlay_text"],
            font_size=60,
            color='yellow',
            stroke_color='black',
            stroke_width=4,
            method='caption',
            size=(900, 300)
        ).with_duration(duration).with_position(('center', 0.70), relative=True)

        # Sahneyi Sesle Birleştir
        composite = CompositeVideoClip([animated_clip, txt_clip]).with_audio(audio_clip)
        video_clips.append(composite)

    logger.info("🎬 Videolar birleştiriliyor ve dikey formata kurgulanıyor...")
    final_video = concatenate_videoclips(video_clips, method="compose")
    output_file = OUT_DIR / "short_video.mp4"
    final_video.write_videofile(str(output_file), fps=24, codec="libx264", audio_codec="aac", logger=None)
    logger.info(f"✅ Video başarıyla oluşturuldu: {output_file}")

    # YouTube Upload
    if not os.path.exists('token.json'):
        logger.error("❌ 'token.json' dosyası eksik. Yükleme yapılamıyor.")
        sys.exit(1)

    logger.info("🚀 YouTube Shorts'a otomatik yükleniyor...")
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
            logger.info("👍 Otomatik beğenildi!")
        except Exception as e:
            logger.warning(f"Auto-like uyarısı: {e}")


if __name__ == "__main__":
    main()
