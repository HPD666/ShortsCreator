import os
import sys
import time
import re
import logging
import tempfile
import warnings
from pathlib import Path

# Log akışını GitHub Actions üzerinde anlık (live) kıl
sys.stdout.reconfigure(line_buffering=True)

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
logger = logging.getLogger("pure-t2v-strict-queue")

YT_API_KEY = os.environ.get("YT_API_KEY")
HF_TOKEN = os.environ.get("HF_TOKEN", None)

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
TMP_DIR = Path(tempfile.mkdtemp(prefix="t2v-queue-"))


# 1. YOUTUBE TREND KONUSUNU ANLAYAN VE JENERİK KELİMELERİ TEMİZLEYEN ANALİZ MOTORU
def analyze_youtube_context():
    logger.info("🔥 YouTube trend videolarının konusu analiz ediliyor...")
    
    context_words = []
    video_titles = []

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
        
        # Yasaklı jenerik kelimeler listesi (Action shot, cinematic vb. temizleme)
        forbidden_words = {
            'shorts', 'video', 'youtube', 'http', 'https', 'subscribe', 'channel', 
            'action', 'shot', 'cinematic', 'viral', 'trending', 'challenge', 'with', 'from'
        }

        for item in res.get('items', []):
            title = item['snippet']['title']
            desc = item['snippet'].get('description', '')
            video_titles.append(title)
            
            clean_text = re.sub(r'[^\w\s]', '', f"{title} {desc}")
            words = [
                w.strip() for w in clean_text.split() 
                if len(w) > 3 and w.lower() not in forbidden_words
            ]
            context_words.extend(words)

    except Exception as e:
        logger.warning(f"⚠️ YouTube API okuma uyarısı: {e}")

    unique_words = list(dict.fromkeys(context_words))
    main_topic = " ".join(unique_words[:3]) if unique_words else "Daily Unique Event"

    # Sadece videonun gerçek konusunu işleyen saf prompt yapısı
    scenes = [
        {
            "prompt": f"Video depicting {main_topic}, realistic movement, natural context",
            "text": unique_words[0].upper() if len(unique_words) > 0 else "LOOK AT THIS"
        },
        {
            "prompt": f"Detailed video scene of {main_topic}, realistic environment",
            "text": unique_words[1].upper() if len(unique_words) > 1 else "WHAT HAPPENS"
        },
        {
            "prompt": f"Focus video on {main_topic}, natural lighting and motion",
            "text": unique_words[2].upper() if len(unique_words) > 2 else "MUST SEE"
        }
    ]

    final_title = f"{video_titles[0][:50]} #shorts #viral" if video_titles else f"{main_topic} #shorts"
    logger.info(f"📌 Analiz Edilen Gerçek Konu: '{main_topic}'")
    logger.info(f"📌 Hedef Video Başlığı: '{final_title}'")
    
    return scenes, final_title


# 2. HER SANİYE SIRA KONTROLÜ YAPAN (STRICT 1-SECOND QUEUE POLLING) T2V MOTORU
def render_video_strict_t2v_queue(prompt: str) -> str:
    logger.info(f"⚡ HF Public T2V GPU alanlarına bağlanılıyor: '{prompt}'")
    
    # Text-To-Video Hizmeti Veren Aktif Kamusal Gradio Alanları
    public_t2v_spaces = [
        ("Wan-Video/Wan2.1-T2V-1.3B", "/predict"),
        ("VideoCrafter/VideoCrafter", "/predict"),
        ("damo-vilab/modelscope-text-to-video-synthesis", "/predict"),
        ("artificialguybr/Text-To-Video-Alpha", "/predict")
    ]

    for space, endpoint in public_t2v_spaces:
        try:
            logger.info(f"⏳ [{space}] alanına bağlanılıyor ve GPU sırasına giriliyor...")
            kwargs = {"verbose": False}
            if HF_TOKEN:
                kwargs["hf_token"] = HF_TOKEN

            client = Client(space, **kwargs)
            job = client.submit(prompt, api_name=endpoint)

            elapsed_seconds = 0
            # HER SANİYE DÖNGÜSÜ: Bağlantıyı koparmadan sırayı saniye saniye takip eder
            while not job.done():
                time.sleep(1)
                elapsed_seconds += 1
                if elapsed_seconds % 5 == 0:  # Her 5 saniyede bir log akışına bilgi basar
                    logger.info(f"⏳ [{space}] GPU Sırası Bekleniyor... ({elapsed_seconds} saniye tamamlandı)")

            result = job.result()
            video_path = result if isinstance(result, str) else (result[0] if isinstance(result, (list, tuple)) else None)

            if video_path and str(video_path).lower().endswith(('.mp4', '.avi', '.mov', '.webm')):
                logger.info(f"✅ [{space}] Video üretimi {elapsed_seconds}. saniyede tamamlandı: {video_path}")
                return str(video_path)

        except Exception as e:
            logger.warning(f"⚠️ [{space}] alanında sıra beklenirken hata oluştu veya alan kapalı: {e}")
            continue

    raise RuntimeError("❌ Kamuya açık hiçbir HF Text-To-Video alanında sıra alınamadı.")


# 3. KESİNTİSİZ MONTAJ VE OTO-YÜKLEME
def main():
    scenes, video_title = analyze_youtube_context()
    video_clips = []

    for idx, scene in enumerate(scenes):
        logger.info(f"🎬 Sahne {idx+1}/{len(scenes)} T2V kuyruğuna gönderiliyor...")
        video_file_path = render_video_strict_t2v_queue(scene["prompt"])
        
        clip = VideoFileClip(video_file_path)
        
        # 9:16 Dikey Kırpma
        clip_resized = clip.resized(height=1920)
        vertical_clip = clip_resized.cropped(x_center=clip_resized.w / 2, width=1080)

        # Yazı Katmanı
        txt_clip = TextClip(
            text=scene["text"],
            font_size=55,
            color='yellow',
            stroke_color='black',
            stroke_width=3,
            method='caption',
            size=(900, 300)
        ).with_duration(vertical_clip.duration).with_position(('center', 0.70), relative=True)

        # Ses Katmanı
        tts_path = TMP_DIR / f"tts_{idx}.mp3"
        gTTS(text=scene["text"], lang='en').save(str(tts_path))
        audio_clip = AudioFileClip(str(tts_path))
        if audio_clip.duration > vertical_clip.duration:
            audio_clip = audio_clip.subclipped(0, vertical_clip.duration)

        composite = CompositeVideoClip([vertical_clip, txt_clip]).with_audio(audio_clip)
        video_clips.append(composite)

    logger.info("🎬 Tüm AI video sahneleri birleştiriliyor...")
    final_video = concatenate_videoclips(video_clips, method="compose")
    output_file = OUT_DIR / "short_video.mp4"
    final_video.write_videofile(str(output_file), fps=24, codec="libx264", audio_codec="aac", logger=None)

    if not os.path.exists('token.json'):
        logger.error("❌ token.json dosyası bulunamadı. Yükleme iptal edildi.")
        sys.exit(1)

    logger.info("🚀 YouTube Shorts'a otomatik yükleniyor...")
    creds = Credentials.from_authorized_user_file('token.json')
    youtube = build('youtube', 'v3', credentials=creds)

    body = {
        'snippet': {
            'title': video_title,
            'description': video_title,
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
        except Exception as e:
            logger.warning(f"Auto-like uyarısı: {e}")


if __name__ == "__main__":
    main()
