"""ffmpeg-based video-tour / reel generation from property photos (Ken Burns + fades + ambient music)."""
import os
import asyncio
import tempfile
import logging

logger = logging.getLogger("watchful.video")

try:
    import imageio_ffmpeg
    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except Exception as e:  # noqa
    FFMPEG_BIN = "ffmpeg"
    logger.warning("imageio-ffmpeg not available, falling back to system ffmpeg: %s", e)

FONT_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "assets", "font.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
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
    if args and args[0] == "ffmpeg":
        args = [FFMPEG_BIN] + list(args[1:])
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        tail = (stderr or b"").decode(errors="ignore")[-800:]
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {tail}")


def _esc(text: str) -> str:
    return (text or "").replace("\\", "").replace(":", " ").replace("'", "").replace("%", "")[:60]


async def _make_clip(img_path, out_path, w, h, secs, idx):
    bw, bh = int(w * 2), int(h * 2)
    frames = int(secs * 30)
    zoom_end = 1.18
    x_expr = "iw/2-(iw/zoom/2)" if idx % 2 == 0 else "(iw-iw/zoom)*(on/{})".format(frames)
    vf = (
        f"scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
        f"zoompan=z='min(zoom+0.0018,{zoom_end})':d={frames}:x='{x_expr}':"
        f"y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=30,setsar=1,"
        f"fade=t=in:st=0:d=0.4,fade=t=out:st={secs-0.4:.2f}:d=0.4,format=yuv420p"
    )
    await _run([
        "ffmpeg", "-y", "-loop", "1", "-i", img_path,
        "-vf", vf, "-t", f"{secs}", "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        out_path,
    ])


def _render_title_png(png_path, w, h, title, subtitle):
    """Render the branded title card with Pillow (the bundled ffmpeg lacks drawtext)."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (w, h), (11, 10, 16))
    d = ImageDraw.Draw(img)
    font_path = _font()
    title = (title or "Watchful")[:44]
    if font_path:
        tf = ImageFont.truetype(font_path, int(h * 0.075))
        tb = d.textbbox((0, 0), title, font=tf)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        ty = h / 2 - th
        d.text(((w - tw) / 2, ty), title, font=tf, fill=(255, 255, 255))
        line_y = ty + th + int(h * 0.035)
        d.rectangle([w / 2 - 46, line_y, w / 2 + 46, line_y + 4], fill=(6, 182, 212))
        if subtitle:
            sub = subtitle[:60]
            sf = ImageFont.truetype(font_path, int(h * 0.033))
            sbb = d.textbbox((0, 0), sub, font=sf)
            sw = sbb[2] - sbb[0]
            d.text(((w - sw) / 2, line_y + int(h * 0.03)), sub, font=sf, fill=(6, 182, 212))
    img.save(png_path, "PNG")


async def _make_title_card(out_path, w, h, secs, title, subtitle):
    png = out_path + ".png"
    await asyncio.to_thread(_render_title_png, png, w, h, title, subtitle)
    frames = int(secs * 30)
    vf = (
        f"scale={w}:{h},zoompan=z='min(zoom+0.0009,1.08)':d={frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=30,setsar=1,"
        f"fade=t=in:st=0:d=0.5,fade=t=out:st={secs-0.6:.2f}:d=0.6,format=yuv420p"
    )
    await _run([
        "ffmpeg", "-y", "-loop", "1", "-i", png,
        "-vf", vf, "-t", f"{secs}", "-r", "30",
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
            await _make_clip(p, clip, w, h, secs, i)
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
