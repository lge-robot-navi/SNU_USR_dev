"""
SNU Integrated Module v4.0



"""
import numpy as np
import datetime

import module_detection as snu_det
import module_tracking as snu_trk
import module_action as snu_acl


class snu_algorithms(object):
    def __init__(self, frameworks):
        # Load Detection Model
        self.det_framework = frameworks["det"]

        # Load Action Classification Model
        self.acl_framework = frameworks["acl"]

        # Initialize Tracklet and Tracklet Candidates
        self.trks, self.trk_cands = [], []

        # Initialize Maximum Tracklet ID
        self.max_trk_id = -1

        # Initialize Detections
        self.detections = {}

        # Initialize Frame Index
        self.fidx = None

        # Initialize Module Time Dictionary
        self.module_time_dict = {
            "det": 0.0,
            "trk": 0.0,
            "acl": 0.0,
        }

    # Detection Module
    def usr_object_detection(self, sync_data_dict, logger, opts):
        # Start Time
        START_TIME = datetime.datetime.now()

        # Parse-out Required Sensor Modalities
        # TODO: Integrate this for all 3 modules
        detection_sensor_data = {}
        for modal, modal_switch in opts.detector.sensor_dict.items():
            if modal_switch is True:
                detection_sensor_data[modal] = sync_data_dict[modal]

        # Activate Module
        dets = snu_det.detect(
            detector=self.det_framework, sync_data_dict=detection_sensor_data,
            opts=opts
        )
        confs, labels = dets[:, 4:5], dets[:, 5:6]
        dets = dets[:, 0:4]

        # Remove Too Small Detections
        keep_indices = []
        for det_idx, det in enumerate(dets):
            if det[2] * det[3] >= opts.detector.tiny_area_threshold:
                keep_indices.append(det_idx)
        dets = dets[keep_indices, :]
        confs = confs[keep_indices, :]
        labels = labels[keep_indices, :]

        # Stop Time
        END_TIME = datetime.datetime.now()

        self.detections = {"dets": dets, "confs": confs, "labels": labels}
        self.module_time_dict["det"] = (END_TIME - START_TIME).total_seconds()

    # Multiple Target Tracking Module
    def usr_multiple_target_tracking(self, sync_data_dict, logger, opts):
        # Start Time
        START_TIME = datetime.datetime.now()

        # Parse-out Required Sensor Modalities
        tracking_sensor_data = {}
        for modal, modal_switch in opts.tracker.sensor_dict.items():
            if modal_switch is True:
                tracking_sensor_data[modal] = sync_data_dict[modal]

        # Activate Module
        self.trks, self.trk_cands = snu_trk.tracker(
            sync_data_dict=tracking_sensor_data, fidx=self.fidx,
            detections=self.detections, max_trk_id=self.max_trk_id,
            opts=opts, trks=self.trks, trk_cands=self.trk_cands
        )

        # Update Maximum Tracklet ID
        for trk in self.trks:
            if trk.id > self.max_trk_id:
                self.max_trk_id = trk.id

        # Stop Time
        END_TIME = datetime.datetime.now()

        self.module_time_dict["trk"] = (END_TIME - START_TIME).total_seconds()

    # Action Classification Module
    def usr_action_classification(self, sync_data_dict, logger, opts):
        START_TIME = datetime.datetime.now()

        # Parse-out Required Sensor Modalities
        aclassify_sensor_data = {}
        for modal, modal_switch in opts.aclassifier.sensor_dict.items():
            if modal_switch is True:
                aclassify_sensor_data[modal] = sync_data_dict[modal]

        # Activate Module
        self.trks = snu_acl.aclassify(
            model=self.acl_framework,
            sync_data_dict=aclassify_sensor_data,
            trackers=self.trks, opts=opts
        )

        END_TIME = datetime.datetime.now()

        self.module_time_dict["acl"] = (END_TIME - START_TIME).total_seconds()

    # Call as Function
    def __call__(self, sync_data_dict, logger, fidx, opts):
        # Update Frame Index
        self.fidx = fidx

        # SNU Object Detector Module
        self.usr_object_detection(
            sync_data_dict=sync_data_dict, logger=logger, opts=opts
        )

        # SNU Multiple Target Tracker Module
        self.usr_multiple_target_tracking(
            sync_data_dict=sync_data_dict, logger=logger, opts=opts
        )

        # SNU Action Classification Module
        self.usr_action_classification(
            sync_data_dict=sync_data_dict, logger=logger, opts=opts
        )

        # NOTE: DO NOT USE PYTHON PRINT FUNCTION, USE "LOGGING" INSTEAD
        # trk_time = "Frame # (%08d) || DET fps:[%3.3f] | TRK fps:[%3.3f]" \
        #            % (self.fidx, 1/self.module_time_dict["det"], 1/self.module_time_dict["trk"])
        # print(trk_time)

        return self.trks, self.detections, self.module_time_dict
