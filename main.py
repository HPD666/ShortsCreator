import os
import sys
import time
import re
import logging
import tempfile
import warnings
from pathlib import Path

# Unbuffered stdout for live progress streaming in CI/CD logs
sys.stdout.reconfigure(line_buffering=True)

# HTTP and SDK warning suppression
warnings.filterwarnings("ignore")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

import modal
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
logger = logging.getLogger("ai-t2v-creator")


# 1. MODAL IMAGE & PERSISTENT VOLUME FOR MODEL CACHING
cache_volume = modal.Volume.from_name("ai-model-cache", create_if_missing=True)

modal_image = (
    modal.Image.debian_slim()
    .pip_install(
        "diffusers",
        "transformers",
        "accelerate",
        "torch",
        "sentencepiece",
        "imageio-ffmpeg",
        "hf-transfer",
        "huggingface_hub"
    )
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "HF_HOME": "/cache"  # Redirect HuggingFace downloads to persistent volume
    })
)

app = modal.App("ai-t2v-creator", image=modal_image)


# 2. GPU RENDERER WITH MOUNTED PERSISTENT VOLUME
@app.cls(
    gpu="a10g", 
    cpu=4.0, 
    memory=32768, 
    timeout=1200, 
    retries=0, 
    volumes={"/cache": cache_volume}
)
class VideoGenerator:
    @modal.enter()
    def load_model(self):
        import torch
        from diffusers import LTXPipeline

        print("⚡ Loading photorealistic LTX-Video model from persistent volume...", flush=True)
        self.pipe = LTXPipeline.from_pretrained(
            "Lightricks/LTX-Video",
            torch_dtype=torch.bfloat16
        )
        self.pipe.enable_model_cpu_offload()
        if hasattr(self.pipe, "enable_vae_slicing"):
            self.pipe.enable_vae_slicing()
        
        # Save cache state to persistent volume
        cache_volume.commit()
        print("✅ Container loaded and model persistent cache committed!", flush=True)

    @modal.method()
    def render_all(self, prompts: list) -> list:
        import gc
        import torch
        import tempfile
        from diffusers.utils import export_to_video

        rendered_list = []
        for idx, prompt in enumerate(prompts):
            gc.collect()
            torch.cuda.empty_cache()

            print(f"🎬 Rendering Video {idx+1}/{len(prompts)}: '{prompt[:40]}...'", flush=True)
            
            video_frames = self.pipe(
                prompt=prompt,
                num_inference_steps=20,
                height=512,
                width=512,
                num_frames=25,
                guidance_scale=3.0,
            ).frames[0]

            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                export_to_video(video_frames, tmp.name, fps=8)
                with open(tmp.name, "rb") as f:
                    rendered_list.append(f.read())

            gc.collect()
            torch.cuda.empty_cache()
            print(f"✅ Video {idx+1} rendered!", flush=True)

        return rendered_list


# OAuth Token Management
if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    try:
        with open('token.json', 'w') as f:
            f.write(os.environ['TOKEN_JSON'])
    except Exception as e:
        logger.warning(f"token.json could not be written: {e}")

YT_API_KEY = os.environ.get("YT_API_KEY", None)

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="ai-t2v-"))


def analyze_live_trends_for_t2v():
    if not YT_API_KEY:
        logger.error("❌ MISSING API KEY! YT_API_KEY is required.")
        sys.exit(1)

    logger.info("🔥 Live YouTube Shorts trends fetching...")
    
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
        
        # Trend başlıklarından özel karakterleri temizleyip anlamlı kelimeleri çekme
        for item in res.get('items', []):
            raw_title = item['snippet']['title']
            clean_title = re.sub(r'[^\w\s]', '', raw_title) # Noktalama işaretlerini kaldırır
            words = [w for w in clean_title.split() if len(w) > 3 and w.lower() not in ['shorts', 'video', 'http', 'https', 'with']]
            extracted_keywords.extend(words)

    except Exception as e:
        logger.warning(f"⚠️ YouTube API warning: {e}. Using fallback keywords.")

    # Çekilen gerçek trend kelimelerini birleştirme
    unique_words = list(dict.fromkeys(extracted_keywords))[:4]
    
    if unique_words:
        trend_phrase = " ".join(unique_words).title()
        final_video_title = f"{trend_phrase} Trend #trend #viral #shorts"
    else:
        final_video_title = "Epic Extreme Action Challenge Trend #trend #viral #shorts"

    logger.info(f"📌 Generated Title: '{final_video_title}'")

    # Fotogerçekçi ve yüksek kaliteli T2V prompt yapıları
    parsed_data = [
        {
            "prompt": "Cinematic photorealistic 8k dynamic action shot of a real person performing an extreme movement, dramatic studio cinematic lighting, ultra detailed",
            "text": "EPIC ACTION"
        },
        {
            "prompt": "Hyper-realistic slow motion cinematic video of a professional athlete completing an intense viral challenge, 4k movie quality, high speed action",
            "text": "UNREAL SKILL"
        },
        {
            "prompt": "Photorealistic 8k close up video of a person performing a high-energy action stunt, realistic skin textures, cinematic lighting",
            "text": "MUST WATCH"
        }
    ]

    return parsed_data, final_video_title


def main():
    scenes, video_title = analyze_live_trends_for_t2v()
    video_clips = []

    logger.info("🚀 Modal GPU session launching...")
    with app.run():
        generator = VideoGenerator()
        prompts = [scene["prompt"] for scene in scenes]
        
        rendered_bytes_list = generator.render_all.remote(prompts)

        for idx, (scene, video_bytes) in enumerate(zip(scenes, rendered_bytes_list)):
            output_path = TMP_DIR / f"ai_generated_{idx}.mp4"
            with open(output_path, "wb") as f:
                f.write(video_bytes)

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"✅ Processing Clip {idx+1}/3...")
                clip = VideoFileClip(str(output_path))

                # 🎬 9:16 VERTICAL CROP
                clip_resized = clip.resized(height=1920)
                vertical_clip = clip_resized.cropped(
                    x_center=clip_resized.w / 2, 
                    width=1080
                )

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
                tts_path = TMP_DIR / f"tts_audio_{idx}.mp3"
                tts = gTTS(text=scene["text"], lang='en')
                tts.save(str(tts_path))

                audio_clip = AudioFileClip(str(tts_path))
                if audio_clip.duration > vertical_clip.duration:
                    audio_clip = audio_clip.subclipped(0, vertical_clip.duration)

                composite = CompositeVideoClip([vertical_clip, txt_clip]).with_audio(audio_clip)
                video_clips.append(composite)

    if not video_clips:
        logger.error("❌ No AI video clips were generated.")
        sys.exit(1)

    try:
        logger.info("🎬 Stitching video clips & finalizing MP4...")
        final_video = concatenate_videoclips(video_clips, method="compose")
        output_file = OUT_DIR / "short_video.mp4"
        
        final_video.write_videofile(
            str(output_file), 
            fps=24, 
            codec="libx264", 
            audio_codec="aac", 
            logger=None
        )
        logger.info(f"✅ Final video saved: {output_file}")

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
