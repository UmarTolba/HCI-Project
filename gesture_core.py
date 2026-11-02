"""
Shared gesture-recognition code used by train_gestures_v3.py and
live_gestures.py, so training and live use exactly the same maths.

Pipeline: pose landmarks (pixels) -> clip-level normalization (origin at the
shoulder midpoint, 1.0 = median shoulder width) -> resample to SEQ_LEN frames
-> position + velocity features -> DTW nearest-class matching.
"""

from pathlib import Path
import traceback

import numpy as np

GESTURES = ["swipe_left", "swipe_right", "raise_hand", "cross_arms"]
UNKNOWN_LABEL = "unknown"

# Shoulders, elbows, wrists, pinkies, index fingers, hips.
LANDMARK_IDS = [11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 23, 24]
WRIST_INDEXES = [LANDMARK_IDS.index(15), LANDMARK_IDS.index(16)]

SEQ_LEN = 30                    # every clip/window is stretched to this length
MIN_VALID_FRAMES = 8            # frames with both shoulders visible
MIN_SHOULDER_VISIBILITY = 0.5   # frames below this are dropped
MIN_LANDMARK_VISIBILITY = 0.35  # other landmarks below this reuse last value
MIN_SHOULDER_PX = 20.0          # median shoulder width smaller -> clip unusable
CLAMP = 5.0                     # safety limit, in shoulder widths
DEFAULT_VELOCITY_WEIGHT = 3.0


# ---------------- POSE EXTRACTION ----------------

def new_pose():
    import mediapipe as mp
    return mp.solutions.pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        smooth_landmarks=True,
        enable_segmentation=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )


def landmarks_to_row(results, width, height):
    """One frame -> (xy pixels (L, 2), visibility (L,)) or None if no pose."""
    if results.pose_landmarks is None:
        return None
    lm = results.pose_landmarks.landmark
    xy = np.array([[lm[i].x * width, lm[i].y * height] for i in LANDMARK_IDS])
    vis = np.array([lm[i].visibility for i in LANDMARK_IDS])
    return xy, vis


def resample(arr, n):
    """Linearly stretch/shrink (frames, landmarks, 2) to n frames."""
    frames = arr.shape[0]
    flat = arr.reshape(frames, -1)
    if frames == n:
        return arr.copy()
    t_old = np.linspace(0.0, 1.0, frames)
    t_new = np.linspace(0.0, 1.0, n)
    cols = [np.interp(t_new, t_old, flat[:, k]) for k in range(flat.shape[1])]
    return np.stack(cols, axis=1).reshape(n, arr.shape[1], arr.shape[2])


def normalize_rows(rows):
    """
    rows: list of (xy pixels, visibility) from landmarks_to_row.
    Returns (sequence (SEQ_LEN, L, 2), None) or (None, reason).

    The scale is the MEDIAN shoulder width over the whole clip, so a single
    frame with badly detected shoulders cannot blow up the coordinates.
    """
    good = [
        (xy, vis) for xy, vis in rows
        if vis[0] >= MIN_SHOULDER_VISIBILITY
        and vis[1] >= MIN_SHOULDER_VISIBILITY
    ]
    if len(good) < MIN_VALID_FRAMES:
        return None, (f"only {len(good)} frames with both shoulders visible "
                      f"(need {MIN_VALID_FRAMES})")

    scale = float(np.median([np.linalg.norm(xy[0] - xy[1]) for xy, _ in good]))
    if scale < MIN_SHOULDER_PX:
        return None, (f"median shoulder width {scale:.0f}px is too small "
                      f"(need {MIN_SHOULDER_PX:.0f}px)")

    out = []
    last = None
    for xy, vis in good:
        center = (xy[0] + xy[1]) / 2.0
        norm = (xy - center) / scale
        if last is not None:
            low = vis < MIN_LANDMARK_VISIBILITY
            norm[low] = last[low]
        last = norm.copy()
        out.append(norm)

    arr = np.clip(np.stack(out), -CLAMP, CLAMP)
    return resample(arr, SEQ_LEN), None


def extract_video_sequence(video_path, max_frames=45):
    """
    Reads a video and returns (sequence, duration_seconds).
    Returns (None, None) (after printing why) if the clip is unusable.
    """
    import cv2

    video_path = Path(video_path)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"[SKIP] Cannot open: {video_path.name}")
        return None, None

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    if frame_count <= 0:
        cap.release()
        print(f"[SKIP] No readable frames: {video_path.name}")
        return None, None

    if frame_count <= max_frames:
        wanted = set(range(frame_count))
    else:
        step = (frame_count - 1) / (max_frames - 1)
        wanted = {round(i * step) for i in range(max_frames)}

    rows = []
    try:
        with new_pose() as pose:
            index = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if index in wanted:
                    h, w = frame.shape[:2]
                    res = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    row = landmarks_to_row(res, w, h)
                    if row is not None:
                        rows.append(row)
                index += 1
    finally:
        cap.release()

    seq, reason = normalize_rows(rows)
    if seq is None:
        print(f"[SKIP] {video_path.name}: {reason}")
        return None, None

    duration = frame_count / fps if fps > 0 else None
    return seq, duration


# ---------------- FEATURES ----------------

def to_features(sequence, velocity_weight=DEFAULT_VELOCITY_WEIGHT):
    """(frames, L, 2) -> (frames, L*2*2): positions + weighted velocity."""
    arr = np.asarray(sequence, dtype=np.float64)
    pos = arr.reshape(arr.shape[0], -1)
    vel = np.diff(pos, axis=0, prepend=pos[:1])
    return np.concatenate([pos, velocity_weight * vel], axis=1)


def motion_amount(sequence):
    """Largest wrist travel (x or y range), in shoulder widths."""
    arr = np.asarray(sequence, dtype=np.float64)
    best = 0.0
    for k in WRIST_INDEXES:
        xs, ys = arr[:, k, 0], arr[:, k, 1]
        best = max(best, xs.max() - xs.min(), ys.max() - ys.min())
    return float(best)


# ---------------- DTW ----------------

def dtw_distance(a, b):
    n, m = len(a), len(b)
    cost = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2).tolist()
    inf = float("inf")

    prev = [inf] * (m + 1)
    prev[0] = 0.0
    for i in range(n):
        cur = [inf] * (m + 1)
        ci = cost[i]
        for j in range(1, m + 1):
            best = prev[j]
            if cur[j - 1] < best:
                best = cur[j - 1]
            if prev[j - 1] < best:
                best = prev[j - 1]
            cur[j] = ci[j - 1] + best
        prev = cur

    return prev[m] / (n + m)


class DTWRecognizer:
    def __init__(self, templates, velocity_weight=DEFAULT_VELOCITY_WEIGHT):
        """templates: list of (label, normalized_sequence)."""
        if not templates:
            raise RuntimeError("No templates given.")
        self.velocity_weight = velocity_weight
        self.templates = [
            (label, to_features(seq, velocity_weight))
            for label, seq in templates
        ]

    def class_distances(self, sequence):
        """Best (smallest) DTW distance to each class."""
        query = to_features(sequence, self.velocity_weight)
        best = {}
        for label, template in self.templates:
            d = dtw_distance(query, template)
            if label not in best or d < best[label]:
                best[label] = d
        return best


def predict(recognizer, sequence, min_margin=0.0, max_distance=None,
            min_motion=0.0):
    """Returns (label, best_distance, margin, motion)."""
    motion = motion_amount(sequence)
    if motion < min_motion:
        return UNKNOWN_LABEL, float("nan"), float("nan"), motion

    try:
        dists = recognizer.class_distances(sequence)
    except Exception:
        traceback.print_exc()
        return "ERROR", float("nan"), float("nan"), motion

    ranked = sorted(dists.items(), key=lambda kv: kv[1])
    label, best = ranked[0]
    margin = ranked[1][1] - best if len(ranked) > 1 else float("inf")

    if label != UNKNOWN_LABEL:
        if margin < min_margin:
            label = UNKNOWN_LABEL
        elif max_distance is not None and best > max_distance:
            label = UNKNOWN_LABEL

    return label, best, margin, motion
