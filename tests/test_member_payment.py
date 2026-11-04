from PyQt5.QtCore import Qt

from tests.mock.mock_api import MockAPI


def test_member_checkout(qtbot):
    from ui.parking_ui import ParkingUI

    ui = ParkingUI(api=MockAPI())
    qtbot.addWidget(ui)

    ui.input_search.setText("BK1234AA")

    qtbot.mouseClick(ui.btn_member, Qt.LeftButton)

    qtbot.waitUntil(lambda: ui.member_banner.isVisible(), timeout=3000)

    assert ui.member_banner.isVisible()
    assert ui.r_plate._val.text() == "BK1234AA"