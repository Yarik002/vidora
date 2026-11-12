"""ffprobe / ffmpeg wrappers. Only fixed argv lists are used (no shell), file paths are ours."""

import asyncio
import json
import logging
from dataclasses import dataclass

log = logging.getLogger("vidora.worker")

# Untrusted input: ffmpeg must not follow URLs/playlists inside the file (SSRF, local file reads)
# and may only use the container demuxers we expect for video uploads.
INPUT_GUARDS = [
    "-protocol_whitelist",
    "file",
    "-format_whitelist",
    "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,avi,mpegts,flv,ogg,asf,mpeg",
]


class MediaError(Exception):
    """The file is not a usable video. Not retried."""


@dataclass
class ProbeResult:
    duration: float
    width: int
    height: int
    has_audio: bool
    format_name: str


async def _run(args: list[str], timeout: float) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise MediaError(f"{args[0]} timed out") from None
    if proc.returncode != 0:
        # stderr may contain internal paths: it goes to the log, the user gets a generic reason.
        tail = err.decode(errors="replace").strip().splitlines()[-3:]
        log.warning("%s failed: %s", args[0], " | ".join(tail)[:500])
        raise MediaError(f"{args[0]} could not decode the file")
    return out


# Containers that ffprobe may "recognize" in a non-video file (images, playlists, text).
_REJECTED_FORMATS = {
    "image2",
    "png_pipe",
    "jpeg_pipe",
    "gif",
    "webp_pipe",
    "svg_pipe",
    "tty",
    "hls",
    "concat",
}


async def probe(path: str, max_duration: float) -> ProbeResult:
    """Validates the file by its content (not by extension or Content-Type)."""
    out = await _run(
        [
            "ffprobe",
            *INPUT_GUARDS,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            path,
        ],
        timeout=60,
    )
    try:
        info = json.loads(out)
    except json.JSONDecodeError as exc:
        raise MediaError("ffprobe returned garbage") from exc

    fmt = info.get("format", {})
    format_name = fmt.get("format_name", "")
    if not format_name or set(format_name.split(",")) & _REJECTED_FORMATS:
        raise MediaError(f"unsupported container: {format_name or 'unknown'}")

    streams = info.get("streams", [])
    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        ),
        None,
    )
    if video is None:
        raise MediaError("no video stream")
    try:
        duration = float(fmt.get("duration") or video.get("duration") or 0)
    except ValueError:
        duration = 0.0
    if duration < 0.5:
        raise MediaError("video is too short or has no duration")
    if duration > max_duration:
        raise MediaError(f"video is longer than {int(max_duration)} seconds")
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    if width < 16 or height < 16 or width > 8192 or height > 8192:
        raise MediaError("unsupported resolution")
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    return ProbeResult(
        duration=duration, width=width, height=height, has_audio=has_audio, format_name=format_name
    )


def target_heights(src_height: int) -> list[int]:
    """720p and 360p like a minimal YouTube ladder; never upscale."""
    heights = [h for h in (720, 360) if h <= src_height]
    if not heights:
        heights = [src_height - src_height % 2]
    return heights


async def transcode(src: str, dst: str, height: int, has_audio: bool, timeout: float) -> None:
    args = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *INPUT_GUARDS,
        "-i",
        src,
        "-map",
        "0:v:0",
        "-vf",
        f"scale=-2:{height}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-profile:v",
        "high",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
    ]
    if has_audio:
        args += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "128k", "-ac", "2"]
    else:
        args += ["-an"]
    # faststart moves the moov atom to the beginning: playback starts before the full download.
    args += ["-movflags", "+faststart", dst]
    await _run(args, timeout=timeout)


async def thumbnail(src: str, dst: str, at_seconds: float) -> None:
    await _run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{at_seconds:.2f}",
            *INPUT_GUARDS,
            "-i",
            src,
            "-frames:v",
            "1",
            "-vf",
            "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
            "-q:v",
            "3",
            dst,
        ],
        timeout=60,
    )


async def stream_info(path: str) -> tuple[int, int, int]:
    """width, height, bitrate of a produced rendition."""
    out = await _run(
        [
            "ffprobe",
            *INPUT_GUARDS,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=bit_rate",
            "-print_format",
            "json",
            path,
        ],
        timeout=30,
    )
    info = json.loads(out)
    stream = (info.get("streams") or [{}])[0]
    return (
        int(stream.get("width") or 0),
        int(stream.get("height") or 0),
        int(info.get("format", {}).get("bit_rate") or 0),
    )
