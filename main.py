import os
import sys
import time
import re
import logging
import tempfile
import requests
import warnings
from pathlib import Path

# Unbuffered stdout for live progress streaming in CI/CD logs
sys.stdout.reconfigure(line_buffering=True)

# HTTP and SDK warning suppression
warnings.filterwarnings("ignore")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

import replicate
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
logger = logging.getLogger("cloud-t2v-creator")

# Secrets and OAuth Token Management
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN")
YT_API_KEY = os.environ.get("YT_API_KEY")

if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    try:
        with open('token.json', 'w') as f:
            f.write(os.environ['TOKEN_JSON'])
    except Exception as e:
        logger.warning(f"token.json could not be written: {e}")

if not REPLICATE_API_TOKEN or not YT_API_KEY:
    logger.error("❌ REPLICATE_API_TOKEN and YT_API_KEY are required!")
    sys.exit(1)

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="ai-t2v-"))


def analyze_live_trends_for_t2v():
    logger.info("🔥 YouTube trend keywords fetching...")
    extracted_keywords = []
    
    try:
        youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
        res = youtube.search().list(
            q='viral shorts trending action challenge',
            type='video',
            videoDuration='short',
            order='viewCount',
            maxResults=5,
            part='snippet'
        ).execute()
        
        for item in res.get('items', []):
            raw_title = item['snippet']['title']
            clean_title = re.sub(r'[^\w\s]', '', raw_title)
            words = [w for w in clean_title.split() if len(w) > 3 and w.lower() not in ['shorts', 'video', 'http', 'https', 'with']]
            extracted_keywords.extend(words)
    except Exception as e:
        logger.warning(f"⚠️ YouTube API warning: {e}")

    unique_words = list(dict.fromkeys(extracted_keywords))[:4]
    trend_phrase = " ".join(unique_words).title() if unique_words else "Epic Extreme Action"
    final_video_title = f"{trend_phrase} Trend #trend #viral #shorts"

    scenes = [
        {
            "prompt": "Cinematic 8k photorealistic action movie scene, real person performing extreme movement, 35mm film style",
            "text": "EPIC ACTION"
        },
        {
            "prompt": "Hyper-realistic slow motion cinematic video of a person completing viral skill stunt, photorealistic textures",
            "text": "UNREAL SKILL"
        },
        {
            "prompt": "Photorealistic 8k dynamic close up shot of a person high-energy challenge action, cinematic lighting",
            "text": "MUST WATCH"
        }
    ]

    logger.info(f"📌 Generated Title: '{final_video_title}'")
    return scenes, final_video_title


def render_video_cloud(prompt: str) -> str:
    logger.info(f"⚡ Replicate LTX-Video cloud render launching: '{prompt[:35]}...'")
    
    output = replicate.run(
        "lightricks/ltx-video:3b8b1d9c15849887b003b544321dd022b467b7e3ba6ef5d233cfed1d943b1f14",
        input={
            "prompt": prompt,
            "negative_prompt": "cartoon, low quality, anime, worst quality, deformed, ugly",
            "width": 704,
            "height": 480,
            "num_frames": 121,
            "frame_rate": 25
        }
    )
    
    video_url = output if isinstance(output, str) else output[0]
    
    local_path = TMP_DIR / f"clip_{time.time()}.mp4"
    r = requests.get(video_url, stream=True)
    with open(local_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
            
    return str(local_path)


def main():
    scenes, video_title = analyze_live_trends_for_t2v()
    video_clips = []

    for idx, scene in enumerate(scenes):
        logger.info(f"🎬 Processing Clip {idx+1}/{len(scenes)}...")
        video_file_path = render_video_cloud(scene["prompt"])
        
        clip = VideoFileClip(video_file_path)
        
        # 🎬 9:16 VERTICAL CROP
        clip_resized = clip.resized(height=1920)
        vertical_clip = clip_resized.cropped(x_center=clip_resized.w / 2, width=1080)

        # 📝 TEXT OVERLAY
        txt_clip = TextClip(
            text=scene["text"],
            font_size=55,
            color='yellow',
            stroke_color='black',
            stroke_width=3,
            method='caption',
            size=(900, 300)
        ).with_duration(vertical_clip.duration).with_position(('center', 0.70), relative=True)

        # 🔊 TTS AUDIO
        tts_path = TMP_DIR / f"tts_{idx}.mp3"
        gTTS(text=scene["text"], lang='en').save(str(tts_path))
        audio_clip = AudioFileClip(str(tts_path))
        if audio_clip.duration > vertical_clip.duration:
            audio_clip = audio_clip.subclipped(0, vertical_clip.duration)

        composite = CompositeVideoClip([vertical_clip, txt_clip]).with_audio(audio_clip)
        video_clips.append(composite)

    if not video_clips:
        logger.error("❌ No video clips were processed.")
        sys.exit(1)

    try:
        logger.info("🎬 Stitching video clips & finalizing MP4...")
        final_video = concatenate_videoclips(video_clips, method="compose")
        output_file = OUT_DIR / "short_video.mp4"
        final_video.write_videofile(str(output_file), fps=24, codec="libx264", audio_codec="aac", logger=None)
        logger.info(f"✅ Final video saved: {output_file}")

        # 🚀 YOUTUBE UPLOAD & AUTO-LIKE
        if os.path.exists('token.json'):
            logger.info("🚀 Uploading to YouTube Shorts...")
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
            logger.info(f"🎉 Successfully uploaded! Video ID: {video_id}")

            if video_id:
                try:
                    youtube.videos().rate(id=video_id, rating='like').execute()
                    logger.info("👍 Auto-liked!")
                except Exception as like_error:
                    logger.warning(f"⚠️ Auto-like skipped: {like_error}")

    except Exception as e:
        logger.error(f"Render/Upload Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
