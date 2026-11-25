import os
import sys
import keyboard
import ctypes
from PyQt6.QtCore import QUrl, Qt, QObject, pyqtSignal, QRect, QTimer, QRectF
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QColor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage

from layout_config import load_layout, ICONS_DIR

# ===== НАСТРОЙКИ =====
GOOGLE_FILE = "google.png"
BASE_ICON_SIZE = 76
ICON_RADIUS = 17
ICON_PADDING = 14
LABEL_WIDTH = 150
LABEL_HEIGHT = 24
LABEL_GAP = 8

HOTKEY = "down"        # планшет
RESET_KEY = "right"    # аварийный сброс

SHOW_DELAY_MS = 425
HIDE_DELAY_MS = 0

GAME_TITLE_PART = "Majestic Multiplayer"
# ===============================

PROFILE_DIR = os.path.join(
    os.path.expanduser("~"), "Documents", "tablet_browser_profile"
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
    handle = kernel32.CreateMutexW(None, False, "Local\\TapTabletMutex")
    # 183 = ERROR_ALREADY_EXISTS
    return kernel32.GetLastError() == 183


def get_profile():
    global profile
    if profile is None:
        os.makedirs(PROFILE_DIR, exist_ok=True)
        profile = QWebEngineProfile("tablet")
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


def game_window_exists():
    found = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
    )

    def callback(hwnd, lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if GAME_TITLE_PART.lower() in buf.value.lower():
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return bool(found)


class Signals(QObject):
    toggle = pyqtSignal()
    reset = pyqtSignal()


class Icon(QWidget):
    """Скруглённая иконка с подписью"""

    def __init__(self, on_click, x, y, size, file_name, label,
                 fallback_text, fallback_color, bg="white", padding=None):
        super().__init__()
        self.on_click = on_click
        self.size_px = size
        self.file_name = file_name
        self.fallback_text = fallback_text
        self.fallback_color = fallback_color
        self.bg = bg
        if padding is None:
            padding = ICON_PADDING * size / BASE_ICON_SIZE
        self.padding = int(padding)

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
        self.text.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.text.setStyleSheet(
            "color: white; font-size: 13px; font-family: 'Segoe UI';"
            "background: transparent;"
        )
        self.text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def make_avatar(self):
        size = self.size_px
        radius = size * ICON_RADIUS / BASE_ICON_SIZE
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
            painter.drawText(result.rect(), Qt.AlignmentFlag.AlignCenter,
                             self.fallback_text)

        painter.end()
        return result

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_click()


class Browser(QWidget):
    """Браузер планшета. Создаётся при открытии, удаляется при закрытии"""

    def __init__(self, rect, start_url):
        super().__init__()
        self.setWindowFlags(BROWSER_FLAGS)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setGeometry(rect)
        self.setStyleSheet("background: #1c1c1e; color: white;")

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
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addLayout(bar)
        layout.addWidget(self.view)

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
        tx, ty, tw, th = layout["tablet"]
        self.tablet_rect = QRect(tx, ty, tw, th)
        gx, gy, gsize = layout["tablet_icon"]

        self.icon = Icon(
            self.open_tablet_browser, gx, gy, gsize,
            GOOGLE_FILE, "Google", "G", "#4285F4",
        )
        self.browser = None
        self.icon_visible = False

        self.show_timer = QTimer()
        self.show_timer.setSingleShot(True)
        self.show_timer.timeout.connect(self.show_icon)

        self.watch_timer = QTimer()
        self.watch_timer.timeout.connect(self.watch_game)
        self.watch_timer.start(500)

    def browser_is_active(self):
        return self.browser is not None and self.browser.isActiveWindow()

    def watch_game(self):
        if self.icon_visible and not game_window_exists():
            self.reset()

    def show_icon(self):
        self.icon.show()
        self.icon_visible = True

    def toggle(self):
        # Включить можно только из игры или из нашего браузера.
        # Выключить уже показанное можно из любого места.
        active = self.icon_visible or self.browser is not None
        if not active and not game_is_active():
            return

        if self.show_timer.isActive():
            # иконка ещё не успела появиться: отменяем показ
            self.show_timer.stop()
        elif active:
            # скрываем всё сразу: иконку и браузер вместе
            self.reset()
        else:
            self.show_timer.start(SHOW_DELAY_MS)

    def open_tablet_browser(self):
        self.close_browser()
        self.browser = Browser(self.tablet_rect, "https://www.google.com")
        self.browser.destroyed.connect(self.on_browser_closed)
        self.browser.show()

    def close_browser(self):
        if self.browser is not None:
            browser = self.browser
            self.browser = None
            browser.close()

    def on_browser_closed(self):
        self.browser = None

    def reset(self):
        self.show_timer.stop()
        self.icon.hide()
        self.close_browser()
        self.icon_visible = False


def run():
    # Второй экземпляр планшета не запускаем: именно он давал дубль Google
    if already_running():
        sys.exit(0)

    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)

    app = App(load_layout())
    signals = Signals()
    signals.toggle.connect(app.toggle)
    signals.reset.connect(app.reset)

    held = set()

    def on_key(event):
        if event.event_type == keyboard.KEY_UP:
            held.discard(event.name)
            return
        # Защита от автоповтора
        if event.name in held:
            return
        held.add(event.name)

        if event.name == HOTKEY:
            signals.toggle.emit()
        elif event.name == RESET_KEY:
            signals.reset.emit()

    keyboard.hook(on_key, suppress=False)
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    run()