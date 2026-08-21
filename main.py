import os
import glob
import random
import time
import xml.etree.ElementTree as ET
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import google.generativeai as genai
from gtts import gTTS
from moviepy.editor import AudioFileClip, VideoClip, CompositeAudioClip
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# --- YOUTUBE TAM YETKİ KAPSAMI (YÜKLEME, LIKE VE COMMENT İÇİN) ---
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']

# --- GITHUB SECRETS DOSYA DÖNÜŞTÜRÜCÜ ---
if os.getenv("YOUTUBE_CLIENT_SECRET") and not os.path.exists("client_secret.json"):
    with open("client_secret.json", "w") as f:
        f.write(os.getenv("YOUTUBE_CLIENT_SECRET"))

if os.getenv("TOKEN_JSON") and not os.path.exists("token.json"):
    with open("token.json", "w") as f:
        f.write(os.getenv("TOKEN_JSON"))

# --- GEMINI AI KURULUMU ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# --- 1. FULL AI TREND VE KONU TESPİTİ ---
def get_trending_topic():
    print("[1/6] Canlı ilginç konu/trend sorgulanıyor...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            items = root.findall('.//item/title')
            if items and items[0].text:
                topic = items[0].text
                print(f"Google Trends Konusu: {topic}")
                return topic
    except Exception as e:
        print(f"Google Trends çekilemedi ({e}), AI canlı konu üretiyor...")

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            "Give me 1 single fascinating real-world subject (a famous landmark, natural wonder, "
            "deep sea marvel, or space object). Return ONLY the subject name. "
            "Do NOT include punctuation, numbers, or extra words."
        )
        response = model.generate_content(prompt)
        topic = response.text.strip().replace('"', '').replace('.', '')
        print(f"Gemini AI Tarafından Üretilen Canlı Konu: {topic}")
        return topic
    except Exception as e:
        print(f"AI Konu Üretim Hatası: {e}")
        return "The Sun"

# --- 2. DİNAMİK BRITANNICA FUN FACT & YORUM ÜRETİCİ ---
def generate_britannica_fact(topic):
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = (
        f"You are a Britannica encyclopedia expert. Generate 1 mind-blowing, 100% true, "
        f"concrete fun fact EXCLUSIVELY about '{topic}'. "
        f"MUST include specific numbers, measurements, dates, or scale comparisons related ONLY to {topic}. "
        f"CRITICAL: Do NOT mention any other landmark or unrelated entity. "
        f"Keep it to 15-20 words max for YouTube Shorts narration."
    )
    for attempt in range(1, 4):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip().replace('"', '')
            print(f"[{topic} Hakkında Gerçek Bilgi]: {text}")
            return text
        except Exception as e:
            print(f"Gemini Fact Hatası (Deneme {attempt}): {e}")
            time.sleep(10)
            
    return f"The {topic} features some of the most extraordinary measurements in nature."

def generate_dynamic_comment(topic, fact_text):
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"Write a 1-sentence engaging question for YouTube viewers specifically about this fact on '{topic}': '{fact_text}'."
    try:
        response = model.generate_content(prompt)
        return response.text.strip().replace('"', '')
    except Exception as e:
        return f"What surprises you the most about {topic}?"

# --- 3. AI GÖRSEL ÜRETİMİ ---
def generate_100pct_ai_video(prompt_text):
    print(f"[2/6] Yüksek çözünürlüklü AI görsel üretiliyor: '{prompt_text}'...")
    encoded = requests.utils.quote(prompt_text)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&model=flux&seed={int(time.time())}"
    
    res = requests.get(url, timeout=30)
    if res.status_code == 200:
        path = "generated_image.jpg"
        with open(path, "wb") as f:
            f.write(res.content)
        return path
    raise Exception("Görsel üretilemedi.")

# --- ALTYAZI VE DİNAMİK ZOOM ---
def add_subtitles_and_motion(image_path, text, duration):
    raw_img = Image.open(image_path).convert("RGB")
    base_img = ImageOps.fit(raw_img, (1080, 1920), method=Image.Resampling.LANCZOS)
    
    draw = ImageDraw.Draw(base_img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 52)
    except:
        font = ImageFont.load_default()
        
    words = text.split()
    lines, current_line = [], []
    for w in words:
        current_line.append(w)
        if len(" ".join(current_line)) > 18:
            lines.append(" ".join(current_line[:-1]))
            current_line = [w]
    if current_line:
        lines.append(" ".join(current_line))
    
    y_start = 1300
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (1080 - w) // 2
        y = y_start + (i * 68)
        
        draw.rectangle([x - 20, y - 5, x + w + 20, y + h + 10], fill=(0, 0, 0, 200))
        draw.text((x, y), line, font=font, fill=(255, 255, 0))

    img_np = np.array(base_img)

    def make_frame(t):
        zoom = 1.0 + 0.10 * (t / duration)
        h, w, _ = img_np.shape
        new_h, new_w = int(h / zoom), int(w / zoom)
        top = (h - new_h) // 2
        left = (w - new_w) // 2
        
        cropped = img_np[top:top+new_h, left:left+new_w]
        pil_crop = Image.fromarray(cropped).resize((1080, 1920), Image.Resampling.LANCZOS)
        return np.array(pil_crop)

    return VideoClip(make_frame, duration=duration)

# --- 4. MONTAJ, AI SESLENDİRME VE TELİFSİZ MÜZİK ---
def process_media(image_path, topic):
    print("[3/6] Dikey video, AI seslendirmesi, telifsiz müzik ve altyazı montajlanıyor...")
    audio_file = "voice.mp3"
    output_filename = "final_shorts.mp4"
    
    fact_text = generate_britannica_fact(topic)
    
    tts = gTTS(text=fact_text, lang='en', slow=False)
    tts.save(audio_file)
    voice_clip = AudioFileClip(audio_file)
    duration = voice_clip.duration

    audio_tracks = [voice_clip]
    music_files = glob.glob("assets/music/*.mp3")
    
    if music_files:
        selected_music = random.choice(music_files)
        print(f"Fon müziği eklendi: {selected_music}")
        bg_music = AudioFileClip(selected_music).subclip(0, duration).volumex(0.15)
        audio_tracks.append(bg_music)
    else:
        print("Uyarı: 'assets/music' klasöründe mp3 bulunamadı, sadece dış ses kullanılacak.")

    final_audio = CompositeAudioClip(audio_tracks)
    
    video_clip = add_subtitles_and_motion(image_path, fact_text, duration)
    final_clip = video_clip.set_audio(final_audio)
        
    final_clip.write_videofile(
        output_filename, 
        codec='libx264',
        audio_codec='aac',
        fps=30
    )
    
    video_clip.close()
    voice_clip.close()
    return output_filename, fact_text

# --- 5. YOUTUBE AUTHENTICATION ---
def get_youtube_client():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        raise Exception("Geçerli token.json bulunamadı veya yetkileri yetersiz.")

    return build('youtube', 'v3', credentials=creds)

# --- 6. TAM YETKİLİ OTOMATİK YÜKLEME, BEĞENİ VE YORUM ---
def upload_and_interact(video_file, topic, fact_text):
    print("[4/6] YouTube Shorts'a yükleniyor...")
    youtube = get_youtube_client()
    
    title_hashtags = "#Shorts #FunFacts #Facts #DidYouKnow #MindBlowing"
    clean_topic_tag = topic.replace(' ', '')
    
    body = {
        'snippet': {
            'title': f"{topic} Fact You Didn't Know! 🤯 {title_hashtags}",
            'description': (
                f"Mind-blowing fun fact about {topic}: {fact_text}\n\n"
                f"#Shorts #FunFacts #Facts #DidYouKnow #MindBlowing #RandomFacts "
                f"#LearnOnYouTube #InterestingFacts #Trivia #{clean_topic_tag}"
            ),
            'tags': [
                topic, 
                'Fun Facts', 
                'Facts', 
                'Did You Know', 
                'Mind Blowing Facts', 
                'Shorts', 
                'Viral Facts', 
                'Random Facts', 
                'Trivia', 
                'Daily Facts'
            ],
            'categoryId': '27'
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False
        }
    }
    
    media = MediaFileUpload(video_file, chunksize=-1, resumable=True)
    response = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media).execute()
    video_id = response['id']
    print(f"✅ BAŞARILI: Video Yüklendi! Video ID: {video_id}")
    
    # YouTube indekslemesi için bekleme süresi
    print("[5/6] YouTube indekslemesi için 15 saniye bekleniyor...")
    time.sleep(15)
    
    # OTOMATİK BEĞENİ
    print("[6/6] Otomatik Beğeni ve Yorum Ekleniyor...")
    for attempt in range(1, 4):
        try:
            youtube.videos().rate(id=video_id, rating='like').execute()
            print("✅ Otomatik LIKE başarıyla atıldı!")
            break
        except Exception as e:
            print(f"⚠️ Beğeni Hatası (Deneme {attempt}): {e}")
            time.sleep(5)

    # OTOMATİK YORUM
    comment_text = generate_dynamic_comment(topic, fact_text)
    for attempt in range(1, 4):
        try:
            youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {
                                "textOriginal": comment_text
                            }
                        }
                    }
                }
            ).execute()
            print(f"✅ Otomatik YORUM başarıyla atıldı: '{comment_text}'")
            break
        except Exception as e:
            print(f"⚠️ Yorum Hatası (Deneme {attempt}): {e}")
            time.sleep(5)

# --- AKIŞ BAŞLATICI ---
if __name__ == "__main__":
    trend = get_trending_topic()
    prompt = f"photorealistic 8k vertical depiction of {trend}, encyclopedia style, highly detailed, cinematic lighting"
    
    generated_media = generate_100pct_ai_video(prompt)
    if generated_media and os.path.exists(generated_media):
        final_file, fact_text = process_media(generated_media, trend)
        upload_and_interact(final_file, trend, fact_text)
    else:
        raise Exception("Görsel üretilemedi.")
