"""
SNU Integrated Module v4.0
    - Code which defines object classes
    [1] Tracklet Candidate Class
    [2] Tracklet Class
    [3] Refine Class Code

"""

# Import Modules
import cv2
import math
import torch
import torch.nn.functional as F
import numpy as np
import filterpy.kalman.kalman_filter as kalmanfilter

# Import Custom Modules
import utils.bounding_box as snu_bbox
import kalman_params as kparams
import utils.patch as snu_patch
import utils.histogram as snu_hist
from utils.profiling import Timer
from lidar import lidar_kernel
from utils.kcf import KCF_PREDICTOR


# Object Instance Class
class object_instance(object):
    def __init__(self, init_fidx, obj_id=None, obj_type=None):
        # Frame Index
        self.fidxs = [init_fidx]

        # Instance ID
        self.id = obj_id

        # Object Type
        self.obj_type = obj_type

    def __repr__(self):
        return self.obj_type

    def __add__(self, bbox):
        raise NotImplementedError()

    def __len__(self):
        return len(self.fidxs)

    def __getitem__(self, idx):
        raise NotImplementedError()

    def __del__(self):
        pass

    def update(self, *args, **kwargs):
        raise NotImplementedError()


# Tracklet Candidate Class
class TrackletCandidate(object_instance):
    def __init__(self, frame, bbox, conf, label, init_fidx, opts):
        super(TrackletCandidate, self).__init__(init_fidx=init_fidx, obj_type="TrackletCandidate")

        # Detection BBOX, Confidence Lists and Label
        self.asso_dets, self.asso_confs = [bbox], [conf]
        self.label = label

        # Association Flag List
        self.is_associated = [True]

        # z (observation bbox type: {u, v, du, dv, w, h})
        self.z = [snu_bbox.bbox_to_zx(bbox, np.zeros(2))]

        # Initialize KCF Module for BBOX Prediction
        self.BBOX_PREDICTOR = KCF_PREDICTOR(
            init_frame=frame,
            init_zx_bbox=snu_bbox.bbox_to_zx(bbox=bbox).reshape(4),
            init_fidx=init_fidx,
            kcf_params=opts.tracker.kcf_params
        )

    # Addition BTW Identical Classes (Tentative)
    def __add__(self, detection_bbox):
        pass

    def __getitem__(self, fidx):
        """
        :param fidx: Associated Detection Frame Index
        :return: Dictionary of (BBOX / Confidence / Label)
        """
        assert (fidx in self.fidxs), "Current Object {} do not exists in Frame #{}".format(self, fidx)

        # Find Index of the input Frame Index
        idx = self.fidxs.index(fidx)

        return {"bbox": self.asso_dets[idx], "conf": self.asso_confs[idx], "label": self.label}

    def get_fidx_patch(self, modal_frame, fidx):
        assert (fidx in self.fidxs), "Current Object {} do not exists in Frame #{}".format(self, fidx)

        # Frame Index BBOX
        fidx_bbox = self.asso_dets[self.fidxs.index(fidx)]

        # Extract Patch
        return snu_patch.get_patch(img=modal_frame, bbox=fidx_bbox)

    def get_rough_depth(self, disparity_frame, opts):
        # Get Disparity Patch
        disparity_patch = self.get_fidx_patch(modal_frame=disparity_frame, fidx=self.fidxs[-1])

        # Get Histogram
        disparity_hist, disparity_hist_idx = snu_hist.histogramize_patch(
            sensor_patch=disparity_patch, dhist_bin=opts.tracker.disparity_params["rough_hist_bin"],
            min_value=opts.sensors.disparity["clip_distance"]["min"],
            max_value=opts.sensors.disparity["clip_distance"]["max"]
        )

        # Get Max-bin and Representative Depth Value of Disparity Histogram
        max_bin = disparity_hist.argmax()
        depth_value = ((disparity_hist_idx[max_bin] + disparity_hist_idx[max_bin + 1]) / 2.0) / 1000.0

        return depth_value

    def get_depth(self, sync_data_dict, opts):
        # Get Observation Patch bbox
        patch_bbox = self.asso_dets[-1]

        # If Label is Human, then re-assign bbox area
        if self.label == 1:
            patch_bbox = snu_bbox.resize_bbox(patch_bbox, x_ratio=0.7, y_ratio=0.7)

        # Get Disparity Frame
        disparity_frame = sync_data_dict["disparity"].get_data(is_processed=True)

        # Get Disparity Patch
        disparity_patch = snu_patch.get_patch(
            img=disparity_frame, bbox=patch_bbox
        )

        # Project XYZ to uv-coordinate
        uv_array, pc_distances, _ = sync_data_dict["lidar"].project_xyz_to_uv_inside_bbox(
            camerainfo_msg=sync_data_dict["color"].camerainfo_msg,
            bbox=patch_bbox, random_sample_number=opts.tracker.lidar_params["sampling_number"]
        )

        # Define LiDAR Kernels
        fusion_depth_list = []
        for uv_array_idx in range(len(uv_array)):
            uv_point, pc_distance = uv_array[uv_array_idx], pc_distances[uv_array_idx]
            l_kernel = lidar_kernel(
                sensor_data=sync_data_dict["disparity"],
                pc_uv=uv_point, pc_distance=pc_distance,
                kernel_size=opts.tracker.lidar_params["lidar_kernel_size"]
            )
            fusion_depth_list.append(l_kernel.get_kernel_average_depth())

        # Get Depth Histogram from Fusion Depth List
        if len(fusion_depth_list) >= np.floor(0.1 * opts.tracker.lidar_params["sampling_number"]):
            depth_hist, depth_hist_idx = np.histogram(fusion_depth_list)

            # Get Max-bin and Representative Depth Value of Disparity Histogram
            max_bin = depth_hist.argmax()
            depth_value = ((depth_hist_idx[max_bin] + depth_hist_idx[max_bin + 1]) / 2.0)

        elif len(fusion_depth_list) > 0:
            # Get Average Depth Value of the Fusion Depth List
            depth_value = np.average(fusion_depth_list)

        else:
            depth_value = 0.0

        return depth_value

    def update(self, fidx, bbox=None, conf=None):
        assert ~np.logical_xor((bbox is None), (conf is None)), "Input Error!"

        # Update Current Frame Index to List
        self.fidxs.append(fidx)

        # Update Detection BBOX
        if bbox is None:
            self.asso_dets.append(None)
            self.asso_confs.append(None)
            self.is_associated.append(False)
            self.z.append(None)
        else:
            z_bbox = snu_bbox.bbox_to_zx(bbox)
            velocity = (z_bbox[0:2] - self.z[-1][0:2]).reshape(2)
            self.asso_dets.append(bbox)
            self.asso_confs.append(conf)
            self.is_associated.append(True)
            self.z.append(snu_bbox.bbox_to_zx(bbox, velocity))

    # Predict BBOX using SOT
    def predict(self, frame, bbox):
        return self.BBOX_PREDICTOR.predict_bbox(frame=frame, roi_bbox=bbox)

    # Initialize Tracklet Class from TrackletCandidate
    def init_tracklet(self, disparity_frame, trk_id, fidx, opts):
        # Get Rough Depth
        depth = self.get_rough_depth(disparity_frame, opts)

        # Tracklet Initialization Dictionary
        init_trk_dict = {
            "asso_dets": self.asso_dets, "asso_confs": self.asso_confs, "label": self.label,
            "is_associated": self.is_associated, "init_depth": depth
        }

        # Initialize Tracklet
        tracklet = Tracklet(trk_id, fidx, opts.tracker, **init_trk_dict)

        return tracklet


class Tracklet(object_instance):
    def __init__(self, trk_id, init_fidx, tracker_opts, **kwargs):
        super(Tracklet, self).__init__(obj_id=trk_id, init_fidx=init_fidx, obj_type="Tracklet")

        # Unpack Input Dictionary
        self.asso_dets = kwargs["asso_dets"]
        self.asso_confs = kwargs["asso_confs"]
        self.label = kwargs["label"]

        # Association Flag
        self.is_associated = kwargs["is_associated"]

        # Tracklet Depth Value
        self.depth = [kwargs["init_depth"]]

        # Tracklet Visualization Color
        self.color = tracker_opts.tracklet_colors[self.id % tracker_opts.trk_color_refresh_period, :] * 255

        # Initialize Tracklet Kalman Parameters
        self.A = tracker_opts.kparam_class.A  # State Transition Matrix (Motion Model)
        self.H = tracker_opts.kparam_class.H  # Unit Transformation Matrix
        self.P = tracker_opts.kparam_class.P  # Error Covariance Matrix
        self.Q = tracker_opts.kparam_class.Q  # State Covariance Matrix
        self.R = tracker_opts.kparam_class.R  # Measurement Covariance Matrix

        # Initialize Image Coordinate Observation Vector
        curr_z2_bbox = snu_bbox.bbox_to_zx(kwargs["asso_dets"][-1])
        if len(kwargs["asso_dets"]) > 1:
            prev_z2_bbox = snu_bbox.bbox_to_zx(kwargs["asso_dets"][-2])
        else:
            prev_z2_bbox = np.vstack((curr_z2_bbox[0:2], np.zeros((2, 1))))
        init_observation = snu_bbox.bbox_to_zx(
            bbox=kwargs["asso_dets"][-1],
            velocity=(curr_z2_bbox - prev_z2_bbox)[0:2].reshape(2),
            depth=kwargs["init_depth"]
        )

        # Kalman State (initial state)
        self.x3 = init_observation
        self.x3p, self.Pp = kalmanfilter.predict(self.x3, self.P, self.A, self.Q)

        # Tracklet States
        self.states = [self.x3]

        # Tracklet Predicted States
        self.pred_states = [self.x3p]

        # 3D Tracklet State on Camera Coordinates
        self.c3 = None

        # Roll, Pitch, Yaw
        self.roll, self.pitch, self.yaw = None, None, None

        # Action Classification Results
        self.pose_list = []
        self.pose = None

    def __add__(self, bbox):
        raise NotImplementedError()

    def __getitem__(self, fidx):
        raise NotImplementedError()

    def update(self, fidx, bbox=None, conf=None):
        assert ~np.logical_xor((bbox is None), (conf is None)), "Input Error!"

        # Append Frame Index
        self.fidxs.append(fidx)

        # If Tracklet is unassociated, replace detection with the previous Kalman Prediction
        if bbox is None:
            self.asso_dets.append(None)
            self.asso_confs.append(None)
            self.is_associated.append(False)
            z3 = self.x3p
        else:
            self.asso_dets.append(bbox)
            self.asso_confs.append(conf)
            self.is_associated.append(True)

            # Get Velocity
            c = np.array([(bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0])
            velocity = c - self.x3p[0:2].reshape(2)

            # Make sure to Update Depth Prior to this code
            assert (len(self.fidxs) == len(self.depth)), "Depth Not Updated!"
            z3 = snu_bbox.bbox_to_zx(bbox=bbox, velocity=velocity, depth=self.depth[-1])

        # Kalman Update
        self.x3, self.P = kalmanfilter.update(self.x3p, self.Pp, z3, self.R, self.H)

        # Append to Tracklet States
        self.states.append(self.x3)

    def predict(self):
        # Kalman Predict
        self.x3p, self.Pp = kalmanfilter.predict(self.x3, self.P, self.A, self.Q)
        self.pred_states.append(self.x3p)

    def get_2d_img_coord_state(self):
        return snu_bbox.zx3_to_zx2(self.x3)

    # Get Tracklet Depth (as an observation, using associated detection bbox)
    def get_depth(self, sync_data_dict, opts):
        # Get Observation Patch bbox
        if self.asso_dets[-1] is not None:
            patch_bbox = self.asso_dets[-1]
        else:
            patch_bbox, _ = snu_bbox.zx_to_bbox(self.x3p)

        # If Label is Human, then re-assign bbox area
        if self.label == 1:
            patch_bbox = snu_bbox.resize_bbox(patch_bbox, x_ratio=0.7, y_ratio=0.7)

        # Get Disparity Frame
        disparity_frame = sync_data_dict["disparity"].get_data(is_processed=True)

        # Get Disparity Patch
        disparity_patch = snu_patch.get_patch(
            img=disparity_frame, bbox=patch_bbox
        )

        color_timestamp, lidar_timestamp = sync_data_dict["color"].timestamp, sync_data_dict["lidar"].timestamp
        if color_timestamp != lidar_timestamp:
            pass

        # Project XYZ to uv-coordinate
        uv_array, pc_distances, _ = sync_data_dict["lidar"].project_xyz_to_uv_inside_bbox(
            camerainfo_msg=sync_data_dict["color"].camerainfo_msg,
            bbox=patch_bbox, random_sample_number=opts.tracker.lidar_params["sampling_number"]
        )

        # Define LiDAR Kernels
        fusion_depth_list = []
        for uv_array_idx in range(len(uv_array)):
            uv_point, pc_distance = uv_array[uv_array_idx], pc_distances[uv_array_idx]
            l_kernel = lidar_kernel(
                    sensor_data=sync_data_dict["disparity"],
                    pc_uv=uv_point, pc_distance=pc_distance,
                    kernel_size=opts.tracker.lidar_params["lidar_kernel_size"]
            )
            fusion_depth_list.append(l_kernel.get_kernel_average_depth())

        # Get Depth Histogram from Fusion Depth List
        if len(fusion_depth_list) >= np.floor(0.1*opts.tracker.lidar_params["sampling_number"]):
            depth_hist, depth_hist_idx = np.histogram(fusion_depth_list)

            # Get Max-bin and Representative Depth Value of Disparity Histogram
            max_bin = depth_hist.argmax()
            depth_value = ((depth_hist_idx[max_bin] + depth_hist_idx[max_bin + 1]) / 2.0)

        elif len(fusion_depth_list) > 0:
            # Get Average Depth Value of the Fusion Depth List
            depth_value = np.average(fusion_depth_list)

        else:
            # Get Kalman Predicted Depth Value
            depth_value = self.x3p[2][0]
        self.depth.append(depth_value)

    # Image Coordinates(2D) to Camera Coordinates(3D) in meters (m)
    def img_coord_to_cam_coord(self, inverse_projection_matrix, opts):
        # If agent type is 'static', the reference point of image coordinate is the bottom center of the tracklet bounding box
        if opts.agent_type == "static":
            img_coord_pos = np.array([self.x3[0][0], (self.x3[1][0] + 0.5 * self.x3[6][0]), 1.0]).reshape((3, 1))
        else:
            img_coord_pos = np.array([self.x3[0][0], self.x3[1][0], 1.0]).reshape((3, 1))
        img_coord_vel = np.array([self.x3[3][0], self.x3[4][0], 1.0]).reshape((3, 1))

        cam_coord_pos = np.matmul(inverse_projection_matrix, img_coord_pos)
        cam_coord_vel = np.matmul(inverse_projection_matrix, img_coord_vel)

        cam_coord_pos *= self.depth[-1]
        cam_coord_vel *= self.depth[-1]

        # Consider Robot Coordinates
        cam_coord_pos = np.array([cam_coord_pos[2][0], -cam_coord_pos[0][0], -cam_coord_pos[1][0]]).reshape((3, 1))
        cam_coord_vel = np.array([cam_coord_vel[2][0], -cam_coord_vel[0][0], -cam_coord_vel[1][0]]).reshape((3, 1))

        # Camera Coordinate State
        self.c3 = np.array([cam_coord_pos[0][0], cam_coord_pos[1][0], cam_coord_pos[2][0],
                            cam_coord_vel[0][0], cam_coord_vel[1][0], cam_coord_vel[2][0]]).reshape((6, 1))

    # Camera Coordinates(3D) to Image Coordinates(2D)
    def cam_coord_to_img_coord(self):
        raise NotImplementedError()

    # Get Roll-Pitch-Yaw
    def compute_rpy(self, roll=0.0):
        direction_vector = self.c3.reshape(6)[3:6].reshape((3, 1))

        # Roll needs additional information
        self.roll = roll

        # Pitch
        denum = np.sqrt(direction_vector[0][0] * direction_vector[0][0] + direction_vector[1][0] * direction_vector[1][0])
        self.pitch = math.atan2(direction_vector[2][0], denum)

        # Yaw
        self.yaw = math.atan2(direction_vector[1][0], direction_vector[0][0])


if __name__ == "__main__":
    tt = np.array([1, 2, 3, 4, 5])
    np.delete(tt, 0)

