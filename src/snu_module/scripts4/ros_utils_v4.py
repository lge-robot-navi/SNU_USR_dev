"""
SNU Integrated Module v4.0
    - Classes for ROS Multimodal Sensors, with Synchronization (sync part from KIRO)
    - Message Wrapper for Publishing Message to ETRI Agent

"""
# Import Modules
import cv2
import os
import yaml
import logging
import numpy as np
import rospy
from cv_bridge import CvBridge, CvBridgeError

# Import ROS Messages
from osr_msgs.msg import Track, Tracks, BoundingBox
from geometry_msgs.msg import Pose, Twist, Point, Quaternion, Vector3
from std_msgs.msg import Header
from sensor_msgs.msg import Image, CameraInfo, PointCloud2
from nav_msgs.msg import Odometry
from rospy.numpy_msg import numpy_msg
from tf.transformations import quaternion_from_euler

# Import KIRO's Synchronized Subscriber
from snu_utils.sync_subscriber import SyncSubscriber


# RUN SNU Module Coverage Class Source
class coverage(object):
    def __init__(self, opts):
        # Load Options
        self.opts = opts

        # CvBridge for Publisher
        self.pub_bridge = CvBridge()

        # ROS Publisher
        self.tracks_pub = rospy.Publisher(
            opts.publish_mesg["tracks"], Tracks, queue_size=1
        )

        # ROS SNU Result Publisher
        self.det_result_pub = rospy.Publisher(
            opts.publish_mesg["det_result_rostopic_name"], Image, queue_size=1
        )
        self.trk_acl_result_pub = rospy.Publisher(
            opts.publish_mesg["trk_acl_result_rostopic_name"], Image, queue_size=1
        )

    # Publish Tracks
    def publish_tracks(self, tracklets, odometry_msg):
        out_tracks = wrap_tracks(trackers=tracklets, odometry=odometry_msg)
        self.tracks_pub.publish(out_tracks)

    # Publish SNU Result Image (DET / TRK + ACL)
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
                    assert 0, "Undefined Module!"


# Sensor Parameter Base Class
class sensor_params(object):
    def __init__(self, param_precision):
        # Set Parameter Precision
        self.param_precision = param_precision

        # Set Projection Matrix and its Pseudo-inverse Matrix
        self.projection_matrix = None
        self.pinv_projection_matrix = None

    # Update Parameters
    def update_params(self, param_argument):
        raise NotImplementedError()


# Sensor Parameter Class (Rostopic)
class sensor_params_rostopic(sensor_params):
    def __init__(self, param_precision=np.float32):
        super(sensor_params_rostopic, self).__init__(param_precision)

        """ Initialize Camera Parameter Matrices
        ----------------------------------------
        D: Distortion Matrix (5x1)
        K: Intrinsic Matrix (3x3)
        R: Rotation Matrix (3x3)
        P: Projection Matrix (3x4)
        ----------------------------------------
        """
        self.D, self.K, self.R, self.P = None, None, None, None

    def update_params(self, msg):
        self.D = msg.D.reshape((5, 1))  # Distortion Matrix
        self.K = msg.K.reshape((3, 3))  # Intrinsic Matrix
        self.R = msg.R.reshape((3, 3))  # Rotation Matrix
        self.P = msg.P.reshape((3, 4))  # Projection Matrix

        self.projection_matrix = self.P
        self.pinv_projection_matrix = np.linalg.pinv(self.P)


# Sensor Parameter Class (File)
class sensor_params_file(sensor_params):
    def __init__(self, param_precision=np.float32):
        super(sensor_params_file, self).__init__(param_precision)

        # Initialize Intrinsic-related Variables
        self.fx, self.fy, self.cx, self.cy = None, None, None, None
        self.w = None

        # Initialize Translation-related Variables
        self.x, self.y, self.z = None, None, None

        # Initialize Pan(yaw) / Tilt(pitch) / Roll Variables
        self.pan, self.tilt, self.roll = None, None, None

        # Set Camera Parameter Matrices
        self.intrinsic_matrix, self.extrinsic_matrix, self.rotation_matrix = None, None, None

    # Update Parameter Variables
    def update_params(self, param_array):
        # Intrinsic-related
        self.fx, self.fy, self.cx, self.cy = \
            param_array[0], param_array[1], param_array[2], param_array[3]
        self.w = param_array[4]

        # Translation-related
        self.x, self.y, self.z = param_array[5], param_array[6], param_array[7]

        # Pan / Tilt / Roll
        self.pan, self.tilt, self.roll = param_array[8], param_array[9], param_array[10]

        # Intrinsic Matrix < 3 x 4 >
        self.intrinsic_matrix = np.array([[self.fx, self.w, self.cx, 0],
                                          [0, self.fy, self.cy, 0],
                                          [0, 0, 1, 0]], dtype=self.param_precision)

        # Rotation Matrix
        self.rotation_matrix = self.convert_ptr_to_rotation()

        # Extrinsic Matrix < 4 x 4 >
        translation_vector = np.matmul(
            self.rotation_matrix,
            np.array([self.x, self.y, self.z], dtype=self.param_precision).reshape((3, 1))
        )
        self.extrinsic_matrix = np.block(
            [np.vstack((self.rotation_matrix, np.zeros((1, 3)))), np.append(translation_vector, 1).reshape(-1, 1)]
        )

        # Get Projection Matrix and its Pseudo-inverse
        self.projection_matrix = np.matmul(self.intrinsic_matrix, self.extrinsic_matrix)
        self.pinv_projection_matrix = np.linalg.pinv(self.projection_matrix)

    # Convert PTR to Rotation Matrix
    def convert_ptr_to_rotation(self):
        r11 = np.sin(self.pan) * np.cos(self.roll) - np.cos(self.pan) * np.sin(self.tilt) * np.sin(self.roll)
        r12 = -np.cos(self.pan) * np.cos(self.roll) - np.sin(self.pan) * np.sin(self.tilt) * np.sin(self.roll)
        r13 = np.cos(self.tilt) * np.sin(self.roll)
        r21 = np.sin(self.pan) * np.sin(self.roll) + np.sin(self.tilt) * np.cos(self.pan) * np.cos(self.roll)
        r22 = -np.cos(self.pan) * np.sin(self.roll) + np.sin(self.tilt) * np.sin(self.pan) * np.cos(self.roll)
        r23 = -np.cos(self.tilt) * np.cos(self.roll)
        r31 = np.cos(self.tilt) * np.cos(self.pan)
        r32 = np.cos(self.tilt) * np.sin(self.pan)
        r33 = np.sin(self.tilt)

        rotation_matrix = np.array([[r11, r12, r13],
                                    [r21, r22, r23],
                                    [r31, r32, r33]], dtype=self.param_precision)
        return rotation_matrix


# Multimodal ROS Sensor Managing Class
class ros_sensor(object):
    def __init__(self, modal_type, stamp):
        # Modal Type (becomes the class representation)
        self.modal_type = modal_type

        # Raw Data
        self.raw_data = None

        # Modal Timestamp
        self.timestamp = stamp

        # Modal Sensor Parameters
        self.sensor_params = None

    def __repr__(self):
        return self.modal_type

    def update_data(self, data, stamp):
        raise NotImplementedError()

    def update_raw_data(self, raw_data):
        """
        In-built Function for Disparity
        """
        self.raw_data = raw_data

    def get_data(self):
        raise NotImplementedError()

    def update_stamp(self, stamp):
        self.timestamp = stamp

    def update_sensor_params_rostopic(self, msg):
        if msg is not None:
            # Initialize Sensor Parameter Object (from rostopic)
            self.sensor_params = sensor_params_rostopic(param_precision=np.float32)

            # Update Parameters
            self.sensor_params.update_params(msg=msg)


class ros_sensor_image(ros_sensor):
    def __init__(self, modal_type, frame=None, stamp=None):
        super(ros_sensor_image, self).__init__(modal_type=modal_type, stamp=stamp)

        # Modal Frame
        self.frame = frame
        self.processed_frame = None

    def __add__(self, other):
        assert isinstance(other, ros_sensor_image), "Argument 'other' must be the same type!"

        # Concatenate Channel-wise
        concat_frame = np.dstack((self.get_data(), other.get_data()))

        # Get Concatenated Modal Type
        concat_modal_type = "{}+{}".format(self, other)

        # Return Concatenated ROS Sensor Image Class
        return ros_sensor_image(concat_modal_type, concat_frame, self.timestamp)

    def get_data(self):
        if self.processed_frame is not None:
            return self.processed_frame
        else:
            return self.frame

    def update_data(self, frame, stamp):
        self.frame = frame
        self.update_stamp(stamp=stamp)

    # Get Normalized Data
    def get_normalized_data(self, min_value=0.0, max_value=1.0):
        frame = self.get_data()
        frame_max_value, frame_min_value = frame.max(), frame.min()
        minmax_normalized_frame = (frame - frame_min_value) / (frame_max_value - frame_min_value)
        normalized_frame = min_value + (max_value - min_value) * minmax_normalized_frame
        return normalized_frame

    def _empty_frame(self):
        self.frame, self.processed_frame = None, None

    def _empty_stamp(self):
        self.timestamp = None


# TODO: Implement MORE MORE MORE!!
class ros_sensor_lidar(ros_sensor):
    def __init__(self, modal_type, lidar_pc_msg=None, stamp=None):
        super(ros_sensor_lidar, self).__init__(modal_type=modal_type, stamp=stamp)

        # Modal LiDAR PointCloud Message (format: ROS "PointCloud2")
        self.lidar_pc_msg = lidar_pc_msg

    def get_data(self):
        # TODO: Convert LiDAR PointCloud2 ROS Message to XYZ format
        raise NotImplementedError()

    def update_data(self, lidar_pc_msg, stamp):
        self.lidar_pc_msg = lidar_pc_msg
        self.update_stamp(stamp=stamp)


# Synchronized Subscriber (from KIRO, SNU Adaptation)
class snu_SyncSubscriber(SyncSubscriber):
    def __init__(self, ros_sync_switch_dict, options):
        super(snu_SyncSubscriber, self).__init__(ros_sync_switch_dict, options)

    def get_sync_data(self):
        self.lock_flag.acquire()
        if self.sync_flag is False:
            self.lock_flag.release()
            return None
        else:
            result_sync_frame_dict = {
                "color": self.sync_color, "disparity": self.sync_depth, "aligned_disparity": self.sync_aligned_depth,
                "thermal": self.sync_thermal, "infrared": self.sync_ir, "nightvision": self.sync_nv1
            }
            result_sync_camerainfo_dict = {
                "color": self.sync_color_camerainfo, "disparity": self.sync_depth_camerainfo,
                "infrared": self.sync_ir_camerainfo
            }
            result_sync_pc_odom_dict = {
                "pointcloud": self.sync_pointcloud, "odometry": self.sync_odometry
            }
            self.lock_flag.release()
            return self.sync_stamp, result_sync_frame_dict, result_sync_camerainfo_dict, result_sync_pc_odom_dict


# Function for Publishing SNU Module Result to ETRI Module
def wrap_tracks(trackers, odometry):
    out_tracks = Tracks()

    # For the header stamp, record current time
    out_tracks.header.stamp = rospy.Time.now()

    # Odometry Information Passes Through SNU Module
    if odometry is not None:
        out_tracks.odom = odometry

    # For each Tracklets,
    for _, tracker in enumerate(trackers):
        # Get Tracklet State
        track_state = tracker.states[-1]
        if len(tracker.states) > 1:
            track_prev_state = tracker.states[-2]
        else:
            # [x,y,dx,dy,w,h]
            track_prev_state = np.zeros(7).reshape((7, 1))
        track_cam_coord_state = tracker.c3

        # Initialize Track
        track = Track()

        # Tracklet ID
        # important: set the Tracklet ID to modulus of 256 since the type is < uint8 >
        track.id = tracker.id % 256

        # Tracklet Object Type (1: Person // 2: Car)
        track.type = tracker.label

        # Tracklet Action Class (Posture)
        # 1: Stand, 2: Sit, 3: Lie
        # (publish if only tracklet object type is person)
        if tracker.label == 1:
            track.posture = (tracker.pose if tracker.pose is not None else 0)
        else:
            track.posture = 0

        # Bounding Box Position [bbox_pose]
        track_bbox = BoundingBox()
        track_bbox.x = np.uint32(track_state[0][0])
        track_bbox.y = np.uint32(track_state[1][0])
        track_bbox.height = np.uint32(track_state[6][0])
        track_bbox.width = np.uint32(track_state[5][0])
        track.bbox_pose = track_bbox

        # Bounding Box Velocity [bbox_velocity]
        track_d_bbox = BoundingBox()
        track_d_bbox.x = np.uint32(track_state[3][0])
        track_d_bbox.y = np.uint32(track_state[4][0])
        track_d_bbox.height = np.uint32((track_state - track_prev_state)[6][0])
        track_d_bbox.width = np.uint32((track_state - track_prev_state)[5][0])
        track.bbox_velocity = track_d_bbox

        # [pose]
        cam_coord_pose = Pose()
        cam_coord_position = Point()
        cam_coord_orientation = Quaternion()

        cam_coord_position.x = np.float64(track_cam_coord_state[0][0])
        cam_coord_position.y = np.float64(track_cam_coord_state[1][0])
        cam_coord_position.z = np.float64(track_cam_coord_state[2][0])

        # Convert to Quaternion
        q = quaternion_from_euler(tracker.roll, tracker.pitch, tracker.yaw)
        cam_coord_orientation.x = np.float64(q[0])
        cam_coord_orientation.y = np.float64(q[1])
        cam_coord_orientation.z = np.float64(q[2])
        cam_coord_orientation.w = np.float64(q[3])

        cam_coord_pose.position = cam_coord_position
        cam_coord_pose.orientation = cam_coord_orientation
        track.pose = cam_coord_pose

        # [twist]
        cam_coord_twist = Twist()
        cam_coord_linear = Vector3()
        cam_coord_angular = Vector3()

        cam_coord_linear.x = np.float64(track_cam_coord_state[3][0])
        cam_coord_linear.y = np.float64(track_cam_coord_state[4][0])
        cam_coord_linear.z = np.float64(track_cam_coord_state[5][0])

        cam_coord_angular.x = np.float64(0)
        cam_coord_angular.y = np.float64(0)
        cam_coord_angular.z = np.float64(0)

        cam_coord_twist.linear = cam_coord_linear
        cam_coord_twist.angular = cam_coord_angular
        track.twist = cam_coord_twist

        # Append to Tracks
        out_tracks.tracks.append(track)

    return out_tracks