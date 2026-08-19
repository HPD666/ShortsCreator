import os, sys, logging, tempfile, requests, json
from pathlib import Path
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload
from moviepy import VideoFileClip, AudioFileClip   # ✅ güncel import
from gradio_client import Client

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("shorts-global")

# Secrets
YT_API_KEY = os.environ.get("YT_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
HF_TOKEN = os.environ.get("HF_TOKEN")
if "TOKEN_JSON" in os.environ and os.environ["TOKEN_JSON"].strip():
    with open("token.json","w") as f: f.write(os.environ["TOKEN_JSON"])

OUT_DIR = Path("outputs"); OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="shorts-"))

# --- 1. Global Shorts Trend Discovery ---
def fetch_global_shorts():
    youtube = build("youtube","v3",developerKey=YT_API_KEY)
    res = youtube.search().list(
        part="snippet",
        type="video",
        videoDuration="short",
        order="date",
        maxResults=25
    ).execute()
    return res.get("items",[])

def pioneer_video(videos):
    if not videos:
        logger.error("❌ Hiç video bulunamadı, YouTube API boş döndü.")
        return None
    videos.sort(key=lambda x: x["snippet"]["publishedAt"])
    return videos[0]

# --- 2. Gemini Prompt ---
def gemini_prompt(title):
    headers = {"Authorization": f"Bearer {GEMINI_API_KEY}"}
    payload = {
        "contents":[{"parts":[{"text":f"Generate a cinematic English AI video prompt for a viral YouTube Shorts trend titled: {title}"}]}]
    }
    r = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
                      headers=headers,json=payload)
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

# --- 3. Video Generation (HF Spaces) ---
def generate_video(prompt):
    spaces = ["artificialguybr/CogVideoX-5B-Text2Video","fffiloni/ZeroScope-T2V"]
    out_path = TMP_DIR / "clip.mp4"
    for space in spaces:
        try:
            client = Client(space,hf_token=HF_TOKEN)
            job = client.submit(prompt=prompt,api_name="/predict")
            result = job.result(timeout=180)
            if result and os.path.exists(str(result)):
                with open(result,"rb") as src, open(out_path,"wb") as dst: dst.write(src.read())
                return str(out_path)
        except Exception as e:
            logger.warning(f"{space} failed: {e}")
    return None

# --- 4. Audio ---
def download_audio():
    url="https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3"
    path=TMP_DIR/"bg.mp3"
    r=requests.get(url); open(path,"wb").write(r.content)
    return str(path)

# --- 5. Upload ---
def upload(video_path,title):
    creds=Credentials.from_authorized_user_file("token.json")
    youtube=build("youtube","v3",credentials=creds)
    body={
        "snippet":{"title":f"{title} #shorts","description":"Global viral trend","categoryId":"22"},
        "status":{"privacyStatus":"public","selfDeclaredMadeForKids":False,"containsSyntheticMedia":True}
    }
    media=MediaFileUpload(video_path,resumable=True,mimetype="video/mp4")
    youtube.videos().insert(part="snippet,status",body=body,media_body=media).execute()
    logger.info("✅ Video YouTube'a yüklendi!")

# --- Main ---
def main():
    vids = fetch_global_shorts()
    pioneer = pioneer_video(vids)
    if pioneer is None:
        sys.exit("Trend bulunamadı, çıkış yapılıyor.")
    title = pioneer["snippet"]["title"]
    prompt = gemini_prompt(title)
    clip_path = generate_video(prompt)
    if not clip_path: sys.exit("Video üretilemedi")
    audio_path = download_audio()
    final = OUT_DIR/"short_video.mp4"
    clip = VideoFileClip(clip_path)
    audio = AudioFileClip(audio_path).subclip(0,clip.duration)
    clip = clip.set_audio(audio)
    clip.write_videofile(str(final),fps=24,codec="libx264",audio_codec="aac",logger=None)
    upload(str(final),title)

if __name__=="__main__":
    main()
