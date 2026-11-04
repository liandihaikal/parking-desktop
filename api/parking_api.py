import requests

from config import API_PARKINGS, API_CHECKIN, API_CHECKOUT, API_MANUAL_CHECKOUT, GATE_CODE, BASE_URL


class ParkingAPI:
    def __init__(
            self,
            
            base_url: str = BASE_URL,
            parking_url: str = API_PARKINGS,
            checkin_url: str = API_CHECKIN,
            checkout_url: str = API_CHECKOUT,
            manual_checkout_url: str = API_MANUAL_CHECKOUT,
            gate_code: str = GATE_CODE,
            timeout: int = 5,
    ):
        self.base_url = base_url
        self.parking_url = parking_url
        self.checkin_url = checkin_url
        self.checkout_url = checkout_url
        self.manual_checkout_url = manual_checkout_url
        self.gate_code = gate_code
        self.timeout = timeout
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true'
        }

    def checkin(self, plate_number: str = None) -> dict:
        try:
            payload = {
                "gate_code": self.gate_code,
                "plate_number": plate_number if plate_number else "-",
                "vehicle_type_code": "MTR"
            }

            if plate_number:
                payload["plate_number"] = plate_number.upper().strip()

            print(f"[API] Check-in request to {self.checkin_url}")
            print(f"[API] Payload: {payload}")

            response = requests.post(
                self.checkin_url,
                json=payload,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'}
            )

            print(f"[API] Response status: {response.status_code}")

            if response.status_code == 201:
                result = response.json()
                return result
            else:
                print(f"[API] Check-in failed: {response.text}")
                return {
                    "success": False,
                    "message": f"HTTP {response.status_code}: {response.text}"
                }

        except requests.exceptions.RequestException as e:
            print(f"[API] Request error: {e}")
            return {"success": False, "message": str(e)}
        except Exception as e:
            print(f"[API] Unexpected error: {e}")
            return {"success": False, "message": str(e)}

    def checkout(self, parking_id: str) -> dict:
        try:
            url = f"{self.parking_url}{parking_id}/checkout"
            payload = {"gate_code": self.gate_code}

            print(f"[API] Online checkout request to {url}")
            print(f"[API] Payload: {payload}")

            response = requests.put(
                url,
                json=payload,
                timeout=self.timeout,
                headers=self.headers
            )

            print(f"[API] Response status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                print(f"[API] Checkout successful: {result.get('message')}")
                return result
            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get('message', error_msg)
                except:
                    pass
                return {"success": False, "message": error_msg}

        except Exception as e:
            print(f"[API ERROR] Checkout failed: {e}")
            return {"success": False, "message": str(e)}

    def manual_checkout(self, queue=None, amount=None, plate=None):
        try:
            payload = {
                "gate_code": self.gate_code
            }

            if queue:
                payload["queue_number"] = queue
            if plate:
                payload["plate_number"] = plate.upper().strip()
            if amount is not None and amount > 0:
                payload["amount"] = amount

            if not queue and not plate:
                raise ValueError("Either queue_number or plate_number must be provided")

            print(f"[API] Manual checkout request to {self.manual_checkout_url}")
            print(f"[API] Payload: {payload}")

            response = requests.post(
                self.manual_checkout_url,
                json=payload,
                timeout=self.timeout,
                headers=self.headers
            )

            print(f"[API] Response status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                return result.get('data', result)
            else:
                try:
                    error_data = response.json()
                    return error_data
                except:
                    return {
                        "success": False,
                        "message": f"HTTP {response.status_code}",
                        "status_code": response.status_code
                    }

        except Exception as e:
            print(f"[API] Error: {e}")
            return {"success": False, "message": str(e)}

    def get_parking_by_id(self, parking_id: str) -> dict:
        try:
            url = f"{self.parking_url}{parking_id}"
            print(f"[API GET] Requesting: {url}")

            response = requests.get(
                url,
                timeout=self.timeout,
                headers=self.headers
            )

            print(f"[API GET] Status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()

                return result
            else:
                print(f"[API GET] Error response: {response.text[:200]}")
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "data": None
                }

        except requests.exceptions.RequestException as e:
            print(f"[API GET] Request error: {e}")
            return {"success": False, "error": str(e), "data": None}

    def update(self, parking_id: str, plate: str, check_in_image: str = None, check_out_image: str = None,
               user_id: str = None):
        try:
            url = f"{self.parking_url}{parking_id}"
            payload = {
                "plate_number": plate if plate else "-",
            }

            if check_in_image:
                payload["check_in_image"] = check_in_image

            if check_out_image:
                payload["check_out_image"] = check_out_image

            if user_id:
                payload["user_id"] = user_id

            print(f"[API] Update {url}")
            print(f"[API] Payload: {payload}")

            response = requests.put(
                url,
                json=payload,
                timeout=self.timeout,
                headers=self.headers
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "message": f"HTTP {response.status_code}"}

        except Exception as e:
            print("[API ERROR]", e)
            return {"success": False, "error": str(e), "data": None}

    def member_checkout(self, plate: str) -> dict:
        try:
            url = f"{self.parking_url}member-checkout"
            payload = {
                "plate_number": plate.upper().strip(),
                "gate_code": self.gate_code
            }

            print(f"[API] Member checkout to {url}")
            print(f"[API] Payload: {payload}")

            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout,
                headers=self.headers
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "message": f"HTTP {response.status_code}"}

        except Exception as e:
            print(f"[API ERROR] {e}")
            return {"success": False, "message": str(e)}

    def validate_exit(self, parking_transaction_id: str) -> dict[str, bool | str] | None:
        try:
            url = f"{self.parking_url}validate-exit"
            payload = {
                "parking_transaction_id": parking_transaction_id,
                "gate_code": self.gate_code
            }

            print(f"[API] Validate Exit URL: {url}")
            print(f"[API] Payload: {payload}")

            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout,
                headers=self.headers
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "message": f"HTTP {response.status_code}"}

        except Exception as e:
            print(f"[API ERROR] {e}")
            return {"success": False, "message": str(e)}

    def login(self, email, password):
        try:
            url = f"{self.base_url}login"
            payload = {
                "email": email,
                "password": password
            }

            print(f"[API] Login URL: {url}")
            print(f"[API] Payload: {payload}")

            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout,
                headers=self.headers
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "message": f"HTTP {response.status_code}"}
        except Exception as e:
            print(f"[API ERROR] {e}")
            return {"success": False, "message": str(e)}
