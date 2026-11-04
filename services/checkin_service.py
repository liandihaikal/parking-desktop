import threading
import time


class CheckinService:
    def __init__(self, api, serial, barrier, sound, printer=None):
        self.api = api
        self.serial = serial  # Untuk sensor IR
        self.barrier = barrier  # Untuk barrier gate (terpisah!)
        self.sound = sound
        self.printer = printer
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

    def process_checkin(self, plate_number: str = None):
        if self._is_cooling_down():
            print("[CHECKIN] ⏳ Cooldown, skipping...")
            return

        self._update_cooldown()

        def checkin_job():
            try:
                print("[CHECKIN] 🎫 Processing check-in...")

                if self.sound:
                    self.sound.play_detect()

                response = self.api.checkin(plate_number)

                if response:
                    ticket_number = response.get('ticket_number', 'N/A')
                    print(f"[CHECKIN] ✅ Check-in successful: {ticket_number}")

                    self.barrier.open()

                    if self.printer and self.printer.is_available:
                        self._print_ticket(response)
                    else:
                        print(f"[CHECKIN] Ticket: {ticket_number}")

                else:
                    error_msg = response.get('message', 'Check-in failed') if response else 'API Error'
                    print(f"[CHECKIN] ❌ {error_msg}")
                    # if self.sound:
                    #     self.sound.play_error()

            except Exception as e:
                print(f"[CHECKIN] ❌ Check-in error: {e}")
                # if self.sound:
                #     self.sound.play_error()

        threading.Thread(target=checkin_job, daemon=True).start()

    def _print_ticket(self, data: dict):
        try:
            ticket = data.get('ticket_number', 'N/A')
            plate = data.get('plate_number', '-')
            checkin_time = data.get('check_in_at', '-')
            vehicle_type = data.get('vehicle_type', '-')

            ticket_text = f"""
            ═══════════════════════════════════
                  TIKET MASUK PARKIR
            ═══════════════════════════════════
            No Tiket    : {ticket}
            Plat Nomor   : {plate}
            Jenis       : {vehicle_type}
            Waktu Masuk : {checkin_time}
            Gate        : {self.api.gate_code}
            ═══════════════════════════════════
            """
            print(ticket_text)

            if self.printer:
                self.printer.print_text(ticket_text)

        except Exception as e:
            print(f"[CHECKIN] Error printing ticket: {e}")
