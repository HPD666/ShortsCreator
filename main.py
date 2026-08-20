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
logger = logging.getLogger("comfyui-auto-engager")

YT_API_KEY = os.environ.get("YT_API_KEY")
COMFYUI_URL = os.environ.get("COMFYUI_URL", "").rstrip("/")
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "")

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
TMP_DIR = Path(tempfile.mkdtemp(prefix="ai-comfyui-"))


def extract_clean_context():
    logger.info("🔍 YouTube trend içerikleri analiz ediliyor...")
    words = []
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

        forbidden = {'shorts', 'video', 'youtube', 'http', 'https', 'subscribe', 'channel', 'action', 'shot', 'cinematic'}

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
    main_subject = " ".join(unique_words[:3]) if unique_words else "Unbelievable Daily Event"

    scenes = [
        {
            "prompt": f"Raw realistic video of {main_subject}, dynamic natural motion, photorealistic",
            "text": unique_words[0].upper() if len(unique_words) > 0 else "LOOK AT THIS"
        },
        {
            "prompt": f"Detailed video focusing on {main_subject}, continuous camera motion, sharp details",
            "text": unique_words[1].upper() if len(unique_words) > 1 else "WAIT FOR IT"
        },
        {
            "prompt": f"Full motion clip depicting {main_subject}, high resolution realistic scene",
            "text": unique_words[2].upper() if len(unique_words) > 2 else "FINAL RESULT"
        }
    ]

    final_title = f"{titles[0][:50]} #shorts #viral" if titles else f"{main_subject} #shorts"
    logger.info(f"📌 Tespit Edilen Ana Konu: '{main_subject}'")
    return scenes, final_title


def render_via_comfyui(prompt: str, index: int) -> str:
    output_path = TMP_DIR / f"ai_generated_{index}.mp4"

    if COMFYUI_URL:
        logger.info(f"⚡ ComfyUI Sunucusuna (`{COMFYUI_URL}`) T2V İstegi Gönderiliyor...")
        workflow = {
            "prompt": {
                "3": {"inputs": {"seed": int(time.time()) + index, "steps": 20, "cfg": 7, "sampler_name": "euler", "scheduler": "normal"}, "class_type": "KSampler"},
                "6": {"inputs": {"text": prompt, "clip": ["11", 0]}, "class_type": "CLIPTextEncode"},
                "10": {"inputs": {"filename_prefix": f"Shorts_{index}", "fps": 24, "images": ["3", 0]}, "class_type": "VHS_VideoCombine"}
            }
        }
        try:
            req = requests.post(f"{COMFYUI_URL}/prompt", json=workflow, timeout=30)
            if req.status_code == 200:
                prompt_id = req.json().get("prompt_id")
                for _ in range(120):
                    time.sleep(2)
                    history_res = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
                    if history_res.status_code == 200 and prompt_id in history_res.json():
                        outputs = history_res.json()[prompt_id]['outputs']
                        for node_id, node_out in outputs.items():
                            if 'gifs' in node_out or 'videos' in node_out:
                                filename = (node_out.get('gifs') or node_out.get('videos'))[0]['filename']
                                video_bytes = requests.get(f"{COMFYUI_URL}/view?filename={filename}", timeout=30).content
                                with open(output_path, 'wb') as f:
                                    f.write(video_bytes)
                                return str(output_path)
        except Exception as e:
            logger.warning(f"⚠️ ComfyUI hatası: {e}. Alternatife geçiliyor.")

    if REPLICATE_API_TOKEN:
        logger.info(f"⚡ Replicate API T2V kuyruğuna giriliyor...")
        headers = {"Authorization": f"Token {REPLICATE_API_TOKEN}", "Content-Type": "application/json"}
        payload = {"version": "be11f6c419130665b17ce377073e9722a48897665bd8a1f810aa78272f23e429", "input": {"prompt": prompt, "n_frames": 32, "steps": 25}}
        res = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload, timeout=30)
        if res.status_code in (200, 201):
            get_url = res.json()["urls"]["get"]
            for _ in range(120):
                time.sleep(2)
                check = requests.get(get_url, headers=headers, timeout=10).json()
                if check["status"] == "succeeded":
                    video_url = check["output"][0] if isinstance(check["output"], list) else check["output"]
                    v_res = requests.get(video_url, timeout=30)
                    with open(output_path, 'wb') as f:
                        f.write(v_res.content)
                    return str(output_path)
                elif check["status"] == "failed":
                    break

    logger.info(f"⚡ Yedek AI Video Motoru çalıştırılıyor...")
    encoded_p = urllib.parse.quote(prompt)
    ai_video_url = f"https://image.pollinations.ai/prompt/{encoded_p}?width=1080&height=1920&model=turbo&nologo=true"
    
    v_res = requests.get(ai_video_url, timeout=60)
    if v_res.status_code == 200:
        with open(output_path, 'wb') as f:
            f.write(v_res.content)
        return str(output_path)

    raise RuntimeError("❌ Hiçbir AI Video motorundan çıktı alınamadı.")


def main():
    scenes, video_title = extract_clean_context()
    video_clips = []

    for idx, scene in enumerate(scenes):
        logger.info(f"🎬 Sahne {idx+1}/{len(scenes)} işleniyor...")
        video_file = render_via_comfyui(scene["prompt"], idx)
        
        if video_file.endswith(('.jpg', '.png', '.jpeg')):
            from moviepy import ImageClip
            clip = ImageClip(video_file).with_duration(3.5)
            clip = clip.resized(height=1920).cropped(x_center=clip.w / 2, width=1080)
            clip = clip.resized(lambda t: 1 + 0.05 * t)
        else:
            clip = VideoFileClip(video_file)
            clip = clip.resized(height=1920).cropped(x_center=clip.w / 2, width=1080)

        txt_clip = TextClip(
            text=scene["text"],
            font_size=60,
            color='yellow',
            stroke_color='black',
            stroke_width=4,
            method='caption',
            size=(900, 300)
        ).with_duration(clip.duration).with_position(('center', 0.70), relative=True)

        tts_path = TMP_DIR / f"tts_{idx}.mp3"
        gTTS(text=scene["text"], lang='en').save(str(tts_path))
        audio_clip = AudioFileClip(str(tts_path))
        if audio_clip.duration > clip.duration:
            audio_clip = audio_clip.subclipped(0, clip.duration)

        composite = CompositeVideoClip([clip, txt_clip]).with_audio(audio_clip)
        video_clips.append(composite)

    logger.info("🎬 Videolar montajlanıyor...")
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

    # OTOMATİK BEĞENME (LIKE)
    if video_id:
        try:
            youtube.videos().rate(id=video_id, rating='like').execute()
            logger.info("👍 Video otomatik olarak beğenildi (Auto-liked)!")
        except Exception as e:
            logger.warning(f"⚠️ Otomatik beğenme sırasında uyarı: {e}")

        # OTOMATİK YORUM KAZIMA / İLK YORUMU ATMA
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
            logger.info("💬 Otomatik sabit yorum eklendi!")
        except Exception as e:
            logger.warning(f"⚠️ Yorum eklenirken uyarı: {e}")


if __name__ == "__main__":
    main()
