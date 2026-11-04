# services/barrier_service.py

import time
import threading
import serial
import serial.tools.list_ports
from typing import Optional

from config import BARRIER_PORT, BARRIER_BAUDRATE, BARRIER_PULSES, BARRIER_DELAY


def _check_port_exists(port: str) -> bool:
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if p.device == port:
            return True
    return False


def _find_arduino_port() -> Optional[str]:
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if 'ttyUSB' in port.device or 'ttyACM' in port.device:
            print(f"[BARRIER] 🔍 Found device on {port.device}")
            return port.device
    return None


class BarrierService:
    def __init__(self, sound=None):
        self.sound = sound
        self.ser = None
        self.is_open = False
        self._lock = threading.Lock()
        self._open_timer = None
        self._connect()

    def _connect(self):
        port = BARRIER_PORT

        if not _check_port_exists(port):
            detected_port = _find_arduino_port()
            if detected_port:
                port = detected_port
                print(f"[BARRIER] 🔄 Using auto-detected port: {port}")

        try:
            print(f"[BARRIER] 🔌 Connecting to {port} at {BARRIER_BAUDRATE} baud...")
            self.ser = serial.Serial(port, BARRIER_BAUDRATE, timeout=1, write_timeout=1)
            time.sleep(2)

            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

            print(f"[BARRIER] ✅ Connected to barrier gate on {port}")
            return True

        except serial.SerialException as e:
            print(f"[BARRIER] ❌ Connection error: {e}")
            self.ser = None
            return False
        except Exception as e:
            print(f"[BARRIER] ❌ Unexpected error: {e}")
            self.ser = None
            return False

    @property
    def is_available(self) -> bool:
        return self.ser is not None and self.ser.is_open

    def _send_pulse_sequence(self):
        if not self.is_available:
            print("[BARRIER] ❌ Serial not available")
            return False

        try:
            print(f"[BARRIER] 📤 Sending {BARRIER_PULSES} pulse bytes...")
            for i in range(BARRIER_PULSES):
                cmd = bytes([i])
                self.ser.write(cmd)
                print(f"[BARRIER]    Sent byte: {i} (0x{i:02X})")
                time.sleep(BARRIER_DELAY)

            print(f"[BARRIER] ✅ Sent {BARRIER_PULSES} pulse bytes successfully")
            return True

        except Exception as e:
            print(f"[BARRIER] ❌ Error sending pulses: {e}")
            return False

    def open(self) -> bool:
        with self._lock:
            if self.is_open:
                print("[BARRIER] ⚠️ Gate already open, skip.")
                return True

            if not self.is_available:
                print("[BARRIER] ❌ Barrier serial not available.")
                print("[BARRIER] 💡 Make sure device is connected and port is correct")
                return False

        print("[BARRIER] 🚪 Opening barrier gate...")

        success = self._send_pulse_sequence()

        if success:
            # Mark as open
            with self._lock:
                self.is_open = True

            print("[BARRIER] ✅ Barrier opened successfully!")

            if self._open_timer:
                self._open_timer.cancel()
            self._open_timer = threading.Timer(3.0, self._reset_gate_status)
            self._open_timer.start()

            return True
        else:
            print("[BARRIER] ❌ Failed to open barrier")
            return False

    def _reset_gate_status(self):
        with self._lock:
            self.is_open = False
        print("[BARRIER] 🔒 Gate status reset (ready for next open)")

    def send_raw_bytes(self, byte_values: list) -> bool:
        if not self.is_available:
            print("[BARRIER] ❌ Barrier serial not available")
            return False

        try:
            for byte_val in byte_values:
                cmd = bytes([byte_val % 256])
                self.ser.write(cmd)
                print(f"[BARRIER]    Sent byte: {byte_val}")
                time.sleep(BARRIER_DELAY)

            print(f"[BARRIER] ✅ Sent {len(byte_values)} raw bytes")
            return True
        except Exception as e:
            print(f"[BARRIER] ❌ Error sending raw bytes: {e}")
            return False

    def get_status(self) -> dict:
        return {
            "available": self.is_available,
            "is_open": self.is_open,
            "port": self.ser.name if self.ser else None,
            "baudrate": BARRIER_BAUDRATE,
            "pulses": BARRIER_PULSES,
            "delay": BARRIER_DELAY
        }

    def close(self):
        if self._open_timer:
            self._open_timer.cancel()

        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
                print("[BARRIER] 🔌 Barrier serial connection closed")
            except:
                pass
