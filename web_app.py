from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
import os

from yt_shorts import download_video, parse_segments, ratio_from_string, resolution_from_arg, process_segments, infer_prefix


app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET", "dev")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
    url = request.form.get("url", "").strip()
    segments_spec = request.form.get("segments", "").strip()
    aspect_str = request.form.get("aspect", "9:16").strip()
    resolution_str = request.form.get("resolution", "").strip() or None
    fps = int(request.form.get("fps", "30"))

    if not url:
        flash("Vui lòng nhập link YouTube")
        return redirect(url_for("index"))

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    aspect = ratio_from_string(aspect_str)

    tmpdir = Path(".tmp")
    tmpdir.mkdir(exist_ok=True)
    video_path = download_video(url, tmpdir)

    from moviepy.editor import VideoFileClip
    clip = VideoFileClip(str(video_path))
    duration = clip.duration
    clip.close()

    if not segments_spec:
        flash("Vui lòng nhập khoảng cắt")
        return redirect(url_for("index"))

    segments = parse_segments(segments_spec, duration)
    resolution = resolution_from_arg(resolution_str, aspect)

    prefix = infer_prefix(video_path)
    outputs = process_segments(video_path, segments, aspect, resolution, fps, output_dir, prefix)

    return render_template("result.html", files=[p.name for p in outputs])


@app.route("/download/<name>")
def download(name: str):
    d = Path("output")
    return send_from_directory(d, name, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=True)

