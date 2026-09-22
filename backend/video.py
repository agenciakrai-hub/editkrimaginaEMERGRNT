"""ffmpeg-based video-tour / reel generation from property photos (Ken Burns + fades + ambient music)."""
import os
import asyncio
import tempfile
import logging
from typing import List, Optional

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


def _font() -> Optional[str]:
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            return f
    return None


FORMATS = {
    "tour": {"w": 1280, "h": 720, "secs": 3.5, "max_photos": 30},
    "reel": {"w": 720, "h": 1280, "secs": 2.5, "max_photos": 8},
}


async def _run(args: List[str], timeout: int = 180) -> None:
    if args and args[0] == "ffmpeg":
        args = [FFMPEG_BIN] + list(args[1:])
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        raise RuntimeError(f"ffmpeg timeout tras {timeout}s")
    if proc.returncode != 0:
        tail = (stderr or b"").decode(errors="ignore")[-800:]
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {tail}")


def _esc(text: str) -> str:
    return (text or "").replace("\\", "").replace(":", " ").replace("'", "").replace("%", "")[:60]


def _motion_vf(motion: str, w: int, h: int, frames: int, fps: int) -> str:
    """Return the zoompan/scale filter chain for a given camera motion."""
    bw, bh = int(w * 1.1), int(h * 1.1)
    base = f"scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    n = max(frames - 1, 1)
    if motion == "none":
        zp = f"zoompan=z=1:d={frames}:x='{cx}':y='{cy}':s={w}x{h}:fps={fps}"
    elif motion == "zoom_in":
        zp = f"zoompan=z='min(1.0+0.0016*on,1.20)':d={frames}:x='{cx}':y='{cy}':s={w}x{h}:fps={fps}"
    elif motion == "zoom_out":
        zp = f"zoompan=z='max(1.20-0.0016*on,1.0)':d={frames}:x='{cx}':y='{cy}':s={w}x{h}:fps={fps}"
    elif motion == "dolly":
        zp = f"zoompan=z='min(1.0+0.0026*on,1.35)':d={frames}:x='{cx}':y='{cy}':s={w}x{h}:fps={fps}"
    elif motion == "pan_left":
        zp = f"zoompan=z=1.12:d={frames}:x='(iw-iw/zoom)*(1-on/{n})':y='{cy}':s={w}x{h}:fps={fps}"
    elif motion == "pan_right":
        zp = f"zoompan=z=1.12:d={frames}:x='(iw-iw/zoom)*(on/{n})':y='{cy}':s={w}x{h}:fps={fps}"
    elif motion == "tilt_up":
        zp = f"zoompan=z=1.12:d={frames}:x='{cx}':y='(ih-ih/zoom)*(1-on/{n})':s={w}x{h}:fps={fps}"
    elif motion == "tilt_down":
        zp = f"zoompan=z=1.12:d={frames}:x='{cx}':y='(ih-ih/zoom)*(on/{n})':s={w}x{h}:fps={fps}"
    else:  # ken_burns, ai, default
        zp = f"zoompan=z='min(1.0+0.0016*on,1.18)':d={frames}:x='(iw-iw/zoom)*(on/{n})':y='{cy}':s={w}x{h}:fps={fps}"
    return base + zp


async def _make_clip(item: dict, out_path: str, w: int, h: int) -> None:
    fps = 25
    secs = float(item.get("secs", 3.5))
    motion = item.get("motion", "ken_burns")
    frames = max(int(secs * fps), 2)
    vf = (
        _motion_vf(motion, w, h, frames, fps)
        + f",setsar=1,fade=t=in:st=0:d=0.4,fade=t=out:st={secs-0.4:.2f}:d=0.4,format=yuv420p"
    )
    await _run([
        "ffmpeg", "-y", "-loop", "1", "-i", item["path"],
        "-vf", vf, "-t", f"{secs}", "-r", f"{fps}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", "-pix_fmt", "yuv420p",
        "-threads", "2",
        out_path,
    ])


def _render_title_png(png_path: str, w: int, h: int, title: Optional[str], subtitle: Optional[str]) -> None:
    """Render the branded title card with Pillow (the bundled ffmpeg lacks drawtext)."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (w, h), (11, 10, 16))
    d = ImageDraw.Draw(img)
    font_path = _font()
    title = (title or "edit KRimagina")[:44]
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


async def _make_title_card(out_path: str, w: int, h: int, secs: float, title: Optional[str], subtitle: Optional[str]) -> None:
    png = out_path + ".png"
    await asyncio.to_thread(_render_title_png, png, w, h, title, subtitle)
    fps = 25
    frames = int(secs * fps)
    vf = (
        f"scale={w}:{h},zoompan=z='min(zoom+0.0009,1.08)':d={frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps},setsar=1,"
        f"fade=t=in:st=0:d=0.5,fade=t=out:st={secs-0.6:.2f}:d=0.6,format=yuv420p"
    )
    await _run([
        "ffmpeg", "-y", "-loop", "1", "-i", png,
        "-vf", vf, "-t", f"{secs}", "-r", f"{fps}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", "-pix_fmt", "yuv420p",
        "-threads", "2",
        out_path,
    ])


async def _make_music(out_path: str, duration: float) -> None:
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


async def generate_video(items: List[dict], out_path: str, fmt: str = "tour", title: Optional[str] = None, subtitle: Optional[str] = None, music: bool = True) -> str:
    """items: list of {path, motion, secs}. Falls back to Ken Burns / format defaults per item."""
    cfg = FORMATS.get(fmt, FORMATS["tour"])
    w, h, default_secs = cfg["w"], cfg["h"], cfg["secs"]
    items = items[: cfg["max_photos"]]
    if not items:
        raise RuntimeError("no_photos")
    for it in items:
        it.setdefault("motion", "ken_burns")
        it["secs"] = float(it.get("secs") or default_secs)

    with tempfile.TemporaryDirectory() as tmp:
        clips = []
        title_secs = 2.2
        title_clip = os.path.join(tmp, "title.mp4")
        await _make_title_card(title_clip, w, h, title_secs, title or "edit KRimagina", subtitle)
        clips.append(title_clip)

        for i, it in enumerate(items):
            clip = os.path.join(tmp, f"clip{i}.mp4")
            await _make_clip(it, clip, w, h)
            clips.append(clip)

        listfile = os.path.join(tmp, "list.txt")
        with open(listfile, "w") as f:
            for c in clips:
                f.write(f"file '{c}'\n")

        concat = os.path.join(tmp, "concat.mp4")
        await _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", "-threads", "2", concat])

        total = title_secs + sum(it["secs"] for it in items)
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
