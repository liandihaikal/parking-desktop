# services/serial_service.py

import time
import threading
import serial
import serial.tools.list_ports
from typing import Optional, Callable
from enum import Enum

from config import SERIAL_PORT, BAUDRATE, BARRIER_PULSES, BARRIER_DELAY, BARRIER_HOLD


class SensorType(Enum):
    TICKET = "ticket"
    RANGE = "range"


def _find_arduino_port() -> Optional[str]:
    ports = serial.tools.list_ports.comports()
    for port in ports:
        # Cek berdasarkan description atau VID/PID
        if 'Arduino' in port.description or 'USB Serial' in port.description:
            print(f"[SERIAL] ✅ Found Arduino on {port.device}")
            return port.device
        # Atau cek berdasarkan ttyUSB/ttyACM
        if 'ttyUSB' in port.device or 'ttyACM' in port.device:
            print(f"[SERIAL] ✅ Found serial device on {port.device}")
            return port.device
    return None


class SerialService:
    def __init__(self, sound=None):
        self.gate_open = False
        self._lock = threading.Lock()
        self._detection_callback: Optional[Callable] = None
        self._sensor_callbacks: dict = {
            SensorType.TICKET: None,
            SensorType.RANGE: None
        }
        self._running = False
        self._read_thread: Optional[threading.Thread] = None
        self._listener_active = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self.sound = sound
        self.ser = None
        self._connect()

    def _connect(self):
        """Establish serial connection with retry"""
        port = SERIAL_PORT

        # Auto-detect if default port not working
        if port == '/dev/ttyUSB0' or port == '/dev/ttyACM0':
            detected_port = _find_arduino_port()
            if detected_port:
                port = detected_port

        try:
            print(f"[SERIAL] 🔌 Attempting to connect to {port} at {BAUDRATE} baud...")
            self.ser = serial.Serial(port, BAUDRATE, timeout=0.5, write_timeout=1)
            time.sleep(2)  # Wait for Arduino to reset

            # Test connection by sending a command
            self.ser.write(b'\n')
            time.sleep(0.1)

            # Flush any initial data
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

            print(f"[SERIAL] ✅ Connected: {port}")
            self._reconnect_attempts = 0
            return True

        except serial.SerialException as e:
            print(f"[SERIAL] ❌ Connection error: {e}")
            self.ser = None
            return False
        except Exception as e:
            print(f"[SERIAL] ❌ Unexpected error: {e}")
            self.ser = None
            return False

    def _reconnect(self):
        """Attempt to reconnect to serial port"""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            print(f"[SERIAL] ❌ Max reconnection attempts reached")
            return False

        self._reconnect_attempts += 1
        print(f"[SERIAL] 🔄 Reconnection attempt {self._reconnect_attempts}/{self._max_reconnect_attempts}...")

        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except:
                pass

        time.sleep(2)  # Wait before reconnecting
        return self._connect()

    def start_detect_listener(self):
        """Start listening for Arduino sensor detection"""
        if not self.is_available:
            print("[SERIAL] ❌ Cannot start listener - serial not available")
            return False

        if self._listener_active:
            print("[SERIAL] ⚠️ Listener already active")
            return True

        self._running = True
        self._listener_active = True
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()
        print("[SERIAL] 📡 Detection listener started")
        return True

    def stop_detect_listener(self):
        """Stop the detection listener"""
        self._running = False
        self._listener_active = False
        if self._read_thread:
            self._read_thread.join(timeout=2)
        print("[SERIAL] 🛑 Detection listener stopped")

    def _read_loop(self):
        """Continuous read loop for Arduino data with error recovery"""
        print("[SERIAL] 🔄 Reading loop started")
        consecutive_errors = 0

        while self._running:
            try:
                # Check if serial is still connected
                if not self.is_available:
                    print("[SERIAL] ⚠️ Serial disconnected, attempting reconnect...")
                    if self._reconnect():
                        print("[SERIAL] ✅ Reconnected successfully")
                        consecutive_errors = 0
                        continue
                    else:
                        print("[SERIAL] ❌ Reconnection failed, stopping listener")
                        break

                # Read data with timeout
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode().strip()
                    if line:
                        self._process_data(line)
                        consecutive_errors = 0  # Reset error counter on success
                else:
                    # Small sleep to prevent CPU hogging
                    time.sleep(0.01)

            except serial.SerialException as e:
                consecutive_errors += 1
                print(f"[SERIAL] ⚠️ Serial exception ({consecutive_errors}): {e}")
                if consecutive_errors >= 3:
                    print("[SERIAL] 🔄 Too many errors, attempting reconnect...")
                    self.ser = None  # Force reconnect
                    consecutive_errors = 0
                    time.sleep(1)

            except UnicodeDecodeError as e:
                # Sometimes garbage data from Arduino
                print(f"[SERIAL] ⚠️ Decode error: {e}")
                continue

            except Exception as e:
                consecutive_errors += 1
                print(f"[SERIAL] ⚠️ Read error ({consecutive_errors}): {e}")
                if consecutive_errors >= 5:
                    print("[SERIAL] ❌ Too many errors, stopping listener")
                    break
                time.sleep(0.5)

        print("[SERIAL] 🔄 Reading loop ended")
        self._listener_active = False

    def _process_data(self, data: str):
        """Process incoming serial data from Arduino"""
        print(f"[SERIAL] 📡 Received: {data}")

        # Handle READY signal from Arduino
        if data == "READY":
            print("[SERIAL] ✅ Arduino is ready")
            return

        # Handle detection signals
        if data == "DETECT_RANGE":
            print("[SERIAL] 🚗 Vehicle detected by range sensor!")
            if self.sound:
                self.sound.play_detect()
            if self._sensor_callbacks[SensorType.RANGE]:
                self._sensor_callbacks[SensorType.RANGE]()

        elif data == "DETECT_TICKET":
            print("[SERIAL] 🎫 Ticket detected!")
            if self._sensor_callbacks[SensorType.TICKET]:
                self._sensor_callbacks[SensorType.TICKET]()

        elif data.startswith("Ticket:"):
            # Parse status line - just log
            pass

        elif data == "OPEN" or data == "GATE_OPENED":
            print("[SERIAL] 🚪 Gate opened confirmation")
        elif data == "CLOSE" or data == "GATE_CLOSED":
            print("[SERIAL] 🚪 Gate closed confirmation")

    def on_ticket_detected(self, callback: Callable):
        """Register callback for ticket sensor (CHECK-IN)"""
        self._sensor_callbacks[SensorType.TICKET] = callback
        print("[SERIAL] 🎫 Ticket detection callback registered")

    def on_range_detected(self, callback: Callable):
        """Register callback for range sensor (vehicle detection)"""
        self._sensor_callbacks[SensorType.RANGE] = callback
        print("[SERIAL] 📡 Range detection callback registered")

    def _send_pulses(self):
        """Send pulse sequence to open barrier"""
        if not self.is_available:
            return

        try:
            for i in range(BARRIER_PULSES):
                self.ser.write(bytes([i]))
                time.sleep(BARRIER_DELAY)
            print(f"[SERIAL] ✅ Sent {BARRIER_PULSES} pulses")
        except Exception as e:
            print(f"[SERIAL] ❌ Error sending pulses: {e}")

    @property
    def is_available(self) -> bool:
        return self.ser is not None and self.ser.is_open

    @property
    def is_listening(self) -> bool:
        return self._listener_active

    def get_status(self) -> dict:
        """Get current serial status"""
        return {
            "available": self.is_available,
            "gate_open": self.gate_open,
            "listening": self._listener_active,
            "ticket_callback": self._sensor_callbacks[SensorType.TICKET] is not None,
            "range_callback": self._sensor_callbacks[SensorType.RANGE] is not None,
            "port": self.ser.name if self.ser else None,
            "baudrate": BAUDRATE
        }

    def close(self):
        """Close serial connection and stop listener"""
        self.stop_detect_listener()
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
                print("[SERIAL] 🔌 Serial connection closed")
            except:
                pass
