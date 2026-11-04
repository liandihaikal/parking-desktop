# test_serial_debug.py

import serial
import serial.tools.list_ports
import time


def test_serial():
    print("=" * 50)
    print("SERIAL PORT DEBUG")
    print("=" * 50)

    # List all ports
    print("\n📡 Available ports:")
    ports = serial.tools.list_ports.comports()
    for port in ports:
        print(f"  - {port.device}: {port.description}")
        print(f"    HWID: {port.hwid}")

    # Try to find Arduino
    arduino_port = None
    for port in ports:
        if 'Arduino' in port.description or 'ttyUSB' in port.device or 'ttyACM' in port.device:
            arduino_port = port.device
            break

    if not arduino_port:
        print("\n❌ No Arduino found!")
        return

    print(f"\n🔌 Trying to connect to {arduino_port}...")

    try:
        ser = serial.Serial(arduino_port, 9600, timeout=1)
        time.sleep(2)
        print(f"✅ Connected to {ser.name}")

        # Send a test command
        ser.write(b'\n')
        time.sleep(0.1)

        # Read for 10 seconds
        print("\n📡 Listening for data (10 seconds)...")
        start_time = time.time()
        data_count = 0

        while time.time() - start_time < 10:
            if ser.in_waiting > 0:
                line = ser.readline().decode().strip()
                if line:
                    print(f"📡 {line}")
                    data_count += 1
            time.sleep(0.01)

        print(f"\n✅ Received {data_count} messages")

        ser.close()
        print("🔌 Connection closed")

    except serial.SerialException as e:
        print(f"❌ Serial error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    test_serial()