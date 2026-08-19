import os
import sys
import logging
import tempfile
import requests
import shutil
import urllib.parse
from pathlib import Path

from gradio_client import Client
from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload
from google import genai

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("shorts-creator")

# Token Kontrolleri
if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    try:
        with open('token.json', 'w') as f:
            f.write(os.environ['TOKEN_JSON'])
    except Exception as e:
        logger.warning(f"token.json yazılamadı: {e}")

HF_TOKEN = os.environ.get("HF_TOKEN", None)
YT_API_KEY = os.environ.get("YT_API_KEY", None)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", None)

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="t2v-pipeline-"))

# 1. CANLI TREND VE PROMPT ÜRETİMİ (YouTube API + Gemini)
def get_live_trend_prompts():
    """Canlı YouTube Shorts trendlerini çeker ve Gemini ile 3D video promptlarına dönüştürür."""
    default_prompts = [
        "3D Pixar style cute robot character, realistic 3D render, vertical 9:16, looking at smartphone shocked",
        "3D Pixar style cute robot character, realistic 3D render, vertical 9:16, dancing energetic viral dance",
        "3D Pixar style cute robot character, realistic 3D render, vertical 9:16, celebrating with colorful confetti"
    ]
    
    if not YT_API_KEY or not GEMINI_API_KEY:
        logger.warning("YT_API_KEY veya GEMINI_API_KEY bulunamadı, varsayılan 3D konsept kullanılıyor.")
        return default_prompts, "#shorts #3d #viral #trending"

    try:
        logger.info("🔥 Canlı YouTube Shorts trendleri çekiliyor...")
        youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
        res = youtube.search().list(q='shorts viral challenge', type='video', videoDuration='short', maxResults=5, part='snippet').execute()
        
        titles = [item['snippet']['title'] for item in res.get('items', [])]
        trend_context = " | ".join(titles)
        logger.info(f"Yakalayan Trendler: {trend_context[:100]}...")

        client = genai.Client(api_key=GEMINI_API_KEY)
        gemini_prompt = (
            f"Şu an YouTube Shorts'ta popüler olan konular: '{trend_context}'. "
            "Bu trende uygun 3D Pixar/Disney stilinde 9:16 dikey formatta 3 farklı video sahne tanımı (İngilizce prompt) yaz. "
            "Promptlar sadece video nesnesini tarif etsin. Yanıtı aralarında '---' olacak şekilde tek metinde ver."
        )
        
        response = client.models.generate_content(model='gemini-2.5-flash', contents=gemini_prompt)
        generated_prompts = [p.strip() for p in response.text.split('---') if p.strip()]
        
        if len(generated_prompts) >= 3:
            return generated_prompts[:3], f"#shorts #trending #{titles[0][:15].replace(' ', '')}"
    except Exception as e:
        logger.warning(f"Trend çekme hatası: {e}")
        
    return default_prompts, "#shorts #3d #viral"

# 2. GERÇEK T2V VİDEO ÜRETİMİ
def generate_t2v_video(prompt: str, idx: int, output_path: Path) -> bool:
    """Aktif T2V modellerini kullanarak gerçek MP4 videosu üretir."""
    logger.info(f"🎬 Klip {idx+1} için T2V üretimi başlatıldı...")

    # Güncel çalışan Text-To-Video Gradio alanları
    spaces_config = [
        {"space": "Wan-AI/Wan2.1-T2V-1.3B", "api_name": "/generate"},
        {"space": "damo-vilab/ModelScope-Text-To-Video-Synthesis", "api_name": "/predict"},
        {"space": "PKU-YuanGroup/Open-Sora-Plan-v1.2.0", "api_name": "/predict"}
    ]

    for config in spaces_config:
        space_name = config["space"]
        api_name = config["api_name"]
        try:
            logger.info(f"🔄 HF Space deneniyor: {space_name}")
            client = Client(space_name, token=HF_TOKEN, verbose=False) if HF_TOKEN else Client(space_name, verbose=False)
            result = client.predict(prompt, api_name=api_name)
            
            video_file = None
            if isinstance(result, str) and os.path.exists(result):
                video_file = result
            elif isinstance(result, (list, tuple)) and len(result) > 0:
                item = result[0]
                if isinstance(item, str) and os.path.exists(item):
                    video_file = item
                elif isinstance(item, dict) and "video" in item:
                    video_file = item["video"]

            if video_file and os.path.exists(video_file) and video_file.endswith('.mp4'):
                shutil.copy(video_file, str(output_path))
                logger.info(f"✅ Klip {idx+1} başarıyla T2V olarak üretildi.")
                return True
        except Exception as e:
            logger.warning(f"⚠️ {space_name} başarısız: {e}")

    return False

# 3. YARDIMCI SES İNDİRİCİ
def download_audio() -> str:
    audio_path = TMP_DIR / "viral_audio.mp3"
    pixabay_url = "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3"
    try:
        res = requests.get(pixabay_url, timeout=30)
        if res.status_code == 200:
            with open(audio_path, "wb") as f:
                f.write(res.content)
            logger.info("🎵 Arka plan müziği indirildi.")
    except Exception as e:
        logger.warning(f"Müzik indirilemedi: {e}")
    return str(audio_path)

# 4. ANA AKIŞ VE ORAN DÜZELTME
def main():
    prompts, video_title = get_live_trend_prompts()
    audio_path = download_audio()
    video_clips = []

    for idx, prompt in enumerate(prompts):
        clip_path = TMP_DIR / f"pure_clip_{idx}.mp4"
        success = generate_t2v_video(prompt, idx, clip_path)
        
        if success and clip_path.exists():
            try:
                clip = VideoFileClip(str(clip_path))
                
                # Yamukluğu Önleme: 9:16 (1080x1920) Dikey Formata Çözünürlük Sabitleme
                w, h = clip.size
                target_ratio = 1080 / 1920
                current_ratio = w / h
                
                if current_ratio != target_ratio:
                    # En-boy oranını bozmadan ortalayarak kırpma ve boyutlandırma
                    clip = clip.cropped(width=min(w, int(h * target_ratio)), height=min(h, int(w / target_ratio)))
                    clip = clip.resized((1080, 1920))
                
                video_clips.append(clip)
            except Exception as e:
                logger.warning(f"Klip işlenemedi: {e}")

    if not video_clips:
        logger.error("❌ Üretilen geçerli klip bulunamadı.")
        sys.exit(0)

    try:
        final_video = concatenate_videoclips(video_clips, method="compose")
        
        if os.path.exists(audio_path):
            try:
                audio_clip = AudioFileClip(audio_path)
                if audio_clip.duration > final_video.duration:
                    audio_clip = audio_clip.subclipped(0, final_video.duration)
                final_video = final_video.with_audio(audio_clip)
            except Exception as e:
                logger.warning(f"Ses birleştirme hatası: {e}")

        output_path = OUT_DIR / "short_video.mp4"
        final_video.write_videofile(
            str(output_path), 
            fps=24, 
            codec="libx264", 
            audio_codec="aac", 
            preset="fast",
            logger=None
        )

        # YouTube Yükleme
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json')
            youtube = build('youtube', 'v3', credentials=creds)

            body = {
                'snippet': {
                    'title': video_title,
                    'description': f'{video_title} #viral #shorts',
                    'categoryId': '22'
                },
                'status': {
                    'privacyStatus': 'public',
                    'selfDeclaredMadeForKids': False,
                    'containsSyntheticMedia': True
                }
            }
            media = MediaFileUpload(str(output_path), chunksize=-1, resumable=True, mimetype='video/mp4')
            youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
            logger.info("🎉 Viral 3D Short YouTube'a yüklendi!")

    except Exception as e:
        logger.error(f"Kurgu/Yükleme hatası: {e}")
        sys.exit(0)

if __name__ == "__main__":
    main()
