import os
import json
import time
import random
import glob
import textwrap
import urllib.parse
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageOps

from google import genai

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from moviepy import ImageClip, AudioFileClip, CompositeVideoClip, CompositeAudioClip

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 1. GENİŞLETİLMİŞ KONU HAVUZU VE ÖZGÜN BİLGİ ÜRETİMİ
def generate_fact_and_image_prompt():
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY bulunamadı!")

    # Çeşitliliği ve verimi artırmak için genişletilmiş konu listesi
    topics = [
        "deep space anomalies and black holes",
        "bizarre deep sea creatures",
        "mysterious human brain phenomena",
        "unsolved ancient history trivia",
        "unusual geography and hidden places",
        "weird animal behavior and adaptations",
        "microscopic world and quantum physics facts",
        "extreme weather phenomena and natural wonders",
        "bizarre historical records and coincidences",
        "obscure tech and futuristic science facts"
    ]
    chosen_topic = random.choice(topics)
    timestamp_seed = int(time.time() * 1000)

    # Tekrarı önleyen ve spesifik detay/rakam isteyen güncel prompt
    prompt = (
        f"Generate a unique JSON response with two keys.\n"
        f"Unique Seed: {timestamp_seed}\n"
        f"Topic: {chosen_topic}\n"
        "1. 'fact': TODAY'S FACT! A 100% scientifically accurate, mind-blowing short fact in VERY SIMPLE, basic English (under 15 words). "
        "CRITICAL: Do NOT use cliché or common facts. Must include a specific number, scale, or rare detail to avoid repetition.\n"
        "2. 'image_prompt': A high quality visual prompt in English to generate a background picture representing this exact fact.\n"
        "Return ONLY raw JSON: {\"fact\": \"...\", \"image_prompt\": \"...\"}"
    )
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    candidate_models = ['gemini-3.6-flash', 'gemini-3.5-flash-lite']
    response = None

    for model_name in candidate_models:
        for attempt in range(1, 4):
            try:
                print(f"[Gemini] Model deneniyor: {model_name} (Deneme {attempt}/3)...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response and response.text:
                    break
            except Exception as e:
                print(f"⚠️ {model_name} hatası: {e}. 3sn bekleniyor...")
                time.sleep(3)
        
        if response and response.text:
            break

    if not response or not response.text:
        raise RuntimeError("Gemini API yanıt veremedi!")

    clean_text = response.text.strip()
    if "```json" in clean_text:
        clean_text = clean_text.split("```json")[1].split("```")[0].strip()
    elif "```" in clean_text:
        clean_text = clean_text.split("```")[1].split("```")[0].strip()
    
    data = json.loads(clean_text)
    fact = data.get("fact", "").strip()
    img_prompt = data.get("image_prompt", "").strip()

    print(f"[Fact]: {fact}")
    print(f"[Prompt]: {img_prompt}")
    return fact, img_prompt

# 2. ORAN BOZULMASIZ GÖRSEL VE SİNEMATİK KARANLIK VIGNETTE KATMANI
def download_ai_image(image_prompt):
    encoded_prompt = urllib.parse.quote(f"{image_prompt}, 8k resolution, cinematic lighting, masterpiece, detailed photorealism")
    seed = random.randint(100000, 999999)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&seed={seed}&enhance=true"
    
    print("AI Görseli indiriliyor...")
    resp = requests.get(url, timeout=40)
    if resp.status_code == 200:
        fixed_bg_path = "background.jpg"
        img = Image.open(BytesIO(resp.content)).convert('RGB')
        
        cropped_img = ImageOps.fit(img, (1080, 1920), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        
        vignette = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
        draw = ImageDraw.Draw(vignette)
        
        for y in range(300):
            alpha = int(180 * (1 - (y / 300)))
            draw.line([(0, y), (1080, y)], fill=(0, 0, 0, alpha))
            draw.line([(0, 1920 - y), (1080, 1920 - y)], fill=(0, 0, 0, alpha))

        final_img = Image.alpha_composite(cropped_img.convert('RGBA'), vignette)
        final_img.convert('RGB').save(fixed_bg_path, quality=95)
        return fixed_bg_path
    else:
        raise Exception("Görsel indirme başarısız oldu!")

# 3. YEREL KLASÖRDEN RASTGELE YOUTUBE KİTAPLIĞI MÜZİĞİ SEÇME
def get_local_background_music():
    music_folder = "assets/music"
    if not os.path.exists(music_folder):
        os.makedirs(music_folder, exist_ok=True)
        
    music_files = glob.glob(os.path.join(music_folder, "*.mp3"))
    
    if not music_files:
        print("⚠️ UYARI: 'assets/music' klasöründe mp3 bulunamadı. Müziksiz devam ediliyor.")
        return None
        
    selected_music = random.choice(music_files)
    print(f"✅ Seçilen Güvenli Arka Plan Müziği: {selected_music}")
    return selected_music

# 4. SİYAH KUTULU METİN KATMANI
def overlay_text_on_image(text, width=1080, height=1920):
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    font_size = 52
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    wrapped_lines = textwrap.wrap(text, width=20)
    
    line_heights = []
    line_widths = []
    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])
    
    max_line_width = max(line_widths) if line_widths else 0
    line_spacing = 16
    total_text_height = sum(line_heights) + (len(wrapped_lines) - 1) * line_spacing
    
    y_start = int(height * 0.28)
    
    padding = 32
    box_left = (width - max_line_width) // 2 - padding
    box_top = y_start - padding
    box_right = (width + max_line_width) // 2 + padding
    box_bottom = y_start + total_text_height + padding
    
    draw.rounded_rectangle(
        [box_left, box_top, box_right, box_bottom],
        radius=24,
        fill=(0, 0, 0, 215)
    )
    
    current_y = y_start
    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (width - text_w) // 2
        
        draw.text((x + 2, current_y + 2), line, font=font, fill=(0, 0, 0, 255))
        draw.text((x, current_y), line, font=font, fill=(255, 255, 255, 255))
        current_y += text_h + line_spacing

    overlay_path = "text_overlay.png"
    img.save(overlay_path)
    return overlay_path

# 5. YOUTUBE AUTHENTICATION
def get_youtube_client():
    token_raw = os.getenv("TOKEN_JSON")
    if not token_raw:
        raise ValueError("TOKEN_JSON eksik!")
    
    info = json.loads(token_raw)
    creds = Credentials(
        token=info.get("token"),
        refresh_token=info["refresh_token"],
        token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=info["client_id"],
        client_secret=info["client_secret"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    
    if creds.expired or not creds.valid:
        creds.refresh(Request())
        
    return build("youtube", "v3", credentials=creds)

# 6. GÜVENLİ YOUTUBE YÜKLEME
def upload_to_youtube(video_path, fact_text):
    youtube = get_youtube_client()
    
    body = {
        'snippet': {
            'title': f"TODAY'S FACT! {fact_text[:40]}... #Shorts",
            'description': f"{fact_text}\n\n#shorts #todaysfact #facts #didyouknow #science",
            'tags': ['shorts', 'todaysfact', 'facts', 'didyouknow'],
            'categoryId': '27'
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False
        }
    }
    
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    req = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
    res = req.execute()
    video_id = res.get('id')
    print(f"✅ Video başarıyla yüklendi! Video ID: {video_id}")

# 7. VİDEO BİRLEŞTİRME VE ZOOM-IN EFEKTİ
def build_shorts_video():
    fact_text, image_prompt = generate_fact_and_image_prompt()
    bg_path = download_ai_image(image_prompt)
    
    duration = 10.0
    overlay_path = overlay_text_on_image(fact_text)
    
    bg_clip = ImageClip(bg_path).with_duration(duration)
    zoomed_bg = bg_clip.resized(lambda t: 1 + 0.08 * (t / duration))
    final_bg_clip = CompositeVideoClip([zoomed_bg.with_position('center')], size=(1080, 1920)).with_duration(duration)
    txt_clip = ImageClip(overlay_path).with_duration(duration)
    
    bg_music_path = get_local_background_music()
    final_video = CompositeVideoClip([final_bg_clip, txt_clip])
    
    if bg_music_path:
        bg_music_clip = AudioFileClip(bg_music_path).subclipped(0, duration).with_volume_scaled(0.15)
        final_video = final_video.with_audio(bg_music_clip)

    output_video_path = "final_shorts.mp4"
    
    final_video.write_videofile(
        output_video_path,
        fps=24,
        codec='libx264',
        audio_codec='aac',
        preset='ultrafast'
    )
    
    return output_video_path, fact_text

if __name__ == "__main__":
    video_path, fact = build_shorts_video()
    upload_to_youtube(video_path, fact)
