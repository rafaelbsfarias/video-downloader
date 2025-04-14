from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess

app = Flask(__name__)
CORS(app)

@app.route("/download", methods=["POST"])
def download():
    data = request.json
    url = data.get("url")
    format_ = data.get("format", "mp4")
    quality = data.get("quality", "best")

    if not url:
        return jsonify({"error": "URL não fornecida"}), 400

    try:
        ydl_cmd = ["yt-dlp", url]

        if format_ == "mp3":
            ydl_cmd += [
                "-x", "--audio-format", "mp3"
            ]
        else:
            if quality in ["720", "480", "360"]:
                ydl_cmd += ["-f", f"bestvideo[height<={quality}]+bestaudio/best"]
            else:
                ydl_cmd += ["-f", quality]

        result = subprocess.run(ydl_cmd, capture_output=True, text=True)

        return jsonify({
            "status": "sucesso",
            "output": result.stdout
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(port=5000)
