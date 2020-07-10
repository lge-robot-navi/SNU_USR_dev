"""
SNU Integrated Module v4.0
    - Coverage Class Module for ROS-embedded Integrated Algorithm

"""
from rospy import Subscriber, Publisher
from cv_bridge import CvBridge

from utils.ros.sensors import ros_sensor_image, ros_sensor_lidar

# Import ROS Message Types
from sensor_msgs.msg import CameraInfo, Image
from osr_msgs.msg import Tracks
from rospy.numpy_msg import numpy_msg


class coverage(object):
    def __init__(self, opts, is_sensor_param_file=False):
        # Load Options
        self.opts = opts

        # Odometry (Pass-through as ROS Message)
        self.odometry = None

        # CvBridge for Publisher
        self.pub_bridge = CvBridge()

        # Initialize Synchronized Timestamp
        self.sync_stamp = None

        # Initialize Modal Objects
        self.color = ros_sensor_image(modal_type="color")
        self.disparity = ros_sensor_image(modal_type="disparity")
        self.thermal = ros_sensor_image(modal_type="thermal")
        self.infrared = ros_sensor_image(modal_type="infrared")
        self.nightvision = ros_sensor_image(modal_type="nightvision")
        self.lidar = ros_sensor_lidar(modal_type="lidar")

        # CameraInfo Subscribers
        if is_sensor_param_file is False:
            # Color CameraInfo Subscriber
            self.color_camerainfo_sub = Subscriber(
                opts.sensors.color["camerainfo_rostopic_name"], numpy_msg(CameraInfo),
                self.color_camerainfo_callback
            )

            # Disparity CameraInfo Subscriber
            self.disparity_camerainfo_sub = Subscriber(
                opts.sensors.disparity["camerainfo_rostopic_name"], numpy_msg(CameraInfo),
                self.disparity_camerainfo_callback
            )

            # Infrared CameraInfo Subscriber
            self.infrared_camerainfo_sub = Subscriber(
                opts.sensors.infrared["camerainfo_rostopic_name"], numpy_msg(CameraInfo),
                self.infrared_camerainfo_callback
            )

            # Thermal CameraInfo Subscriber
            self.thermal_camerainfo_sub = Subscriber(
                opts.sensors.thermal["camerainfo_rostopic_name"], numpy_msg(CameraInfo),
                self.thermal_camerainfo_callback
            )

        # ROS Publisher
        self.tracks_pub = Publisher(
            opts.publish_mesg["tracks"], Tracks, queue_size=1
        )

        # ROS SNU Result Publisher
        self.det_result_pub = Publisher(
            opts.publish_mesg["det_result_rostopic_name"], Image, queue_size=1
        )
        self.trk_acl_result_pub = Publisher(
            opts.publish_mesg["trk_acl_result_rostopic_name"], Image, queue_size=1
        )

    # Color CameraInfo Callback Function
    def color_camerainfo_callback(self, msg):
        if self.color.get_sensor_params() is None:
            self.color.update_sensor_params_rostopic(msg=msg)

    # Disparity CameraInfo Callback Function
    def disparity_camerainfo_callback(self, msg):
        if self.disparity.get_sensor_params() is None:
            self.disparity.update_sensor_params_rostopic(msg=msg)

    # Infrared CameraInfo Callback Function
    def infrared_camerainfo_callback(self, msg):
        if self.infrared.get_sensor_params() is None:
            self.infrared.update_sensor_params_rostopic(msg=msg)

    # Thermal CameraInfo Callback Function
    def thermal_camerainfo_callback(self, msg):
        if self.thermal.get_sensor_params() is None:
            self.thermal.update_sensor_params_rostopic(msg=msg)

    # Publish SNU Result Image ( DET / TRK + ACL )
    def publish_snu_result_image(self, result_frame_dict):
        for module, result_frame in result_frame_dict.items():
            if result_frame is not None:
                if module == "det":
                    if self.opts.detector.is_result_publish is True:
                        self.det_result_pub.publish(
                            self.pub_bridge.cv2_to_imgmsg(
                                result_frame, "rgb8"
                            )
                        )
                elif module == "trk_acl":
                    if self.opts.tracker.is_result_publish is True:
                        self.trk_acl_result_pub.publish(
                            self.pub_bridge.cv2_to_imgmsg(
                                result_frame, "rgb8"
                            )
                        )
                else:
                    raise NotImplementedError("Undefined Module: {}".format(module))

    # Update All Modal Data
    def update_all_modal_data(self, sync_data):
        sync_stamp = sync_data[0]
        sync_frame_dict = sync_data[1]
        sync_pc_odom_dict = sync_data[2]

        # Update Synchronized Timestamp
        self.sync_stamp = sync_stamp

        # Update Modal Frames
        self.color.update_data(frame=sync_frame_dict["color"], stamp=sync_stamp)

        self.disparity.update_data(frame=sync_frame_dict["aligned_disparity"], stamp=sync_stamp)
        self.disparity.update_raw_data(raw_data=sync_frame_dict["disparity"])

        self.thermal.update_data(frame=sync_frame_dict["thermal"], stamp=sync_stamp)

        self.infrared.update_data(frame=sync_frame_dict["infrared"], stamp=sync_stamp)

        self.nightvision.update_data(frame=sync_frame_dict["nightvision"], stamp=sync_stamp)

        self.lidar.update_data(data=sync_pc_odom_dict["pointcloud"], stamp=sync_stamp)

        # Get Odometry
        self.odometry = sync_pc_odom_dict["odometry"]

    def get_sync_timestamp(self):
        return self.sync_stamp

    def gather_all_modal_data(self):
        sensor_data = {
            "color": self.color,
            "disparity": self.disparity,
            "thermal": self.thermal,
            "infrared": self.infrared,
            "nightvision": self.nightvision,
            "lidar": self.lidar
        }
        return sensor_data

    def gather_all_modal_sensor_params(self):
        sensor_params_dict = {
            "color": self.color.get_sensor_params(),
            "disparity": self.disparity.get_sensor_params(),
            "thermal": self.thermal.get_sensor_params(),
            "infrared": self.infrared.get_sensor_params(),
            "nightvision": self.nightvision.get_sensor_params(),
            "lidar": self.lidar.get_sensor_params()
        }
        return sensor_params_dict


if __name__ == "__main__":
    pass