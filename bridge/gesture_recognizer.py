"""
Gesture recognition for the Museum Ticket Kiosk (MediaPipe skeleton + DollarPy).

    webcam --> MediaPipe Pose (skeleton) --> wrist positions --> motion segmenter
           --> DollarPy ($P recogniser) --> "swipe_left" | "swipe_right" | "raise_hand" | "cross_arms"
           --> emit(name)  -->  bridge.py  -->  socket  -->  Java

How a gesture is recognised
  1. MediaPipe's PoseLandmarker gives the 33 body landmarks per frame; we only use the two wrists.
     x is mirrored (x = 1 - x) so "right" on screen is the person's right.
  2. A segmenter waits until a wrist starts moving, records until both wrists are still again,
     then hands that one movement to the classifier.
  3. The movement is turned into 4 curves over time (active wrist dx, dy and other wrist dx, dy,
     all relative to where they started) and drawn into one point cloud, so DollarPy sees the SHAPE
     of the movement over time. Plotting against time is what lets it tell left from right,
     because a plain $P point cloud ignores the direction of travel.
  4. DollarPy compares that cloud with the templates and returns (name, score).

Templates: built-in ones are generated in code so it works out of the box. For better accuracy
record your own (they replace the built-in ones for that gesture):

    python gesture_recognizer.py --record swipe_left --samples 6
    python gesture_recognizer.py --record cross_arms --samples 6      (do some with each hand)

Try it alone (no Java needed):   python gesture_recognizer.py --show --debug
"""
import argparse
import json
import os
import sys
import threading
import time
import traceback
import urllib.request
from collections import deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "pose_landmarker_lite.task")
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
             "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task")
TEMPLATE_FILE = os.path.join(HERE, "gesture_templates.json")

GESTURES = ("swipe_left", "swipe_right", "raise_hand", "cross_arms")
LEFT_WRIST, RIGHT_WRIST = 15, 16      # MediaPipe pose landmark indices

N_FRAMES = 24          # every movement is resampled to this many frames
TIME_SCALE = 3.0       # width of the time axis in the point cloud
CHANNEL_GAP = 1.4      # vertical gap between the 4 curves so they do not overlap


# --------------------------------------------------------------------------------------
# Movement -> DollarPy points
# --------------------------------------------------------------------------------------
def to_channels(arr, n=N_FRAMES):
    """arr: rows of (t, lx, ly, rx, ry). Returns 4 x n array of movement relative to the start:
    active wrist dx, dy and other wrist dx, dy ("active" = the wrist that moved more)."""
    t = arr[:, 0]
    tt = np.linspace(t[0], t[-1], n)
    w = [np.interp(tt, t, arr[:, k]) for k in (1, 2, 3, 4)]
    left, right = (w[0], w[1]), (w[2], w[3])

    def path(p):
        return float(np.sum(np.hypot(np.diff(p[0]), np.diff(p[1]))))

    active, other = (left, right) if path(left) >= path(right) else (right, left)
    return np.stack([active[0] - active[0][0], active[1] - active[1][0],
                     other[0] - other[0][0], other[1] - other[1][0]])


def channels_to_points(channels, Point):
    """4 curves -> one DollarPy point cloud (each curve is its own stroke id)."""
    n = channels.shape[1]
    pts = []
    for k, row in enumerate(channels):
        for i, v in enumerate(row):
            pts.append(Point(i / (n - 1) * TIME_SCALE, float(v) + k * CHANNEL_GAP, k + 1))
    return pts


def builtin_channels():
    """Generated templates: {gesture: [4 x N arrays]}. Image y grows downwards, so rising = negative."""
    out = {g: [] for g in GESTURES}
    s = np.linspace(0, 1, N_FRAMES)
    zero = np.zeros(N_FRAMES)
    for amp in (0.75, 1.25):
        for e in (s, 0.5 - 0.5 * np.cos(np.pi * s)):          # constant speed / smooth start-stop
            out["swipe_right"].append(np.stack([0.45 * amp * e, zero, zero, zero]))
            out["swipe_left"].append(np.stack([-0.45 * amp * e, zero, zero, zero]))
            out["raise_hand"].append(np.stack([zero, -0.6 * amp * e, zero, zero]))
            for sign in (1, -1):                                # either hand can be the "active" one
                out["cross_arms"].append(np.stack([sign * 0.25 * amp * e, -0.15 * amp * e,
                                                   -sign * 0.25 * amp * e, -0.15 * amp * e]))
    return out


def load_template_channels():
    chans = builtin_channels()
    if os.path.exists(TEMPLATE_FILE):
        try:
            with open(TEMPLATE_FILE) as f:
                saved = json.load(f)
            for name, samples in saved.items():
                if name in chans and samples:
                    chans[name] = [np.array(x, dtype=float) for x in samples]   # yours replace built-ins
                    print(f"[GESTURE] using {len(samples)} recorded template(s) for {name}")
        except (OSError, ValueError) as err:
            print(f"[GESTURE] could not read {TEMPLATE_FILE}: {err}")
    return chans


class DollarClassifier:
    """Thin wrapper around DollarPy's Recognizer."""

    def __init__(self, min_score=0.5, debug=False):
        from dollarpy import Recognizer, Template, Point
        self.Point = Point
        self.min_score = min_score
        self.debug = debug
        templates = []
        for name, samples in load_template_channels().items():
            for ch in samples:
                templates.append(Template(name, channels_to_points(ch, Point)))
        self.recognizer = Recognizer(templates)
        print(f"[GESTURE] DollarPy ready with {len(templates)} templates")

    @staticmethod
    def _parse(result):
        if isinstance(result, (list, tuple)) and len(result) >= 2:
            return str(result[0]), float(result[1])
        if hasattr(result, "name"):
            return str(result.name), float(getattr(result, "score", 1.0))
        return None, 0.0

    def classify(self, arr):
        """Returns (gesture name, score). Name is 'unknown' if nothing matched well enough."""
        name, score = self._parse(self.recognizer.recognize(channels_to_points(to_channels(arr), self.Point)))
        if self.debug:
            print(f"[GESTURE] best match: {name} (score {score:.2f})")
        if name not in GESTURES or score < self.min_score:
            return "unknown", score
        return name, score


# --------------------------------------------------------------------------------------
# Cutting the continuous wrist stream into single movements
# --------------------------------------------------------------------------------------
class GestureSegmenter:
    START_SPEED = 0.5      # wrist speed (frame-widths/second) that starts a movement
    STOP_SPEED = 0.25      # below this the hand counts as still
    STILL_TIME = 0.3       # seconds of stillness that end a movement
    MIN_DURATION = 0.2
    MAX_DURATION = 2.0
    MIN_PATH = 0.15        # ignore tiny movements (jitter, scratching your nose)
    PRE_ROLL = 0.15
    SMOOTH = 0.5           # exponential smoothing of the wrist positions

    def __init__(self, on_segment, cooldown=1.2):
        """on_segment(arr) -> True if it produced a result (starts the cooldown)."""
        self.on_segment = on_segment
        self.cooldown = cooldown
        self.hist = deque()
        self.rec = None
        self.smooth = None
        self.last_move = 0.0
        self.blocked_until = 0.0
        self.armed = True            # becomes False after a gesture until the hands are still again
        self.still_since = None

    def feed(self, t, lx, ly, rx, ry):
        p = np.array([lx, ly, rx, ry], dtype=float)
        self.smooth = p if self.smooth is None else self.SMOOTH * p + (1 - self.SMOOTH) * self.smooth
        row = (t, *self.smooth)
        self.hist.append(row)
        while self.hist and t - self.hist[0][0] > 0.5:
            self.hist.popleft()
        speed = self._speed(t)

        if self.rec is None:
            if t < self.blocked_until:
                return
            if not self.armed:                      # wait for the hands to settle (e.g. lowering after a raise)
                if speed < self.STOP_SPEED:
                    self.still_since = self.still_since or t
                    if t - self.still_since >= 0.25:
                        self.armed = True
                else:
                    self.still_since = None
                return
            if speed > self.START_SPEED:
                self.rec = [h for h in self.hist if h[0] >= t - self.PRE_ROLL]
                self.last_move = t
            return
        self.rec.append(row)
        if speed > self.STOP_SPEED:
            self.last_move = t
        if t - self.last_move > self.STILL_TIME or t - self.rec[0][0] > self.MAX_DURATION:
            self._finish(t)

    def reset(self):
        self.rec = None
        self.hist.clear()
        self.smooth = None
        self.armed, self.still_since = True, None

    def _speed(self, t):
        recent = [h for h in self.hist if h[0] >= t - 0.15]
        if len(recent) < 2 or recent[-1][0] - recent[0][0] < 0.03:
            return 0.0
        dt = recent[-1][0] - recent[0][0]
        a, b = np.array(recent[0][1:]), np.array(recent[-1][1:])
        return float(max(np.hypot(*(b[0:2] - a[0:2])), np.hypot(*(b[2:4] - a[2:4]))) / dt)

    def _finish(self, t):
        rec = [r for r in self.rec if r[0] <= self.last_move + 0.1]
        self.rec = None
        if len(rec) < 4 or rec[-1][0] - rec[0][0] < self.MIN_DURATION:
            return
        arr = np.array(rec)
        path = max(float(np.sum(np.hypot(np.diff(arr[:, 1]), np.diff(arr[:, 2])))),
                   float(np.sum(np.hypot(np.diff(arr[:, 3]), np.diff(arr[:, 4])))))
        if path < self.MIN_PATH:
            return
        if self.on_segment(arr, path):
            self.blocked_until = t + self.cooldown
            self.armed, self.still_since = False, None


# --------------------------------------------------------------------------------------
# Camera + MediaPipe
# --------------------------------------------------------------------------------------
def ensure_model():
    if not os.path.exists(MODEL_PATH):
        print("[GESTURE] downloading the MediaPipe pose model (about 5 MB, one time)...")
        try:
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        except Exception as err:
            raise RuntimeError(f"could not download the pose model ({err}). Download {MODEL_URL} "
                               f"into the bridge folder") from err
    return MODEL_PATH


def open_camera(cv2, index):
    """Open a webcam and make sure it really delivers frames. On Windows several backends are tried,
    because some built-in cameras only work with one of them."""
    backends = [None]
    if sys.platform.startswith("win"):
        backends += [cv2.CAP_MSMF, cv2.CAP_DSHOW]
    for backend in backends:
        cap = cv2.VideoCapture(index) if backend is None else cv2.VideoCapture(index, backend)
        if cap.isOpened():
            for _ in range(30):                       # some cameras need a moment before the first frame
                ok, _frame = cap.read()
                if ok:
                    return cap
                time.sleep(0.1)
        cap.release()
    return None


class GestureRecognizer:
    def __init__(self, camera=0, show=False, debug=False, min_score=0.5, invert_swipes=False,
                 record=None, samples=5):
        self.camera, self.show, self.debug = camera, show, debug
        self.invert_swipes = invert_swipes
        self.record, self.samples = record, samples
        self.recorded = []
        self.emit = lambda name: print(f"[GESTURE] {name}")
        self.running = False
        self.status = ""
        self.classifier = None if record else DollarClassifier(min_score, debug)
        self.segmenter = GestureSegmenter(self._on_segment, cooldown=2.0 if record else 1.2)

    # ---- called by the segmenter with one complete movement ----
    def _on_segment(self, arr, path):
        if self.record:
            self.recorded.append(to_channels(arr).tolist())
            print(f"[RECORD] sample {len(self.recorded)}/{self.samples} captured. Lower your hands.")
            self.status = f"recorded {len(self.recorded)}/{self.samples}"
            if len(self.recorded) >= self.samples:
                self._save_samples()
                self.running = False
            return True
        name, score = self.classifier.classify(arr)
        if name == "unknown" and path < 0.25:
            return False                                   # a small wobble is not worth an error message
        if self.invert_swipes and name in ("swipe_left", "swipe_right"):
            name = "swipe_right" if name == "swipe_left" else "swipe_left"
        self.status = f"{name} ({score:.2f})"
        self.emit(name)
        return True

    def _save_samples(self):
        data = {}
        if os.path.exists(TEMPLATE_FILE):
            with open(TEMPLATE_FILE) as f:
                data = json.load(f)
        data.setdefault(self.record, []).extend(self.recorded)
        with open(TEMPLATE_FILE, "w") as f:
            json.dump(data, f)
        print(f"[RECORD] saved {len(self.recorded)} samples for {self.record} to {TEMPLATE_FILE}")

    # ---- main loop ----
    def start(self, emit):
        """Background-thread mode (no preview window)."""
        self.emit, self.show = emit, False
        threading.Thread(target=self.run, daemon=True).start()

    def run(self, emit=None, on_ready=None, on_problem=None):
        """Blocking loop. Use this from the main thread if you want the preview window (--show).
        on_ready() is called once the camera and the pose model are up; on_problem(text) if they cannot be."""
        problem = on_problem or (lambda text: print(f"[GESTURE] PROBLEM: {text}"))
        try:
            self._run(emit, on_ready, problem)
        except Exception as err:                      # missing library, model download, camera driver...
            traceback.print_exc()
            problem(f"{type(err).__name__}: {err}")

    def _run(self, emit, on_ready, problem):
        import cv2
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        if emit:
            self.emit = emit
        options = vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=ensure_model()),
            running_mode=vision.RunningMode.VIDEO, num_poses=1)
        cap = open_camera(cv2, self.camera)
        if cap is None:
            problem(f"cannot open camera {self.camera}, or it gives no picture. Another program (reacTIVision?) "
                    f"may be using it. Try another number with -Dkiosk.gestureCamera=1")
            return
        if self.record:
            print(f"[RECORD] do the '{self.record}' gesture {self.samples} times. Pause between each.")
        print("[GESTURE] camera running. Stand 1-2 m from the camera with both wrists visible.")
        self.running = True
        last_ts = 0
        with vision.PoseLandmarker.create_from_options(options) as landmarker:
            if on_ready:
                on_ready()
            while self.running:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.01)
                    continue
                ts = max(int(time.monotonic() * 1000), last_ts + 1)
                last_ts = ts
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
                wrists = None
                if result.pose_landmarks:
                    lm = result.pose_landmarks[0]
                    lw, rw = lm[LEFT_WRIST], lm[RIGHT_WRIST]
                    if min(lw.visibility, rw.visibility) > 0.2:
                        wrists = (1 - lw.x, lw.y, 1 - rw.x, rw.y)          # x mirrored
                        self.segmenter.feed(ts / 1000.0, *wrists)
                if self.show:
                    self._draw(cv2, frame, wrists)
                    if cv2.waitKey(1) & 0xFF == 27:                          # ESC
                        self.running = False
        cap.release()
        if self.show:
            cv2.destroyAllWindows()

    def _draw(self, cv2, frame, wrists):
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        if wrists:
            for x, y in ((wrists[0], wrists[1]), (wrists[2], wrists[3])):
                cv2.circle(frame, (int(x * w), int(y * h)), 10, (0, 200, 255), -1)
        label = "recording..." if self.segmenter.rec else "ready"
        cv2.putText(frame, f"{label}  {self.status}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("Gesture recognizer (ESC to quit)", frame)

    def stop(self):
        self.running = False


def main():
    p = argparse.ArgumentParser(description="MediaPipe + DollarPy gesture recognizer (stand-alone test)")
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--show", action="store_true", help="preview window")
    p.add_argument("--debug", action="store_true", help="print the best match and score for every movement")
    p.add_argument("--min-score", type=float, default=0.5)
    p.add_argument("--invert-swipes", action="store_true")
    p.add_argument("--record", choices=GESTURES, help="record your own templates for this gesture")
    p.add_argument("--samples", type=int, default=5)
    a = p.parse_args()
    GestureRecognizer(a.camera, a.show, a.debug, a.min_score, a.invert_swipes, a.record, a.samples).run()


if __name__ == "__main__":
    main()
