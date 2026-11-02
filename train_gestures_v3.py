"""
Train/evaluate the gesture recognizer (v3).

Run:  python train_gestures_v3.py
      python train_gestures_v3.py --dataset /path/to/gesture_dataset

Expects DATASET_DIR/<swipe_left|swipe_right|raise_hand|cross_arms|unknown>/*.mov
Saves gesture_templates.pkl next to this script, which live_gestures.py loads.
"""

import argparse
from pathlib import Path
import pickle
import random
import statistics
import sys

import gesture_core as core

# ---------------- SETTINGS ----------------

DATASET_DIR = Path("/Users/mahmoud/Documents/gesture_dataset")
OUTPUT_FILE = Path(__file__).with_name("gesture_templates.pkl")

UNKNOWN_FOLDER = "unknown"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".m4v"}

TEST_FRACTION = 0.20
RANDOM_SEED = 42

# How strongly movement counts compared with position (0 = positions only).
# If real gestures get labelled unknown, try 1.5 to 2.
VELOCITY_WEIGHT = 3.0

# Rejection rules, used for the evaluation below. Leave off for the first run
# to see the raw numbers, then tune. The live script has its own LIVE_* values.
MIN_MARGIN = 0.0
MAX_DISTANCE = None
MIN_MOTION = 0.0


# ---------------- DATASET ----------------

def list_videos(folder):
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    )


def split_videos(videos, rng):
    videos = list(videos)
    rng.shuffle(videos)
    if len(videos) < 2:
        return videos, []
    test_count = max(1, round(len(videos) * TEST_FRACTION))
    test_count = min(test_count, len(videos) - 1)
    return videos[test_count:], videos[:test_count]


def process_videos(videos, label, target, tag, durations):
    for video in videos:
        print(f"[PROCESSING {tag}] {video.name}", flush=True)
        seq, duration = core.extract_video_sequence(video)
        if seq is None:
            continue
        target.append((label, video.name, seq))
        if duration is not None and label != core.UNKNOWN_LABEL:
            durations.append(duration)


def load_dataset(dataset_dir):
    rng = random.Random(RANDOM_SEED)
    training, testing, unknown_testing, durations = [], [], [], []

    for gesture in core.GESTURES:
        videos = list_videos(dataset_dir / gesture)
        train_videos, test_videos = split_videos(videos, rng)
        print(f"\n{gesture}: {len(train_videos)} training / "
              f"{len(test_videos)} testing")
        process_videos(train_videos, gesture, training, "TRAIN", durations)
        process_videos(test_videos, gesture, testing, "TEST", durations)

    # Unknown is a real class: some clips become templates, the rest are held
    # out to measure how well unknowns are rejected.
    unknown_videos = list_videos(dataset_dir / UNKNOWN_FOLDER)
    train_unk, test_unk = split_videos(unknown_videos, rng)
    print(f"\n{core.UNKNOWN_LABEL}: {len(train_unk)} training / "
          f"{len(test_unk)} testing")
    process_videos(train_unk, core.UNKNOWN_LABEL, training,
                   "TRAIN UNKNOWN", durations)
    process_videos(test_unk, core.UNKNOWN_LABEL, unknown_testing,
                   "TEST UNKNOWN", durations)

    return training, testing, unknown_testing, durations


# ---------------- EVALUATION ----------------

def run_predict(recognizer, seq):
    return core.predict(recognizer, seq, MIN_MARGIN, MAX_DISTANCE, MIN_MOTION)


def evaluate(recognizer, testing, unknown_testing):
    print("\n========== GESTURE TEST ==========")
    correct = 0
    for actual, filename, seq in testing:
        predicted, dist, margin, motion = run_predict(recognizer, seq)
        correct += predicted == actual
        print(f"Actual: {actual:12} | Predicted: {predicted:12} | "
              f"Dist: {dist:.3f} | Margin: {margin:.3f} | "
              f"Motion: {motion:.2f} | {filename}")

    if testing:
        print(f"\nGesture accuracy: {correct}/{len(testing)} "
              f"({100 * correct / len(testing):.1f}%)")
    else:
        print("\nNo held-out gesture clips available.")

    print("\n========== UNKNOWN TEST (held-out) ==========")
    rejected = 0
    for _, filename, seq in unknown_testing:
        predicted, dist, margin, motion = run_predict(recognizer, seq)
        rejected += predicted == core.UNKNOWN_LABEL
        print(f"Predicted: {predicted:12} | Dist: {dist:.3f} | "
              f"Margin: {margin:.3f} | Motion: {motion:.2f} | {filename}")

    if unknown_testing:
        print(f"\nUnknown correctly rejected: {rejected}/"
              f"{len(unknown_testing)} "
              f"({100 * rejected / len(unknown_testing):.1f}%)")
    else:
        print("\nNo held-out unknown clips available.")

    print("\nSanity check: Motion should mostly be about 0.5 to 4 (shoulder "
          "widths). Values far above that mean pose detection failed on that "
          "clip, so look at the video or re-record it.")


# ---------------- MAIN ----------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DATASET_DIR)
    args = parser.parse_args()
    dataset_dir = args.dataset

    print(f"Dataset: {dataset_dir}")
    if not dataset_dir.is_dir():
        sys.exit("Dataset folder not found. Check DATASET_DIR or --dataset.")
    for name in core.GESTURES + [UNKNOWN_FOLDER]:
        if not (dataset_dir / name).is_dir():
            sys.exit(f"Missing folder: {dataset_dir / name}")

    training, testing, unknown_testing, durations = load_dataset(dataset_dir)

    missing = [g for g in core.GESTURES
               if not any(t[0] == g for t in training)]
    if missing:
        sys.exit(f"No usable training videos for: {missing}")
    if not any(t[0] == core.UNKNOWN_LABEL for t in training):
        print("\n[WARNING] No unknown templates were created; unknown "
              "rejection will rely on the margin/distance/motion rules only.")

    recognizer = core.DTWRecognizer(
        [(label, seq) for label, _, seq in training], VELOCITY_WEIGHT)
    evaluate(recognizer, testing, unknown_testing)

    suggested_window = None
    if durations:
        suggested_window = min(max(statistics.median(durations), 1.0), 4.0)
        print(f"\nMedian gesture clip length: "
              f"{statistics.median(durations):.2f}s "
              f"(live window will default to {suggested_window:.2f}s)")

    payload = {
        "method": "dtw",
        "seq_len": core.SEQ_LEN,
        "landmark_ids": core.LANDMARK_IDS,
        "velocity_weight": VELOCITY_WEIGHT,
        "unknown_label": core.UNKNOWN_LABEL,
        "suggested_window_seconds": suggested_window,
        "templates": [(label, name, seq) for label, name, seq in training],
    }
    with OUTPUT_FILE.open("wb") as f:
        pickle.dump(payload, f)

    print(f"\nSaved {len(training)} templates to:\n{OUTPUT_FILE}")
    print("\nTraining finished!")


if __name__ == "__main__":
    main()
