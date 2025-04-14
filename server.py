from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess

app = Flask(__name__)
CORS(app)  # <--- permite chamadas da extensão

@app.route("/download", methods=["POST"])
def download():
    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({"error": "URL não fornecida"}), 400

    try:
        result = subprocess.run(["yt-dlp", url], capture_output=True, text=True)
        return jsonify({
            "status": "sucesso",
            "output": result.stdout
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(port=5000)
