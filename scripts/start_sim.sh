#!/usr/bin/env bash
# Phase 1: Launch Gazebo Sim Mars world + ROS 2 parameter_bridge.
# Run from repo root, or the script will cd to repo root (parent of scripts/).

set -e

# Repo root: parent of directory containing this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

export GZ_SIM_RESOURCE_PATH="$REPO_ROOT/simulation/models"
SIM_WORLD="${HERMES_SIM_WORLD:-simulation/worlds/mars_terrain.sdf}"
SIM_VERBOSITY="${HERMES_SIM_VERBOSITY:-3}"

# Source ROS 2 (prefer Jazzy, then Humble)
if [ -f /opt/ros/jazzy/setup.bash ]; then
  source /opt/ros/jazzy/setup.bash
elif [ -f /opt/ros/humble/setup.bash ]; then
  source /opt/ros/humble/setup.bash
else
  echo "No ROS 2 (jazzy/humble) setup.bash found. Source your distro manually if needed."
fi

# Launch: gz sim + parameter_bridge (no ROS package required)
cleanup() { kill $GZ_PID 2>/dev/null || true; exit 0; }
trap cleanup SIGINT SIGTERM

gz sim -r "$SIM_WORLD" -v "$SIM_VERBOSITY" &
GZ_PID=$!

# Give Gazebo a moment to start
sleep 3

ros2 run ros_gz_bridge parameter_bridge \
  /rover/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist \
  /rover/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry \
  /rover/navcam_left@sensor_msgs/msg/Image[gz.msgs.Image \
  /rover/mastcam@sensor_msgs/msg/Image[gz.msgs.Image \
  /rover/hazcam_front@sensor_msgs/msg/Image[gz.msgs.Image \
  /rover/hazcam_rear@sensor_msgs/msg/Image[gz.msgs.Image \
  /rover/lidar@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan \
  /rover/imu@sensor_msgs/msg/Imu[gz.msgs.IMU \
  /rover/joint_states@sensor_msgs/msg/JointState[gz.msgs.Model

# If bridge exits, kill Gazebo
cleanup
