class MockAPI:
    def login(self, email, password):
        return {
            "data": {
                "id": 1,
                "name": "Admin",
                "token": "abc123"
            }
        }

    def member_checkout(self, plate):
        return {
            "data": {
                "found": True,
                "plate_number": plate,
                "queue_number": "A001",
                "member": {
                    "name": "Budi",
                    "card_number": "M001",
                    "vehicle_type": {"name": "Mobil"}
                }
            }
        }

    def manual_checkout(self, queue, amount=None):
        if amount:
            return {
                "data": {
                    "success": True,
                    "paid": amount,
                    "remaining": 0,
                    "change": 2000
                }
            }
        else:
            return {
                "data": {
                    "found": True,
                    "plate_number": "BK1234AA",
                    "queue_number": queue,
                    "total": 5000,
                    "paid": 0,
                    "remaining": 5000
                }
            }

    def get_parking_by_id(self, id):
        return {
            "data": {
                "id": id,
                "success": True,
                "plate_number": "BK9999ZZ"
            }
        }

    def update(self, *args, **kwargs):
        return {"success": True}
