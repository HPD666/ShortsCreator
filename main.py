import os
import sys
import logging
import tempfile
import requests
import shutil
from pathlib import Path

from gradio_client import Client
from moviepy.editor import VideoFileClip, ImageClip, AudioFileClip, concatenate_videoclips
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

# Gemini SDK Güvenli Yükleme
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

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

# 1. CANLI TREND VE PROMPT ÜRETİMİ
def get_live_trend_prompts():
    default_prompts = [
        "3D Pixar style cute robot character, highly detailed, vertical 9:16, shocked looking at smartphone",
        "3D Pixar style cute robot character, highly detailed, vertical 9:16, dancing energetic viral dance",
        "3D Pixar style cute robot character, highly detailed, vertical 9:16, celebrating with colorful confetti"
    ]
    
    if not YT_API_KEY or not GEMINI_API_KEY or not GENAI_AVAILABLE:
        logger.warning("Eksik API veya kütüphane. Varsayılan 3D konsept kullanılıyor.")
        return default_prompts, "#shorts #3d #viral #trending"

    try:
        logger.info("🔥 Canlı YouTube Shorts trendleri çekiliyor...")
        youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
        res = youtube.search().list(q='shorts viral challenge', type='video', videoDuration='short', maxResults=5, part='snippet').execute()
        
        titles = [item['snippet']['title'] for item in res.get('items', [])]
        trend_context = " | ".join(titles)

        client = genai.Client(api_key=GEMINI_API_KEY)
        gemini_prompt = (
            f"YouTube Shorts trendleri: '{trend_context}'. "
            "Bu trende uygun 3D Pixar stilinde 9:16 dikey formatta 3 farklı sahne tanımı (İngilizce prompt) yaz. "
            "Yanıtı aralarında '---' olacak şekilde tek metinde ver."
        )
        
        response = client.models.generate_content(model='gemini-2.5-flash', contents=gemini_prompt)
        generated_prompts = [p.strip() for p in response.text.split('---') if p.strip()]
        
        if len(generated_prompts) >= 3:
            clean_tag = titles[0][:15].replace(' ', '').replace('#', '')
            return generated_prompts[:3], f"#shorts #trending #{clean_tag}"
    except Exception as e:
        logger.warning(f"Trend çekme hatası: {e}")
        
    return default_prompts, "#shorts #3d #viral"

# 2. GARANTİLİ VİDEO / GÖRSEL ÜRETİCİ
def generate_clip(prompt: str, idx: int, output_path: Path) -> bool:
    """Önce T2V dener; başarısız olursa 3D görseli videoya dönüştürür."""
    logger.info(f"🎬 Klip {idx+1} oluşturuluyor...")

    # Yöntem A: HuggingFace Text-To-Video Spaces
    spaces_config = [
        {"space": "damo-vilab/ModelScope-Text-To-Video-Synthesis", "api_name": "/predict"},
        {"space": "fffiloni/ZeroScope-T2V", "api_name": "/predict"}
    ]

    for config in spaces_config:
        try:
            client = Client(config["space"], token=HF_TOKEN, verbose=False) if HF_TOKEN else Client(config["space"], verbose=False)
            result = client.predict(prompt, api_name=config["api_name"])
            
            video_file = None
            if isinstance(result, str) and os.path.exists(result):
                video_file = result
            elif isinstance(result, (list, tuple)) and len(result) > 0:
                item = result[0]
                video_file = item if isinstance(item, str) else item.get("video")

            if video_file and os.path.exists(video_file) and str(video_file).endswith('.mp4'):
                shutil.copy(video_file, str(output_path))
                logger.info(f"✅ Klip {idx+1} HF T2V ile üretildi.")
                return True
        except Exception as e:
            logger.warning(f"⚠️ HF Space ({config['space']}) es geçildi: {e}")

    # Yöntem B (Garantili Yedek): 3D Dikey Görsel üret ve 3s MP4 klip yap
    try:
        logger.info(f"⚡ Klip {idx+1} için yedek motor (Görsel -> Video) çalıştırılıyor...")
        encoded_prompt = requests.utils.quote(prompt)
        img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true&seed={idx+100}"
        
        res = requests.get(img_url, timeout=45)
        if res.status_code == 200 and len(res.content) > 5000:
            temp_img = TMP_DIR / f"frame_{idx}.jpg"
            with open(temp_img, "wb") as f:
                f.write(res.content)
            
            # Görseli 3 saniyelik dikey videoya çevir
            img_clip = ImageClip(str(temp_img)).set_duration(3)
            img_clip.write_videofile(str(output_path), fps=24, codec="libx264", logger=None)
            img_clip.close()
            logger.info(f"✅ Klip {idx+1} yedek motordan başarıyla oluşturuldu.")
            return True
    except Exception as e:
        logger.error(f"❌ Yedek motor hatası: {e}")

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

# 4. ANA AKIŞ
def main():
    prompts, video_title = get_live_trend_prompts()
    audio_path = download_audio()
    video_clips = []

    for idx, prompt in enumerate(prompts):
        clip_path = TMP_DIR / f"pure_clip_{idx}.mp4"
        success = generate_clip(prompt, idx, clip_path)
        
        if success and clip_path.exists():
            try:
                clip = VideoFileClip(str(clip_path))
                video_clips.append(clip)
            except Exception as e:
                logger.warning(f"Klip okunamadı: {e}")

    if not video_clips:
        logger.error("❌ Hiçbir kaynaktan klip üretilemedi.")
        sys.exit(1)

    try:
        final_video = concatenate_videoclips(video_clips, method="compose")
        
        if os.path.exists(audio_path):
            try:
                audio_clip = AudioFileClip(audio_path)
                if audio_clip.duration > final_video.duration:
                    audio_clip = audio_clip.subclip(0, final_video.duration)
                final_video = final_video.set_audio(audio_clip)
            except Exception as e:
                logger.warning(f"Ses eklenemedi: {e}")

        output_path = OUT_DIR / "short_video.mp4"
        final_video.write_videofile(
            str(output_path), 
            fps=24, 
            codec="libx264", 
            audio_codec="aac", 
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
            logger.info("🎉 Video YouTube Shorts'a yüklendi!")

    except Exception as e:
        logger.error(f"Kurgu/Yükleme hatası: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
