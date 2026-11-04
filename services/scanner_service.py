# services/scanner_service.py

import threading
import time


class ScannerService:
    def __init__(self, api, barrier, sound):
        self.api = api
        self.barrier = barrier  # Gunakan barrier service
        self.sound = sound
        self._cooldown = False
        self._cooldown_time = 0
        self._cooldown_duration = 3

    def _is_cooling_down(self) -> bool:
        if not self._cooldown:
            return False
        if time.time() - self._cooldown_time > self._cooldown_duration:
            self._cooldown = False
            return False
        return True

    def _update_cooldown(self):
        self._cooldown = True
        self._cooldown_time = time.time()

    def process_checkout(self, queue_number: str, amount: float = 0):
        if self._is_cooling_down():
            print("[SCANNER] ⏳ Cooldown, skipping...")
            return

        self._update_cooldown()

        def checkout_job():
            try:
                print(f"[SCANNER] 📷 QR Scanned: {queue_number}")

                response = self.api.manual_checkout(queue=queue_number, amount=amount)

                if response and response.get('success'):
                    print(f"[SCANNER] ✅ Checkout successful")

                    if self.sound:
                        self.sound.play_success()

                    self.barrier.open()

                    change = response.get('change', 0)
                    if change > 0:
                        print(f"[SCANNER] 💰 Kembalian: Rp {change:,.0f}")

                elif response and response.get('remaining', 0) > 0:
                    remaining = response.get('remaining', 0)
                    total = response.get('total', 0)
                    paid = response.get('paid', 0)

                    print(f"[SCANNER] ❌ Kurang bayar!")
                    print(f"[SCANNER]    Total: Rp {total:,.0f}")
                    print(f"[SCANNER]    Dibayar: Rp {paid:,.0f}")
                    print(f"[SCANNER]    Sisa: Rp {remaining:,.0f}")

                    if self.sound:
                        self.sound.play_unpaid()

                else:
                    error_msg = response.get('message', 'Checkout failed') if response else 'API Error'
                    print(f"[SCANNER] ❌ {error_msg}")
                    if self.sound:
                        self.sound.play_error()

            except Exception as e:
                print(f"[SCANNER] ❌ Checkout error: {e}")
                if self.sound:
                    self.sound.play_error()

        threading.Thread(target=checkout_job, daemon=True).start()

    def run_loop(self):
        print("[SCANNER] 📡 Scanner loop started. Scan QR code for checkout...")
        while True:
            try:
                qr_input = input().strip()
                if qr_input:
                    print(f"[SCANNER] 📷 QR Code scanned: {qr_input}")
                    self.process_checkout(qr_input)
            except EOFError:
                break
            except KeyboardInterrupt:
                break
