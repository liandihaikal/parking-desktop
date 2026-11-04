import os
from dotenv import load_dotenv

load_dotenv()

PUSHER_APP_KEY = "7f15bbff208c94dea64f"
PUSHER_CLUSTER = "ap1"

AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID', 'kifnSfso6qwckDfitySg')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', 'L5rZeU9qmtTzZDoTPVBrcHkJYlqQd8MpM36DEGuR')
AWS_DEFAULT_REGION = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
AWS_BUCKET = os.getenv('AWS_BUCKET', 'erp-dev')
AWS_ENDPOINT = os.getenv('AWS_ENDPOINT', 'https://storage.marsindo.my.id')
AWS_USE_PATH_STYLE_ENDPOINT = os.getenv('AWS_USE_PATH_STYLE_ENDPOINT', 'true').lower() == 'true'

# MinIO Configuration (untuk backward compatibility)
MINIO_ENDPOINT = AWS_ENDPOINT
MINIO_ACCESS_KEY = AWS_ACCESS_KEY_ID
MINIO_SECRET_KEY = AWS_SECRET_ACCESS_KEY
MINIO_BUCKET = AWS_BUCKET
MINIO_SECURE = AWS_ENDPOINT.startswith('https')
MINIO_REGION = AWS_DEFAULT_REGION

RTSP_URL = "rtsp://admin:admin123@192.168.0.106:554/Streaming/Channels/101"
ANPR_MODEL_PATH = "license_plate_detector.pt"

BASE_URL = "https://siphonlike-uncourtly-jimmy.ngrok-free.dev/"
API_CHECKIN = BASE_URL + "/parkings/checkin"
API_CHECKOUT = BASE_URL + "/parkings/checkout"
API_MANUAL_CHECKOUT = BASE_URL + "/parkings/manual-checkout"
API_PARKINGS = BASE_URL + "/parkings/"
API_UPDATE_PLATE = BASE_URL + "/parkings/update-plate"

GATE_CODE = "GATE_A"
COOLDOWN = 3

SERIAL_PORT = "/dev/ttyUSB0"
BAUDRATE = 9600
BARRIER_PULSES = 10
BARRIER_DELAY = 0.1
BARRIER_HOLD = 2.0

BARRIER_PORT = os.getenv('BARRIER_PORT', '/dev/ttyUSB0')
BARRIER_BAUDRATE = int(os.getenv('BARRIER_BAUDRATE', '9600'))
BARRIER_OPEN_DURATION = float(os.getenv('BARRIER_OPEN_DURATION', '3.0'))
CAPTURE_DIR = os.getenv('CAPTURE_DIR', 'captures')

PRINTER_IP = "192.168.0.114"
PRINTER_WIDTH = 320

SOUND_UNPAID = "assets/sounds/unpaid.mp3"
SOUND_SUCCESS = "assets/sounds/success.mp3"
SOUND_ERROR = "assets/sounds/error.mp3"
SOUND_DETECT = "assets/sounds/detect.mp3"

CHANNEL_ACTIVITY = "parking-activity"
CHANNEL_GATE = "parking-gate"

EVENT_CHECKED_IN = "vehicle.checked_in"
EVENT_CHECKED_OUT = "vehicle.checked_out"
EVENT_GATE_STATUS = "gate.status.changed"
