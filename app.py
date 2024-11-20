
from flask import Flask, request, jsonify, render_template
import requests
import os
import uuid
from google.cloud import storage
from elevenlabs.client import ElevenLabs

# Initialize Flask app
app = Flask(__name__)

# API Keys and Configurations (Replace with actual values)
ELEVEN_LABS_API_KEY = "sk_a9680d7cbc98ccd67dc607ea34de269ffadf525369bbe239"
STUDIO_DID_API_KEY = "bWFuaXVzaXNrYXNwYXJhc0BnbWFpbC5jb20"
GCS_BUCKET = "anthropos_videos"
SERVICE_ACCOUNT_JSON = "service-account.json.json"
AVATAR_IMAGE = "greenscrimage.png"

# Function to convert text to speech
def text_to_speech(text, output_file="generated_audio.mp3"):
    try:
        client = ElevenLabs(api_key=ELEVEN_LABS_API_KEY)
        audio_stream = client.text_to_speech.convert(
            voice_id="ultIypcv8jQiHOQCSlPH",  # Replace with your preferred voice ID
            output_format="mp3_22050_32",  # Format of the output audio
            text=text
        )
        with open(output_file, 'wb') as f:
            for chunk in audio_stream:
                f.write(chunk)
        return output_file
    except Exception as e:
        print(f"Error during text-to-speech conversion: {e}")
        return None

# Function to upload files to Google Cloud Storage
def upload_to_gcs(file_name, destination_blob_name=None):
    try:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_ACCOUNT_JSON
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        if destination_blob_name is None:
            destination_blob_name = file_name
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(file_name)
        return f"https://storage.googleapis.com/{GCS_BUCKET}/{destination_blob_name}"
    except Exception as e:
        print(f"Error during file upload to GCS: {e}")
        return None

# Function to create talking video
def create_talk(image_url, audio_url):
    try:
        talk_url = "https://api.d-id.com/talks"
        headers = {
            'Authorization': f'Basic {STUDIO_DID_API_KEY}',
            "Content-Type": "application/json",
            "accept": "application/json"
        }
        payload = {
            "source_url": image_url,
            "script": {
                "type": "audio",
                "audio_url": audio_url
            },
            "config": {"result_format": "mp4"}
        }
        response = requests.post(talk_url, headers=headers, json=payload)
        if response.status_code == 201:
            return response.json().get('id')
        else:
            print(f"Failed to create talk. Response: {response.text}")
            return None
    except Exception as e:
        print(f"Error creating talk: {e}")
        return None

# Poll for video status and download
def poll_for_video(talk_id, output_file="output_video.mp4"):
    try:
        talk_url = f"https://api.d-id.com/talks/{talk_id}"
        headers = {
            'Authorization': f'Basic {STUDIO_DID_API_KEY}',
            "accept": "application/json"
        }
        while True:
            response = requests.get(talk_url, headers=headers)
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'done':
                    video_url = result.get('result_url')
                    download_video(video_url, output_file)
                    return output_file
                elif result.get('status') == 'error':
                    print("Video generation failed.")
                    return None
            else:
                print("Waiting for video to be ready...")
    except Exception as e:
        print(f"Error polling for video: {e}")
        return None

# Function to download video
def download_video(video_url, output_file="output_video.mp4"):
    try:
        video_response = requests.get(video_url, stream=True)
        if video_response.status_code == 200:
            with open(output_file, 'wb') as f:
                for chunk in video_response.iter_content(chunk_size=1024):
                    f.write(chunk)
    except Exception as e:
        print(f"Error downloading video: {e}")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
def generate():
    text = request.form.get("text")
    if not text:
        return jsonify({"error": "No text provided"}), 400

    # Generate unique IDs for files
    unique_id = uuid.uuid4().hex
    audio_file = f"audio_{unique_id}.mp3"
    video_file = f"video_{unique_id}.mp4"

    # Text to speech
    audio_path = text_to_speech(text, audio_file)
    if not audio_path:
        return jsonify({"error": "Failed to generate audio"}), 500

    # Upload files to GCS
    audio_url = upload_to_gcs(audio_path, destination_blob_name=audio_file)
    image_url = upload_to_gcs(AVATAR_IMAGE, destination_blob_name=f"image_{unique_id}.png")
    if not audio_url or not image_url:
        return jsonify({"error": "Failed to upload files to GCS"}), 500

    # Create talk
    talk_id = create_talk(image_url, audio_url)
    if not talk_id:
        return jsonify({"error": "Failed to create talk"}), 500

    # Poll for video and download
    video_path = poll_for_video(talk_id, video_file)
    if not video_path:
        return jsonify({"error": "Failed to generate video"}), 500

    return jsonify({"video_url": f"/static/{video_path}"}), 200

if __name__ == "__main__":
    app.run(debug=True)
