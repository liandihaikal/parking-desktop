# services/camera_service.py

import cv2
import os
from datetime import datetime
from typing import Optional

from config import CAPTURE_DIR


class CameraService:
    def __init__(self, rtsp_url=None):
        self.rtsp_url = rtsp_url
        self.cap = None
        self._connect()

        self.capture_dir = CAPTURE_DIR
        self.checkin_dir = os.path.join(self.capture_dir, 'checkin')
        self.checkout_dir = os.path.join(self.capture_dir, 'checkout')

        os.makedirs(self.checkin_dir, exist_ok=True)
        os.makedirs(self.checkout_dir, exist_ok=True)

        print(f"[CAMERA] Capture directories: {self.checkin_dir}, {self.checkout_dir}")

    def _connect(self):
        """Connect to camera"""
        try:
            if self.rtsp_url:
                self.cap = cv2.VideoCapture(self.rtsp_url)
            else:
                self.cap = cv2.VideoCapture(0)  # Default webcam

            print(f"[CAMERA] ✅ Connected to camera")
        except Exception as e:
            print(f"[CAMERA] ❌ Connection failed: {e}")
            self.cap = None

    def capture(self, filename: str, subdir: str = 'checkin') -> Optional[cv2.Mat]:
        """
        Capture image from camera and save to file

        Args:
            filename: Nama file (contoh: capture_TKT-xxx.jpg)
            subdir: Subdirectory ('checkin' or 'checkout')

        Returns:
            Frame image or None if failed
        """
        if not self.cap or not self.cap.isOpened():
            print("[CAMERA] ❌ Camera not available")
            return None

        try:
            ret, frame = self.cap.read()
            if not ret:
                print("[CAMERA] ❌ Failed to capture frame")
                return None

            # Tentukan path lengkap
            if subdir == 'checkin':
                save_path = os.path.join(self.checkin_dir, filename)
            else:
                save_path = os.path.join(self.checkout_dir, filename)

            # Simpan gambar
            cv2.imwrite(save_path, frame)
            print(f"[CAMERA] 💾 Image saved: {save_path}")

            return frame

        except Exception as e:
            print(f"[CAMERA] ❌ Capture error: {e}")
            return None

    def capture_to_bytes(self) -> Optional[bytes]:
        """Capture image and return as bytes (without saving)"""
        if not self.cap or not self.cap.isOpened():
            return None

        try:
            ret, frame = self.cap.read()
            if not ret:
                return None

            _, buffer = cv2.imencode('.jpg', frame)
            return buffer.tobytes()

        except Exception as e:
            print(f"[CAMERA] ❌ Capture error: {e}")
            return None

    def release(self):
        """Release camera"""
        if self.cap:
            self.cap.release()
            print("[CAMERA] 🔌 Camera released")