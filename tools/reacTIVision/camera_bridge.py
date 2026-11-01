"""
FaceTime camera -> Unity Video Capture bridge for reacTIVision.

reacTIVision 1.5.1 reads cameras through DirectShow, which gets no frames from the
built-in FaceTime HD camera under Boot Camp (known Apple driver issue). This script
reads the camera through Media Foundation instead and republishes it as
"Unity Video Capture" (camera id 1 in camera.xml), then starts reacTIVision and keeps
running until reacTIVision exits.

Unity Capture is used rather than OBS Virtual Camera because its default format is
RGB24; reacTIVision 1.5.1 mishandles virtual cameras that default to NV12 (OBS) and
rejects every frame with "SampleCB() - buffer sizes do not match".

Usage:
    python camera_bridge.py              bridge + start reacTIVision
    python camera_bridge.py --no-launch  bridge only (Ctrl+C to stop)

Requires: Unity Capture filter registered (regsvr32 UnityCaptureFilter64.dll),
opencv-python, pyvirtualcam.
"""
import argparse
import os
import subprocess
import sys
import time

import cv2
import pyvirtualcam

WIDTH, HEIGHT, FPS = 640, 480, 30
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-launch", action="store_true", help="only run the bridge, don't start reacTIVision")
    parser.add_argument("--camera", type=int, default=0, help="Media Foundation camera index (default 0)")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.camera, cv2.CAP_MSMF)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    ok, frame = cap.read()
    if not ok:
        sys.exit(f"Could not read from camera {args.camera}. Is another app (Zoom, Teams, browser) using it?")

    with pyvirtualcam.Camera(WIDTH, HEIGHT, FPS, fmt=pyvirtualcam.PixelFormat.BGR, backend="unitycapture") as vcam:
        print(f"Bridging camera {args.camera} -> {vcam.device} at {WIDTH}x{HEIGHT} @ {FPS} fps")

        reactivision = None
        launch_at = None if args.no_launch else time.time() + 1.0  # let frames flow before reacTIVision opens the device
        failures = 0
        try:
            while reactivision is None or reactivision.poll() is None:
                ok, frame = cap.read()
                if not ok:
                    failures += 1
                    if failures > FPS * 5:
                        print("Camera stopped delivering frames, exiting.")
                        break
                    continue
                failures = 0
                if frame.shape[1] != WIDTH or frame.shape[0] != HEIGHT:
                    frame = cv2.resize(frame, (WIDTH, HEIGHT))
                vcam.send(frame)

                if launch_at is not None and time.time() >= launch_at:
                    launch_at = None
                    reactivision = subprocess.Popen([os.path.join(HERE, "reacTIVision.exe")], cwd=HERE)
        except KeyboardInterrupt:
            pass
        finally:
            cap.release()
            if reactivision is not None and reactivision.poll() is None:
                reactivision.terminate()


if __name__ == "__main__":
    main()
