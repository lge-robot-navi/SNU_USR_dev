"""
SNU Integrated Module v3.0
    - Configuration File


"""
# Import Module
import os

# Import Config Module
from yacs.config import CfgNode as CN

# Get NN Model Base Path
model_base_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models")

# Config Class Initialization
__C = CN(new_allowed=False)

# Load this Variable when importing this file as a module
cfg = __C

# Agent Options
__C.agent = CN(new_allowed=False)
__C.agent.type = "NULL"
__C.agent.name = "NULL"
__C.agent.daytime = "NULL"

# ROS Odometry Message
__C.odometry_rostopic_name = "/robot_odom"

# --------------------- #
# ROS Publisher Options #
# --------------------- #
__C.publisher = CN(new_allowed=False)
__C.publisher.tracks = "/osr/tracks"
__C.publisher.result_image = "/osr/snu_result_image"

__C.publisher.det_result_image = "/osr/snu_det_result_image"
__C.publisher.trk_acl_result_image = "/osr/snu_trk_acl_result_image"

# ------------------ #
# ROS Sensor Options #
# ------------------ #

# ROS Sensor Option Initialization
__C.sensors = CN(new_allowed=False)

# ROS Sensors Initialization
__C.sensors.color = CN(new_allowed=True)
__C.sensors.color.is_valid = True
__C.sensors.color.encoding = "8UC3"
__C.sensors.color.rostopic_name = "/osr/image_color"
__C.sensors.color.camerainfo_rostopic_name = "/camera/color/camera_info"
__C.sensors.color.calibration_target_sensor = "color"


__C.sensors.disparity = CN(new_allowed=True)
__C.sensors.disparity.is_valid = True
__C.sensors.disparity.encoding = "16UC1"
__C.sensors.disparity.rostopic_name = "/osr/image_depth"
__C.sensors.disparity.camerainfo_rostopic_name = "/camera/depth/camera_info"
__C.sensors.disparity.calibration_target_sensor = "color"

__C.sensors.disparity.clip = CN(new_allowed=False)
__C.sensors.disparity.clip.value = -1
__C.sensors.disparity.clip.min_distance = 1000
__C.sensors.disparity.clip.max_distance = 15000


__C.sensors.thermal = CN(new_allowed=True)
__C.sensors.thermal.is_valid = True
__C.sensors.thermal.encoding = "16UC1"
__C.sensors.thermal.rostopic_name = "/osr/image_thermal"
__C.sensors.thermal.camerainfo_rostopic_name = "NULL"
__C.sensors.thermal.calibration_target_sensor = "color"


__C.sensors.infrared = CN(new_allowed=True)
__C.sensors.infrared.is_valid = True
__C.sensors.infrared.encoding = "8UC1"
__C.sensors.infrared.rostopic_name = "/osr/image_infrared"
__C.sensors.infrared.camerainfo_rostopic_name = "NULL"
__C.sensors.infrared.calibration_target_sensor = "color"


__C.sensors.nightvision = CN(new_allowed=True)
__C.sensors.nightvision.is_valid = True
__C.sensors.nightvision.encoding = "8UC3"
__C.sensors.nightvision.rostopic_name = "/osr/image_nv1"
__C.sensors.nightvision.camerainfo_rostopic_name = "NULL"
__C.sensors.nightvision.calibration_target_sensor = "color"


__C.sensors.lidar = CN(new_allowed=True)
__C.sensors.lidar.is_valid = True
__C.sensors.lidar.encoding = "8UC3"
__C.sensors.lidar.rostopic_name = "/osr/camera_lidar"
__C.sensors.lidar.camerainfo_rostopic_name = "NULL"
__C.sensors.lidar.calibration_target_sensor = "color"

# ---------------- #
# Detector Options #
# ---------------- #
# TODO: Add options/parameters that can be easily modified while impacting the overall performance
__C.detector = CN(new_allowed=True)
__C.detector.name = "RefineDet"
__C.detector.device = 0
__C.detector.model_base_path = os.path.join(model_base_path, "detector")

# ------------------------------- #
# Multiple Target Tracker Options #
# ------------------------------- #
# TODO: Add options/parameters that can be easily modified while impacting the overall performance
__C.tracker = CN(new_allowed=True)
__C.tracker.name = "Custom"
__C.tracker.device = 0

# ----------------------------- #
# Action Classification Options #
# ----------------------------- #
# TODO: Add options/parameters that can be easily modified while impacting the overall performance
__C.aclassifier = CN(new_allowed=True)
__C.aclassifier.name = "Custom"
__C.aclassifier.device = 0
__C.aclassifier.model_base_path = os.path.join(model_base_path, "aclassifier")

# --------------------- #
# Visualization Options #
# --------------------- #
__C.visualization = CN(new_allowed=True)

# Detection
__C.visualization.detection = CN(new_allowed=True)
__C.visualization.detection.show = True
__C.visualization.detection.color = (255, 0, 0)

# Tracking
__C.visualization.tracking = CN(new_allowed=True)
__C.visualization.tracking.show = True
__C.visualization.tracking.color = (0, 0, 255)

# Action Classification
__C.visualization.aclassification = CN(new_allowed=True)
__C.visualization.aclassification.show = True


if __name__ == "__main__":
    pass
