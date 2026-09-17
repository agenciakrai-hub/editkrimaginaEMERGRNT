"""ffmpeg-based video-tour / reel generation from property photos (Ken Burns + fades + ambient music)."""
import os
import asyncio
import tempfile
import logging

logger = logging.getLogger("watchful.video")

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font():
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            return f
    return None


FORMATS = {
    "tour": {"w": 1920, "h": 1080, "secs": 3.5, "max_photos": 30},
    "reel": {"w": 1080, "h": 1920, "secs": 2.5, "max_photos": 8},
}


async def _run(args):
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        tail = (stderr or b"").decode(errors="ignore")[-800:]
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {tail}")


def _esc(text: str) -> str:
    return (text or "").replace("\\", "").replace(":", " ").replace("'", "").replace("%", "")[:60]


async def _make_clip(img_path, out_path, w, h, secs, idx, title=None, subtitle=None):
    bw, bh = int(w * 2), int(h * 2)
    frames = int(secs * 30)
    zoom_end = 1.18
    # alternate pan for variety
    x_expr = "iw/2-(iw/zoom/2)" if idx % 2 == 0 else "(iw-iw/zoom)*(on/{})".format(frames)
    vf = (
        f"scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
        f"zoompan=z='min(zoom+0.0018,{zoom_end})':d={frames}:x='{x_expr}':"
        f"y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=30,setsar=1,"
        f"fade=t=in:st=0:d=0.4,fade=t=out:st={secs-0.4:.2f}:d=0.4,format=yuv420p"
    )
    font = _font()
    if font and (title or subtitle):
        if title:
            vf += (
                f",drawtext=fontfile={font}:text='{_esc(title)}':fontcolor=white:fontsize={int(h*0.05)}:"
                f"x=(w-text_w)/2:y=h-{int(h*0.16)}:box=1:boxcolor=black@0.45:boxborderw=20:"
                f"enable='between(t,0.4,{secs})'"
            )
        if subtitle:
            vf += (
                f",drawtext=fontfile={font}:text='{_esc(subtitle)}':fontcolor=white@0.85:fontsize={int(h*0.03)}:"
                f"x=(w-text_w)/2:y=h-{int(h*0.09)}:enable='between(t,0.4,{secs})'"
            )
    await _run([
        "ffmpeg", "-y", "-loop", "1", "-i", img_path,
        "-vf", vf, "-t", f"{secs}", "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        out_path,
    ])


async def _make_title_card(out_path, w, h, secs, title, subtitle):
    font = _font()
    frames_dur = secs
    inputs = f"color=c=0x0B0A10:s={w}x{h}:d={frames_dur}:r=30"
    vf = "format=yuv420p,fade=t=in:st=0:d=0.4,fade=t=out:st={:.2f}:d=0.5".format(secs - 0.5)
    if font:
        vf = (
            f"drawtext=fontfile={font}:text='{_esc(title)}':fontcolor=white:fontsize={int(h*0.07)}:"
            f"x=(w-text_w)/2:y=(h-text_h)/2-{int(h*0.02)}:enable='between(t,0.3,{secs})',"
        )
        if subtitle:
            vf += (
                f"drawtext=fontfile={font}:text='{_esc(subtitle)}':fontcolor=0x06B6D4:fontsize={int(h*0.035)}:"
                f"x=(w-text_w)/2:y=(h/2)+{int(h*0.05)}:enable='between(t,0.3,{secs})',"
            )
        vf += f"format=yuv420p,fade=t=in:st=0:d=0.4,fade=t=out:st={secs-0.5:.2f}:d=0.5"
    await _run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", inputs,
        "-vf", vf, "-t", f"{secs}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        out_path,
    ])


async def _make_music(out_path, duration):
    # Soft ambient A-minor pad from mixed sine tones, low volume with fades.
    await _run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=220:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=277:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=330:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-filter_complex",
        f"[0][1][2][3]amix=inputs=4:duration=longest,volume=0.10,"
        f"afade=t=in:d=1.5,afade=t=out:st={max(duration-2,0):.2f}:d=2,aformat=sample_rates=44100:channel_layouts=stereo",
        "-t", f"{duration}", out_path,
    ])


async def generate_video(img_paths, out_path, fmt="tour", title=None, subtitle=None, music=True):
    cfg = FORMATS.get(fmt, FORMATS["tour"])
    w, h, secs = cfg["w"], cfg["h"], cfg["secs"]
    img_paths = img_paths[: cfg["max_photos"]]
    if not img_paths:
        raise RuntimeError("no_photos")

    with tempfile.TemporaryDirectory() as tmp:
        clips = []
        title_secs = 2.2
        title_clip = os.path.join(tmp, "title.mp4")
        await _make_title_card(title_clip, w, h, title_secs, title or "Watchful", subtitle)
        clips.append(title_clip)

        for i, p in enumerate(img_paths):
            clip = os.path.join(tmp, f"clip{i}.mp4")
            await _make_clip(p, clip, w, h, secs, i, title=None, subtitle=None)
            clips.append(clip)

        listfile = os.path.join(tmp, "list.txt")
        with open(listfile, "w") as f:
            for c in clips:
                f.write(f"file '{c}'\n")

        concat = os.path.join(tmp, "concat.mp4")
        await _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", concat])

        total = title_secs + secs * len(img_paths)
        if music:
            try:
                musicfile = os.path.join(tmp, "music.wav")
                await _make_music(musicfile, total)
                await _run([
                    "ffmpeg", "-y", "-i", concat, "-i", musicfile,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest",
                    "-movflags", "+faststart", out_path,
                ])
            except Exception as e:
                logger.warning("music step failed, exporting silent: %s", e)
                await _run(["ffmpeg", "-y", "-i", concat, "-c", "copy", "-movflags", "+faststart", out_path])
        else:
            await _run(["ffmpeg", "-y", "-i", concat, "-c", "copy", "-movflags", "+faststart", out_path])

    return out_path
