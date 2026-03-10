"""
Capture rover camera images from Gazebo Transport topics and save them as image files.
"""
import json
import math
import re
import struct
import subprocess
import ast
from datetime import datetime
from pathlib import Path

TOOL_SCHEMA = {
    "name": "capture_camera_image",
    "description": (
        "Capture a rover camera frame from Gazebo and save it to a real image file. "
        "Use this for MastCam/NavCam screenshots or depth-camera snapshots that can "
        "later be delivered with send_message using MEDIA:/absolute/path/to/file."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "camera": {
                "type": "string",
                "enum": ["mastcam", "navcam", "navcam_left", "hazcam_front", "hazcam_rear"],
                "description": "Which rover camera to capture.",
            },
            "output_dir": {
                "type": "string",
                "description": "Optional directory for saved images. Defaults to ~/rover_images.",
            },
            "filename": {
                "type": "string",
                "description": "Optional output filename. If omitted, a timestamped name is used.",
            },
        },
        "required": ["camera"],
    },
}

_CAMERA_SPECS = {
    "mastcam": {"topic": "/rover/mastcam", "mode": "rgb", "ext": ".jpg"},
    "navcam": {"topic": "/rover/navcam_left", "mode": "rgb", "ext": ".jpg"},
    "navcam_left": {"topic": "/rover/navcam_left", "mode": "rgb", "ext": ".jpg"},
    "hazcam_front": {"topic": "/rover/hazcam_front", "mode": "depth", "ext": ".png"},
    "hazcam_rear": {"topic": "/rover/hazcam_rear", "mode": "depth", "ext": ".png"},
}


def _read_topic(topic: str, timeout_sec: float = 10) -> str:
    result = subprocess.run(
        ["gz", "topic", "-e", "-t", topic, "-n", "1"],
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "gz topic failed").strip())
    return result.stdout or ""


def _extract_int(raw: str, field: str) -> int:
    match = re.search(rf"\b{re.escape(field)}\s*:\s*(\d+)", raw)
    if not match:
        raise ValueError(f"Missing {field} in Gazebo image payload")
    return int(match.group(1))


def _extract_data_bytes(raw: str) -> bytes:
    match = re.search(r'data\s*:\s*"((?:\\.|[^"\\])*)"', raw, re.S)
    if not match:
        raise ValueError("Missing image data in Gazebo image payload")

    payload_literal = '"' + match.group(1) + '"'
    try:
        decoded = ast.literal_eval(payload_literal)
        return decoded.encode("latin1", "ignore")
    except Exception as exc:
        raise ValueError(f"Failed to decode Gazebo image data: {exc}") from exc


def _extract_image_payload(raw: str) -> tuple[int, int, int, bytes]:
    width = _extract_int(raw, "width")
    height = _extract_int(raw, "height")
    step = _extract_int(raw, "step")
    data = _extract_data_bytes(raw)
    return width, height, step, data


def _rgb_rows_to_bytes(width: int, height: int, step: int, data: bytes) -> bytes:
    row_width = width * 3
    needed = height * step
    if len(data) < needed:
        raise ValueError(f"RGB payload shorter than expected: {len(data)} < {needed}")

    rgb = bytearray()
    for row in range(height):
        start = row * step
        rgb.extend(data[start:start + row_width])
    return bytes(rgb)


def _depth_rows_to_grayscale(width: int, height: int, step: int, data: bytes) -> bytes:
    row_width = width * 4
    needed = height * step
    if len(data) < needed:
        raise ValueError(f"Depth payload shorter than expected: {len(data)} < {needed}")

    depths: list[float] = []
    finite_positive: list[float] = []
    for row in range(height):
        row_bytes = data[row * step:row * step + row_width]
        for col in range(width):
            chunk = row_bytes[col * 4:(col + 1) * 4]
            value = struct.unpack("<f", chunk)[0]
            depths.append(value)
            if math.isfinite(value) and value > 0.0:
                finite_positive.append(value)

    if not finite_positive:
        return bytes([0] * (width * height))

    min_depth = min(finite_positive)
    max_depth = max(finite_positive)
    span = max(max_depth - min_depth, 1e-6)

    gray = bytearray()
    for value in depths:
        if not math.isfinite(value) or value <= 0.0:
            gray.append(0)
            continue
        norm = (value - min_depth) / span
        gray.append(max(0, min(255, int(255 * (1.0 - norm)))))
    return bytes(gray)


def _save_image_bytes(mode: str, width: int, height: int, pixels: bytes, output_path: Path) -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "Pillow is required for capture_camera_image. Install it with: pip install Pillow"
        ) from exc

    image = Image.frombytes(mode, (width, height), pixels)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() in {".jpg", ".jpeg"}:
        image.save(output_path, format="JPEG", quality=90)
    else:
        image.save(output_path)


def _build_output_path(camera: str, output_dir: str | None, filename: str | None) -> Path:
    spec = _CAMERA_SPECS[camera]
    out_dir = Path(output_dir).expanduser() if output_dir else Path("~/rover_images").expanduser()
    if filename:
        path = out_dir / filename
        if not path.suffix:
            path = path.with_suffix(spec["ext"])
        return path.resolve()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (out_dir / f"{camera}_{stamp}{spec['ext']}").resolve()


async def execute(*, camera: str, output_dir: str | None = None, filename: str | None = None, **_) -> str:
    camera_name = str(camera or "").strip().lower()
    if camera_name not in _CAMERA_SPECS:
        return json.dumps({"success": False, "error": f"Unknown camera: {camera_name}"})

    spec = _CAMERA_SPECS[camera_name]
    try:
        raw = _read_topic(spec["topic"])
        width, height, step, data = _extract_image_payload(raw)
        if spec["mode"] == "rgb":
            pixels = _rgb_rows_to_bytes(width, height, step, data)
            mode = "RGB"
        else:
            pixels = _depth_rows_to_grayscale(width, height, step, data)
            mode = "L"

        output_path = _build_output_path(camera_name, output_dir, filename)
        _save_image_bytes(mode, width, height, pixels, output_path)
        return json.dumps(
            {
                "success": True,
                "camera": camera_name,
                "topic": spec["topic"],
                "width": width,
                "height": height,
                "file_path": str(output_path),
                "media_tag": f"MEDIA:{output_path}",
                "message": (
                    "Image captured successfully. "
                    "To deliver it on Telegram, use send_message with the MEDIA path."
                ),
            }
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"success": False, "camera": camera_name, "error": "Timed out waiting for camera frame"})
    except Exception as exc:
        return json.dumps({"success": False, "camera": camera_name, "error": str(exc)})

