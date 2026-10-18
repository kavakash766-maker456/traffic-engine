"""
video_editor.py
Converts a raw movie clip into a viral 9:16 Short.
- Crops/scales to 1080x1920
- Optional split-screen (60% clip / 40% ambient background)
- Auto-subtitles via faster-whisper
- Animated CTA banner overlay
- Domain watermark
"""

import os
import json
import logging
import subprocess
import tempfile
from pathlib import Path

from faster_whisper import WhisperModel
from moviepy.editor import (
    VideoFileClip, TextClip, CompositeVideoClip,
    ImageClip, ColorClip, concatenate_videoclips
)
from moviepy.video.fx.all import crop, resize
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.json"
with open(SETTINGS_PATH) as f:
    SETTINGS = json.load(f)

VS          = SETTINGS["video_settings"]
TARGET_W    = VS["output_resolution"][0]   # 1080
TARGET_H    = VS["output_resolution"][1]   # 1920
SPLIT       = VS["split_screen"]
SPLIT_RATIO = VS["split_ratio"]           # 0.6 → top 60%
WATERMARK   = VS["watermark_text"]
CTA_TEXT    = VS["cta_text"]
SUB_SIZE    = VS["subtitle_font_size"]
SUB_COLOR   = VS["subtitle_color"]
OUTPUT_DIR  = Path("output/shorts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

AMBIENT_DIR = Path("assets/ambient")
AMBIENT_DIR.mkdir(parents=True, exist_ok=True)

WHISPER_MODEL = None


def _load_whisper():
    global WHISPER_MODEL
    if WHISPER_MODEL is None:
        log.info("Loading Whisper model (base)...")
        WHISPER_MODEL = WhisperModel("base", device="cpu", compute_type="int8")
    return WHISPER_MODEL


def transcribe_clip(clip_path: Path) -> list[dict]:
    """Returns list of {start, end, text} subtitle segments."""
    model    = _load_whisper()
    segments, _ = model.transcribe(str(clip_path), beam_size=5)
    result   = [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]
    log.info(f"Transcribed {len(result)} subtitle segments.")
    return result


def _extract_best_segment(clip: VideoFileClip, duration: int = 45) -> VideoFileClip:
    """Extract the highest-energy segment from the clip."""
    total = clip.duration
    # Sample 5 windows and pick middle-ish segment as it usually has action
    if total <= duration:
        return clip
    start = max(0, total * 0.25)
    end   = min(total, start + duration)
    return clip.subclip(start, end)


def _make_vertical_clip(clip: VideoFileClip) -> VideoFileClip:
    """Crop and resize clip to fill 1080xTOP_H pixels."""
    top_h    = int(TARGET_H * SPLIT_RATIO) if SPLIT else TARGET_H
    # Resize keeping aspect ratio to fill width
    scale    = TARGET_W / clip.w
    scaled   = resize(clip, width=TARGET_W)
    # Center-crop height
    if scaled.h < top_h:
        scale2  = top_h / scaled.h
        scaled  = resize(scaled, height=top_h)
    y_offset = max(0, (scaled.h - top_h) // 2)
    cropped  = crop(scaled, x1=0, y1=y_offset, x2=TARGET_W, y2=y_offset + top_h)
    return cropped


def _make_ambient_bottom(duration: float) -> VideoFileClip | ColorClip:
    """Load ambient footage for the bottom split or use a dark color fill."""
    ambient_files = list(AMBIENT_DIR.glob("*.mp4"))
    if ambient_files:
        ambient = VideoFileClip(str(ambient_files[0])).loop(duration=duration)
        bottom_h = TARGET_H - int(TARGET_H * SPLIT_RATIO)
        ambient  = resize(ambient, width=TARGET_W)
        if ambient.h > bottom_h:
            y1      = (ambient.h - bottom_h) // 2
            ambient = crop(ambient, y1=y1, y2=y1 + bottom_h)
        return ambient
    bottom_h = TARGET_H - int(TARGET_H * SPLIT_RATIO)
    return ColorClip(size=(TARGET_W, bottom_h), color=(10, 10, 10), duration=duration)


def _build_subtitle_clips(segments: list[dict], y_base: int, duration: float) -> list[TextClip]:
    clips = []
    for seg in segments:
        if seg["end"] > duration:
            break
        txt = TextClip(
            seg["text"],
            fontsize=SUB_SIZE,
            color=SUB_COLOR,
            stroke_color="black",
            stroke_width=2,
            method="caption",
            size=(TARGET_W - 60, None),
            font="Arial-Bold",
        )
        txt = txt.set_start(seg["start"]).set_end(seg["end"])
        txt = txt.set_position(("center", y_base))
        clips.append(txt)
    return clips


def _build_watermark(duration: float) -> TextClip:
    wm = TextClip(
        WATERMARK,
        fontsize=28,
        color="white",
        stroke_color="black",
        stroke_width=1,
        font="Arial",
    )
    return wm.set_duration(duration).set_position((20, 20)).set_opacity(0.75)


def _build_cta_banner(duration: float) -> CompositeVideoClip:
    """Animated CTA banner that fades in at t=5."""
    bg = ColorClip(size=(TARGET_W, 90), color=(220, 30, 30)).set_duration(duration)
    bg = bg.set_position(("center", TARGET_H - 110)).set_opacity(0.92)
    txt = TextClip(
        CTA_TEXT,
        fontsize=34,
        color="white",
        font="Arial-Bold",
        method="label",
    ).set_duration(duration)
    txt = txt.set_position(("center", TARGET_H - 100))
    cta = CompositeVideoClip([bg, txt], size=(TARGET_W, TARGET_H)).set_start(5)
    return cta


def edit_clip(
    input_path: Path,
    movie_name: str,
    output_path: Path | None = None,
) -> Path:
    """
    Full pipeline: trim → vertical → split-screen → subs → watermark → CTA.
    Returns path to finished short.
    """
    if output_path is None:
        safe   = "".join(c if c.isalnum() or c in " _-" else "" for c in movie_name).strip().replace(" ", "_")
        output_path = OUTPUT_DIR / f"{safe}_short.mp4"

    log.info(f"Editing: {input_path.name}")
    raw_clip  = VideoFileClip(str(input_path))
    trimmed   = _extract_best_segment(raw_clip, duration=50)

    top_clip  = _make_vertical_clip(trimmed)
    duration  = top_clip.duration

    layers = []

    if SPLIT:
        bottom     = _make_ambient_bottom(duration)
        top_h      = int(TARGET_H * SPLIT_RATIO)
        bottom_h   = TARGET_H - top_h
        top_pos    = top_clip.set_position((0, 0))
        bottom_pos = bottom.set_position((0, top_h))
        bg         = ColorClip(size=(TARGET_W, TARGET_H), color=(0, 0, 0), duration=duration)
        layers     = [bg, top_pos, bottom_pos]
        sub_y_base = top_h - 100
    else:
        bg         = top_clip.set_position((0, 0))
        layers     = [bg]
        sub_y_base = TARGET_H - 250

    # Subtitles
    try:
        segments    = transcribe_clip(input_path)
        sub_clips   = _build_subtitle_clips(segments, sub_y_base, duration)
        layers.extend(sub_clips)
    except Exception as e:
        log.warning(f"Subtitle generation failed: {e}")

    # Watermark + CTA
    layers.append(_build_watermark(duration))
    layers.append(_build_cta_banner(duration))

    final = CompositeVideoClip(layers, size=(TARGET_W, TARGET_H))
    final = final.set_duration(duration)

    log.info(f"Rendering → {output_path}")
    final.write_videofile(
        str(output_path),
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        threads=4,
        logger=None,
    )

    raw_clip.close()
    log.info(f"Short ready: {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  required=True, help="Path to raw clip")
    parser.add_argument("--name",   required=True, help="Movie name")
    parser.add_argument("--output", default=None,  help="Output path")
    args = parser.parse_args()
    result = edit_clip(Path(args.input), args.name, Path(args.output) if args.output else None)
    print(f"Done: {result}")
