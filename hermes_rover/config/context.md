# Hermes Mars Rover — Project Context

- **This is a Gazebo Sim rover simulation**. Camera topics are available even when the sim is headless.

- **Available tools:** drive_rover, read_sensors, navigate_to, capture_camera_image.

- **Sensor data comes from gz topic commands** — tools use subprocess calls to `gz topic` (no ROS 2 / rclpy). Odometry: `/rover/odometry`. IMU: `/rover/imu`. LIDAR: `/rover/lidar`. Cameras: `/rover/mastcam`, `/rover/navcam_left`, `/rover/hazcam_front`, `/rover/hazcam_rear`.

- **All actions should be logged for session reports** — what the rover did, when, and why. Prefer short, structured summaries.
- **Mission behavior learning is active** — before path planning in a similar sensor context, consult learned behaviors and prefer those with strong success over failure counts.
- **Successful non-trivial maneuvers should be saved** — use `rover_memory(action="save_behavior", trigger=..., behavior_action=..., session_id=...)` with coarse sensor-context triggers and existing rover tool names only.

- **Skill creation:** When solving new problems, write SKILL.md files in the project’s skills directory so the same situation can be handled better in the future.

- **Reports:** When generating any report or research summary (e.g. MARS_RESEARCH_REPORT.md, mission reports, survey data), save the file under the project’s **reports/** directory. The project root is the current working directory when started from the launch script — write reports to `reports/<filename>` (e.g. `reports/MARS_RESEARCH_REPORT.md`, `reports/mission_YYYYMMDD_HHMMSS.json`) so they are accessible directly in the project folder.

## Reliability Rules (Messaging + Reports)

- Never claim a file/report was sent unless the messaging tool result confirms success.
- If a command exits non-zero, treat it as failure and report it; do not continue as if successful.
- For Telegram PDF delivery, first call `GET /report/pdf/save` to obtain a persistent absolute path in `~/.hermes/document_cache`, then use `send_message` with `MEDIA:/absolute/path/to/report.pdf`.
- For Telegram image delivery, first call `capture_camera_image`, then use `send_message` with the returned `MEDIA:/absolute/path/to/image`.
- Prefer project/API report generation paths over ad-hoc inline Python scripts.
