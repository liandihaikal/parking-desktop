import sys
import re
import os
import urllib.request
import tempfile
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QSizePolicy,
    QGroupBox, QMessageBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QColor, QPalette, QPixmap

from api.parking_api import ParkingAPI
from services.barrier_service import BarrierService
from services.sound_service import SoundService
from config import GATE_CODE
from ui.dialogs.login_dialog import LoginDialog
from ui.dialogs.logout_dialog import LogoutDialog


# ──────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────

def extract_id(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    if "id=" in value:
        try:
            return value.split("id=")[-1].split("&")[0]
        except Exception:
            pass
    if "/" in value:
        return value.rstrip("/").split("/")[-1]
    return value


def fmt_rupiah(value) -> str:
    try:
        return f"Rp {float(value):,.0f}"
    except (TypeError, ValueError):
        return "Rp 0"


def fmt_datetime(raw: str) -> str:
    if not raw:
        return "-"
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.strftime("%d-%m-%Y %H:%M")
    except Exception:
        return str(raw)


def _unwrap(result: dict) -> dict:
    if isinstance(result, dict) and "data" in result:
        inner = result["data"]
        if isinstance(inner, dict):
            return inner
    return result


def _is_plate(text: str) -> bool:
    t = text.upper().replace(" ", "")
    return bool(re.match(r'^[A-Z]{1,2}[0-9]{1,4}[A-Z]{1,3}$', t))


# ──────────────────────────────────────────────────────────────
#  THREADS
# ──────────────────────────────────────────────────────────────

class ScannerThread(QThread):
    scanned = pyqtSignal(str)

    def run(self):
        while True:
            try:
                line = input()
                if line.strip():
                    self.scanned.emit(line.strip())
            except EOFError:
                break


class APIThread(QThread):
    result = pyqtSignal(dict)

    def __init__(self, fn, *args):
        super().__init__()
        self._fn = fn
        self._args = args

    def run(self):
        try:
            print("fn: ", self._fn, " args: ", self._args, "")
            self.result.emit(self._fn(*self._args))
        except Exception as e:
            self.result.emit({"success": False, "message": str(e)})


class CheckoutImageCaptureThread(QThread):
    image_captured = pyqtSignal(str)
    capture_failed = pyqtSignal(str)

    def __init__(self, camera, minio, api, parking_id, ticket_number: str, plate_number: str):
        super().__init__()
        self.camera = camera
        self.minio = minio
        self.api = api
        self.parking_id = parking_id
        self.ticket_number = ticket_number
        self.plate_number = plate_number

    def run(self):
        try:
            identifier = self.ticket_number or self.plate_number or "unknown"
            print(f"[CAMERA] Capturing checkout image for: {identifier}")

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"checkout_{identifier}_{timestamp}.jpg"

            frame = self.camera.capture(filename, subdir='checkout')
            if frame is None:
                self.capture_failed.emit("Failed to capture from camera")
                return

            date_path = datetime.now().strftime('%Y/%m/%d')
            object_name = f"checkout/{date_path}/{identifier}_{timestamp}.jpg"
            image_url = self.minio.upload_cv2_image(frame, object_name, quality=85)

            if image_url:
                print(f"[MINIO] Checkout image uploaded: {object_name}")
                self.image_captured.emit(image_url)
                self.api.update(self.parking_id, "", "", check_out_image=image_url, user_id=self.api.user_id)
            else:
                self.capture_failed.emit("Failed to upload to MinIO")

        except Exception as e:
            print(f"[CAMERA] Error: {e}")
            self.capture_failed.emit(str(e))


class ImageViewer(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QLabel {
                background:#f3f4f6;
                border:1px solid #e5e7eb;
                border-radius:8px;
                padding: 4px;
            }
        """)
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(False)
        self._reset_text()
        self._tmp = None
        self._current_pixmap = None

    def _reset_text(self):
        self.clear()
        self.setText("📷\nNo Image")
        self.setStyleSheet(self.styleSheet() + """
            QLabel {
                font-size: 11px;
                color: #9ca3af;
            }
        """)

    def load_url(self, url: str):
        if not url:
            self._reset_text()
            return
        self._clean_tmp()
        try:
            with urllib.request.urlopen(url, timeout=8) as r:
                data = r.read()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f:
                f.write(data)
                self._tmp = f.name

            pixmap = QPixmap(self._tmp)
            if not pixmap.isNull():
                target_height = self.height() - 10
                if target_height > 0:
                    scaled_pixmap = pixmap.scaledToHeight(target_height, Qt.SmoothTransformation)
                    self.setPixmap(scaled_pixmap)
                    self._current_pixmap = scaled_pixmap
                else:
                    self._reset_text()
            else:
                self._reset_text()
        except Exception as e:
            print(f"[ImageViewer] Error: {e}")
            self._reset_text()

    def load_path(self, path: str):
        if path and os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                target_height = self.height() - 10
                if target_height > 0:
                    scaled_pixmap = pixmap.scaledToHeight(target_height, Qt.SmoothTransformation)
                    self.setPixmap(scaled_pixmap)
                    self._current_pixmap = scaled_pixmap
                else:
                    self._reset_text()
            else:
                self._reset_text()
        else:
            self._reset_text()

    def clear_image(self):
        self._clean_tmp()
        self._reset_text()
        self._current_pixmap = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._current_pixmap and not self._current_pixmap.isNull():
            target_height = self.height() - 10
            if target_height > 0:
                scaled_pixmap = self._current_pixmap.scaledToHeight(target_height, Qt.SmoothTransformation)
                self.setPixmap(scaled_pixmap)

    def _clean_tmp(self):
        if self._tmp and os.path.exists(self._tmp):
            try:
                os.unlink(self._tmp)
            except Exception:
                pass
        self._tmp = None


# ──────────────────────────────────────────────────────────────
#  BASE WIDGETS
# ──────────────────────────────────────────────────────────────

class Divider(QFrame):
    def __init__(self, color: str = "#e5e7eb"):
        super().__init__()
        self.setFrameShape(QFrame.HLine)
        self.setFixedHeight(1)
        self.setStyleSheet(f"background:{color}; border:none;")


class InfoRow(QFrame):
    def __init__(self, label, icon=""):
        super().__init__()

        # 🔥 TANPA BORDER & RADIUS
        self.setStyleSheet("""
            QFrame {
                background: transparent;
                border: none;
            }
        """)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)

        row = QHBoxLayout()
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(10)

        # ICON
        self.icon_box = QLabel(icon)
        self.icon_box.setFixedSize(28, 28)
        self.icon_box.setAlignment(Qt.AlignCenter)
        self.icon_box.setStyleSheet("""
            QLabel {
                background:#f3f4f6;
                border-radius:0px;   /* 🔥 NO RADIUS */
                font-size:12px;
            }
        """)

        # LABEL
        self._lbl = QLabel(label)
        self._lbl.setFixedWidth(110)
        self._lbl.setStyleSheet("""
            color:#6b7280;
            font-size:10px;
        """)

        # VALUE
        self._val = QLabel("-")
        self._val.setAlignment(Qt.AlignRight)
        self._val.setStyleSheet("""
            color:#111827;
            font-size:11px;
            font-weight:600;
        """)

        row.addWidget(self.icon_box)
        row.addWidget(self._lbl)
        row.addStretch()
        row.addWidget(self._val)

        # 🔥 SEPARATOR LINE
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#e5e7eb; margin-left:38px;")

        self.main_layout.addLayout(row)
        self.main_layout.addWidget(line)

    def set_value(self, val):
        self._val.setText(val)

    def setText(self, val):  # backward safe
        self._val.setText(val)

    def set_highlight(self, color):
        self._val.setStyleSheet(f"""
            color:{color};
            font-size:12px;
            font-weight:700;
        """)


class StatusBadge(QLabel):
    _S = {
        "idle": ("MENUNGGU SCAN", "#f3f4f6", "#6b7280"),
        "loading": ("MEMPROSES...", "#dbeafe", "#2563eb"),
        "found": ("DATA DITEMUKAN", "#dcfce7", "#16a34a"),
        "member": ("MEMBER AKTIF", "#fef9c3", "#ca8a04"),
        "success": ("LUNAS", "#dcfce7", "#16a34a"),
        "error": ("GAGAL", "#fee2e2", "#dc2626"),
        "open": ("GATE TERBUKA", "#dbeafe", "#2563eb"),
        "online": ("LUNAS ONLINE", "#dcfce7", "#16a34a"),
        "capturing": ("CAPTURE FOTO...", "#dbeafe", "#2563eb"),
    }

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(36)
        self.set_state("idle")

    def set_state(self, state: str, extra: str = ""):
        text, bg, fg = self._S.get(state, self._S["idle"])
        self.setText(f"{text}  {extra}" if extra else text)
        self.setStyleSheet(f"""
            QLabel {{
                background:{bg}; color:{fg};
                border:1px solid {fg}40; border-radius:4px;
                font-size:11px; font-weight:700; letter-spacing:1.5px;
                padding:0 14px; font-family:'Segoe UI',monospace;
            }}
        """)


class TitleBar(QWidget):
    window_minimized = pyqtSignal()
    window_maximized = pyqtSignal()
    window_closed = pyqtSignal()
    window_logout = pyqtSignal()  # 🔥 tambahan

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.is_maximized = False
        self.drag_position = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)

        # ===== TITLE =====
        self.title_label = QLabel("KASIR PARKIR")
        self.title_label.setStyleSheet("""
                QLabel { color:white; font-size:18px; font-weight:bold;
                         font-family:'Segoe UI',monospace; padding:5px; }
            """)

        # ===== GATE =====
        self.gate_badge = QLabel(GATE_CODE)
        self.gate_badge.setStyleSheet("""
                QLabel { color:#2563eb; background:#dbeafe; border-radius:8px;
                         font-size:12px; font-weight:bold; padding:4px 12px;
                         font-family:'Segoe UI',monospace; }
            """)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        _btn_css = """
                QPushButton {{
                    background:{bg};
                    color:white;
                    border:none;
                    border-radius:5px;
                    font-size:14px;
                    font-weight:bold;
                }}
                QPushButton:hover   {{ background:{hv}; }}
                QPushButton:pressed {{ background:{pr}; }}
            """

        # ===== LOGOUT BUTTON (SMALL) =====
        self.logout_btn = QPushButton("Logout")
        self.logout_btn.setCursor(Qt.PointingHandCursor)
        self.logout_btn.setToolTip("Logout")

        # 🔥 ukuran kecil tapi tidak kepotong
        self.logout_btn.setFixedHeight(30)
        self.logout_btn.setMinimumWidth(70)

        # 🔥 tetap pakai system style kamu
        self.logout_btn.setStyleSheet(_btn_css.format(
            bg="#f59e0b",
            hv="#fbbf24",
            pr="#d97706"
        ))

        self.logout_btn.clicked.connect(self.logout_window)
        # ===== MIN =====
        self.minimize_btn = QPushButton("—")
        self.minimize_btn.setFixedSize(30, 30)
        self.minimize_btn.setCursor(Qt.PointingHandCursor)
        self.minimize_btn.setStyleSheet(_btn_css.format(
            bg="#374151", hv="#4b5563", pr="#1f2937"
        ))

        # ===== MAX =====
        self.maximize_btn = QPushButton("□")
        self.maximize_btn.setFixedSize(30, 30)
        self.maximize_btn.setCursor(Qt.PointingHandCursor)
        self.maximize_btn.setStyleSheet(_btn_css.format(
            bg="#374151", hv="#4b5563", pr="#1f2937"
        ))

        # ===== CLOSE =====
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet(_btn_css.format(
            bg="#dc2626", hv="#ef4444", pr="#b91c1c"
        ))

        # connect
        self.minimize_btn.clicked.connect(self.minimize_window)
        self.maximize_btn.clicked.connect(self.toggle_maximize)
        self.close_btn.clicked.connect(self.close_window)

        # layout (logout di kiri minimize)
        for w in [
            self.title_label,
            self.gate_badge,
            spacer,
            self.logout_btn,
            self.minimize_btn,
            self.maximize_btn,
            self.close_btn
        ]:
            layout.addWidget(w)

        self.setFixedHeight(50)
        self.setStyleSheet("QWidget { background:#1f2937; border-bottom:2px solid #374151; }")

    def minimize_window(self):
        self.window_minimized.emit()

    def toggle_maximize(self):
        self.window_maximized.emit()
        self.is_maximized = not self.is_maximized

    def close_window(self):
        self.window_closed.emit()

    def logout_window(self):
        print("[TITLEBAR] Logout clicked")
        self.window_logout.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_position and not self.is_maximized:
            self.parent.move(event.globalPos() - self.drag_position)
            event.accept()


# ──────────────────────────────────────────────────────────────
#  STYLED FACTORIES
# ──────────────────────────────────────────────────────────────

_FIELD = """
    QLineEdit {{
        background:#ffffff; color:#1f2937;
        border:1.5px solid {b}; border-radius:6px;
        padding:10px 14px; font-size:14px;
        font-family:'Segoe UI',monospace;
    }}
    QLineEdit:focus    {{ border:1.5px solid #3b82f6; }}
    QLineEdit:disabled {{ color:#9ca3af; border-color:#e5e7eb; background:#f9fafb; }}
"""
_BTN = """
    QPushButton {{
        background:{bg}; color:{fg}; border:none; border-radius:6px;
        font-size:13px; font-weight:600; padding:10px 18px;
        font-family:'Segoe UI',monospace;
    }}
    QPushButton:hover    {{ background:{hv}; }}
    QPushButton:pressed  {{ background:{pr}; }}
    QPushButton:disabled {{ background:#e5e7eb; color:#9ca3af; }}
"""


def mk_input(ph: str, border: str = "#e5e7eb") -> QLineEdit:
    w = QLineEdit()
    w.setPlaceholderText(ph)
    w.setFixedHeight(42)
    w.setStyleSheet(_FIELD.format(b=border))
    return w


def mk_btn(t, bg, hv, pr, h=42):
    b = QPushButton(t)
    b.setFixedHeight(h)
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet(_BTN.format(bg=bg, fg="#fff", hv=hv, pr=pr))
    return b


def blue_btn(t):   return mk_btn(t, "#2563eb", "#3b82f6", "#1d4ed8")


def green_btn(t):  return mk_btn(t, "#16a34a", "#22c55e", "#15803d")


def orange_btn(t): return mk_btn(t, "#ea580c", "#f97316", "#c2410c")


def grey_btn(t):
    b = mk_btn(t, "#f3f4f6", "#e5e7eb", "#d1d5db", h=38)
    b.setStyleSheet(b.styleSheet().replace("color:#fff", "color:#4b5563"))
    return b


# ──────────────────────────────────────────────────────────────
#  MEMBER INPUT SECTION  (muncul setelah scan tiket berhasil)
# ──────────────────────────────────────────────────────────────

class MemberInputSection(QFrame):
    """
    Input plat nomor untuk mencari member, muncul di state S_CHECKED.
    Memancarkan signal `search_requested(plate)` saat user submit.
    Signal `clear_requested` saat user klik tombol hapus member.
    """
    search_requested = pyqtSignal(str)  # plate_number
    clear_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background: #eff6ff;
                border: 2px solid #bfdbfe;
                border-radius: 10px;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(6)

        # Header
        hdr = QHBoxLayout()
        icon = QLabel("🔎")
        icon.setStyleSheet("font-size:14px; background:transparent; border:none;")
        title = QLabel("UPDATE PLAT & CARI MEMBER  (opsional)")
        title.setStyleSheet("""
            color:#1e40af; font-size:10px; font-weight:bold;
            letter-spacing:1px; font-family:'Segoe UI',monospace;
            background:transparent; border:none;
        """)
        hint = QLabel("Lihat foto plat → ketik plat → plat diperbarui + member dicari otomatis")
        hint.setStyleSheet("""
            color:#3b82f6; font-size:9px;
            font-family:'Segoe UI',monospace;
            background:transparent; border:none;
        """)
        hdr.addWidget(icon)
        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(hint)
        lay.addLayout(hdr)

        # Input row
        inp_row = QHBoxLayout()
        inp_row.setSpacing(8)

        self.input_plate = QLineEdit()
        self.input_plate.setPlaceholderText("Ketik plat dari foto (cth: BK1234XY)")
        self.input_plate.setFixedHeight(38)
        self.input_plate.setStyleSheet("""
            QLineEdit {
                background:#ffffff; color:#1f2937;
                border:1.5px solid #93c5fd; border-radius:6px;
                padding:8px 12px; font-size:14px; font-weight:600;
                font-family:'Segoe UI',monospace;
                text-transform: uppercase;
            }
            QLineEdit:focus { border:1.5px solid #2563eb; }
            QLineEdit:disabled { background:#f1f5f9; color:#94a3b8; border-color:#e2e8f0; }
        """)
        self.input_plate.returnPressed.connect(self._on_submit)
        self.input_plate.textChanged.connect(
            lambda t: self.input_plate.setText(t.upper())
        )

        self.btn_cari = QPushButton("UPDATE PLAT + CARI MEMBER")
        self.btn_cari.setFixedHeight(38)
        self.btn_cari.setCursor(Qt.PointingHandCursor)
        self.btn_cari.setStyleSheet("""
            QPushButton {
                background:#2563eb; color:white; border:none; border-radius:6px;
                font-size:12px; font-weight:700; padding:0 16px;
                font-family:'Segoe UI',monospace;
            }
            QPushButton:hover    { background:#3b82f6; }
            QPushButton:pressed  { background:#1d4ed8; }
            QPushButton:disabled { background:#bfdbfe; color:#93c5fd; }
        """)
        self.btn_cari.clicked.connect(self._on_submit)

        self.btn_clear_member = QPushButton("✕")
        self.btn_clear_member.setFixedSize(38, 38)
        self.btn_clear_member.setCursor(Qt.PointingHandCursor)
        self.btn_clear_member.setToolTip("Hapus member dari tiket ini")
        self.btn_clear_member.setStyleSheet("""
            QPushButton {
                background:#fee2e2; color:#dc2626; border:none; border-radius:6px;
                font-size:14px; font-weight:700;
            }
            QPushButton:hover    { background:#fecaca; }
            QPushButton:pressed  { background:#fca5a5; }
            QPushButton:disabled { background:#f3f4f6; color:#9ca3af; }
        """)
        self.btn_clear_member.clicked.connect(self.clear_requested.emit)
        self.btn_clear_member.setVisible(False)  # muncul hanya jika member sudah terkait

        inp_row.addWidget(self.input_plate, 1)
        inp_row.addWidget(self.btn_cari)
        inp_row.addWidget(self.btn_clear_member)
        lay.addLayout(inp_row)

        # Status info (loading / hasil)
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("""
            QLabel {
                color:#6b7280; font-size:10px;
                font-family:'Segoe UI',monospace;
                background:transparent; border:none;
            }
        """)
        self.lbl_status.setVisible(False)
        lay.addWidget(self.lbl_status)

        self.setVisible(False)  # disembunyikan sampai S_CHECKED

    # ── public API ──────────────────────────────────────────────

    def show_section(self):
        self.set_idle()
        self.setVisible(True)

    def hide_section(self):
        self.setVisible(False)
        self.reset()

    def reset(self):
        self.input_plate.clear()
        self.lbl_status.setVisible(False)
        self.btn_clear_member.setVisible(False)
        self.set_idle()

    def set_loading(self):
        self.input_plate.setEnabled(False)
        self.btn_cari.setEnabled(False)
        self.btn_cari.setText("⏳ Memproses...")
        self._set_status("⏳ Mengupdate plat & mencari member...", "#2563eb")

    def set_found(self, name: str):
        self.input_plate.setEnabled(False)
        self.btn_cari.setEnabled(False)
        self.btn_clear_member.setVisible(True)
        self._set_status(f"✅ Plat diperbarui · Member: {name}", "#16a34a", bold=True)
        self.setStyleSheet(self.styleSheet().replace("#eff6ff", "#f0fdf4")
                           .replace("#bfdbfe", "#bbf7d0"))

    def set_not_found(self, msg: str = "Member tidak ditemukan"):
        self.input_plate.setEnabled(True)
        self.btn_cari.setEnabled(True)
        self.btn_cari.setText("UPDATE PLAT + CARI MEMBER")
        self._set_status(f"⚠ {msg}", "#d97706")

    def set_idle(self):
        self.input_plate.setEnabled(True)
        self.btn_cari.setEnabled(True)
        self.btn_cari.setText("UPDATE PLAT + CARI MEMBER")
        self.btn_clear_member.setVisible(False)
        self.lbl_status.setVisible(False)
        self.setStyleSheet("""
            QFrame {
                background: #eff6ff;
                border: 2px solid #bfdbfe;
                border-radius: 10px;
            }
        """)

    def get_plate(self) -> str:
        return self.input_plate.text().strip().upper()

    # ── private ─────────────────────────────────────────────────

    def _on_submit(self):
        plate = self.get_plate()
        if not plate:
            self._set_status("⚠ Masukkan plat nomor terlebih dahulu", "#d97706")
            return
        self.search_requested.emit(plate)

    def _set_status(self, text: str, color: str, bold: bool = False):
        weight = "font-weight:700;" if bold else ""
        self.lbl_status.setStyleSheet(f"""
            QLabel {{
                color:{color}; font-size:10px; {weight}
                font-family:'Segoe UI',monospace;
                background:transparent; border:none;
            }}
        """)
        self.lbl_status.setText(text)
        self.lbl_status.setVisible(True)


# ──────────────────────────────────────────────────────────────
#  MEMBER BANNER  (inline di dalam card)
# ──────────────────────────────────────────────────────────────

class MemberBanner(QFrame):
    """
    Banner kuning yang ditampilkan di dalam card detail tiket
    ketika tiket milik member. Tersembunyi secara default.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background: #fef9c3;
                border: 1.5px solid #fde68a;
                border-radius: 8px;
            }
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(3)

        # Header baris: ikon + judul + tanggal valid
        hdr = QHBoxLayout()
        icon = QLabel("⭐")
        icon.setStyleSheet("font-size:16px; background:transparent; border:none;")
        title = QLabel("MEMBER AKTIF")
        title.setStyleSheet("""
            color:#92400e; font-size:10px; font-weight:bold;
            letter-spacing:1.2px; font-family:'Segoe UI',monospace;
            background:transparent; border:none;
        """)
        self.lbl_valid = QLabel("")
        self.lbl_valid.setStyleSheet("""
            color:#a16207; font-size:9px;
            font-family:'Segoe UI',monospace;
            background:transparent; border:none;
        """)
        hdr.addWidget(icon)
        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(self.lbl_valid)
        lay.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background:#fde68a; border:none;")
        lay.addWidget(sep)

        # Info rows member (compact)
        self.r_name = self._mk_row("NAMA")
        self.r_card = self._mk_row("NO. KARTU")
        self.r_vehicle = self._mk_row("KENDARAAN")
        for r in [self.r_name, self.r_card, self.r_vehicle]:
            lay.addWidget(r)

        self.setVisible(False)

    @staticmethod
    def _mk_row(label: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 1, 0, 1)
        lbl = QLabel(label)
        lbl.setFixedWidth(80)
        lbl.setStyleSheet("color:#a16207; font-size:10px; font-family:'Segoe UI',monospace;")
        val = QLabel("-")
        val.setAlignment(Qt.AlignRight)
        val.setStyleSheet("color:#78350f; font-size:11px; font-weight:600; font-family:'Segoe UI',monospace;")
        h.addWidget(lbl)
        h.addWidget(val, 1)
        w._val = val  # simpan ref
        return w

    def populate(self, member: dict):
        """Isi data member dan tampilkan banner."""
        if not member:
            self.setVisible(False)
            return

        self.r_name._val.setText(member.get("name", "-"))
        self.r_card._val.setText(member.get("card_number", "-"))

        vt = member.get("vehicle_type", "-")
        self.r_vehicle._val.setText(
            vt.get("name", "-") if isinstance(vt, dict) else vt
        )

        valid = member.get("valid_until", "")
        self.lbl_valid.setText(f"berlaku s/d {valid}" if valid else "")

        self.setVisible(True)

    def clear(self):
        self.setVisible(False)


# ──────────────────────────────────────────────────────────────
#  MAIN WINDOW
# ──────────────────────────────────────────────────────────────

class ParkingUI(QWidget):
    S_IDLE = "idle"
    S_LOADING = "loading"
    S_MEMBER = "member"
    S_CHECKED = "checked"
    S_OPENING = "opening"

    def __init__(self, barier=None, sound=None, api=None, camera=None, minio=None):
        super().__init__()
        self.api = api if api is not None else ParkingAPI()
        self.barier = barier if barier is not None else BarrierService()
        self.sound = sound if sound is not None else SoundService()
        self.camera = camera
        self.minio = minio

        self._state = self.S_IDLE
        self._queue_number = None
        self._is_member = False
        self._is_free = False
        self._threads: list[APIThread] = []
        self._capture_threads: list[CheckoutImageCaptureThread] = []

        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._build_ui()
        self._apply_theme()
        self._start_scanner()
        self._set_state(self.S_IDLE)
        self.showFullScreen()

    # ───────────────────────────────────────────────────────────
    #  BUILD UI
    # ───────────────────────────────────────────────────────────

    def _build_ui(self):
        main_container = QWidget()
        main_container.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f9fafb, stop:1 #f3f4f6);
            }
        """)

        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Title bar
        self.title_bar = TitleBar(self)
        self.title_bar.window_logout.connect(self.logout)
        self.title_bar.window_minimized.connect(self.showMinimized)
        self.title_bar.window_maximized.connect(self.toggle_fullscreen)
        self.title_bar.window_closed.connect(self.close)
        main_layout.addWidget(self.title_bar)

        # Content
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        root = QVBoxLayout(content)
        root.setContentsMargins(30, 10, 30, 10)
        root.setSpacing(8)

        # ── HEADER ──
        header = QHBoxLayout()
        date_label = QLabel(datetime.now().strftime("%A, %d %B %Y %H:%M"))
        date_label.setStyleSheet("color:#6b7280; font-size:12px; font-family:'Segoe UI',monospace;")
        header.addWidget(date_label)
        header.addStretch()

        self.btn_reset = green_btn("↩ Transaksi Baru")
        self.btn_reset.setFixedHeight(40)
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.clicked.connect(self._reset)
        header.addWidget(self.btn_reset)

        self.date_timer = QTimer()
        self.date_timer.timeout.connect(
            lambda: date_label.setText(datetime.now().strftime("%A, %d %B %Y %H:%M"))
        )
        self.date_timer.start(1000)

        root.addLayout(header)
        root.addWidget(Divider())

        # ── INPUT GROUP ──
        ig = QGroupBox("🚗 CHECKOUT | Scan QR / Nomor Antrian / Plat")
        ig.setStyleSheet("""
            QGroupBox {
                font-weight:bold; font-size:13px;
                border:2px solid #e5e7eb; border-radius:10px;
                margin-top:8px; font-family:'Segoe UI',monospace; background:white;
            }
            QGroupBox::title { subcontrol-origin:margin; left:15px; padding:0 8px; color:#374151; }
        """)
        ig_lay = QVBoxLayout(ig)
        ig_lay.setSpacing(8)
        ig_lay.setContentsMargins(15, 15, 15, 15)

        self.input_search = mk_input("Scan QR Code / Nomor Antrian / Plat Nomor", border="#3b82f640")
        self.input_search.setFixedHeight(40)
        self.input_search.returnPressed.connect(self._do_search)
        ig_lay.addWidget(self.input_search)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_cek = blue_btn("🔍 CEK TIKET")
        self.btn_member = orange_btn("⭐ CHECKOUT MEMBER")
        self.btn_cek.setFixedHeight(40)
        self.btn_member.setFixedHeight(40)
        self.btn_cek.clicked.connect(self._do_search)
        self.btn_member.clicked.connect(self._do_member_checkout)
        btn_row.addWidget(self.btn_cek)
        btn_row.addWidget(self.btn_member)
        ig_lay.addLayout(btn_row)

        hint = QLabel("💡 Scan QR/nomor antrian untuk checkout biasa | Plat nomor untuk checkout member")
        hint.setStyleSheet("color:#6b7280; font-size:10px; font-family:'Segoe UI',monospace;")
        hint.setWordWrap(True)
        ig_lay.addWidget(hint)

        root.addWidget(ig)

        # =============================
        # 🔥 MAIN LAYOUT (FINAL FIX)
        # =============================
        main_row = QHBoxLayout()
        main_row.setSpacing(15)

        # =========================================
        # 🔥 LEFT: DETAIL TIKET (FLAT CLEAN)
        # =========================================
        left_box = QVBoxLayout()
        left_box.setSpacing(6)

        self.card = QFrame()
        self.card.setMaximumWidth(420)

        # 🔥 TANPA RADIUS
        self.card.setStyleSheet("""
            QFrame {
                background:white;
                border:1px solid #e5e7eb;
                border-radius:12px;
            }
        """)

        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(4)

        # ===== TITLE =====
        title_row = QHBoxLayout()

        icon = QLabel("🏷️")
        icon.setStyleSheet("font-size:16px;")

        lbl_d = QLabel("DETAIL TIKET")
        lbl_d.setStyleSheet("""
            QLabel {
                color:#1f2937;
                font-size:13px;
                font-weight:bold;
            }
        """)

        title_row.addWidget(icon)
        title_row.addWidget(lbl_d)
        title_row.addStretch()

        cl.addLayout(title_row)

        # =============================
        # 🔹 INFO UTAMA
        # =============================
        self.r_plate = InfoRow("PLAT NOMOR", "🚗")
        self.r_type = InfoRow("JENIS", "🏍️")
        self.r_gate = InfoRow("GATE MASUK", "🚧")
        self.r_checkin = InfoRow("WAKTU MASUK", "📅")
        self.r_dur = InfoRow("DURASI", "⏱️")

        # =============================
        # 🔹 PAYMENT
        # =============================
        self.r_total = InfoRow("TOTAL", "💳")
        self.r_paid = InfoRow("DIBAYAR", "💰")
        self.r_sisa = InfoRow("SISA", "❗")

        # ADD ALL
        for w in [
            self.r_plate,
            self.r_type,
            self.r_gate,
            self.r_checkin,
            self.r_dur,
            self.r_total,
            self.r_paid,
            self.r_sisa
        ]:
            cl.addWidget(w)

        # =============================
        # 🔹 HIGHLIGHT
        # =============================
        self.r_total.set_highlight("#f59e0b")  # orange
        self.r_sisa.set_highlight("#ef4444")  # red

        # =============================
        # 🔹 MEMBER
        # =============================
        self.member_banner = MemberBanner()
        cl.addWidget(self.member_banner)

        left_box.addWidget(self.card)

        # =========================================
        # 🟩 RIGHT: IMAGE (LEBIH BESAR)
        # =========================================
        right_box = QVBoxLayout()
        right_box.setSpacing(12)

        def make_image_group(title):
            grp = QGroupBox(title)
            grp.setStyleSheet("""
                QGroupBox {
                    font-weight:bold;
                    font-size:11px;
                    border:2px solid #e5e7eb;
                    border-radius:10px;
                    margin-top:8px;
                    font-family:'Segoe UI',monospace;
                    background:white;
                }
                QGroupBox::title {
                    subcontrol-origin:margin;
                    left:12px;
                    padding:0 6px;
                    color:#374151;
                }
            """)

            lay = QVBoxLayout(grp)
            lay.setContentsMargins(10, 12, 10, 10)

            viewer = ImageViewer()
            viewer.setMinimumHeight(220)  # 🔥 gambar lebih besar
            viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            lay.addWidget(viewer)

            return grp, viewer

        # ===== CHECK-IN =====
        grp_in, self.checkin_img = make_image_group("📷 CHECK-IN")

        # ===== CHECK-OUT =====
        grp_out, self.checkout_img = make_image_group("📷 CHECK-OUT")

        right_box.addWidget(grp_in)
        right_box.addWidget(grp_out)

        # =========================================
        # 🔥 COMBINE (PROPORSI FIX)
        # =========================================
        main_row.addLayout(left_box, 1)  # 🔥 kecil
        main_row.addLayout(right_box, 2)  # 🔥 besar

        # TAMBAHKAN KE ROOT
        root.addLayout(main_row)

        # ── MEMBER INPUT SECTION (muncul saat S_CHECKED) ──
        self.member_input_section = MemberInputSection()
        self.member_input_section.search_requested.connect(self._do_find_member)
        self.member_input_section.clear_requested.connect(self._do_clear_member)
        root.addWidget(self.member_input_section)

        # ── PEMBAYARAN ──
        lbl_pay = QLabel("💳 PEMBAYARAN")
        lbl_pay.setStyleSheet("""
            QLabel { color:#374151; font-size:13px; font-weight:bold;
                     font-family:'Segoe UI',monospace; padding:5px; }
        """)
        root.addWidget(lbl_pay)

        self.input_pay = mk_input("Jumlah bayar (Rp)", border="#16a34a40")
        self.input_pay.setFixedHeight(44)
        self.input_pay.setStyleSheet(self.input_pay.styleSheet() +
                                     "QLineEdit { font-size:15px; padding:10px 14px; }")
        self.input_pay.returnPressed.connect(self._do_payment)

        self.btn_pay = green_btn("BAYAR ✓")
        self.btn_pay.setFixedHeight(44)
        self.btn_pay.clicked.connect(self._do_payment)
        self._pay_widgets = [lbl_pay, self.input_pay, self.btn_pay]

        row_pay = QHBoxLayout()
        row_pay.setSpacing(15)
        row_pay.addWidget(self.input_pay, 1)
        row_pay.addWidget(self.btn_pay)
        root.addLayout(row_pay)

        # ── STATUS ──
        self.status = StatusBadge()
        self.status.setFixedHeight(28)
        root.addWidget(self.status)

        # ── KEMBALIAN ──
        self.change_label = QLabel("")
        self.change_label.setAlignment(Qt.AlignCenter)
        self.change_label.setFixedHeight(36)
        self.change_label.setStyleSheet("""
            QLabel { color:#16a34a; font-size:16px; font-weight:bold;
                     background:#dcfce7; border-radius:8px;
                     font-family:'Segoe UI',monospace; }
        """)
        self.change_label.setVisible(False)
        root.addWidget(self.change_label)

        root.addStretch()
        main_layout.addWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(main_container)
        self.setLayout(outer)

    def _apply_theme(self):
        self.setStyleSheet("QWidget { color:#1f2937; } QGroupBox { background:white; }")

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.title_bar.maximize_btn.setText("□")
            self.title_bar.is_maximized = False
        else:
            self.showFullScreen()
            self.title_bar.maximize_btn.setText("❐")
            self.title_bar.is_maximized = True

    def logout(self):
        print("[UI] Logout → kembali ke login")

        # =============================
        # 🔥 PAKAI CUSTOM DIALOG
        # =============================
        dialog = LogoutDialog(self)

        if dialog.exec_() != dialog.Accepted:
            return

        print("[UI] Logout confirmed")

        # =============================
        # 🔧 SIMPAN SERVICE
        # =============================
        barier = self.barier
        sound = self.sound
        api = self.api
        camera = self.camera
        minio = self.minio

        # =============================
        # 🔐 CLEAR SESSION
        # =============================
        api.token = None
        api.user_id = None

        # =============================
        # ❌ TUTUP WINDOW LAMA
        # =============================
        self.close()

        # =============================
        # 🔁 LOGIN ULANG
        # =============================
        login = LoginDialog(api=api)

        user_data = {}

        def on_login_success(data):
            nonlocal user_data
            user_data = data

        login.login_successful.connect(on_login_success)

        if login.exec_() == login.Accepted:
            api.token = user_data.get("token")
            api.user_id = user_data.get("user_id")

            # 🔥 WINDOW BARU
            new_window = self.__class__(
                barier=barier,
                sound=sound,
                api=api,
                camera=camera,
                minio=minio
            )

            new_window.user_data = user_data
            new_window.show()
        else:
            QApplication.quit()

    # ───────────────────────────────────────────────────────────
    #  STATE MACHINE
    # ───────────────────────────────────────────────────────────

    def _show_pay_form(self, visible: bool):
        for w in self._pay_widgets:
            w.setVisible(visible)
        self.input_pay.setEnabled(visible)
        self.btn_pay.setEnabled(visible)

    def _set_state(self, state: str):
        self._state = state

        self.btn_cek.setEnabled(True)
        self.btn_member.setEnabled(True)
        self.input_search.setEnabled(True)
        self.change_label.setVisible(False)

        if state == self.S_IDLE:
            self._clear_card()
            self.member_banner.clear()
            self.member_input_section.hide_section()
            self._show_pay_form(True)
            self.input_pay.setEnabled(False)
            self.btn_pay.setEnabled(False)
            self.r_total.setVisible(True)
            self.r_paid.setVisible(True)
            self.r_sisa.setVisible(True)
            self.status.set_state("idle")
            self.checkin_img.clear_image()
            self.checkout_img.clear_image()
            self.input_search.setFocus()

        elif state == self.S_LOADING:
            self._show_pay_form(False)
            self.member_input_section.hide_section()
            self.btn_cek.setEnabled(False)
            self.btn_member.setEnabled(False)
            self.input_search.setEnabled(False)
            self.status.set_state("loading")

        elif state == self.S_MEMBER:
            self._show_pay_form(False)
            self.member_input_section.hide_section()
            self.btn_cek.setEnabled(False)
            self.btn_member.setEnabled(False)
            self.input_search.setEnabled(False)
            self.r_total.setVisible(False)
            self.r_paid.setVisible(False)
            self.r_sisa.setVisible(False)
            self.status.set_state("member", "Akses gratis")

        elif state == self.S_CHECKED:
            self._show_pay_form(True)
            self.member_input_section.show_section()  # ← TAMPILKAN input member
            self.input_pay.setEnabled(True)
            self.btn_pay.setEnabled(True)
            self.btn_cek.setEnabled(False)
            self.btn_member.setEnabled(False)
            self.input_search.setEnabled(False)
            self.r_total.setVisible(True)
            self.r_paid.setVisible(True)
            self.r_sisa.setVisible(True)
            self.status.set_state("found", "Silakan bayar")
            QTimer.singleShot(50, self.input_pay.setFocus)

        elif state == self.S_OPENING:
            self._show_pay_form(False)
            self.member_input_section.hide_section()
            self.btn_cek.setEnabled(False)
            self.btn_member.setEnabled(False)
            self.input_search.setEnabled(False)
            self.status.set_state("open")
            QTimer.singleShot(4000, self._reset)

    # ───────────────────────────────────────────────────────────
    #  CARD HELPERS
    # ───────────────────────────────────────────────────────────

    def _clear_card(self):
        for r in [self.r_plate, self.r_type, self.r_gate,
                  self.r_checkin, self.r_dur,
                  self.r_total, self.r_paid, self.r_sisa]:
            r.set_value("-")

    def _populate_card(self, data: dict):
        self.r_plate.set_value(data.get("plate_number") or data.get("plateNumber", "-"))

        vt = data.get("vehicle_type")
        self.r_type.set_value(vt.get("name", "-") if isinstance(vt, dict) else (vt or "-"))

        gi = data.get("gate_in")
        self.r_gate.set_value(
            gi.get("code", "-") if isinstance(gi, dict) else (gi or data.get("gateCode", "-"))
        )

        self.r_checkin.set_value(
            fmt_datetime(data.get("check_in_at") or data.get("checkInAt", ""))
        )

        dur = data.get("duration_minutes")
        if dur is not None:
            h, m = divmod(int(dur), 60)
            self.r_dur.set_value(f"{h} jam {m} menit" if h else f"{m} menit")
        else:
            self.r_dur.set_value(data.get("duration", "-"))

        total = float(data.get("total", 0) or data.get("total_fare", 0) or 0)
        paid = float(data.get("paid", 0) or data.get("paid_amount", 0) or 0)
        remaining = float(data.get("remaining", 0) or max(0, total - paid))

        self.r_total.set_value(fmt_rupiah(total))
        self.r_paid.set_value(fmt_rupiah(paid))
        self.r_sisa.set_value(fmt_rupiah(remaining))

        # Gambar
        ci_url = data.get("check_in_image_url") or data.get("check_in_image")
        co_url = data.get("check_out_image_url") or data.get("check_out_image")
        print(f"[DEBUG] Check-in URL: {ci_url}")
        print(f"[DEBUG] Check-out URL: {co_url}")

        if ci_url:
            self.checkin_img.load_url(ci_url)
        else:
            self.checkin_img.clear_image()

        if co_url:
            self.checkout_img.load_url(co_url)

        # ── Tampilkan banner member jika data mengandung info member ──
        member = data.get("member")
        if member:
            self.member_banner.populate(member)
        else:
            self.member_banner.clear()

    def _populate_member(self, member: dict):
        """Dipanggil secara eksplisit; delegate ke MemberBanner."""
        self.member_banner.populate(member)

    # ───────────────────────────────────────────────────────────
    #  THREAD MANAGEMENT
    # ───────────────────────────────────────────────────────────

    def _run_api(self, fn, *args, on_result):
        t = APIThread(fn, *args)
        t.result.connect(on_result)
        self._threads.append(t)
        t.finished.connect(self._gc_threads)
        t.start()
        return t

    def _gc_threads(self):
        self._threads = [t for t in self._threads if t.isRunning()]

    def _run_capture_thread(self, parking_id: str, ticket_number: str, plate_number: str):
        if not self.camera or not self.minio:
            print("[WARNING] Camera atau Minio service tidak tersedia")
            return
        t = CheckoutImageCaptureThread(
            self.camera, self.minio, self.api, parking_id, ticket_number, plate_number
        )
        t.image_captured.connect(self._on_checkout_image_captured)
        t.capture_failed.connect(self._on_checkout_image_failed)
        self._capture_threads.append(t)
        t.finished.connect(self._gc_capture_threads)
        t.start()

    def _gc_capture_threads(self):
        self._capture_threads = [t for t in self._capture_threads if t.isRunning()]

    def _on_checkout_image_captured(self, image_url: str):
        print(f"[UI] Checkout image captured and uploaded: {image_url}")
        if hasattr(self, 'checkout_img'):
            self.checkout_img.load_url(image_url)
        self._checkout_image_url = image_url

    def _on_checkout_image_failed(self, error_msg: str):
        print(f"[UI] Checkout image capture failed: {error_msg}")
        self.status.set_state("error", f"Capture gagal: {error_msg}")

    # ───────────────────────────────────────────────────────────
    #  ACTIONS
    # ───────────────────────────────────────────────────────────

    def _do_search(self):
        raw = self.input_search.text().strip()
        if not raw:
            return
        if _is_plate(extract_id(raw)):
            self._do_member_checkout()
        else:
            self._do_get_data()

    def _do_get_data(self):
        raw = self.input_search.text().strip()
        if not raw:
            return
        extracted = extract_id(raw)
        print(f"[UI] '{raw}' → '{extracted}'")
        self._set_state(self.S_LOADING)

        if "-" in extracted and len(extracted) > 20:
            self._run_api(self.api.get_parking_by_id, extracted, on_result=self._on_uuid_result)
        else:
            self._run_api(self.api.manual_checkout, extracted, on_result=self._on_data_result)

    def _on_uuid_result(self, result: dict):
        print("[DEBUG uuid_result]", result)
        data = _unwrap(result)
        self.parking_id = data.get("id")

        if not data:
            self._set_state(self.S_IDLE)
            self.status.set_state("error", "Data tidak ditemukan")
            return

        total_fare = float(data.get("total_fare", 0) or data.get("total", 0) or 0)
        paid_amount = float(data.get("paid_amount", 0) or data.get("paid", 0) or 0)
        pay_status = data.get("payment_status", "")
        check_out_at = data.get("check_out_at")

        if check_out_at is not None:
            self._set_state(self.S_IDLE)
            self.status.set_state("error", "Tiket sudah digunakan")
            return

        if data.get("success"):
            self._populate_card(data)
            ticket_number = data.get("ticket_number")
            plate = data.get("plate_number") or data.get("plateNumber")
            self._run_capture_thread(self.parking_id, ticket_number, plate)
            self.status.set_state("online", "Pembayaran online terverifikasi")
            self._open_gate()
            return

        already_paid = pay_status == "paid" or (total_fare > 0 and paid_amount >= total_fare)
        if already_paid:
            queue = data.get("queue_number")
            if queue:
                self._populate_card(data)
                self.status.set_state("online", "Lunas → membuka gate...")
                self._run_api(
                    self.api.manual_checkout, queue, 0,
                    on_result=self._on_paid_online_result,
                )
                ticket_number = data.get("ticket_number")
                plate = data.get("plate_number") or data.get("plateNumber")
                self._run_capture_thread(self.parking_id, ticket_number, plate)
                return
            else:
                self._populate_card(data)
                ticket_number = data.get("ticket_number")
                plate = data.get("plate_number") or data.get("plateNumber")
                self.status.set_state("online", "Lunas → membuka gate...")
                self._run_capture_thread(self.parking_id, ticket_number, plate)
                self._open_gate()
                return

        queue = data.get("queue_number")
        ticket_number = data.get("ticket_number")
        parking_id = data.get("id")
        if queue:
            self._queue_number = queue
            self._populate_card(data)
            self.parking_id = data.get("parking_id")
            plate = data.get("plate_number") or data.get("plateNumber")
            self._run_capture_thread(parking_id, ticket_number, plate)
            self._set_state(self.S_CHECKED)
        else:
            self._set_state(self.S_IDLE)
            self.status.set_state("error", "Queue tidak ditemukan")

    def _on_paid_online_result(self, result: dict):
        print("[DEBUG paid_online]", result)
        data = _unwrap(result)
        if data.get("success") or data.get("is_free"):
            self.status.set_state("online", "Gate terbuka")
            self._open_gate()
        else:
            msg = data.get("message", "")
            print(f"[UI] manual_payment(0) response: {msg} → buka gate lokal")
            self.status.set_state("open")
            self._open_gate()

    def _do_member_checkout(self):
        plate = self.input_search.text().strip()
        if not plate:
            self.status.set_state("error", "Masukkan plat nomor!")
            return
        self._set_state(self.S_LOADING)
        self._current_plate = plate
        self._run_api(self.api.member_checkout, plate, on_result=self._on_member_checkout_result)

    def _on_member_checkout_result(self, result: dict):
        print("[DEBUG member checkout]", result)
        data = _unwrap(result)

        if not data or data.get("found") is False:
            self._set_state(self.S_IDLE)
            self.status.set_state("error", data.get("message", "Member tidak ditemukan"))
            return

        self._queue_number = data.get("queue_number")
        self._current_ticket = self._queue_number
        self._current_plate = data.get("plate_number") or data.get("plateNumber")

        self._populate_card(data)  # ← akan auto-populate member_banner

        self._run_capture_thread(self._queue_number, self._current_ticket, self._current_plate)

        # Jika member tidak ada di data, populate manual
        if data.get("member") and not self.member_banner.isVisible():
            self._populate_member(data.get("member"))

        self._set_state(self.S_MEMBER)
        QTimer.singleShot(500, self._open_gate)

    def _on_data_result(self, result: dict):
        print("[DEBUG data_result RAW]", result)
        data = _unwrap(result)
        print("[DEBUG data_result UNWRAPPED]", data)
        self.parking_id = data.get("id")

        if not data:
            self._set_state(self.S_IDLE)
            self.status.set_state("error", "Data kosong")
            return

        if data.get("found") is False:
            self._set_state(self.S_IDLE)
            self.status.set_state("error", data.get("message", "Tiket tidak ditemukan"))
            return

        if data.get("message") == "Tiket sudah digunakan":
            self._set_state(self.S_IDLE)
            self.status.set_state("error", "Tiket sudah digunakan")
            return

        self._current_ticket = self._queue_number
        self._current_plate = data.get("plate_number") or data.get("plateNumber")

        self._populate_card(data)

        co_url = data.get("check_out_image_url") or data.get("check_out_image")
        if not co_url:
            print("[UI] Capture checkout image NOW (on scan)")
            self._run_capture_thread(self.parking_id, self._current_ticket, self._current_plate)
        else:
            print("[UI] Checkout image already exists: " + co_url)
            self.checkout_img.load_url(co_url)

        member = data.get("member")
        if self._is_member and member:
            self._set_state(self.S_MEMBER)
            if self._is_free or data.get("success"):
                QTimer.singleShot(500, self._open_gate)
        else:
            self._set_state(self.S_CHECKED)

    # ── UPDATE PLAT + CARI MEMBER ───────────────────────────────

    def _do_find_member(self, plate: str):
        """
        Alur 2 step:
          Step 1 → api.update(parking_id, plate_number=plate)
                   update plat ke tiket yang sudah di-scan
          Step 2 → api.member_checkout(plate)
                   cari member berdasarkan plat yang baru diupdate
        """
        if not getattr(self, "parking_id", None):
            self.member_input_section.set_not_found("ID tiket tidak ditemukan, scan ulang")
            return

        plate = plate.upper().strip()
        print(f"[PLATE+MEMBER] Step-1 update plat='{plate}' parking_id={self.parking_id}")
        self.member_input_section.set_loading()

        # Simpan plate sementara agar bisa dipakai di step-2
        self._pending_plate = plate

        # Step 1: update plate_number ke tiket
        # api.update(parking_id, plate, check_in_image, check_out_image, user_id)
        self._run_api(
            self.api.update,
            self.parking_id,  # parking_id
            plate,  # plate  ← posisi kedua sesuai signature
            on_result=self._on_plate_updated,
        )

    def _on_plate_updated(self, result: dict):
        """Callback Step-1: update plat selesai."""
        print(f"[PLATE] Step-1 result: {result}")
        data = _unwrap(result)

        # Anggap sukses jika HTTP 200 (success=True) ATAU data tidak kosong
        ok = (
                result.get("success") is True
                or (isinstance(data, dict) and data.get("plate_number"))
                or (isinstance(data, dict) and not data.get("error"))
        )

        if not ok:
            msg = data.get("message") or result.get("message", "Gagal update plat ke tiket")
            print(f"[PLATE] Gagal: {msg}")
            self.member_input_section.set_not_found(f"Gagal update plat: {msg}")
            return

        # Update card plat langsung dari input (API mungkin tidak return plate)
        plate = getattr(self, "_pending_plate", "") or data.get("plate_number", "")
        if plate:
            self.r_plate.set_value(plate)
            self._current_plate = plate
            print(f"[PLATE] Card diupdate → {plate}")

        # Step 2: cari member berdasarkan plat
        print(f"[PLATE+MEMBER] Step-2 cari member by plate='{plate}'")
        self._run_api(
            self.api.member_checkout,
            plate,
            on_result=self._on_find_member_result,
        )

    def _on_find_member_result(self, result: dict):
        """Callback Step-2: hasil pencarian member by plate."""
        print(f"[MEMBER] Step-2 result: {result}")
        data = _unwrap(result)

        plate = getattr(self, "_pending_plate", self._current_plate or "")

        # member_checkout mengembalikan found=False jika tidak ada member
        if not data or data.get("found") is False:
            msg = data.get("message", "Tidak ada member terdaftar untuk plat ini")
            print(f"[MEMBER] Tidak ditemukan: {msg}")
            self.member_input_section.set_not_found(
                f"Plat {plate} diperbarui · Bukan member"
            )
            self.member_banner.clear()
            self.status.set_state("found", f"Plat → {plate} · Bukan member")
            return

        # Member ditemukan
        member = data.get("member") or data  # member_checkout kadang return flat dict
        name = member.get("name", "-") if isinstance(member, dict) else "-"

        self.member_input_section.set_found(name)
        self.member_banner.populate(member if isinstance(member, dict) else data)
        self.status.set_state("found", f"Plat {plate} · Member: {name}")
        print(f"[MEMBER] Ditemukan: {name}")

    def _do_clear_member(self):
        """
        Hapus keterkaitan member dari tiket ini (panggil API unlink member).
        """
        if not getattr(self, "parking_id", None):
            return

        print(f"[MEMBER CLEAR] parking_id={self.parking_id}")
        self.member_input_section.set_loading()

        self._run_api(
            self.api.clear_member,  # ← sesuaikan nama method API Anda
            self.parking_id,
            on_result=self._on_clear_member_result,
        )

    def _on_clear_member_result(self, result: dict):
        print("[DEBUG clear_member]", result)
        data = _unwrap(result)

        if data.get("success") or data.get("message", "").lower().find("berhasil") >= 0:
            self.member_banner.clear()
            self.member_input_section.reset()
            self.status.set_state("found", "Member dilepas dari tiket")
            print("[MEMBER CLEAR] Member berhasil dilepas")
        else:
            # Tetap tampilkan tombol clear, informasikan error
            msg = data.get("message", "Gagal melepas member")
            self.member_input_section.set_not_found(msg)
            print(f"[MEMBER CLEAR] Gagal: {msg}")

    def _do_payment(self):
        if self._state != self.S_CHECKED:
            return
        if not self._queue_number:
            self.status.set_state("error", "Scan tiket dulu")
            return

        amount_str = (
            self.input_pay.text().strip()
            .replace("Rp", "").replace(" ", "")
            .replace(",", "").replace(".", "")
        )
        if not amount_str:
            self.status.set_state("error", "Masukkan jumlah bayar")
            return

        try:
            amount = float(amount_str)
        except ValueError:
            self.status.set_state("error", "Jumlah tidak valid")
            return

        if amount <= 0:
            self.status.set_state("error", "Jumlah harus > 0")
            return

        self.status.set_state("loading")
        self.btn_pay.setEnabled(False)
        self.input_pay.setEnabled(False)
        self.btn_cek.setEnabled(False)

        self._run_api(
            self.api.manual_checkout, self._queue_number, amount,
            on_result=self._on_payment_result,
        )

    def _on_payment_result(self, result: dict):
        print("[DEBUG payment RAW]", result)
        data = _unwrap(result)
        print("[DEBUG payment UNWRAPPED]", data)

        try:
            self.r_paid.set_value(fmt_rupiah(data.get("paid", 0)))
            self.r_sisa.set_value(fmt_rupiah(data.get("remaining", 0)))
        except Exception:
            pass

        if data.get("success"):
            change = float(data.get("change", 0) or 0)
            if change > 0:
                self.change_label.setText(f"↩  KEMBALIAN  {fmt_rupiah(change)}")
                self.change_label.setVisible(True)
                self._animate_change()
                QTimer.singleShot(5000, lambda: self.change_label.setVisible(False))

            self.status.set_state("success", f"Kembalian {fmt_rupiah(change)}" if change else "")
            self._open_gate()
        else:
            remaining = float(data.get("remaining", 0) or 0)
            msg = data.get("message", "Kurang bayar")
            self.status.set_state("error", f"{msg}  |  Sisa {fmt_rupiah(remaining)}")
            self.btn_pay.setEnabled(True)
            self.input_pay.setEnabled(True)
            self.input_pay.clear()
            self.input_pay.setFocus()

    def _animate_change(self):
        try:
            self.change_label.adjustSize()
            geo = self.change_label.geometry()
            start = geo.translated(0, 20)
            self._anim = QPropertyAnimation(self.change_label, b"geometry")
            self._anim.setDuration(400)
            self._anim.setStartValue(start)
            self._anim.setEndValue(geo)
            self._anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.start()
        except Exception:
            pass

    # ───────────────────────────────────────────────────────────
    #  GATE
    # ───────────────────────────────────────────────────────────

    def _open_gate(self):
        self._set_state(self.S_OPENING)
        print("[GATE] → Membuka palang...")
        self.barier.open()

    # ───────────────────────────────────────────────────────────
    #  RESET
    # ───────────────────────────────────────────────────────────

    def _reset(self):
        self._gc_threads()
        self._gc_capture_threads()
        self._queue_number = None
        self._is_member = False
        self._is_free = False
        self._checkout_image_url = None
        self.input_search.clear()
        self.input_pay.clear()
        self.checkin_img.clear_image()
        self.checkout_img.clear_image()
        self.member_banner.clear()
        self.member_input_section.hide_section()  # ← bersihkan input member
        self._set_state(self.S_IDLE)

    def _start_scanner(self):
        self._scanner = ScannerThread()
        self._scanner.scanned.connect(self._on_hardware_scan)
        self._scanner.start()

    def _on_hardware_scan(self, raw: str):
        if self._state == self.S_MEMBER:
            if self._current_ticket or self._current_plate:
                self._run_capture_thread(
                    self.parking_id, self._current_ticket, self._current_plate
                )
            self._open_gate()
        elif self._state == self.S_IDLE:
            self.input_search.setText(raw)
            self._do_search()
        else:
            print(f"[SCAN HW] State '{self._state}', diabaikan.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    p = QPalette()
    p.setColor(QPalette.Window, QColor("#f9fafb"))
    p.setColor(QPalette.WindowText, QColor("#1f2937"))
    p.setColor(QPalette.Base, QColor("#ffffff"))
    p.setColor(QPalette.AlternateBase, QColor("#f9fafb"))
    p.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    p.setColor(QPalette.ToolTipText, QColor("#1f2937"))
    p.setColor(QPalette.Text, QColor("#1f2937"))
    p.setColor(QPalette.Button, QColor("#f3f4f6"))
    p.setColor(QPalette.ButtonText, QColor("#1f2937"))
    p.setColor(QPalette.Highlight, QColor("#3b82f6"))
    p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(p)

    window = ParkingUI()
    window.show()
    sys.exit(app.exec_())
