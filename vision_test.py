#!/usr/bin/env python3
from __future__ import annotations

import time

from camera_vision import CameraVision


def main() -> int:
    vision = CameraVision(interval=1.0)
    vision.start()

    print("Desk Buddy vision test")
    print("Show your RIGHT hand as a clear open palm with all five fingers.")
    print("Keep your face visible if possible.")
    print()

    last_frame_at = 0.0
    started = time.monotonic()

    try:
        while time.monotonic() - started < 18.0:
            state = vision.snapshot()

            if state.error:
                print(f"ERROR: {state.error}")
                return 2

            if (
                state.last_frame_at > 0.0
                and state.last_frame_at != last_frame_at
            ):
                last_frame_at = state.last_frame_at

                print(
                    "frame "
                    f"face={int(state.face_present)} "
                    f"fingers={state.finger_count} "
                    f"right_candidate={int(state.right_hand_candidate)} "
                    f"rh5={int(state.right_hand_five_fingers)} "
                    f"confidence={state.open_palm_confidence:.2f} "
                    f"hand_x={state.hand_x:+.2f}"
                )

                if vision.consume_right_hand_five():
                    print()
                    print("PASS: right-hand open palm trigger fired.")
                    return 0

            time.sleep(0.08)

        print()
        print("FAIL: no confirmed right-hand open palm in 18 seconds.")
        print(
            "Use the frame lines above to see whether the problem is "
            "skin/shape confidence, finger count, or handedness."
        )
        return 1

    finally:
        vision.stop()


if __name__ == "__main__":
    raise SystemExit(main())
