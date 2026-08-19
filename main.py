import os
import sys
import logging
import tempfile
from pathlib import Path

from huggingface_hub import InferenceClient
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

if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    try:
        with open('token.json', 'w') as f:
            f.write(os.environ['TOKEN_JSON'])
    except Exception as e:
        logger.warning(f"token.json yazılamadı: {e}")

YT_API_KEY = os.environ.get("YT_API_KEY", None)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", None)
HF_TOKEN = os.environ.get("HF_TOKEN", None)

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="ai-t2v-"))

def analyze_live_trends_for_t2v():
    if not YT_API_KEY or not GEMINI_API_KEY or not GENAI_AVAILABLE:
        logger.error("❌ EKSIK API KEY! YT_API_KEY ve GEMINI_API_KEY tanımlı olmalıdır.")
        sys.exit(1)

    logger.info("🔥 Live YouTube Shorts trends fetching...")
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

    client = genai.Client(api_key=GEMINI_API_KEY)
    gemini_prompt = (
        f"Based on trends: '{trend_context}'. "
        "Write 3 detailed English prompts for realistic 3D cinematic animated motion scenes. "
        "Also provide a 3-word English overlay text for each scene. "
        "Format output: T2V_PROMPT|TEXT_OVERLAY for each line, separated by '---'."
    )
    
    response = client.models.generate_content(model='gemini-3.6-flash', contents=gemini_prompt)

    if not response or not response.text:
        logger.error("❌ Gemini trend analizinde hata oluştu.")
        sys.exit(1)

    raw_items = [s.strip() for s in response.text.split('---') if s.strip()]
    parsed_data = []
    for item in raw_items:
        if '|' in item:
            p, t = item.split('|', 1)
            parsed_data.append({"prompt": p.strip(), "text": t.strip()})
    
    if len(parsed_data) < 3:
        logger.error("❌ Yetersiz sayıda prompt üretildi.")
        sys.exit(1)

    
return parsed_data[:3], "#trend #viral #shorts"


def generate_ai_video_clip(prompt: str, idx: int) -> str:
    logger.info(f"🤖 Generating AI Video {idx+1} with HF InferenceClient: '{prompt[:40]}...'")
    output_path = TMP_DIR / f"ai_generated_{idx}.mp4"

    if not HF_TOKEN:
        logger.error("❌ HF_TOKEN ortam değişkeni bulunamadı!")
        return None

    # Hugging Face InferenceClient
    client = InferenceClient(token=HF_TOKEN)

    # Sunucu tarafında aktif çalışan modeller
    models_to_try = [
        "Lightricks/LTX-Video",
        "tencent/HunyuanVideo",
        "damo-vilab/text-to-video-ms-1.7b"
    ]

    for model_name in models_to_try:
        try:
            logger.info(f"🔄 Requesting model: {model_name}...")
            video_bytes = client.text_to_video(prompt, model=model_name)
            
            with open(output_path, "wb") as f:
                f.write(video_bytes)

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"✅ AI Video Clip {idx+1} generated from {model_name}!")
                return str(output_path)
        except Exception as e:
            logger.warning(f"Model {model_name} failed: {e}")

    # GradioClient alternatif bağlantı testi (Headers auth ile)
    try:
        from gradio_client import Client as GradioClient
        logger.info("🔄 Trying GradioClient with Authorization header fallback...")
        g_client = GradioClient("Lightricks/LTX-Video-Demo", headers={"Authorization": f"Bearer {HF_TOKEN}"})
        result = g_client.predict(prompt, api_name="/generate_video")
        video_file = result[0] if isinstance(result, (list, tuple)) else result
        if video_file and os.path.exists(video_file):
            os.replace(video_file, output_path)
            return str(output_path)
    except Exception as e:
        logger.warning(f"Gradio fallback failed: {e}")

    logger.error(f"❌ All T2V attempts failed for clip {idx+1}.")
    return None

def main():
    scenes, video_title = analyze_live_trends_for_t2v()
    video_clips = []

    for idx, scene in enumerate(scenes):
        ai_video_file = generate_ai_video_clip(scene["prompt"], idx)
        
        if ai_video_file and os.path.exists(ai_video_file):
            try:
                clip = VideoFileClip(ai_video_file).resized(height=1024)

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
                logger.warning(f"Klip işleme hatası ({idx+1}): {e}")

    if not video_clips:
        logger.error("❌ Hiçbir AI video klibi oluşturulamadı. İşlem durduruluyor.")
        sys.exit(1)

    try:
        logger.info("🎬 Final video kurgulanıyor...")
        final_video = concatenate_videoclips(video_clips, method="compose")
        output_file = OUT_DIR / "short_video.mp4"
        
        final_video.write_videofile(
            str(output_file), 
            fps=24, 
            codec="libx264", 
            audio_codec="aac", 
            logger=None
        )
        logger.info(f"✅ Final AI video kaydedildi: {output_file}")

        if os.path.exists('token.json'):
            logger.info("🚀 YouTube Shorts'a yükleniyor...")
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
            logger.info("🎉 Video YouTube Shorts'a yüklendi!")

    except Exception as e:
        logger.error(f"Render/Yükleme hatası: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
