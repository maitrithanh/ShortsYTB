import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

from moviepy.editor import VideoFileClip
import yt_dlp


def download_video(url: str, output_dir: Path) -> Path:
    ydl_opts = {
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
    p = Path(filename)
    if p.exists():
        return p
    mp4 = p.with_suffix(".mp4")
    if mp4.exists():
        return mp4
    return p


def parse_time(s: str) -> float:
    if re.match(r"^\d+(\.\d+)?$", s):
        return float(s)
    m = re.match(r"^(\d+):(\d{1,2})(?::(\d{1,2}))?$", s)
    if not m:
        raise ValueError(f"Thời gian không hợp lệ: {s}")
    h = int(m.group(1))
    mm = int(m.group(2))
    ss = int(m.group(3)) if m.group(3) else 0
    return h * 3600 + mm * 60 + ss


def parse_segments(spec: str, duration: float) -> list[tuple[float, float]]:
    segments = []
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    for part in parts:
        if "-" not in part and ":" in part and part.count(":") == 1:
            a, b = part.split(":")
        else:
            a, b = part.split("-")
        start = parse_time(a)
        end = parse_time(b)
        if start < 0 or end <= start:
            raise ValueError(f"Khoảng cắt không hợp lệ: {part}")
        if start >= duration:
            continue
        end = min(end, duration)
        segments.append((start, end))
    return segments


def ratio_from_string(s: str) -> tuple[int, int]:
    m = re.match(r"^(\d+)\s*:\s*(\d+)$", s)
    if not m:
        raise ValueError("Tỷ lệ không hợp lệ, ví dụ: 9:16 hoặc 16:9")
    return int(m.group(1)), int(m.group(2))


def crop_to_ratio(clip: VideoFileClip, target_ratio: tuple[int, int]) -> VideoFileClip:
    w, h = clip.size
    trw, trh = target_ratio
    target = trw / trh
    current = w / h
    if abs(current - target) < 1e-6:
        return clip
    if current > target:
        new_w = int(h * target)
        x1 = (w - new_w) // 2
        x2 = x1 + new_w
        return clip.crop(x1=x1, y1=0, x2=x2, y2=h)
    else:
        new_h = int(w / target)
        y1 = (h - new_h) // 2
        y2 = y1 + new_h
        return clip.crop(x1=0, y1=y1, x2=w, y2=y2)


def resolution_from_arg(arg: str | None, aspect: tuple[int, int]) -> tuple[int, int]:
    if arg:
        m = re.match(r"^(\d+)x(\d+)$", arg)
        if not m:
            raise ValueError("Độ phân giải không hợp lệ, ví dụ: 1080x1920")
        return int(m.group(1)), int(m.group(2))
    if aspect == (9, 16):
        return 1080, 1920
    return 1920, 1080


def process_segments(video_path: Path, segments: list[tuple[float, float]], aspect: tuple[int, int], resolution: tuple[int, int], fps: int, output_dir: Path, prefix: str) -> list[Path]:
    outputs = []
    base = VideoFileClip(str(video_path))
    for i, (start, end) in enumerate(segments, start=1):
        sub = base.subclip(start, end)
        cropped = crop_to_ratio(sub, aspect)
        resized = cropped.resize(newsize=resolution)
        out = output_dir / f"{prefix}_part{i}.mp4"
        resized.write_videofile(
            str(out),
            codec="libx264",
            audio_codec="aac",
            fps=fps,
            threads=os.cpu_count() or 4,
            verbose=False,
            logger=None,
        )
        outputs.append(out)
    base.close()
    return outputs


def infer_prefix(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"\s+", "_", stem)
    return stem[:60]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="yt-shorts", description="Tải, cắt và tạo video tỷ lệ 9:16 hoặc 16:9 từ YouTube")
    parser.add_argument("--url", required=True, help="Link video YouTube")
    parser.add_argument("--segments", help="Danh sách khoảng cắt, ví dụ: 0:10,30:45 hoặc 00:00-00:10,00:30-00:45")
    parser.add_argument("--aspect", default="9:16", help="Tỷ lệ đầu ra, ví dụ: 9:16 hoặc 16:9")
    parser.add_argument("--resolution", help="Độ phân giải đầu ra, ví dụ: 1080x1920 hoặc 1920x1080")
    parser.add_argument("--fps", type=int, default=30, help="FPS đầu ra")
    parser.add_argument("--output", default="output", help="Thư mục lưu video")
    parser.add_argument("--keep", action="store_true", help="Giữ file gốc sau khi xử lý")
    args = parser.parse_args(argv)

    aspect = ratio_from_string(args.aspect)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        video_path = download_video(args.url, tmpdir)
        clip = VideoFileClip(str(video_path))
        duration = clip.duration
        clip.close()
        if not args.segments:
            print(f"Thời lượng: {duration:.2f}s")
            print("Nhập các khoảng cắt, ví dụ: 0:10,30:45")
            spec = input("Segments: ").strip()
        else:
            spec = args.segments.strip()
        segments = parse_segments(spec, duration)
        if not segments:
            print("Không có khoảng cắt hợp lệ")
            sys.exit(1)
        resolution = resolution_from_arg(args.resolution, aspect)
        outputs = process_segments(video_path, segments, aspect, resolution, args.fps, output_dir, infer_prefix(video_path))
        if args.keep:
            final_src = output_dir / (infer_prefix(video_path) + "_source.mp4")
            try:
                os.rename(video_path, final_src)
            except Exception:
                pass
        print("Đã tạo:")
        for p in outputs:
            print(str(p))


if __name__ == "__main__":
    main()

