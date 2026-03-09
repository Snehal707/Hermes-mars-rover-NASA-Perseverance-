from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        # Launch Gazebo with Mars world (run from repo root)
        ExecuteProcess(
            cmd=['gz', 'sim', '-r', 'simulation/worlds/mars_terrain.sdf', '-v', '3'],
            output='screen',
        ),
        # ROS-Gazebo bridge: [ = GZ->ROS, ] = ROS->GZ
        Node(
            package='ros_gz_bridge',
            executable='parameter_bridge',
            arguments=[
                '/rover/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist',
                '/rover/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry',
                '/rover/navcam_left@sensor_msgs/msg/Image[gz.msgs.Image',
                '/rover/mastcam@sensor_msgs/msg/Image[gz.msgs.Image',
                '/rover/hazcam_front@sensor_msgs/msg/Image[gz.msgs.Image',
                '/rover/hazcam_rear@sensor_msgs/msg/Image[gz.msgs.Image',
                '/rover/lidar@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
                '/rover/imu@sensor_msgs/msg/Imu[gz.msgs.IMU',
                '/rover/joint_states@sensor_msgs/msg/JointState[gz.msgs.Model',
            ],
            output='screen',
        ),
    ])
