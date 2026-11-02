"""
Live gesture recognizer for the museum ticket kiosk.

Start the Java kiosk FIRST (it listens on port 5000), then run:
    python live_gestures.py
Useful flags:
    --flip          mirror the camera image (use if swipe left triggers right)
    --camera 1      pick another webcam
    --window 2.0    seconds of history per recognition (default: training clip length)
    --no-send       recognize and show results but don't talk to the kiosk

Sends one line per recognized gesture, e.g.  gesture:swipe_left\\n
(the exact strings MainFrame.onGesture expects). It never sends "unknown",
because MainFrame would show an error screen for it.
Press q in the preview window to quit.
"""

import argparse
from collections import deque
from pathlib import Path
import pickle
import socket
import sys
import time

import cv2

import gesture_core as core

# ---------------- SETTINGS ----------------

TEMPLATES_FILE = Path(__file__).with_name("gesture_templates.pkl")

HOST = "127.0.0.1"
PORT = 5000

CAMERA_INDEX = 0
FLIP_CAMERA = False           # True if the kiosk camera is mirrored vs training

RECOGNIZE_EVERY = 0.1        # seconds between recognitions
CONFIRMATIONS = 2             # same label this many times in a row
LIVE_MIN_MARGIN = 0.3         # best class must beat the runner-up by this
LIVE_MIN_MOTION = 0.8         # wrist travel in shoulder widths
LIVE_MAX_DISTANCE = None      # e.g. 3.0 to also reject poor matches
COOLDOWN_SECONDS = 3.0        # after a send (MainFrame error screen is 2.5s)
MIN_WINDOW_FILL = 0.6         # fraction of the window that must be filled


# ---------------- KIOSK CONNECTION ----------------

class KioskLink:
    """TCP client that stays connected and reconnects when needed."""

    def __init__(self, host, port, enabled=True):
        self.host, self.port, self.enabled = host, port, enabled
        self.sock = None
        if enabled:
            self._connect()

    def _connect(self):
        try:
            self.sock = socket.create_connection((self.host, self.port), 2)
            print(f"[SOCKET] Connected to {self.host}:{self.port}")
        except OSError as e:
            self.sock = None
            print(f"[SOCKET] Cannot connect to {self.host}:{self.port} ({e}). "
                  "Is the Java kiosk running?")

    def send(self, label):
        line = f"gesture:{label}\n"
        if not self.enabled:
            print(f"[DRY RUN] would send {line.strip()}")
            return True
        for _ in range(2):
            if self.sock is None:
                self._connect()
            if self.sock is None:
                return False
            try:
                self.sock.sendall(line.encode("utf-8"))
                print(f"[SEND] {line.strip()}")
                return True
            except OSError:
                try:
                    self.sock.close()
                except OSError:
                    pass
                self.sock = None
        return False

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass


# ---------------- MAIN ----------------

def draw_status(frame, lines, color=(0, 255, 0)):
    y = 28
    for text in lines:
        cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    color, 2, cv2.LINE_AA)
        y += 30


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--flip", action="store_true", default=FLIP_CAMERA)
    parser.add_argument("--camera", type=int, default=CAMERA_INDEX)
    parser.add_argument("--window", type=float, default=None)
    parser.add_argument("--no-send", action="store_true")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    if not TEMPLATES_FILE.is_file():
        sys.exit(f"{TEMPLATES_FILE.name} not found. "
                 "Run train_gestures_v3.py first.")
    with TEMPLATES_FILE.open("rb") as f:
        payload = pickle.load(f)

    recognizer = core.DTWRecognizer(
        [(label, seq) for label, _, seq in payload["templates"]],
        payload.get("velocity_weight", core.DEFAULT_VELOCITY_WEIGHT),
    )
    window = args.window or payload.get("suggested_window_seconds") or 2.0
    print(f"Loaded {len(payload['templates'])} templates. "
          f"Window: {window:.2f}s. Flip: {args.flip}")

    link = KioskLink(args.host, args.port, enabled=not args.no_send)

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        sys.exit(f"Cannot open camera {args.camera}.")

    buffer = deque()          # (timestamp, row)
    last_label = None
    streak = 0
    next_check = 0.0
    cooldown_until = 0.0
    info = "waiting..."

    try:
        with core.new_pose() as pose:
            while True:
                ok, frame = cap.read()
                if not ok:
                    print("Camera read failed.")
                    break
                if args.flip:
                    frame = cv2.flip(frame, 1)

                now = time.time()
                h, w = frame.shape[:2]
                results = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                row = core.landmarks_to_row(results, w, h)

                in_cooldown = now < cooldown_until
                if row is not None and not in_cooldown:
                    buffer.append((now, row))
                while buffer and now - buffer[0][0] > window:
                    buffer.popleft()

                if in_cooldown:
                    info = f"cooldown {cooldown_until - now:.1f}s"
                elif row is None:
                    info = "no person detected"
                    streak, last_label = 0, None
                elif (now >= next_check and len(buffer) >= core.MIN_VALID_FRAMES
                      and buffer[-1][0] - buffer[0][0]
                      >= MIN_WINDOW_FILL * window):
                    next_check = now + RECOGNIZE_EVERY
                    seq, why = core.normalize_rows([r for _, r in buffer])

                    if seq is None:
                        info = why
                        streak, last_label = 0, None
                    else:
                        label, dist, margin, motion = core.predict(
                            recognizer, seq, LIVE_MIN_MARGIN,
                            LIVE_MAX_DISTANCE, LIVE_MIN_MOTION)
                        info = (f"{label} d={dist:.2f} m={margin:.2f} "
                                f"motion={motion:.2f}")

                        if label in core.GESTURES:
                            streak = streak + 1 if label == last_label else 1
                            last_label = label
                        else:
                            streak, last_label = 0, None

                        if streak >= CONFIRMATIONS:
                            link.send(label)
                            cooldown_until = time.time() + COOLDOWN_SECONDS
                            buffer.clear()
                            streak, last_label = 0, None

                if results.pose_landmarks is not None:
                    import mediapipe as mp
                    mp.solutions.drawing_utils.draw_landmarks(
                        frame, results.pose_landmarks,
                        mp.solutions.pose.POSE_CONNECTIONS)
                draw_status(frame, [info],
                            (0, 200, 255) if in_cooldown else (0, 255, 0))
                cv2.imshow("Gesture kiosk (q to quit)", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        link.close()


if __name__ == "__main__":
    main()
