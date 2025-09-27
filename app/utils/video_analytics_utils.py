import cv2
import numpy as np


def decode_frame_bytes(frame_bytes: bytes):
    """Decode bytes to OpenCV frame."""
    np_arr = np.frombuffer(frame_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    return frame
