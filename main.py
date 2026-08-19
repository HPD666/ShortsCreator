import os
import sys
import time
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

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', force=True)
logger = logging.getLogger("ai-t2v-creator")


# 1. MODAL IMAGE WITH HIGH-SPEED HF-TRANSFER ENABLED
modal_image = (
    modal.Image.debian_slim()
    .pip_install(
        "diffusers",
        "transformers",
        "accelerate",
        "torch",
        "sentencepiece",
        "imageio-ffmpeg",
        "hf-transfer"
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

app = modal.App("ai-t2v-creator", image=modal_image)


# 2. MODAL GPU CLASS WITH EXPLICIT STEP LOGGING
@app.cls(gpu="a10g", timeout=900)
class VideoGenerator:
    @modal.enter()
    def load_model(self):
        import torch
        from diffusers import LTXPipeline
        print("⚡ [GPU Container] Starting LTX-Video model load...", flush=True)
        self.pipe = LTXPipeline.from_pretrained(
            "Lightricks/LTX-Video",
            torch_dtype=torch.bfloat16
        ).to("cuda")
        
        # Memory optimization settings
        self.pipe.enable_model_cpu_offload()
        if hasattr(self.pipe, "enable_vae_slicing"):
            self.pipe.enable_vae_slicing()
            
        print("✅ [GPU Container] Model successfully loaded into VRAM!", flush=True)

    @modal.method()
    def render(self, prompt: str) -> bytes:
        import tempfile
        from diffusers.utils import export_to_video

        print(f"🎬 [GPU Container] Rendering video prompt: '{prompt[:50]}...'", flush=True)
        video_frames = self.pipe(
            prompt=prompt,
            num_inference_steps=25,
            height=512,
            width=512,
            num_frames=25,
        ).frames[0]

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            export_to_video(video_frames, tmp.name, fps=8)
            with open(tmp.name, "rb") as f:
                data = f.read()
            print("✅ [GPU Container] Frame rendering complete!", flush=True)
            return data


# OAuth Token Management
if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    try:
        with open('token.json', 'w') as f:
            f.write(os.environ['TOKEN_JSON'])
    except Exception as e:
        logger.warning(f"token.json could not be written: {e}")

YT_API_KEY = os.environ.get("YT_API_KEY", None)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", None)

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="ai-t2v-"))


def analyze_live_trends_for_t2v():
    if not YT_API_KEY or not GEMINI_API_KEY or not GENAI_AVAILABLE:
        logger.error("❌ MISSING API KEYS! Both YT_API_KEY and GEMINI_API_KEY are required.")
        sys.exit(1)

    logger.info("🔥 Live YouTube Shorts trends fetching...")
    youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
    
    res = youtube.search().list(
        q='viral shorts trending action challenge',
        type='video',
        videoDuration='short',
        order='viewCount',
        maxResults=10,
        part='snippet'
    ).execute()
    
    titles = [item['snippet']['title'] for item in res.get('items', [])]
    trend_context = " | ".join(titles)

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    gemini_prompt = (
        f"Analyze these trending YouTube Shorts titles: '{trend_context}'. "
        "Identify the core trending visual action or concept (e.g., flying, jumping, superhero motion, viral challenge). "
        "Write 3 detailed English text-to-video prompts depicting a REAL PERSON or REALISTIC CHARACTER performing that exact trending action. "
        "CRITICAL: Style MUST BE hyper-realistic, photorealistic, 8k resolution, cinematic movie scene. Do NOT make it cartoon. "
        "Also provide a catchy 3-word English overlay text for each scene. "
        "Format output: T2V_PROMPT|TEXT_OVERLAY for each line, separated by '---'."
    )
    
    response = None
    models_to_try = ['gemini-3.6-flash', 'gemini-2.5-flash', 'gemini-2.0-flash']
    
    for model_name in models_to_try:
        for attempt in range(3):
            try:
                logger.info(f"🤖 Requesting Gemini model: {model_name} (Attempt {attempt + 1}/3)...")
                response = client.models.generate_content(model=model_name, contents=gemini_prompt)
                if response and response.text:
                    logger.info(f"✅ Gemini response successfully received ({model_name}).")
                    break
            except Exception as e:
                logger.warning(f"⚠️ {model_name} (Attempt {attempt + 1}) failed: {e}")
                time.sleep(3)
        
        if response and response.text:
            break

    if not response or not response.text:
        logger.error("❌ Gemini trend analysis failed.")
        sys.exit(1)

    raw_items = [s.strip() for s in response.text.split('---') if s.strip()]
    parsed_data = []
    for item in raw_items:
        if '|' in item:
            p, t = item.split('|', 1)
            parsed_data.append({"prompt": p.strip(), "text": t.strip()})
    
    if len(parsed_data) < 3:
        logger.error("❌ Insufficient prompts generated.")
        sys.exit(1)

    return parsed_data[:3], "#trend #viral #shorts"


def main():
    scenes, video_title = analyze_live_trends_for_t2v()
    video_clips = []

    logger.info("🚀 Modal GPU session launching...")
    with app.run():
        generator = VideoGenerator()
        for idx, scene in enumerate(scenes):
            logger.info(f"🤖 Generating AI Video {idx+1}/3 on Modal GPU...")
            output_path = TMP_DIR / f"ai_generated_{idx}.mp4"

            try:
                video_bytes = generator.render.remote(scene["prompt"])
                with open(output_path, "wb") as f:
                    f.write(video_bytes)

                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    logger.info(f"✅ AI Video Clip {idx+1} rendered and received locally!")
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

            except Exception as e:
                logger.error(f"❌ Error processing clip {idx+1}: {e}")

    if not video_clips:
        logger.error("❌ No AI video clips were generated. Aborting execution.")
        sys.exit(1)

    try:
        logger.info("🎬 Combining clips and rendering final audio-video stream...")
        final_video = concatenate_videoclips(video_clips, method="compose")
        output_file = OUT_DIR / "short_video.mp4"
        
        final_video.write_videofile(
            str(output_file), 
            fps=24, 
            codec="libx264", 
            audio_codec="aac", 
            logger=None
        )
        logger.info(f"✅ Final video created: {output_file}")

        if os.path.exists('token.json'):
            logger.info("🚀 Uploading to YouTube Shorts...")
            creds = Credentials.from_authorized_user_file('token.json')
            youtube = build('youtube', 'v3', credentials=creds)

            body = {
                'snippet': {
                    'title': video_title,
                    'description': f'{video_title} #shorts #trending',
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

            # 🚀 AUTO-LIKE UPLOADED VIDEO
            if video_id:
                try:
                    youtube.videos().rate(id=video_id, rating='like').execute()
                    logger.info("👍 Video automatically liked!")
                except Exception as like_error:
                    logger.warning(f"⚠️ Unable to auto-like video: {like_error}")

    except Exception as e:
        logger.error(f"Render/Upload Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
