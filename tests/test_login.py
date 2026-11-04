from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog

from tests.mock.mock_api import MockAPI
from ui.dialogs.login_dialog import LoginDialog


def test_login_success(qtbot):
    dialog = LoginDialog(api=MockAPI())
    qtbot.addWidget(dialog)

    dialog.email.setText("admin@test.com")
    dialog.password.setText("123")

    with qtbot.waitSignal(dialog.login_successful, timeout=2000):
        qtbot.mouseClick(dialog.btn_login, Qt.LeftButton)

    assert dialog.result() == QDialog.Accepted
