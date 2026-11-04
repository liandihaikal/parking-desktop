import base64
import time
from io import BytesIO

from escpos.printer import Network
from PIL import Image

from config import PRINTER_IP, PRINTER_WIDTH


class PrinterService:
    def __init__(self, ip: str = PRINTER_IP, width: int = PRINTER_WIDTH):
        self.ip = ip
        self.width = width
        self.printer = self._init_printer()

    def _init_printer(self):
        try:
            printer = Network(self.ip)
            print(f"[PRINTER] ✅ Connected: {self.ip}")
            return printer
        except Exception as e:
            print(f"[PRINTER] ❌ Error: {e}")
            return None

    def _decode_qr(self, qr_base64: str) -> Image.Image:
        raw = qr_base64.split(",")[1] if "," in qr_base64 else qr_base64
        img = Image.open(BytesIO(base64.b64decode(raw)))
        return img.resize((self.width, self.width), Image.NEAREST)

    @staticmethod
    def center_text(text: str, width: int = 32) -> str:
        return text.center(width)

    @staticmethod
    def divider(char: str = "-", width: int = 32) -> str:
        return char * width

    @property
    def is_available(self) -> bool:
        return self.printer is not None

    def print_ticket(self, data: dict) -> bool:
        if not self.is_available:
            print("[PRINTER] ❌ Printer tidak tersedia.")
            return False

        try:
            p = self.printer
            p.set(align="center", font="b")
            p.text("PARKING TICKET\n")
            p.text(self.divider() + "\n")
            queue = data.get("queueNumber") or data.get("queue_number")
            if queue:
                p.set(font="b", width=2, height=2)
                p.text(self.center_text(f"ANTRIAN: {queue}") + "\n")
                p.set(font="a", width=1, height=1)
                p.text(self.divider() + "\n")

            p.set(align="left", font="a")
            fields = [
                ("Tiket  ", data.get("ticketNumber", "-")),
                ("Plat   ", data.get("plateNumber", "-")),
                ("Jenis  ", data.get("vehicleType", "-")),
                ("Gate   ", data.get("gateCode", "-")),
                ("Masuk  ", data.get("checkInAt", "-")),
            ]
            for label, value in fields:
                p.text(f" {label}: {value}\n")

            p.text("\n")
            p.set(align="center")
            p.text(self.center_text("Scan untuk pembayaran") + "\n")
            p.text("\n")

            qr_img = self._decode_qr(data["qrCode"])
            p.image(qr_img)

            time.sleep(0.3)
            p.text("\n")
            p.text(self.center_text("Terima kasih") + "\n")
            p.text(self.divider() + "\n")
            p.cut()

            print("[PRINTER] 🖨️  Tiket dicetak.")
            return True

        except Exception as e:
            print(f"[PRINTER] ❌ Print error: {e}")
            return False
