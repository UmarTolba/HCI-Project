"""
Hook for Person 1's gesture recognition + a keyboard stand-in for testing.

Person 1: write a class with a start(emit) method. When your code recognises a
gesture, call emit("swipe_left") (or any name below). Anything not in
VALID_GESTURES is sent as "unknown", which makes the Java app show
"Gesture not recognized".  Example:

    class MyGestures:
        def start(self, emit):
            threading.Thread(target=self.loop, args=(emit,), daemon=True).start()
        def loop(self, emit):
            while True:
                name = my_model_predict()      # e.g. "swipe_left"
                if name: emit(name)

then in bridge.py:  from my_file import MyGestures  and pass it as the gesture source.
"""
import threading

# Names the Java app (MainFrame.onGesture) understands
VALID_GESTURES = {"swipe_left", "swipe_right", "raise_hand", "cross_arms", "unknown"}


def normalize(name):
    name = str(name).strip().lower()
    return name if name in VALID_GESTURES else "unknown"


class ConsoleSource:
    """Type commands instead of using the camera (like phone_app.py in Lab 3).

        l = swipe_left   r = swipe_right   h = raise_hand   c = cross_arms   x = unknown gesture
        m1 .. m4 = place marker 1..4 (any number works, e.g. m9 = unknown marker)     q = quit
    """
    GESTURE_KEYS = {"l": "swipe_left", "r": "swipe_right", "h": "raise_hand",
                    "c": "cross_arms", "x": "unknown"}

    def __init__(self, publish):
        self.publish = publish

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        print("Console: l/r = swipe left/right, h = raise hand, c = cross arms, "
              "x = unknown gesture, m1..m4 = marker, q = quit")
        while True:
            try:
                text = input().strip().lower()
            except EOFError:
                return
            if text == "q":
                import os
                os._exit(0)
            if text in self.GESTURE_KEYS:
                self.publish("gesture", self.GESTURE_KEYS[text])
            elif text.startswith("m") and text[1:].isdigit():
                self.publish("marker", text[1:])
            elif text:
                print("   ? try l, r, h, c, x, m1..m4, q")
