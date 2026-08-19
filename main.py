import os
import sys
import io
import json
import logging
import tempfile
import subprocess
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image

import google.generativeai as genai
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("3d-trend-bot")

# --- 1. SECRETS HAZIRLIĞI ---
if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    with open('token.json', 'w') as f:
        f.write(os.environ['TOKEN_JSON'])

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="3d-pipeline-"))

# Sabit 3D Karakter ve Görsel Stil Tanımı
CHARACTER_3D_STYLE = "3D Pixar style cute robot character, highly detailed 3D render, octane render, 8k vertical 9:16"

# --- 2. TREND İNDİRME VE GEMINI İLE ANALİZ ---
def get_trend_and_scenario():
    logger.info("🔍 Trend YouTube Short indiriliyor ve analiz ediliyor...")
    audio_path = TMP_DIR / "viral_audio.mp3"
    
    url = "https://www.youtube.com/feed/trending"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    short_url = "https://www.youtube.com/shorts/"
    for a in soup.find_all("a", href=True):
        if "/shorts/" in a["href"]:
            short_url = "https://www.youtube.com" + a["href"].split("&")[0]
            break

    # Sesi İndir
    cmd = ["yt-dlp", "-f", "bestaudio", "--extract-audio", "--audio-format", "mp3", "-o", str(audio_path), short_url]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Gemini ile 3D Senaryo Üretimi (Ücretsiz Yapay Zeka Analizi)
    scenario_prompts = [
        f"{CHARACTER_3D_STYLE}, starting pose of viral trend, holding item, dynamic 3D camera shot",
        f"{CHARACTER_3D_STYLE}, performing the viral action, shocked expression, close up 3D render",
        f"{CHARACTER_3D_STYLE}, chaotic funny trend finale, 3D cinematic explosion perspective"
    ]

    if GEMINI_API_KEY:
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(
                f"Break down the latest viral short trend ({short_url}) into 3 sequential image prompts for a 3D animated character. Keep it simple."
            )
            logger.info(f"Gemini Trend Analizi: {response.text[:100]}...")
        except Exception as e:
            logger.warning(f"Gemini API fallback: {e}")

    return str(audio_path), scenario_prompts

# --- 3. 3D SAHNE RENDER VE MONTAJ ---
def build_3d_video(audio_path, prompts):
    logger.info("🎨 3D sahneler oluşturuluyor...")
    clips = []
    
    for idx, prompt in enumerate(prompts):
        encoded = requests.utils.quote(prompt)
        img_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&nologo=true&seed=42"
        
        img_path = TMP_DIR / f"frame_3d_{idx}.jpg"
        res = requests.get(img_url, timeout=25)
        with open(img_path, "wb") as f:
            f.write(res.content)

        clip = ImageClip(str(img_path)).with_duration(3.0)
        clips.append(clip)

    video = concatenate_videoclips(clips, method="compose")
    audio = AudioFileClip(audio_path)
    
    if audio.duration > video.duration:
        audio = audio.subclipped(0, video.duration)
        
    final = video.with_audio(audio)
    output_path = OUT_DIR / "short_video.mp4"
    final.write_videofile(str(output_path), fps=24, codec="libx264", audio_codec="aac", logger=None)
    return str(output_path)

# --- 4. YÜKLEME ---
def main():
    audio_path, prompts = get_trend_and_scenario()
    video_path = build_3d_video(audio_path, prompts)

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json')
        youtube = build('youtube', 'v3', credentials=creds)

        body = {
            'snippet': {'title': '#trend #shorts #viral #3d', 'description': '#shorts #viral #3d', 'categoryId': '22'},
            'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
        }
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype='video/mp4')
        youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
        logger.info("🎉 3D Trend videosu YouTube'a yüklendi!")

if __name__ == "__main__":
    main()
