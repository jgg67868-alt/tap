import os
import sys
import keyboard
import mouse
import ctypes
from PyQt6.QtCore import QUrl, Qt, QObject, pyqtSignal, QRect, QTimer, QRectF
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QRegion
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage

from layout_config import load_layout, ICONS_DIR

# ===== НАСТРОЙКИ (меняй тут) =====
# Подгонка окна Телеграма под экран телефона (в пикселях)
# Сдвиг влево (минус) или вправо (плюс)
WINDOW_SHIFT_X = -9
# Растянуть окно вверх и вниз
WINDOW_GROW_TOP = 0
WINDOW_GROW_BOTTOM = 12

TELEGRAM_FILE = "telegram.png"

# Скругление углов окна Телеграма (под форму телефона)
WINDOW_RADIUS = 40

# Подпись и скругление иконки
ICON_RADIUS = 17
ICON_PADDING = 10
LABEL_WIDTH = 150
LABEL_HEIGHT = 24
LABEL_GAP = 8

# Клавиши
PHONE_HOTKEY = "up"   # телефон
RESET_KEY = "right"   # аварийный сброс

# Задержка после клика по экрану блокировки, миллисекунды
PHONE_ICON_DELAY_MS = 300

GAME_TITLE_PART = "Majestic Multiplayer"
TELEGRAM_URL = "https://web.telegram.org/a/"
# ===============================

PROFILE_DIR = os.path.join(
    os.path.expanduser("~"), "Documents", "telegram_browser_profile"
)

BROWSER_FLAGS = (
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

OVERLAY_FLAGS = (
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Tool
)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

profile = None


def already_running():
    """Защита от двойного запуска: именованный мьютекс Windows."""
    handle = kernel32.CreateMutexW(None, False, "Local\\TapPhoneMutex")
    # 183 = ERROR_ALREADY_EXISTS
    return kernel32.GetLastError() == 183


def get_profile():
    global profile
    if profile is None:
        os.makedirs(PROFILE_DIR, exist_ok=True)
        profile = QWebEngineProfile("telegram")
        profile.setHttpUserAgent(USER_AGENT)
        profile.setPersistentStoragePath(PROFILE_DIR)
        profile.setCachePath(os.path.join(PROFILE_DIR, "cache"))
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
    return profile


def get_active_window_title():
    hwnd = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def game_is_active():
    return GAME_TITLE_PART.lower() in get_active_window_title().lower()


class Signals(QObject):
    phone_toggle = pyqtSignal()
    phone_click = pyqtSignal()
    reset = pyqtSignal()


class Icon(QWidget):
    """Скруглённая иконка с подписью"""

    def __init__(self, on_click, x, y, size, file_name, label,
                 fallback_text, fallback_color, bg="white",
                 padding=ICON_PADDING):
        super().__init__()
        self.on_click = on_click
        self.size_px = size
        self.file_name = file_name
        self.fallback_text = fallback_text
        self.fallback_color = fallback_color
        self.bg = bg
        self.padding = padding

        self.setWindowFlags(OVERLAY_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        width = max(LABEL_WIDTH, size)
        self.setGeometry(
            x + size // 2 - width // 2, y,
            width, size + LABEL_GAP + LABEL_HEIGHT,
        )

        self.pic = QLabel(self)
        self.pic.setGeometry((width - size) // 2, 0, size, size)
        self.pic.setPixmap(self.make_avatar())
        self.pic.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.text = QLabel(label, self)
        self.text.setGeometry(0, size + LABEL_GAP, width, LABEL_HEIGHT)
        self.text.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
        self.text.setStyleSheet(
            "color: white; font-size: 13px; font-family: 'Segoe UI';"
            "background: transparent;"
        )
        self.text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def make_avatar(self):
        size = self.size_px
        radius = size * ICON_RADIUS / 76
        result = QPixmap(size, size)
        result.fill(Qt.GlobalColor.transparent)

        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        shape = QPainterPath()
        shape.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
        painter.setClipPath(shape)
        painter.fillRect(result.rect(), QColor(self.bg))

        path = os.path.join(ICONS_DIR, self.file_name)
        if os.path.exists(path):
            inner = size - self.padding * 2
            logo = QPixmap(path).scaled(
                inner, inner,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(
                (size - logo.width()) // 2,
                (size - logo.height()) // 2,
                logo,
            )
        else:
            print("Не найден файл иконки:", path)
            painter.setPen(QColor(self.fallback_color))
            font = painter.font()
            font.setPixelSize(int(size * 0.58))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                result.rect(), Qt.AlignmentFlag.AlignCenter,
                self.fallback_text,
            )
        painter.end()
        return result

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_click()


class Browser(QWidget):
    """Браузер телефона. Создаётся при открытии, удаляется при закрытии"""

    def __init__(self, rect, start_url):
        super().__init__()
        self.setWindowFlags(BROWSER_FLAGS)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setGeometry(rect)
        self.setStyleSheet("background: #1c1c1e; color: white;")

        # Обрезаем окно по скруглённой форме телефона
        self.apply_round_mask()

        self.view = QWebEngineView()
        self.page = QWebEnginePage(get_profile(), self.view)
        self.view.setPage(self.page)
        self.view.setUrl(QUrl(start_url))

        self.address = QLineEdit()
        self.address.returnPressed.connect(self.go)
        self.view.urlChanged.connect(
            lambda u: self.address.setText(u.toString())
        )

        back = QPushButton("<")
        back.clicked.connect(self.view.back)
        forward = QPushButton(">")
        forward.clicked.connect(self.view.forward)
        close = QPushButton("✕")
        close.clicked.connect(self.close)

        bar = QHBoxLayout()
        bar.addWidget(back)
        bar.addWidget(forward)
        bar.addWidget(self.address)
        bar.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(bar)
        layout.addWidget(self.view)

    def apply_round_mask(self):
        # Маска со скруглёнными углами: всё, что за её пределами, не рисуется
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(0, 0, self.width(), self.height()),
            WINDOW_RADIUS, WINDOW_RADIUS,
        )
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event):
        # Если размер окна поменялся, маску пересчитываем
        super().resizeEvent(event)
        self.apply_round_mask()

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        self.force_focus()
        self.view.setFocus()

    def force_focus(self):
        try:
            user32.SetForegroundWindow(int(self.winId()))
        except Exception:
            pass

    def mousePressEvent(self, event):
        self.force_focus()
        super().mousePressEvent(event)

    def go(self):
        text = self.address.text().strip()
        if not text.startswith("http"):
            text = "https://" + text
        self.view.setUrl(QUrl(text))


class App:
    def __init__(self, layout):
        px, py, pw, ph = layout["phone"]
        self.phone_rect = QRect(
            px + WINDOW_SHIFT_X,
            py - WINDOW_GROW_TOP,
            pw,
            ph + WINDOW_GROW_TOP + WINDOW_GROW_BOTTOM,
        )
        ix, iy, isize = layout["phone_icon"]

        self.phone_icon = Icon(
            self.open_phone_browser,
            ix, iy, isize,
            TELEGRAM_FILE, "Telegram", "T", "white",
            bg="#21A1E4", padding=ICON_PADDING,
        )
        self.phone_browser = None
        self.phone_visible = False   # иконка Телеграма показана
        self.phone_waiting = False   # ждём клик по экрану блокировки

        self.phone_timer = QTimer()
        self.phone_timer.setSingleShot(True)
        self.phone_timer.timeout.connect(self.show_phone_icon)

    def browser_is_open(self):
        return self.phone_browser is not None

    def anything_visible(self):
        return self.phone_visible or self.phone_waiting or self.browser_is_open()

    def phone_toggle(self):
        # Стрелка вверх: открыть или закрыть телефон.
        # Закрыть можно из любого окна, а открыть только из игры.
        if not self.anything_visible() and not game_is_active():
            return
        if self.anything_visible() or self.phone_timer.isActive():
            self.reset()
        else:
            self.phone_waiting = True

    def phone_click(self):
        # Нас интересует только клик, пока ждём разблокировку
        if not self.phone_waiting:
            return
        self.phone_waiting = False
        self.phone_timer.start(PHONE_ICON_DELAY_MS)

    def show_phone_icon(self):
        self.phone_icon.show()
        self.phone_visible = True

    def open_phone_browser(self):
        self.close_browser()
        self.phone_icon.hide()
        self.phone_visible = False

        self.phone_browser = Browser(self.phone_rect, TELEGRAM_URL)
        self.phone_browser.destroyed.connect(self.on_browser_closed)
        self.phone_browser.show()

    def close_browser(self):
        if self.phone_browser is not None:
            browser = self.phone_browser
            self.phone_browser = None
            browser.close()

    def on_browser_closed(self):
        self.phone_browser = None

    def reset(self):
        self.phone_timer.stop()
        self.phone_icon.hide()
        self.close_browser()
        self.phone_visible = False
        self.phone_waiting = False


def run():
    # Второй экземпляр телефона не запускаем
    if already_running():
        sys.exit(0)

    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)

    app = App(load_layout())
    signals = Signals()
    signals.phone_toggle.connect(app.phone_toggle)
    signals.phone_click.connect(app.phone_click)
    signals.reset.connect(app.reset)

    held = set()

    # Ловим само нажатие клавиши, чтобы работало, даже когда зажаты W, A, S, D
    def on_key(event):
        if event.event_type == keyboard.KEY_UP:
            held.discard(event.name)
            return
        # Защита от автоповтора
        if event.name in held:
            return
        held.add(event.name)

        if event.name == PHONE_HOTKEY:
            signals.phone_toggle.emit()
        elif event.name == RESET_KEY:
            signals.reset.emit()

    keyboard.hook(on_key, suppress=False)

    # Ловим левый клик мыши, чтобы понять, что экран блокировки разблокирован
    mouse.on_click(signals.phone_click.emit)

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    run()