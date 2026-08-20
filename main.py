import os
import sys
import time
import re
import logging
import tempfile
import requests
import warnings
from pathlib import Path

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
logger = logging.getLogger("context-aware-t2v")

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
TMP_DIR = Path(tempfile.mkdtemp(prefix="ai-video-"))


# 1. TREND VİDEOLARIN İÇERİĞİNİ BİREBİR ANALİZ EDEN MOTOR
def extract_topic_and_generate_prompts():
    logger.info("🔥 YouTube trend videolarının konusu ve detayları analiz ediliyor...")
    
    extracted_context = []
    video_titles = []

    try:
        youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
        res = youtube.search().list(
            q='viral shorts trending',
            type='video',
            videoDuration='short',
            order='viewCount',
            maxResults=5,
            part='snippet'
        ).execute()
        
        for item in res.get('items', []):
            title = item['snippet']['title']
            description = item['snippet'].get('description', '')
            video_titles.append(title)
            
            # Başlık ve açıklamayı temizleyip ana konuyu çıkarır
            combined = f"{title} {description}"
            clean_text = re.sub(r'[^\w\s]', '', combined)
            words = [w for w in clean_text.split() if len(w) > 3 and w.lower() not in ['shorts', 'video', 'youtube', 'http', 'https', 'subscribe', 'channel']]
            extracted_context.extend(words)
            
    except Exception as e:
        logger.warning(f"⚠️ YouTube API analiz hatası: {e}")

    # En çok geçen trend konu kelimeleri
    unique_words = list(dict.fromkeys(extracted_context))
    main_subject = " ".join(unique_words[:3]).title() if unique_words else "Interesting Daily Challenge"
    
    # Videonun gerçek konusuna uygun dinamik görsel istemleri (Prompt)
    scenes = [
        {
            "prompt": f"A realistic 8k video clip showing {main_subject}, detailed subject focus, cinematic lighting",
            "text": unique_words[0].upper() if len(unique_words) > 0 else "LOOK AT THIS"
        },
        {
            "prompt": f"Close up video shot centered on {main_subject}, high resolution, natural motion",
            "text": unique_words[1].upper() if len(unique_words) > 1 else "WHAT HAPPENS"
        },
        {
            "prompt": f"A detailed cinematic scene depicting {main_subject}, smooth movement, photorealistic",
            "text": unique_words[2].upper() if len(unique_words) > 2 else "FINAL RESULT"
        }
    ]

    final_title = f"{video_titles[0][:50]} #shorts #trending" if video_titles else f"{main_subject} #shorts"
    logger.info(f"📌 Tespit Edilen Ana Konu: '{main_subject}'")
    logger.info(f"📌 Video Başlığı: '{final_title}'")
    
    return scenes, final_title


# 2. HUGGING FACE GPU KUYRUK BEKLEME MOTORU
def render_video_with_patient_queue(prompt: str) -> str:
    logger.info(f"⚡ HF Public GPU alanına bağlanılıyor: '{prompt[:40]}...'")
    
    # Kamu kullanımına açık, sıra bekleten Gradio alanları
    public_spaces = [
        ("damo-vilab/modelscope-text-to-video-synthesis", "/predict"),
        ("guoyww/AnimateDiff", "/generate"),
        ("ginipick/text-to-video", "/generate_video")
    ]

    for space, endpoint in public_spaces:
        try:
            logger.info(f"⏳ [{space}] alanında GPU kuyruğuna giriliyor...")
            kwargs = {"verbose": False}
            if HF_TOKEN:
                kwargs["hf_token"] = HF_TOKEN

            client = Client(space, **kwargs)
            job = client.submit(prompt, api_name=endpoint)

            wait_time = 0
            while not job.done():
                time.sleep(20)
                wait_time += 20
                logger.info(f"⏳ [{space}] GPU kuyruğunda sıra bekleniyor... ({wait_time} saniye oldu)")

            result = job.result()
            video_path = result if isinstance(result, str) else result[0]

            if str(video_path).lower().endswith(('.mp4', '.avi', '.mov', '.webm')):
                logger.info(f"✅ [{space}] Kuyruk tamamlandı, video teslim alındı: {video_path}")
                return video_path

        except Exception as e:
            logger.warning(f"⚠️ [{space}] alanında sıra beklenirken bağlantı kesildi/meşgul: {e}")
            continue

    raise RuntimeError("❌ Kamuya açık hiçbir HF alanında sıra alınamadı.")


# 3. OTOMATİK DÜZENLEME, MONTAJ VE YÜKLEME
def main():
    scenes, video_title = extract_topic_and_generate_prompts()
    video_clips = []

    for idx, scene in enumerate(scenes):
        logger.info(f"🎬 Sahne {idx+1}/{len(scenes)} hazırlanıyor...")
        video_file_path = render_video_with_patient_queue(scene["prompt"])
        
        clip = VideoFileClip(video_file_path)
        
        # 9:16 Dikey Format
        clip_resized = clip.resized(height=1920)
        vertical_clip = clip_resized.cropped(x_center=clip_resized.w / 2, width=1080)

        # Dinamik Konu Yazısı
        txt_clip = TextClip(
            text=scene["text"],
            font_size=55,
            color='yellow',
            stroke_color='black',
            stroke_width=3,
            method='caption',
            size=(900, 300)
        ).with_duration(vertical_clip.duration).with_position(('center', 0.70), relative=True)

        # Ses
        tts_path = TMP_DIR / f"tts_{idx}.mp3"
        gTTS(text=scene["text"], lang='en').save(str(tts_path))
        audio_clip = AudioFileClip(str(tts_path))
        if audio_clip.duration > vertical_clip.duration:
            audio_clip = audio_clip.subclipped(0, vertical_clip.duration)

        composite = CompositeVideoClip([vertical_clip, txt_clip]).with_audio(audio_clip)
        video_clips.append(composite)

    logger.info("🎬 Videolar birleştiriliyor...")
    final_video = concatenate_videoclips(video_clips, method="compose")
    output_file = OUT_DIR / "short_video.mp4"
    final_video.write_videofile(str(output_file), fps=24, codec="libx264", audio_codec="aac", logger=None)

    if not os.path.exists('token.json'):
        logger.error("❌ token.json bulunamadı. Otomatik yükleme iptal edildi.")
        sys.exit(1)

    logger.info("🚀 YouTube Shorts'a yükleniyor...")
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
    logger.info(f"🎉 Yüklendi! Video ID: {video_id}")

    if video_id:
        try:
            youtube.videos().rate(id=video_id, rating='like').execute()
            logger.info("👍 Otomatik beğenildi (Auto-liked)!")
        except Exception as e:
            logger.warning(f"Auto-like uyarısı: {e}")


if __name__ == "__main__":
    main()
