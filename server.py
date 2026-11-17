import sys
sys.dont_write_bytecode = True
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
import subprocess
import threading
import logging
import queue
import json
import time
import re
import os
import sys
import shutil

LOG_FILE = os.path.join(os.path.dirname(__file__), "server.log")

def get_yt_dlp_cmd():
    # 1. Executável dentro do ambiente virtual ativo
    venv_bin = os.path.join(os.path.dirname(sys.executable), "yt-dlp")
    if os.path.isfile(venv_bin) and os.access(venv_bin, os.X_OK):
        return [venv_bin]
    # 2. Executável no .venv_linux do projeto
    local_venv_bin = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv_linux", "bin", "yt-dlp")
    if os.path.isfile(local_venv_bin) and os.access(local_venv_bin, os.X_OK):
        return [local_venv_bin]
    # 3. Executável no PATH do sistema
    path_bin = shutil.which("yt-dlp")
    if path_bin:
        return [path_bin]
    # 4. Fallback para módulo python
    return [sys.executable, "-m", "yt_dlp"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("video-downloader")

app = Flask(__name__)
CORS(app)

progress_queue = queue.Queue()

ITEM_RE = re.compile(r'\[download\] Downloading item (\d+) of (\d+)')
PROGRESS_RE = re.compile(r'(\d{1,3}\.\d)%')
DEST_RE = re.compile(r'\[download\] Destination: (.+)')
MERGE_RE = re.compile(r'\[Merger\] Merging formats into "(.+)"')
EXTRACT_RE = re.compile(r'\[ExtractAudio\] Destination: (.+)')
ALREADY_RE = re.compile(r'\[download\] (.+) has already been downloaded')
VIDEO_ID_RE = re.compile(r'\[youtube\] ([a-zA-Z0-9_-]{11}): Downloading webpage')
ERROR_RE = re.compile(r'ERROR:\s*(.+)')
WARN_RE = re.compile(r'WARNING:\s*(.+)')


def limpar_fila():
    while not progress_queue.empty():
        try:
            progress_queue.get_nowait()
        except queue.Empty:
            break


def emitir_evento(payload):
    payload["timestamp"] = time.strftime("%H:%M:%S")
    progress_queue.put(payload)


def baixar_video(url, format_, quality, is_playlist, save_thumb):
    output_dir = os.path.join(os.path.dirname(__file__), "downloads")
    os.makedirs(output_dir, exist_ok=True)

    cookie_file = os.path.join(os.path.dirname(__file__), "cookies.txt")
    cookie_args = ["--cookies", cookie_file] if os.path.isfile(cookie_file) else []

    ydl_cmd = [
        *get_yt_dlp_cmd(),
        *cookie_args,
        "--newline",
        "--ignore-errors",
        "-P", output_dir
    ]

    if is_playlist:
        ydl_cmd += [
            "--yes-playlist",
            "-o", "%(playlist_title, title)s/%(playlist_index)02d - %(title)s.%(ext)s"
        ]
    else:
        ydl_cmd += [
            "--no-playlist",
            "-o", "%(title)s.%(ext)s"
        ]

    if format_ == "thumb":
        ydl_cmd += [
            "--skip-download",
            "--write-thumbnail",
            "--convert-thumbnails", "jpg"
        ]
    elif format_ == "mp3":
        ydl_cmd += ["-x", "--audio-format", "mp3"]
        if save_thumb:
            ydl_cmd += [
                "--embed-thumbnail",
                "--write-thumbnail",
                "--convert-thumbnails", "jpg"
            ]
    else:
        # MP4 - Prioriza H.264 (avc1) e AAC (mp4a) para compatibilidade universal em qualquer player de vídeo
        if quality == "best":
            ydl_cmd += [
                "-f", "bestvideo[vcodec^=avc]+bestaudio[acodec^=mp4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best",
                "--merge-output-format", "mp4"
            ]
        elif quality == "worst":
            ydl_cmd += [
                "-f", "worstvideo[vcodec^=avc]+worstaudio[acodec^=mp4a]/worstvideo+worstaudio/worst",
                "--merge-output-format", "mp4"
            ]
        elif quality in ["1080", "720", "480", "360"]:
            ydl_cmd += [
                "-f", f"bestvideo[height<={quality}][vcodec^=avc]+bestaudio[acodec^=mp4a]/bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}]/best",
                "--merge-output-format", "mp4"
            ]
        else:
            ydl_cmd += ["-f", quality, "--merge-output-format", "mp4"]
        if save_thumb:
            ydl_cmd += [
                "--write-thumbnail",
                "--convert-thumbnails", "jpg"
            ]

    ydl_cmd.append(url)
    cmd_str = " ".join(ydl_cmd)
    logger.info("Iniciando comando: %s", cmd_str)
    emitir_evento({"log": f"$ {cmd_str}", "done": False})

    current_item = None
    total_items = None
    current_title = None
    current_video_id = None
    failed_items = []
    success_count = 0
    downloaded_files = []

    def registrar_arquivo(path_str):
        if not path_str:
            return
        path_clean = path_str.strip('"\';')
        if not os.path.isabs(path_clean):
            path_clean = os.path.join(output_dir, path_clean)
        try:
            rel = os.path.relpath(path_clean, output_dir)
            if rel not in downloaded_files and not rel.endswith((".part", ".ytdl", ".temp", ".tmp")):
                downloaded_files.append(rel)
        except Exception:
            pass

    try:
        process = subprocess.Popen(
            ydl_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue

            logger.info("[yt-dlp] %s", line)

            err_match = ERROR_RE.search(line)
            if err_match:
                err_msg = err_match.group(1)
                item_label = f"Item {current_item}" if current_item else (current_video_id or "vídeo")
                failed_items.append(f"{item_label}: {err_msg}")
                emitir_evento({
                    "log": f"❌ ERRO ({item_label}): {err_msg}",
                    "item_error": err_msg,
                    "current_item": current_item,
                    "total_items": total_items,
                    "failed_count": len(failed_items),
                    "done": False
                })
                continue

            warn_match = WARN_RE.search(line)
            if warn_match:
                warn_msg = warn_match.group(1)
                emitir_evento({
                    "log": f"⚠️ AVISO: {warn_msg}",
                    "done": False
                })
                continue

            vid_match = VIDEO_ID_RE.search(line)
            if vid_match:
                current_video_id = vid_match.group(1)
                emitir_evento({
                    "progress": 0,
                    "current_item": current_item,
                    "total_items": total_items,
                    "title": current_title,
                    "video_id": current_video_id,
                    "log": f"🎬 Extraindo vídeo ID: {current_video_id}",
                    "done": False
                })
                continue

            item_match = ITEM_RE.search(line)
            if item_match:
                current_item = int(item_match.group(1))
                total_items = int(item_match.group(2))
                emitir_evento({
                    "progress": 0,
                    "current_item": current_item,
                    "total_items": total_items,
                    "title": current_title,
                    "video_id": current_video_id,
                    "log": f"📋 Iniciando item {current_item} de {total_items}",
                    "done": False
                })
                continue

            merge_match = MERGE_RE.search(line)
            if merge_match:
                fpath = merge_match.group(1).strip()
                registrar_arquivo(fpath)
                current_title = os.path.basename(fpath)
                emitir_evento({
                    "current_item": current_item,
                    "total_items": total_items,
                    "title": current_title,
                    "video_id": current_video_id,
                    "log": f"🎬 Vídeo final processado: {current_title}",
                    "done": False
                })
                continue

            extract_match = EXTRACT_RE.search(line)
            if extract_match:
                fpath = extract_match.group(1).strip()
                registrar_arquivo(fpath)
                current_title = os.path.basename(fpath)
                emitir_evento({
                    "current_item": current_item,
                    "total_items": total_items,
                    "title": current_title,
                    "video_id": current_video_id,
                    "log": f"🎵 Áudio final extraído: {current_title}",
                    "done": False
                })
                continue

            already_match = ALREADY_RE.search(line)
            if already_match:
                fpath = already_match.group(1).strip()
                registrar_arquivo(fpath)
                current_title = os.path.basename(fpath)
                success_count += 1
                emitir_evento({
                    "current_item": current_item,
                    "total_items": total_items,
                    "title": current_title,
                    "video_id": current_video_id,
                    "log": f"⚡ Já baixado: {current_title}",
                    "done": False
                })
                continue

            dest_match = DEST_RE.search(line)
            if dest_match:
                filepath = dest_match.group(1).strip()
                current_title = os.path.basename(filepath)
                if not any(filepath.endswith(ext) for ext in [".f313.webm", ".f137.mp4", ".f251.webm", ".f140.m4a", ".temp.mp4", ".part"]):
                    registrar_arquivo(filepath)
                if not current_title.endswith(".jpg") and not current_title.endswith(".webp"):
                    success_count += 1
                emitir_evento({
                    "current_item": current_item,
                    "total_items": total_items,
                    "title": current_title,
                    "video_id": current_video_id,
                    "log": f"💾 Salvando: {current_title}",
                    "done": False
                })
                continue

            prog_match = PROGRESS_RE.search(line)
            if prog_match:
                progress = float(prog_match.group(1))
                emitir_evento({
                    "progress": progress,
                    "current_item": current_item,
                    "total_items": total_items,
                    "title": current_title,
                    "video_id": current_video_id,
                    "done": False
                })
            else:
                emitir_evento({
                    "log": line,
                    "done": False
                })

        process.wait()
        logger.info(
            "Processo finalizado (code=%s, sucessos=%d, falhas=%d)",
            process.returncode, success_count, len(failed_items)
        )

        arquivos_finais = []
        for rel in downloaded_files:
            abs_p = os.path.join(output_dir, rel)
            if os.path.isfile(abs_p) and not rel.endswith((".part", ".ytdl", ".temp", ".tmp")):
                if format_ == "mp3" and rel.endswith((".webm", ".m4a")):
                    continue
                if rel not in arquivos_finais:
                    arquivos_finais.append(rel)

        if not arquivos_finais and current_title:
            cand = os.path.join(output_dir, current_title)
            if os.path.isfile(cand):
                arquivos_finais.append(current_title)

        if process.returncode == 0 and not failed_items:
            emitir_evento({
                "progress": 100,
                "current_item": current_item,
                "total_items": total_items,
                "title": current_title,
                "video_id": current_video_id,
                "files": arquivos_finais,
                "log": "✅ Todos os downloads concluídos com sucesso!",
                "done": True
            })
        elif success_count > 0 or (is_playlist and total_items and len(failed_items) < total_items):
            emitir_evento({
                "progress": 100,
                "current_item": current_item,
                "total_items": total_items,
                "title": current_title,
                "video_id": current_video_id,
                "files": arquivos_finais,
                "partial_warning": f"Concluído com {len(failed_items)} falha(s) em itens da playlist.",
                "failed_items": failed_items,
                "log": f"⚠️ Concluído parcialmente ({len(failed_items)} falha(s)).",
                "done": True
            })
        else:
            detalhe = failed_items[-1] if failed_items else f"yt-dlp encerrou com código {process.returncode}"
            emitir_evento({
                "error": detalhe,
                "failed_items": failed_items,
                "log": f"❌ Falha fatal: {detalhe}",
                "done": True
            })
    except Exception as exc:
        logger.exception("Exceção ao executar yt-dlp")
        emitir_evento({
            "error": str(exc),
            "log": f"🔥 Exceção interna: {exc}",
            "done": True
        })


@app.route("/info", methods=["GET"])
def info():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "URL não fornecida"}), 400
    try:
        cookie_file = os.path.join(os.path.dirname(__file__), "cookies.txt")
        cookie_args = ["--cookies", cookie_file] if os.path.isfile(cookie_file) else []
        res = subprocess.run(
            [*get_yt_dlp_cmd(), *cookie_args, "--flat-playlist", "-J", "--playlist-items", "1", url],
            capture_output=True,
            text=True,
            timeout=10
        )
        if res.returncode == 0:
            data = json.loads(res.stdout)
            title = data.get("title")
            thumb = None
            thumbnails = data.get("thumbnails") or []
            if thumbnails:
                thumb = thumbnails[-1].get("url")
            entries = data.get("entries") or []
            if not thumb and entries:
                vid = entries[0].get("id")
                if vid:
                    thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
            return jsonify({"title": title, "thumbnail": thumb})
    except Exception as exc:
        logger.error("Erro em /info: %s", exc)
        return jsonify({"error": str(exc)}), 500
    return jsonify({}), 200


@app.route("/logs", methods=["GET"])
def get_logs():
    lines_count = int(request.args.get("lines", 100))
    if not os.path.exists(LOG_FILE):
        return jsonify({"logs": []})
    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
    return jsonify({"logs": [l.rstrip("\n") for l in all_lines[-lines_count:]]})


@app.route("/download", methods=["POST"])
def download():
    data = request.json or {}
    url = data.get("url")
    format_ = data.get("format", "mp4")
    quality = data.get("quality", "best")
    is_playlist = bool(data.get("playlist", False))
    save_thumb = bool(data.get("save_thumb", True))

    if not url:
        return jsonify({"error": "URL não fornecida"}), 400

    logger.info(
        "Nova requisição /download: url=%s, format=%s, quality=%s, playlist=%s, save_thumb=%s",
        url, format_, quality, is_playlist, save_thumb
    )
    limpar_fila()
    threading.Thread(
        target=baixar_video,
        args=(url, format_, quality, is_playlist, save_thumb),
        daemon=True
    ).start()
    return jsonify({"status": "sucesso"})


@app.route("/progress")
def progress():
    def event_stream():
        while True:
            try:
                event_data = progress_queue.get(timeout=60)
                yield f"data: {json.dumps(event_data)}\n\n"
                if event_data.get("done") or event_data.get("error"):
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'keepalive': True})}\n\n"
    return Response(event_stream(), mimetype="text/event-stream")


@app.route("/files/<path:filename>", methods=["GET", "DELETE"])
def handle_file(filename):
    output_dir = os.path.join(os.path.dirname(__file__), "downloads")
    safe_path = os.path.abspath(os.path.join(output_dir, filename))
    if not safe_path.startswith(os.path.abspath(output_dir)):
        return jsonify({"error": "Caminho inválido"}), 400

    if request.method == "DELETE":
        if not os.path.isfile(safe_path):
            return jsonify({"status": "ja_removido"}), 200
        try:
            os.remove(safe_path)
            logger.info("Arquivo removido do servidor com sucesso: %s", filename)
            parent_dir = os.path.dirname(safe_path)
            if parent_dir != os.path.abspath(output_dir) and os.path.isdir(parent_dir):
                if not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
            return jsonify({"status": "sucesso", "deleted": filename})
        except Exception as exc:
            logger.error("Erro ao remover %s: %s", filename, exc)
            return jsonify({"error": str(exc)}), 500

    # GET
    if not os.path.isfile(safe_path):
        return jsonify({"error": "Arquivo não encontrado"}), 404
    return send_from_directory(output_dir, filename, as_attachment=True)


def iniciar_auto_cleanup():
    def cleanup_loop():
        while True:
            time.sleep(120)  # Checa a cada 2 minutos
            try:
                output_dir = os.path.join(os.path.dirname(__file__), "downloads")
                if not os.path.exists(output_dir):
                    continue
                now = time.time()
                for root, dirs, files in os.walk(output_dir, topdown=False):
                    for f in files:
                        fpath = os.path.join(root, f)
                        # Remove arquivos que fiquem no servidor por mais de 15 minutos
                        if now - os.path.getmtime(fpath) > 900:
                            try:
                                os.remove(fpath)
                                logger.info("Auto-cleanup removeu arquivo expirado: %s", f)
                            except Exception:
                                pass
                    for d in dirs:
                        dpath = os.path.join(root, d)
                        if not os.listdir(dpath):
                            try:
                                os.rmdir(dpath)
                            except Exception:
                                pass
            except Exception as exc:
                logger.error("Erro no auto_cleanup: %s", exc)

    t = threading.Thread(target=cleanup_loop, daemon=True)
    t.start()


iniciar_auto_cleanup()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
