#!/usr/bin/env python3
"""
Main entry point untuk Parking Gate System dengan auto checkout image capture.

Sebelumnya: main.py hanya support CLI mode atau UI mode dengan parking_ui.py
Sekarang: Tambahan support untuk parking_ui_v2.py dengan auto checkout image capture

Services yang digunakan:
  - CameraService (existing) - untuk capture foto
  - MinioService (new/existing) - untuk upload ke MinIO/S3
  - BarrierService (existing) - untuk kontrol gate
  - SerialService (existing) - untuk sensor IR
  - ParkingAPI (existing) - untuk API calls
"""

import sys
import signal
import time
import os

from config import GATE_CODE, RTSP_URL
from api.parking_api import ParkingAPI
from services.camera_service import CameraService
from services.minio_service import MinioService  # ← NEW
from services.serial_service import SerialService
from services.barrier_service import BarrierService
from services.printer_service import PrinterService
from services.sound_service import SoundService
from services.pusher_service import PusherService
from services.scanner_service import ScannerService
from services.checkin_service import CheckinService
from utils.logger import logger
from ui.parking_ui import ParkingUI
from ui.dialogs.login_dialog import LoginDialog
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPalette, QColor


def on_ticket_sensor():
    """Callback when ticket sensor is triggered - CHECK-IN (MASUK)"""
    logger.info("? Ticket sensor triggered - Processing CHECK-IN")
    checkin_service.process_checkin()


def on_range_sensor():
    """Callback when range sensor is triggered - just notification"""
    logger.info("? Vehicle detected by range sensor")
    sound.play_detect()


def shutdown(sig=None, frame=None):
    logger.info("Shutdown dimulai...")
    try:
        pusher.disconnect()
        serial.close()
        barrier.close()
        camera.release()  # ← Release camera
        # Note: minio tidak perlu close, client auto-cleanup
    except Exception as e:
        logger.error(f"Error saat shutdown: {e}")
    logger.info("=== SYSTEM STOPPED ===")
    sys.exit(0)


# ============================================================================
# INITIALIZE SERVICES
# ============================================================================

logger.info(f"=== PARKING GATE SYSTEM STARTING [Gate: {GATE_CODE}] ===")

# Sound service (untuk beep & error notification)
sound = SoundService()

# ========== CAMERA & IMAGE SERVICES ==========
try:
    camera = CameraService(RTSP_URL)
    logger.info("[CAMERA] ? Initialized")
except Exception as e:
    logger.error(f"[CAMERA] ? Failed to initialize: {e}")
    camera = None

try:
    minio = MinioService()  # ← NEW: MinIO service untuk upload gambar
    logger.info("[MINIO] ? Initialized")
except Exception as e:
    logger.error(f"[MINIO] ? Failed to initialize: {e}")
    minio = None

# ========== HARDWARE SERVICES ==========
try:
    serial = SerialService(sound=sound)
    logger.info("[SERIAL] ? Initialized")
except Exception as e:
    logger.error(f"[SERIAL] ? Failed to initialize: {e}")
    serial = None

try:
    barrier = BarrierService(sound=sound)
    logger.info("[BARRIER] ? Initialized")
except Exception as e:
    logger.error(f"[BARRIER] ? Failed to initialize: {e}")
    barrier = None

try:
    printer = PrinterService()
    logger.info("[PRINTER] ? Initialized")
except Exception as e:
    logger.error(f"[PRINTER] ? Failed to initialize: {e}")
    printer = None

# ========== API & COMMUNICATION SERVICES ==========
try:
    api = ParkingAPI()
    logger.info("[API] ? Initialized")
except Exception as e:
    logger.error(f"[API] ? Failed to initialize: {e}")
    api = None

# ========== BUSINESS LOGIC SERVICES ==========
try:
    checkin_service = CheckinService(
        api=api,
        serial=serial,
        barrier=barrier,
        sound=sound,
        printer=printer
    )
    logger.info("[CHECKIN] ? Initialized")
except Exception as e:
    logger.error(f"[CHECKIN] ? Failed to initialize: {e}")
    checkin_service = None

try:
    scanner_service = ScannerService(
        api=api,
        barrier=barrier,
        sound=sound
    )
    logger.info("[SCANNER] ? Initialized")
except Exception as e:
    logger.error(f"[SCANNER] ? Failed to initialize: {e}")
    scanner_service = None

try:
    pusher = PusherService(
        serial=serial,
        barrier=barrier,
        printer=printer,
        sound=sound,
        camera=camera,
        api=api
    )
    logger.info("[PUSHER] ? Initialized")
except Exception as e:
    logger.error(f"[PUSHER] ? Failed to initialize: {e}")
    pusher = None

# ============================================================================
# REGISTER CALLBACKS
# ============================================================================

if serial:
    serial.on_ticket_detected(on_ticket_sensor)
    serial.on_range_detected(on_range_sensor)

    if serial.start_detect_listener():
        logger.info("[SERIAL] ? Sensor listener started")
    else:
        logger.error("[SERIAL] ? Failed to start sensor listener")

# ============================================================================
# PRINT STATUS
# ============================================================================

print("\n" + "=" * 70)
print("SERVICE STATUS:")
print(f"  Camera (RTSP)       : {'? OK' if camera else '? FAILED'}")
print(f"  MinIO/S3            : {'? OK' if minio else '? FAILED'}")
print(f"  Sensor Serial (IR)  : {'? OK' if serial and serial.is_available else '? not available'}")
print(f"  Barrier Serial      : {'? OK' if barrier and barrier.is_available else '? not available'}")
print(f"  Printer             : {'? OK' if printer and printer.is_available else '? not available'}")
print(f"  Check-in Service    : {'? OK' if checkin_service else '? FAILED'}")
print(f"  Scanner Service     : {'? OK' if scanner_service else '? FAILED'}")
print(f"  Pusher Service      : {'? OK' if pusher else '? FAILED'}")
print(f"  Parking API         : {'? OK' if api else '? FAILED'}")
print("=" * 70)

if camera and minio:
    print("\n✓ Auto checkout image capture: ENABLED")
    print("  - Photo will be captured automatically on ticket scan")
    print("  - Image will be uploaded to MinIO/S3")
    print("  - Photo will be displayed in UI")
else:
    print("\n⚠ Auto checkout image capture: DISABLED")
    if not camera:
        print("  - Camera service not available")
    if not minio:
        print("  - MinIO service not available")

print("=" * 70 + "\n")

# ============================================================================
# SETUP SIGNAL HANDLERS
# ============================================================================

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

# ============================================================================
# CONNECT PUSHER & START SERVICES
# ============================================================================

if pusher:
    pusher.connect()
    time.sleep(1)

logger.info("? SYSTEM READY\n")
logger.info("? CHECK-IN: Masukkan tiket ke sensor IR")
logger.info("? CHECK-OUT: Scan QR code ticket\n")

# ============================================================================
# RUN APPLICATION
# ============================================================================

os.environ["QT_QPA_PLATFORM"] = "xcb"

app = QApplication(sys.argv)
app.setStyle("Fusion")

p = QPalette()
p.setColor(QPalette.Window, QColor("#0a0c10"))
p.setColor(QPalette.WindowText, QColor("#e5e7eb"))
p.setColor(QPalette.Base, QColor("#111318"))
p.setColor(QPalette.AlternateBase, QColor("#0a0c10"))
p.setColor(QPalette.Text, QColor("#e5e7eb"))
p.setColor(QPalette.Button, QColor("#1f2937"))
p.setColor(QPalette.ButtonText, QColor("#e5e7eb"))
p.setColor(QPalette.Highlight, QColor("#2563eb"))
p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
app.setPalette(p)

logger.info("Using ParkingUI v2 (with auto checkout image capture)")

login = LoginDialog(api=api)

user_data = {}


def on_login_success(data):
    global user_data
    user_data = data


login.login_successful.connect(on_login_success)

if login.exec_() == login.Accepted:
    api.token = user_data.get("token")
    api.user_id = user_data.get("user_id")

    window = ParkingUI(
        barier=barrier,
        sound=sound,
        api=api,
        camera=camera,
        minio=minio
    )

    window.user_data = user_data
    window.show()
    sys.exit(app.exec_())
else:
    sys.exit(0)
