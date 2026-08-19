import os
import sys
import logging
import tempfile
from pathlib import Path

from gradio_client import Client as GradioClient
from moviepy import (
    VideoFileClip,
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ai-t2v-creator")

# Setup auth token
if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    try:
        with open('token.json', 'w') as f:
            f.write(os.environ['TOKEN_JSON'])
    except Exception as e:
        logger.warning(f"token.json write error: {e}")

YT_API_KEY = os.environ.get("YT_API_KEY", None)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", None)

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="ai-t2v-"))

def analyze_live_trends_for_t2v():
    """Analyzes live YouTube trends and generates 3D English T2V prompts."""
    if not YT_API_KEY or not GEMINI_API_KEY or not GENAI_AVAILABLE:
        logger.error("❌ Missing YT_API_KEY or GEMINI_API_KEY!")
        sys.exit(1)

    logger.info("🔥 Fetching live YouTube Shorts trends...")
    youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
    
    res = youtube.search().list(
        q='viral shorts trending',
        type='video',
        videoDuration='short',
        order='viewCount',
        maxResults=10,
        part='snippet'
    ).execute()
    
    titles = [item['snippet']['title'] for item in res.get('items', [])]
    trend_context = " | ".join(titles)
    logger.info(f"📊 Current Trends: {trend_context[:120]}...")

    client = genai.Client(api_key=GEMINI_API_KEY)
    gemini_prompt = (
        f"Analyze these current viral YouTube Shorts titles: '{trend_context}'. "
        "Create 3 highly detailed English Text-to-Video AI prompts describing realistic 3D motion scenes matching what is trending right now. "
        "Also provide a short 3-word English text overlay for each scene. "
        "Do NOT use pre-fixed themes. "
        "Format output as: T2V_PROMPT|TEXT_OVERLAY for each line, separated by '---'."
    )
    
    response = client.models.generate_content(model='gemini-3.6-flash', contents=gemini_prompt)

    if not response or not response.text:
        logger.error("❌ Gemini failed to generate AI video prompts.")
        sys.exit(1)

    raw_items = [s.strip() for s in response.text.split('---') if s.strip()]
    parsed_data = []
    for item in raw_items:
        if '|' in item:
            p, t = item.split('|', 1)
            parsed_data.append({"prompt": p.strip(), "text": t.strip()})
    
    if len(parsed_data) < 3:
        logger.error("❌ Insufficient trend prompts generated.")
        sys.exit(1)

    return parsed_data[:3], f"Trending Now #{titles[0].split()[0].replace('#', '')} #shorts #ai"

def generate_ai_video_clip(prompt: str, idx: int) -> str:
    """Generates a real AI video clip from a text prompt using a free HuggingFace T2V Space."""
    logger.info(f"🤖 Generating AI Video {idx+1} for prompt: '{prompt[:40]}...'")
    output_path = TMP_DIR / f"ai_generated_{idx}.mp4"

    try:
        # Connecting to free open-source Text-to-Video AI space
        client = GradioClient("damo-vilab/text-to-video-ms-1.7b")
        result = client.predict(
            prompt,
            api_name="/predict"
        )
        
        if result and os.path.exists(result):
            os.replace(result, output_path)
            logger.info(f"✅ AI Video Clip {idx+1} successfully rendered!")
            return str(output_path)
    except Exception as e:
        logger.warning(f"Primary T2V Space busy: {e}. Trying fallback AI video model...")

    # Fallback to alternative free ZeroScope / LTX T2V Space
    try:
        client = GradioClient("fffilimonov/zeroscope_v2_xl")
        result = client.predict(
            prompt,
            0,      # seed
            24,     # frames
            api_name="/generate"
        )
        if result and os.path.exists(result):
            os.replace(result, output_path)
            logger.info(f"✅ AI Video Clip {idx+1} rendered via Fallback AI!")
            return str(output_path)
    except Exception as e:
        logger.error(f"❌ AI Video generation failed for clip {idx+1}: {e}")
        return None

def main():
    scenes, video_title = analyze_live_trends_for_t2v()
    video_clips = []

    for idx, scene in enumerate(scenes):
        ai_video_file = generate_ai_video_clip(scene["prompt"], idx)
        
        if ai_video_file and os.path.exists(ai_video_file):
            try:
                clip = VideoFileClip(ai_video_file)
                # Resize to vertical 9:16 Shorts aspect ratio
                clip = clip.resized(height=1024)

                txt_clip = TextClip(
                    text=scene["text"],
                    font_size=42,
                    color='yellow',
                    stroke_color='black',
                    stroke_width=2,
                    method='caption',
                    size=(500, 200)
                ).with_duration(clip.duration).with_position(('center', 0.75), relative=True)

                video_clips.append(CompositeVideoClip([clip, txt_clip]))
            except Exception as e:
                logger.warning(f"Error processing clip {idx+1}: {e}")

    if not video_clips:
        logger.error("❌ No AI video clips were generated. Aborting.")
        sys.exit(1)

    try:
        logger.info("🎬 Assembling final AI Shorts video...")
        final_video = concatenate_videoclips(video_clips, method="compose")
        output_file = OUT_DIR / "short_video.mp4"
        
        final_video.write_videofile(
            str(output_file), 
            fps=24, 
            codec="libx264", 
            audio_codec="aac", 
            logger=None
        )
        logger.info(f"✅ Final AI Video saved at: {output_file}")

        if os.path.exists('token.json'):
            logger.info("🚀 Uploading AI Video to YouTube Shorts...")
            creds = Credentials.from_authorized_user_file('token.json')
            youtube = build('youtube', 'v3', credentials=creds)

            body = {
                'snippet': {
                    'title': video_title,
                    'description': f'{video_title} #shorts #aivideo #trending',
                    'categoryId': '22'
                },
                'status': {
                    'privacyStatus': 'public',
                    'selfDeclaredMadeForKids': False,
                    'containsSyntheticMedia': True
                }
            }
            media = MediaFileUpload(str(output_file), chunksize=-1, resumable=True, mimetype='video/mp4')
            youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
            logger.info("🎉 AI Short video successfully published to YouTube!")

    except Exception as e:
        logger.error(f"Render/Upload Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
