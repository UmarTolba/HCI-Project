"""
Python <-> Java bridge for the Museum Ticket Kiosk.

    reacTIVision --UDP/TUIO--> [TuioMarkerSource] --\
                                                     >--> one queue --> [SocketClient] --TCP--> Java app
    webcam -> MediaPipe + DollarPy -> [GestureRecognizer] --/            (one connection, one message per line)
    keyboard (testing) --------> [ConsoleSource] --/

Message format (one per line, matches Main/MainFrame on the Java side):
    marker:<id>          e.g. marker:2
    notice:<text>        e.g. notice:Wheelchairs are available.   (sent right after the marker)
    gesture:<name>       e.g. gesture:swipe_left

Run order:  1) reacTIVision   2) Java app   3) python bridge.py
            (the bridge keeps retrying, so the order is not critical)

Gestures need a camera of their own (--camera N): reacTIVision keeps its camera busy, so use a second
webcam. Without mediapipe/dollarpy installed, or with --no-gestures, only markers + the keyboard work.
"""
import argparse
import sys
import time

from gestures import ConsoleSource, normalize
from socket_client import SocketClient
from tuio_markers import TuioMarkerSource, notice_for


def problem_text(text):
    return " ".join(str(text).split())[:220]          # one line, so it fits the socket protocol


class MessageStream:
    """The single merged stream. Every source calls publish(); order is kept by the queue."""

    def __init__(self, client, gesture_gap=0.4):
        self.client = client
        self.gesture_gap = gesture_gap
        self.last_gesture = ("", 0.0)

    def publish(self, kind, value):
        if kind == "gesture":
            value = normalize(value)
            name, when = self.last_gesture
            now = time.time()
            if value == name and now - when < self.gesture_gap:
                return                                  # same gesture fired twice in a row: one gesture
            self.last_gesture = (value, now)
        self.client.send(f"{kind}:{value}")
        if kind == "marker":                            # same path for camera markers and typed m1..m5
            text = notice_for(value)
            if text:
                self.client.send(f"notice:{text}")


def main():
    parser = argparse.ArgumentParser(description="Marker + gesture bridge to the Java kiosk")
    parser.add_argument("--java-host", default="127.0.0.1")
    parser.add_argument("--java-port", type=int, default=5000)
    parser.add_argument("--tuio-port", type=int, default=3333, help="reacTIVision's TUIO port")
    parser.add_argument("--no-tuio", action="store_true", help="no camera: use the console only")
    parser.add_argument("--no-console", action="store_true", help="do not read typed test commands")
    parser.add_argument("--no-gestures", action="store_true", help="do not start the MediaPipe gesture recognizer")
    parser.add_argument("--camera", type=int, default=0, help="webcam index for gestures (not reacTIVision's)")
    parser.add_argument("--show", action="store_true", help="preview window with the tracked wrists (ESC closes it)")
    parser.add_argument("--debug-gestures", action="store_true", help="print DollarPy's best match and score")
    parser.add_argument("--min-score", type=float, default=0.5, help="below this DollarPy score = unknown gesture")
    parser.add_argument("--invert-swipes", action="store_true", help="swap swipe_left / swipe_right")
    args = parser.parse_args()

    client = SocketClient(args.java_host, args.java_port)
    client.start()
    stream = MessageStream(client)

    if not args.no_tuio:
        TuioMarkerSource(stream.publish, port=args.tuio_port).start()

    recognizer = None
    if not args.no_gestures:
        try:
            from gesture_recognizer import GestureRecognizer
            recognizer = GestureRecognizer(args.camera, args.show, args.debug_gestures,
                                           args.min_score, args.invert_swipes)
        except Exception as err:                         # missing mediapipe / opencv / dollarpy, broken install...
            print(f"[GESTURE] disabled ({err}). Run: pip install -r requirements.txt  (with {sys.executable})")
            stream.publish("status", "problem:" + problem_text(
                f"gesture libraries not ready ({err}). Run: pip install -r requirements.txt"))

    if not args.no_console:
        ConsoleSource(stream.publish).start()

    print("Bridge running. Ctrl+C to quit.")
    try:
        if recognizer:
            # runs in the main thread so the --show preview window works on every OS
            recognizer.run(lambda name: stream.publish("gesture", name),
                           on_ready=lambda: stream.publish("status", "gesture_ready"),
                           on_problem=lambda text: (print(f"[GESTURE] PROBLEM: {text}"),
                                                    stream.publish("status", "problem:" + problem_text(text))))
            time.sleep(1.0)                              # let the problem message leave the socket queue
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    print("Bridge stopped")
    client.stop()


if __name__ == "__main__":
    main()
