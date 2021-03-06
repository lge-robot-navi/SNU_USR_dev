"""
SNU Integrated Module v4.5
    - Code which defines object classes
    [1] Trajectory Candidate Class
    [2] Trajectory Class
    [3] Refine Class Code

"""

# Import Modules
import math
import numpy as np
import filterpy.kalman.kalman_filter as kalmanfilter

# # Import Custom Modules
# from detection_lib.yolov5 import utils as snu_bbox, utils as snu_patch, utils as snu_hist
# from detection_lib.yolov5.utils import lidar_window
# from detection_lib.yolov5.utils import KCF_PREDICTOR

# Import Custom Modules
import utils.bounding_box as snu_bbox
import utils.patch as snu_patch
import utils.histogram as snu_hist
from utils.profiling import Timer
from utils.lidar import lidar_window
from utils.kcf import KCF_PREDICTOR


# Object Instance Class
class object_instance(object):
    def __init__(self, init_fidx, modal, obj_id=None, obj_type=None):
        # Frame Index
        self.fidxs = [init_fidx]

        # Instance ID
        self.id = obj_id

        # Object Type
        self.obj_type = obj_type

        # Set Modal
        self.modal = modal

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


# Trajectory Candidate Class
class TrajectoryCandidate(object_instance):
    def __init__(self, frame, bbox, conf, label, init_fidx, modal, opts):
        super(TrajectoryCandidate, self).__init__(init_fidx=init_fidx, modal=modal, obj_type="TrajectoryCandidate")

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

    def get_depth(self, sync_data_dict, opts):
        # Parse and Check KWARGS Variable
        assert opts.__class__.__name__ == "snu_option_class"

        # Get Observation Patch bbox
        patch_bbox = self.asso_dets[-1]

        # If LiDAR is unavailable, set depth value as 1.0
        if sync_data_dict["lidar"] is None:
            depth_value = 0.0
        else:
            # Project XYZ to uv-coordinate
            uv_array, pc_distances, _ = sync_data_dict["lidar"].project_xyz_to_uv_inside_bbox(
                camerainfo_msg=sync_data_dict[self.modal].get_camerainfo_msg(), modal=self.modal,
                bbox=patch_bbox, random_sample_number=opts.tracker.lidar_params["sampling_number"]
            )

            # Get Number of LiDAR uv points inside BBOX, if none replace depth value with previous value
            if len(uv_array) == 0:
                depth_value = -np.inf
            else:
                # Define Steepness Parameter w.r.t. Standard Deviation of Point-cloud Distance Distribution
                # PC_stdev is Low -> Gradual Counting Weight (to consider more samples)
                #             High  -> Steep Counting Weight (to consider less samples near average point)
                # stnp = (1.0 / (np.std(pc_distances) + 1e-6))
                stnp = np.std(pc_distances)

                # Compute Counting Weight for LiDAR UV-points, w.r.t. center L2-distance
                _denom = (patch_bbox[2] - patch_bbox[0]) ** 2 + (patch_bbox[3] - patch_bbox[1]) ** 2
                cx, cy = (patch_bbox[0]+patch_bbox[2])/2.0, (patch_bbox[1]+patch_bbox[3])/2.0
                _num = np.sum((uv_array - np.array([cx, cy])) ** 2, axis=1)
                _w = np.exp(-stnp*4.0*(_num / (_denom + 1e-6)))
                counting_weight = _w / _w.sum()

                # Weighted Distance Sum
                depth_value = np.inner(pc_distances, counting_weight)
                if np.isnan(depth_value):
                    depth_value = np.median(pc_distances)
                # print(depth_value)

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

    # Initialize Trajectory Class from TrajectoryCandidate
    def init_tracklet(self, sync_data_dict, trk_id, fidx, opts):
        # Get Depth
        if opts.agent_type == "static":
        # if sync_data_dict["disparity"] is None:
            depth = 1.0
        else:
            depth = self.get_depth(sync_data_dict=sync_data_dict, opts=opts)

        if depth == -np.inf:
            return None

        # Trajectory Initialization Dictionary
        init_trk_dict = {
            "asso_dets": self.asso_dets, "asso_confs": self.asso_confs, "label": self.label,
            "is_associated": self.is_associated, "init_depth": depth
        }

        # Initialize Trajectory
        trajectory = Trajectory(trk_id, fidx, self.modal, opts.tracker, **init_trk_dict)

        return trajectory


class Trajectory(object_instance):
    def __init__(self, trk_id, init_fidx, modal, tracker_opts, **kwargs):
        super(Trajectory, self).__init__(obj_id=trk_id, init_fidx=init_fidx, modal=modal, obj_type="Trajectory")

        # Unpack Input Dictionary
        self.asso_dets = kwargs["asso_dets"]
        self.asso_confs = kwargs["asso_confs"]
        self.label = kwargs["label"]

        # Association Flag
        self.is_associated = kwargs["is_associated"]

        # Trajectory Depth Value
        self.depth = [kwargs["init_depth"]]

        # Trajectory Visualization Color
        self.color = tracker_opts.trajectory_colors[self.id % tracker_opts.trk_color_refresh_period, :] * 255

        # Initialize Trajectory Kalman Parameters
        self.A = tracker_opts.kparams.A  # State Transition Matrix (Motion Model)
        self.H = tracker_opts.kparams.H  # Unit Transformation Matrix
        self.P = tracker_opts.kparams.P  # Error Covariance Matrix
        self.Q = tracker_opts.kparams.Q  # State Covariance Matrix
        self.R = tracker_opts.kparams.R  # Measurement Covariance Matrix

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

        # Trajectory States
        self.states = [self.x3]

        # Trajectory Predicted States
        self.pred_states = [self.x3p]

        # 3D Trajectory State on Camera Coordinates
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

        # If Trajectory is unassociated, replace detection with the previous Kalman Prediction
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

        # Append to Trajectory States
        self.states.append(self.x3)

    def predict(self):
        # Kalman Predict
        self.x3p, self.Pp = kalmanfilter.predict(self.x3, self.P, self.A, self.Q)
        self.pred_states.append(self.x3p)

    def get_2d_img_coord_state(self):
        return snu_bbox.zx3_to_zx2(self.x3)

    def get_depth(self, sync_data_dict, opts):
        # Parse and Check KWARGS Variable
        assert opts.__class__.__name__ == "snu_option_class"

        # Get Observation Patch Bounding Box
        if self.asso_dets[-1] is not None:
            patch_bbox = self.asso_dets[-1]
        else:
            patch_bbox, _ = snu_bbox.zx_to_bbox(self.x3p)

        # # If Label is Human, re-assign bbox area
        # if self.label == 1:
        #     patch_bbox = snu_bbox.resize_bbox(patch_bbox, x_ratio=0.7, y_ratio=0.7)

        # If LiDAR is unavailable, set depth value as 1.0
        if sync_data_dict["lidar"] is None:
            self.depth.append(1.0)
        else:
            # Project XYZ to uv-coordinate
            uv_array, pc_distances, _ = sync_data_dict["lidar"].project_xyz_to_uv_inside_bbox(
                camerainfo_msg=sync_data_dict[self.modal].get_camerainfo_msg(), modal=self.modal,
                bbox=patch_bbox, random_sample_number=opts.tracker.lidar_params["sampling_number"]
            )

            # Get Number of LiDAR uv points inside BBOX, if none replace depth value with previous value
            if len(uv_array) == 0:
                depth_value = self.depth[-1]
            else:
                # Define Steepness Parameter w.r.t. Standard Deviation of Point-cloud Distance Distribution
                # PC_stdev is Low -> Gradual Counting Weight (to consider more samples)
                #             High  -> Steep Counting Weight (to consider less samples near average point)
                # stnp = (1.0 / (np.std(pc_distances) + 1e-6))
                stnp = np.std(pc_distances)

                # Compute Counting Weight for LiDAR UV-points, w.r.t. center L2-distance
                _denom = (patch_bbox[2] - patch_bbox[0]) ** 2 + (patch_bbox[3] - patch_bbox[1]) ** 2
                cx, cy = (patch_bbox[0]+patch_bbox[2])/2.0, (patch_bbox[1]+patch_bbox[3])/2.0
                _num = np.sum((uv_array - np.array([cx, cy])) ** 2, axis=1)
                _w = np.exp(-stnp*4.0*(_num / (_denom + 1e-6)))
                counting_weight = _w / _w.sum()

                # Weighted Distance Sum
                depth_value = np.inner(pc_distances, counting_weight)
                if np.isnan(depth_value):
                    depth_value = np.median(pc_distances)
                # print(depth_value)

            # Append Depth
            self.depth.append(depth_value)

    # Image Coordinates(2D) to Camera Coordinates(3D) in meters (m)
    def img_coord_to_cam_coord(self, inverse_projection_matrix, opts):
        # If agent type is 'static', the reference point of image coordinate is the bottom center of the trajectory bounding box
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

    # Image Coordinates(2D) to Ground Plane in meters (m)
    def img_coord_to_ground_plane(self, sensor_params):
        img_coord_pos = np.array([self.x3[0][0], (self.x3[1][0] + 0.5 * self.x3[6][0])])
        img_coord_vel = np.array([self.x3[3][0], self.x3[4][0]])

        # NOTE: Change Variable names to Ground Coordinates
        world_coord_pos = sensor_params.get_ground_plane_coord(
            x=img_coord_pos[0], y=img_coord_pos[1], norm_mode="pos"
        )
        world_coord_vel = sensor_params.get_ground_plane_coord(
            x=img_coord_vel[0], y=img_coord_vel[1], norm_mode="vel"
        )

        self.c3 = np.array([world_coord_pos[1][0], -world_coord_pos[0][0], world_coord_pos[2][0],
                            world_coord_vel[1][0], -world_coord_vel[0][0], world_coord_vel[2][0]]).reshape((6, 1))

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

