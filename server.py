from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import subprocess
import threading
import queue
import re

app = Flask(__name__)
CORS(app)

progress_queue = queue.Queue()

def baixar_video(url, format_, quality):
    ydl_cmd = ["yt-dlp", "--newline"]

    if format_ == "mp3":
        ydl_cmd += ["-x", "--audio-format", "mp3"]
    else:
        if quality in ["720", "480", "360"]:
            ydl_cmd += ["-f", f"bestvideo[height<={quality}]+bestaudio/best"]
        else:
            ydl_cmd += ["-f", quality]

    ydl_cmd.append(url)

    process = subprocess.Popen(ydl_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    for line in process.stdout:
        # Tenta extrair progresso da linha
        match = re.search(r'(\d{1,3}\.\d)%', line)
        if match:
            progress = float(match.group(1))
            progress_queue.put(progress)

    progress_queue.put(100)

@app.route("/download", methods=["POST"])
def download():
    data = request.json
    url = data.get("url")
    format_ = data.get("format", "mp4")
    quality = data.get("quality", "best")

    if not url:
        return jsonify({"error": "URL não fornecida"}), 400

    threading.Thread(target=baixar_video, args=(url, format_, quality)).start()
    return jsonify({"status": "sucesso"})

@app.route("/progress")
def progress():
    def event_stream():
        while True:
            try:
                progress = progress_queue.get(timeout=30)
                yield f"data: {{\"progress\": {progress}}}\n\n"
                if progress >= 100:
                    break
            except queue.Empty:
                break
    return Response(event_stream(), mimetype="text/event-stream")

if __name__ == "__main__":
    app.run(port=5000, threaded=True)
