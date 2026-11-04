from PyQt5.QtCore import Qt

from tests.mock.mock_api import MockAPI


def test_online_payment(qtbot):
    from ui.parking_ui import ParkingUI

    class OnlineAPI(MockAPI):
        def get_parking_by_id(self, id):
            return {
                "data": {
                    "id": id,
                    "success": True,
                    "plate_number": "BK9999ZZ"
                }
            }

    ui = ParkingUI(api=OnlineAPI())
    qtbot.addWidget(ui)

    ui.input_search.setText("uuid-123456789")

    qtbot.mouseClick(ui.btn_cek, Qt.LeftButton)

    qtbot.waitUntil(lambda: ui._state == ui.S_OPENING, timeout=3000)

    assert ui._state == ui.S_OPENING