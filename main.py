import os
import sys
import time
import re
import json
import logging
import tempfile
import requests
import warnings
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
warnings.filterwarnings("ignore")

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
logger = logging.getLogger("comfyui-pure-engine")

YT_API_KEY = os.environ.get("YT_API_KEY")
COMFYUI_URL = os.environ.get("COMFYUI_URL", "").rstrip("/")

if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    try:
        with open('token.json', 'w') as f:
            f.write(os.environ['TOKEN_JSON'])
    except Exception as e:
        logger.warning(f"token.json okunamadı: {e}")

if not YT_API_KEY:
    logger.error("❌ YT_API_KEY zorunludur!")
    sys.exit(1)

if not COMFYUI_URL:
    logger.error("❌ COMFYUI_URL tanımlı değil! İşlem durduruldu.")
    sys.exit(1)

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="comfyui-video-"))


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
    main_subject = " ".join(unique_words[:3]) if unique_words else "Unbelievable Event"

    scenes = [
        {
            "prompt": f"Raw dynamic video of {main_subject}, smooth continuous motion, photorealistic video footage",
            "text": unique_words[0].upper() if len(unique_words) > 0 else "LOOK AT THIS"
        },
        {
            "prompt": f"Action video focusing on {main_subject}, continuous camera movement, high speed video",
            "text": unique_words[1].upper() if len(unique_words) > 1 else "WAIT FOR IT"
        },
        {
            "prompt": f"Full motion video depicting {main_subject}, dynamic cinematic action scene",
            "text": unique_words[2].upper() if len(unique_words) > 2 else "FINAL RESULT"
        }
    ]

    final_title = f"{titles[0][:50]} #shorts #viral" if titles else f"{main_subject} #shorts"
    return scenes, final_title


def render_comfyui_video(prompt: str, index: int) -> str:
    output_path = TMP_DIR / f"comfy_video_{index}.mp4"
    logger.info(f"⚡ ComfyUI Sunucusuna (`{COMFYUI_URL}`) Video İsteği Gönderiliyor... Sahne #{index+1}")

    workflow = {
        "prompt": {
            "3": {"inputs": {"seed": int(time.time()) + index, "steps": 20, "cfg": 7, "sampler_name": "euler", "scheduler": "normal"}, "class_type": "KSampler"},
            "6": {"inputs": {"text": prompt, "clip": ["11", 0]}, "class_type": "CLIPTextEncode"},
            "10": {"inputs": {"filename_prefix": f"Shorts_Vid_{index}", "fps": 24, "images": ["3", 0]}, "class_type": "VHS_VideoCombine"}
        }
    }

    response = None
    for attempt in range(1, 6):
        try:
            req = requests.post(f"{COMFYUI_URL}/prompt", json=workflow, timeout=40)
            if req.status_code == 200:
                response = req.json()
                break
            else:
                logger.warning(f"⚠️ Bağlantı denemesi {attempt}/5 başarısız (Status: {req.status_code}). 5sn bekleniyor...")
        except Exception as e:
            logger.warning(f"⚠️ Bağlantı hatası deneme {attempt}/5: {e}")
        time.sleep(5)

    if not response or "prompt_id" not in response:
        raise RuntimeError("❌ ComfyUI sunucusuna erişilemedi. Colab hücresinin çalıştığından emin ol.")

    prompt_id = response.get("prompt_id")
    logger.info(f"⏳ ComfyUI İşleme Alındı (Prompt ID: {prompt_id}). Video bekleniyor...")

    for _ in range(180):
        time.sleep(3)
        try:
            history_res = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=15)
            if history_res.status_code == 200 and prompt_id in history_res.json():
                outputs = history_res.json()[prompt_id]['outputs']
                for node_id, node_out in outputs.items():
                    media_list = node_out.get('gifs') or node_out.get('videos')
                    if media_list:
                        filename = media_list[0]['filename']
                        subfolder = media_list[0].get('subfolder', '')
                        file_type = media_list[0].get('type', 'output')

                        video_url = f"{COMFYUI_URL}/view?filename={filename}&subfolder={subfolder}&type={file_type}"
                        video_bytes = requests.get(video_url, timeout=60).content

                        with open(output_path, 'wb') as f:
                            f.write(video_bytes)

                        logger.info(f"✅ ComfyUI video dosyası indirildi: {output_path}")
                        return str(output_path)
        except Exception:
            continue

    raise RuntimeError("❌ ComfyUI video çıktısı zaman aşımına uğradı.")


def main():
    scenes, video_title = extract_clean_context()
    video_clips = []

    for idx, scene in enumerate(scenes):
        logger.info(f"🎬 Sahne {idx+1}/{len(scenes)} ComfyUI ile işleniyor...")
        video_file = render_comfyui_video(scene["prompt"], idx)

        clip = VideoFileClip(video_file)
        clip_resized = clip.resized(height=1920)
        clip_final = clip_resized.cropped(x_center=clip_resized.w / 2, width=1080)

        txt_clip = TextClip(
            text=scene["text"],
            font_size=60,
            color='yellow',
            stroke_color='black',
            stroke_width=4,
            method='caption',
            size=(900, 300)
        ).with_duration(clip_final.duration).with_position(('center', 0.70), relative=True)

        tts_path = TMP_DIR / f"tts_{idx}.mp3"
        gTTS(text=scene["text"], lang='en').save(str(tts_path))
        audio_clip = AudioFileClip(str(tts_path))
        if audio_clip.duration > clip_final.duration:
            audio_clip = audio_clip.subclipped(0, clip_final.duration)

        composite = CompositeVideoClip([clip_final, txt_clip]).with_audio(audio_clip)
        video_clips.append(composite)

    logger.info("🎬 ComfyUI videoları birleştiriliyor...")
    final_video = concatenate_videoclips(video_clips, method="compose")
    output_file = OUT_DIR / "short_video.mp4"
    final_video.write_videofile(str(output_file), fps=24, codec="libx264", audio_codec="aac", logger=None)

    if not os.path.exists('token.json'):
        logger.error("❌ 'token.json' bulunamadı. Yükleme yapılamadı.")
        sys.exit(1)

    logger.info("🚀 YouTube Shorts'a yükleniyor...")
    creds = Credentials.from_authorized_user_file('token.json')
    youtube = build('youtube', 'v3', credentials=creds)

    body = {
        'snippet': {'title': video_title, 'description': video_title, 'categoryId': '22'},
        'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False, 'containsSyntheticMedia': True}
    }
    media = MediaFileUpload(str(output_file), chunksize=-1, resumable=True, mimetype='video/mp4')
    
    upload_response = youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
    video_id = upload_response.get('id')
    logger.info(f"🎉 Başarıyla yüklendi! Video ID: {video_id}")

    if video_id:
        try:
            youtube.videos().rate(id=video_id, rating='like').execute()
            logger.info("👍 Video otomatik olarak beğenildi!")
        except Exception as e:
            logger.warning(f"⚠️ Otomatik beğenme uyarısı: {e}")

        try:
            comment_body = {
                'snippet': {
                    'videoId': video_id,
                    'topLevelComment': {
                        'snippet': {
                            'textOriginal': 'Subscribe for more daily shorts! 🔔'
                        }
                    }
                }
            }
            youtube.commentThreads().insert(part='snippet', body=comment_body).execute()
            logger.info("💬 Otomatik yorum eklendi!")
        except Exception as e:
            logger.warning(f"⚠️ Yorum ekleme uyarısı: {e}")


if __name__ == "__main__":
    main()
