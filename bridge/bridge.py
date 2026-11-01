"""
Python <-> Java bridge for the Museum Ticket Kiosk.

    reacTIVision --UDP/TUIO--> [TuioMarkerSource] --\
                                                     >--> one queue --> [SocketClient] --TCP--> Java app
    Person 1 gestures ---------> [gesture source] --/                   (one connection, one message per line)
    keyboard (testing) --------> [ConsoleSource] --/

Message format (one per line, matches Main/MainFrame on the Java side):
    marker:<id>          e.g. marker:2
    gesture:<name>       e.g. gesture:swipe_left

Run order:  1) reacTIVision   2) Java app   3) python bridge.py
            (the bridge keeps retrying, so the order is not critical)
"""
import argparse
import time

from gestures import ConsoleSource, normalize
from socket_client import SocketClient
from tuio_markers import TuioMarkerSource


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


def main():
    parser = argparse.ArgumentParser(description="Marker + gesture bridge to the Java kiosk")
    parser.add_argument("--java-host", default="127.0.0.1")
    parser.add_argument("--java-port", type=int, default=5000)
    parser.add_argument("--tuio-port", type=int, default=3333, help="reacTIVision's TUIO port")
    parser.add_argument("--no-tuio", action="store_true", help="no camera: use the console only")
    parser.add_argument("--no-console", action="store_true", help="do not read typed test commands")
    args = parser.parse_args()

    client = SocketClient(args.java_host, args.java_port)
    client.start()
    stream = MessageStream(client)

    if not args.no_tuio:
        TuioMarkerSource(stream.publish, port=args.tuio_port).start()

    # ---- Person 1: start the real gesture recognition here, e.g.
    #       from person1_gestures import GestureRecognizer
    #       GestureRecognizer().start(lambda name: stream.publish("gesture", name))
    # -------------------------------------------------------------------------------

    if not args.no_console:
        ConsoleSource(stream.publish).start()

    print("Bridge running. Ctrl+C to quit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Bridge stopped")
        client.stop()


if __name__ == "__main__":
    main()
