from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt


class LogoutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedSize(400, 180)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        container = QVBoxLayout(self)
        container.setContentsMargins(10, 10, 10, 10)

        # ===== CARD =====
        card = QVBoxLayout()
        card.setSpacing(20)

        wrapper = QLabel()
        wrapper.setStyleSheet("""
            QLabel {
                background: #ffffff;
                border-radius: 12px;
            }
        """)
        wrapper.setFixedSize(380, 160)

        inner = QVBoxLayout(wrapper)
        inner.setContentsMargins(20, 20, 20, 20)
        inner.setSpacing(20)

        # ===== TITLE =====
        title = QLabel("Logout")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #111827;
        """)

        # ===== TEXT =====
        text = QLabel("Apakah kamu yakin ingin keluar dari sistem?")
        text.setAlignment(Qt.AlignCenter)
        text.setWordWrap(True)
        text.setStyleSheet("""
            font-size: 13px;
            color: #374151;
        """)

        # ===== BUTTON =====
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)

        self.btn_cancel = QPushButton("Batal")
        self.btn_cancel.setFixedHeight(40)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background: #e5e7eb;
                border-radius: 8px;
                color: #111827;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #d1d5db;
            }
        """)

        self.btn_logout = QPushButton("Logout")
        self.btn_logout.setFixedHeight(40)
        self.btn_logout.setStyleSheet("""
            QPushButton {
                background: #ef4444;
                border-radius: 8px;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #dc2626;
            }
        """)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_logout)

        # ===== BUILD =====
        inner.addWidget(title)
        inner.addWidget(text)
        inner.addLayout(btn_layout)

        container.addWidget(wrapper)

        # ===== ACTION =====
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_logout.clicked.connect(self.accept)
