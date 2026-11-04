from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QHBoxLayout
)
from PyQt5.QtCore import pyqtSignal, Qt, QSettings


class LoginDialog(QDialog):
    login_successful = pyqtSignal(dict)

    def __init__(self, api=None, parent=None):
        super().__init__(parent)
        self.api = api

        self.setWindowTitle("Login Kasir")
        self.setFixedSize(360, 360)
        self.setStyleSheet(self._style())

        self.settings = QSettings("ParkingApp", "Login")

        layout = QVBoxLayout(self)
        layout.setSpacing(14)  # 🔥 spacing lebih lega

        # ===== TITLE =====
        self.title = QLabel("PARKING SYSTEM")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setObjectName("title")
        layout.addWidget(self.title)

        self.subtitle = QLabel("Silakan login untuk melanjutkan")
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setObjectName("subtitle")
        layout.addWidget(self.subtitle)

        # ===== EMAIL =====
        self.email = QLineEdit()
        self.email.setPlaceholderText("Email")
        layout.addWidget(self.email)

        # ===== PASSWORD =====
        pwd_layout = QVBoxLayout()
        pwd_layout.setSpacing(6)  # 🔥 biar tidak terhimpit

        self.password = QLineEdit()
        self.password.setPlaceholderText("Password")
        self.password.setEchoMode(QLineEdit.Password)
        self.password.returnPressed.connect(self.handle_login)
        pwd_layout.addWidget(self.password)

        # ===== SHOW PASSWORD =====
        row = QHBoxLayout()
        row.setContentsMargins(0, 2, 0, 0)

        self.chk_show = QCheckBox("Tampilkan password")
        self.chk_show.stateChanged.connect(self._toggle_password)

        row.addWidget(self.chk_show)
        row.addStretch()

        pwd_layout.addLayout(row)
        layout.addLayout(pwd_layout)

        # ===== REMEMBER =====
        self.chk_remember = QCheckBox("Ingat saya")
        layout.addWidget(self.chk_remember)

        # ===== STATUS =====
        self.status = QLabel("")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setObjectName("status")
        layout.addWidget(self.status)

        # ===== BUTTON =====
        self.btn_login = QPushButton("LOGIN")
        self.btn_login.clicked.connect(self.handle_login)
        layout.addWidget(self.btn_login)

        # load saved
        self._load_saved()
        self.email.setFocus()

    # =============================
    # 🔐 TOGGLE PASSWORD
    # =============================
    def _toggle_password(self):
        if self.chk_show.isChecked():
            self.password.setEchoMode(QLineEdit.Normal)
        else:
            self.password.setEchoMode(QLineEdit.Password)

    # =============================
    # 💾 LOAD SAVED
    # =============================
    def _load_saved(self):
        email = self.settings.value("email", "")
        password = self.settings.value("password", "")

        self.email.setText(email)
        self.password.setText(password)

        if email:
            self.chk_remember.setChecked(True)

    # =============================
    # 🔐 LOGIN
    # =============================
    def handle_login(self):
        email = self.email.text().strip()
        pwd = self.password.text().strip()

        if not email or not pwd:
            self.status.setText("Email & password wajib")
            return

        self.status.setText("Loading...")
        self.btn_login.setEnabled(False)

        try:
            result = self.api.login(email, pwd)

            if result.get("data"):
                data = result.get("data", {})

                # save
                if self.chk_remember.isChecked():
                    self.settings.setValue("email", email)
                    self.settings.setValue("password", pwd)
                else:
                    self.settings.clear()

                self.login_successful.emit({
                    "email": email,
                    "name": data.get("name", email),
                    "token": data.get("token"),
                    "user_id": data.get("id")
                })

                self.accept()
            else:
                self.status.setText(result.get("message", "Login gagal"))
                self.btn_login.setEnabled(True)

        except Exception as e:
            self.status.setText(f"Error: {str(e)}")
            self.btn_login.setEnabled(True)

    # =============================
    # 🎨 STYLE
    # =============================
    def _style(self):
        return """
        QDialog {
            background: #f9fafb;
            border-radius: 12px;
            font-family: 'Segoe UI', monospace;
        }

        QLabel#title {
            font-size: 18px;
            font-weight: bold;
            color: #1f2937;
        }

        QLabel#subtitle {
            font-size: 11px;
            color: #6b7280;
        }

        QLabel#status {
            font-size: 11px;
            color: #dc2626;
        }

        /* INPUT */
        QLineEdit {
            background: #ffffff;
            color: #111827;
            border: 1.5px solid #e5e7eb;
            border-radius: 8px;
            padding: 10px;
            font-size: 13px;
        }

        QLineEdit:focus {
            border: 1.5px solid #2563eb;
        }

        QLineEdit::placeholder {
            color: #9ca3af;
        }

        /* BUTTON */
        QPushButton {
            background: #2563eb;
            color: white;
            border-radius: 8px;
            padding: 10px;
            font-weight: bold;
            font-size: 13px;
        }

        QPushButton:hover {
            background: #3b82f6;
        }

        QPushButton:pressed {
            background: #1d4ed8;
        }

        QPushButton:disabled {
            background: #9ca3af;
        }

        /* CHECKBOX */
        QCheckBox {
            color: #374151;
            font-size: 11px;
            spacing: 6px;
        }

        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1.5px solid #d1d5db;
            background: #ffffff;
        }

        QCheckBox::indicator:checked {
            background: #2563eb;
            border: 1.5px solid #2563eb;
        }

        QCheckBox::indicator:hover {
            border: 1.5px solid #2563eb;
        }
        """
