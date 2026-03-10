---
name: camera-telegram-delivery
description: Capture rover camera images and deliver them as real Telegram attachments
version: 1.0.0
metadata:
  hermes:
    tags: [camera, media, telegram, mars, rover]
---

# Camera Capture + Telegram Delivery Skill

Use this skill whenever the user asks for a rover photo, selfie, or image export, especially if they mention Telegram or “send me the picture”.

## Tools and Endpoints

- `capture_camera_image` — primary tool for grabbing frames from:
  - MastCam: `camera="mastcam"`
  - NavCam: `camera="navcam"` or `"navcam_left"`
  - HazCam Front: `camera="hazcam_front"`
  - HazCam Rear: `camera="hazcam_rear"`
- `send_message` (Hermes tool) with `target: "telegram"` to send media using `MEDIA:/absolute/path/to/file`.

## Protocol

1. **Choose camera**
   - If user says “front camera” or “ahead”, prefer `navcam` or `hazcam_front`.
   - If user says “rear view” or “behind”, prefer `hazcam_rear`.
   - For “science photo”, “zoomed” or “detailed panorama”, prefer `mastcam`.

2. **Capture image**
   - Call `capture_camera_image` with:
     - `camera`: one of `mastcam`, `navcam`, `navcam_left`, `hazcam_front`, `hazcam_rear`.
     - Let `output_dir` default (rover_images) unless user specifies a path.
   - On success, read `file_path` and `media_tag` (e.g. `MEDIA:/abs/path/image.jpg`) from the JSON result.

3. **Send to Telegram**
   - If the user wants the **actual image** in Telegram (not just a description):
     - Call `send_message` with:
       - `target: "telegram"`
       - `text` including the exact `media_tag` (e.g. `MEDIA:/abs/path/image.jpg`) plus a short caption (location, camera, purpose).
   - Only claim “image sent” if the `send_message` result shows success and no attachment errors.

4. **Fallback behavior**
   - If `capture_camera_image` fails (timeout, missing topic, or Pillow not installed):
     - Explain the failure in natural language to the user.
     - Do **not** claim image delivery.
     - Optionally, use `read_sensors` or existing terrain skills to describe what the rover likely “sees” based on sensors, marking that this is a description, not a real photo.

5. **Logging**
   - Mention in mission summaries that a photo was captured, which camera was used, and whether it was successfully delivered to Telegram.

