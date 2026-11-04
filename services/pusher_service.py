# services/pusher_service.py

import json
import threading
import time
from datetime import datetime
from collections import deque

import cv2
import pysher

from services.barrier_service import BarrierService
from services.camera_service import CameraService
from services.minio_service import MinioService
from services.serial_service import SerialService
from services.printer_service import PrinterService
from services.sound_service import SoundService
from api.parking_api import ParkingAPI

from config import (
    PUSHER_APP_KEY, PUSHER_CLUSTER, COOLDOWN,
    CHANNEL_ACTIVITY, CHANNEL_GATE,
    EVENT_CHECKED_IN, EVENT_CHECKED_OUT, EVENT_GATE_STATUS,
)


def _on_gate_status_changed(raw: str):
    try:
        data = json.loads(raw)
        print(f"[PUSHER] 🚪 Gate status: {data.get('gate_code')} -> {data.get('status')}")
    except json.JSONDecodeError as e:
        print(f"[PUSHER] ❌ JSON error (gate_status): {e}")


class PusherService:
    def __init__(
            self,
            serial: SerialService,
            printer: PrinterService,
            barrier: BarrierService,
            sound: SoundService,
            camera: CameraService,
            api: ParkingAPI,
            cooldown: float = COOLDOWN,
    ):
        self.serial = serial
        self.printer = printer
        self.barrier = barrier
        self.sound = sound
        self.cooldown = cooldown
        self._last_trigger_time: float = 0
        self._pusher = self._init_pusher()
        self.camera = camera
        self.api = api
        self.minio = MinioService()

        # Track processed tickets to avoid duplicates
        self._processed_tickets = deque(maxlen=100)
        self._processing_lock = threading.Lock()

    def _init_pusher(self) -> pysher.Pusher:
        pusher = pysher.Pusher(
            key=PUSHER_APP_KEY,
            cluster=PUSHER_CLUSTER,
            secure=True,
        )
        pusher.connection.bind(
            "pusher:connection_established",
            self._on_connected,
        )
        return pusher

    def _is_cooling_down(self) -> bool:
        return (time.time() - self._last_trigger_time) < self.cooldown

    def _update_cooldown(self):
        self._last_trigger_time = time.time()

    def _is_ticket_processed(self, ticket_number: str) -> bool:
        """Check if ticket has been processed recently"""
        with self._processing_lock:
            return ticket_number in self._processed_tickets

    def _mark_ticket_processed(self, ticket_number: str):
        """Mark ticket as processed"""
        with self._processing_lock:
            self._processed_tickets.append(ticket_number)
            print(f"[PUSHER] 📝 Ticket marked as processed: {ticket_number}")

    def _on_connected(self, _data):
        print("[PUSHER] ✅ Connected to Pusher.")

        ch_activity = self._pusher.subscribe(CHANNEL_ACTIVITY)
        ch_activity.bind(EVENT_CHECKED_IN, self._on_vehicle_checked_in)
        ch_activity.bind(EVENT_CHECKED_OUT, self._on_vehicle_checked_out)

        ch_gate = self._pusher.subscribe(CHANNEL_GATE)
        ch_gate.bind(EVENT_GATE_STATUS, _on_gate_status_changed)

        print(f"[PUSHER] ✅ Subscribed: {CHANNEL_ACTIVITY}, {CHANNEL_GATE}")

    def _on_vehicle_checked_in(self, raw: str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"[PUSHER] ❌ JSON error: {e}")
            return

        print("[PUSHER] 🚗 Vehicle checked in event received")
        parking_id = data.get("id", "unknown")

        def capture_job():
            filename = f"{parking_id}.jpg"

            frame = self.camera.capture(filename, subdir='checkin')
            if frame is None:
                print("[PUSHER] ❌ Failed to capture image")
                return

            object_name = self.minio.generate_object_name(parking_id, 'checkin')
            check_in_image = self.minio.upload_cv2_image(frame, object_name, quality=85)

            if check_in_image:
                print(f"[PUSHER] ✅ Image uploaded to MinIO: {object_name}")
                self.api.update(parking_id, "", check_in_image, "")
            else:
                print("[PUSHER] ❌ Failed to upload image to MinIO")
                print(f"[PUSHER] 💾 Image already saved locally in captures/checkin/")

        threading.Thread(target=capture_job, daemon=True).start()

        print("[PUSHER] 🖨️ Printing ticket...")
        self.printer.print_ticket(data)

        if not self.barrier.is_open and not self._is_cooling_down():
            self._update_cooldown()
            print("[PUSHER] 🚪 Opening barrier gate...")
            self.barrier.open()
        else:
            if self.barrier.is_open:
                print("[PUSHER] ⚠️ Barrier already open, skipping")
            elif self._is_cooling_down():
                print("[PUSHER] ⏳ Cooldown active, skipping barrier open")

    def _on_vehicle_checked_out(self, raw: str):
        try:
            data = json.loads(raw)
            parking_id = data.get("ticketNumber", "unknown")

            print(f"[PUSHER] 🚗 Vehicle checked out: {data.get('plateNumber', '?')}")

            def capture_job():
                filename = f"{parking_id}.jpg"

                frame = self.camera.capture(filename, subdir='checkin')
                if frame is None:
                    print("[PUSHER] ❌ Failed to capture image")
                    return

                object_name = self.minio.generate_object_name(parking_id, 'checkout')
                check_out_image = self.minio.upload_cv2_image(frame, object_name, quality=85)

                if check_out_image:
                    print(f"[PUSHER] ✅ Image uploaded to MinIO: {object_name}")
                    self.api.update(parking_id, "", "", check_out_image)
                else:
                    print("[PUSHER] ❌ Failed to upload image to MinIO")
                    print(f"[PUSHER] 💾 Image already saved locally in captures/checkin/")

            threading.Thread(target=capture_job, daemon=True).start()

            if self._is_ticket_processed(f"out_{parking_id}"):
                print(f"[PUSHER] ⚠️ Checkout for {parking_id} already processed")
                return

            self._mark_ticket_processed(f"out_{parking_id}")

            if not self._is_cooling_down():
                self._update_cooldown()
                print(f"[PUSHER] 🚪 Opening barrier for checkout...")
                self.barrier.open()

        except json.JSONDecodeError as e:
            print(f"[PUSHER] ❌ JSON error (checked_out): {e}")

    def connect(self):
        print("[PUSHER] 🔌 Connecting...")
        self._pusher.connect()

    def disconnect(self):
        self._pusher.disconnect()
        print("[PUSHER] 🔌 Disconnected.")
