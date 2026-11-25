import os
import sys
import subprocess
from PyQt6.QtCore import Qt, QRect, QPoint, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QIcon, QPixmap, QAction, QRegion
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCheckBox, QSystemTrayIcon, QMenu,
    QSpinBox, QComboBox, QFrame,
)

from layout_config import load_layout, save_layout, BASE_DIR, ICONS_DIR, FROZEN

# Режим запуска: без аргумента — окно настроек, "tablet" или "phone" — отдельный скрипт
MODE = sys.argv[1] if len(sys.argv) > 1 else "panel"

# ===== НАСТРОЙКИ =====
APP_NAME = "Tap"
TABLET_SCRIPT = "browser.py"
PHONE_SCRIPT = "telegram_browser.py"
TRAY_ICON_FILE = "telegram.png"  # картинка для иконки в трее и в окне
APP_ICON_FILE = "tap.png"       # аватарка приложения, лежит в папке icons
GRIP = 14        # толщина ловимой крайней полосы
HANDLE_H = 26    # высота ручки для перетаскивания рамки
ICON_GRIP = 16   # размер уголка для изменения размера иконки
ICON_MIN = 20    # минимальный размер иконки
ICON_MAX = 200   # максимальный размер иконки
# ===============================

# Чёрно-белая палитра
WHITE = QColor(245, 245, 245)
GRAY = QColor(150, 150, 150)
LIGHT_GRAY = QColor(210, 210, 210)

COLORS = {"phone": GRAY, "tablet": WHITE}
FRAME_NAMES = {"phone": "Телефон", "tablet": "Планшет"}

STYLE = """
QWidget#root {
    background: #0a0a0a;
}
QLabel {
    color: #e6e6e6;
    font-family: 'Segoe UI';
    font-size: 13px;
    background: transparent;
}
QLabel#title {
    color: #ffffff;
    font-size: 30px;
    font-weight: 800;
    letter-spacing: 3px;
}
QLabel#subtitle {
    color: #8a8a8a;
    font-size: 12px;
    letter-spacing: 4px;
}
QLabel#section {
    color: #ffffff;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 2px;
}
QLabel#hint {
    color: #8a8a8a;
    font-size: 12px;
}
QLabel#status {
    color: #bdbdbd;
    font-size: 12px;
}
QFrame#card {
    background: #141414;
    border: 1px solid #2e2e2e;
    border-radius: 12px;
}
QFrame#line {
    background: #ffffff;
    max-height: 2px;
    min-height: 2px;
    border: none;
}
QCheckBox {
    color: #ffffff;
    font-family: 'Segoe UI';
    font-size: 14px;
    font-weight: 600;
    spacing: 10px;
    background: transparent;
}
QCheckBox::indicator {
    width: 22px;
    height: 22px;
    border-radius: 6px;
    border: 2px solid #8a8a8a;
    background: #0a0a0a;
}
QCheckBox::indicator:checked {
    background: #ffffff;
    border: 2px solid #ffffff;
}
QComboBox, QSpinBox {
    background: #1c1c1c;
    color: #ffffff;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 4px 6px;
    font-family: 'Segoe UI';
    font-size: 13px;
}
QComboBox:hover, QSpinBox:hover {
    border: 1px solid #ffffff;
}
QComboBox QAbstractItemView {
    background: #1c1c1c;
    color: #ffffff;
    selection-background-color: #ffffff;
    selection-color: #0a0a0a;
    border: 1px solid #3a3a3a;
}
QPushButton {
    background: #1c1c1c;
    color: #ffffff;
    border: 1px solid #4a4a4a;
    border-radius: 10px;
    padding: 9px 14px;
    font-family: 'Segoe UI';
    font-size: 13px;
    font-weight: 700;
}
QPushButton:hover {
    border: 1px solid #ffffff;
}
QPushButton:checked {
    background: #ffffff;
    color: #0a0a0a;
    border: 1px solid #ffffff;
}
QPushButton#save {
    background: #ffffff;
    color: #0a0a0a;
    border: 1px solid #ffffff;
    font-size: 14px;
    letter-spacing: 2px;
}
QPushButton#save:hover {
    background: #d9d9d9;
    border: 1px solid #d9d9d9;
}
"""


class Overlay(QWidget):
    """Прозрачный слой поверх игры с рамкой окна и иконкой.

    Важно: маска окна включает только края рамки, ручку, иконку и её уголок.
    Всё остальное, включая середину рамки, пропускает мышь в игру.
    """

    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.fit_to_screen()

        self.mode = None
        self.start_pos = QPoint()
        self.start_data = None
        self.update_mask()

    def fit_to_screen(self):
        # Подгоняем слой под текущий размер экрана
        self.setGeometry(QApplication.primaryScreen().geometry())

    # текущие данные находятся в окне настроек
    def data(self):
        return self.panel.layout_data

    def frame_rect(self):
        x, y, w, h = self.data()[self.panel.device()]
        return QRect(x, y, w, h)

    def icon_rect(self):
        x, y, size = self.data()[self.panel.device() + "_icon"]
        return QRect(x, y, size, size)

    def icon_grip_rect(self):
        # Уголок в правом нижнем углу иконки, за него меняем размер
        r = self.icon_rect()
        return QRect(r.right() - ICON_GRIP + 1, r.bottom() - ICON_GRIP + 1,
                     ICON_GRIP, ICON_GRIP)

    def handle_rect(self):
        # Ручка для перетаскивания рамки целиком: полоска внутри рамки сверху
        f = self.frame_rect()
        return QRect(f.left() + GRIP, f.top() + GRIP,
                     max(f.width() - GRIP * 2, 10), HANDLE_H)

    def update_mask(self):
        # Маска: ловим мышь только на краях рамки, ручке, иконке и её уголке.
        # Середина рамки и всё остальное пропускают клики в игру.
        f = self.frame_rect()
        outer = f.adjusted(-GRIP, -GRIP, GRIP, GRIP)
        inner = f.adjusted(GRIP, GRIP, -GRIP, -GRIP)
        region = QRegion(outer).subtracted(QRegion(inner))
        region = region.united(QRegion(self.handle_rect()))
        icon = self.icon_rect().adjusted(-4, -4, 4, 4)
        region = region.united(QRegion(icon))
        region = region.united(QRegion(self.icon_grip_rect().adjusted(-4, -4, 4, 4)))
        self.setMask(region)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = COLORS[self.panel.device()]

        # Рамка окна
        frame = self.frame_rect()
        painter.setPen(QPen(color, 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(frame)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        for corner in (frame.topLeft(), frame.topRight(),
                       frame.bottomLeft(), frame.bottomRight()):
            painter.drawEllipse(corner, 6, 6)

        # Ручка для перетаскивания
        handle = self.handle_rect()
        fill = QColor(color)
        fill.setAlpha(150)
        painter.setBrush(fill)
        painter.drawRoundedRect(handle, 6, 6)
        painter.setPen(QColor(10, 10, 10))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.drawText(handle, Qt.AlignmentFlag.AlignCenter,
                         FRAME_NAMES[self.panel.device()].upper() + "  •  тяни за меня")

        # Иконка приложения (обложка)
        icon = self.icon_rect()
        painter.setBrush(QColor(255, 255, 255, 110))
        painter.setPen(QPen(LIGHT_GRAY, 3))
        painter.drawRoundedRect(icon, 12, 12)

        # Уголок для изменения размера иконки
        grip = self.icon_grip_rect()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(10, 10, 10, 220))
        painter.drawRect(grip)
        painter.setPen(QPen(WHITE, 2))
        painter.drawLine(grip.left() + 4, grip.bottom() - 2,
                         grip.right() - 2, grip.top() + 4)

    def hit(self, pos):
        """Что под курсором: icon_resize (уголок), icon, M (ручка = двигать всё), край рамки (T, B, L, R, углы)."""
        if self.icon_grip_rect().adjusted(-4, -4, 4, 4).contains(pos):
            return "icon_resize"
        if self.icon_rect().contains(pos):
            return "icon"
        if self.handle_rect().contains(pos):
            return "M"

        rect = self.frame_rect()
        if not rect.adjusted(-GRIP, -GRIP, GRIP, GRIP).contains(pos):
            return None

        edge = ""
        if abs(pos.y() - rect.top()) <= GRIP:
            edge += "T"
        elif abs(pos.y() - rect.bottom()) <= GRIP:
            edge += "B"
        if abs(pos.x() - rect.left()) <= GRIP:
            edge += "L"
        elif abs(pos.x() - rect.right()) <= GRIP:
            edge += "R"
        return edge or None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position().toPoint()
        self.mode = self.hit(pos)
        self.start_pos = pos
        device = self.panel.device()
        self.start_data = (
            list(self.data()[device]),
            list(self.data()[device + "_icon"]),
        )

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self.mode is None:
            return

        delta = pos - self.start_pos
        device = self.panel.device()
        frame0, icon0 = self.start_data

        if self.mode == "icon_resize":
            # Тянем за уголок: размер меняется по большему смещению,
            # иконка остаётся квадратной, левый верхний угол стоит на месте
            change = max(delta.x(), delta.y())
            size = max(ICON_MIN, min(ICON_MAX, icon0[2] + change))
            self.data()[device + "_icon"] = [icon0[0], icon0[1], size]
        elif self.mode == "icon":
            self.data()[device + "_icon"] = [
                icon0[0] + delta.x(), icon0[1] + delta.y(), icon0[2]
            ]
        else:
            rect = QRect(frame0[0], frame0[1], frame0[2], frame0[3])
            if self.mode == "M":
                rect.translate(delta)
            else:
                if "T" in self.mode:
                    rect.setTop(rect.top() + delta.y())
                if "B" in self.mode:
                    rect.setBottom(rect.bottom() + delta.y())
                if "L" in self.mode:
                    rect.setLeft(rect.left() + delta.x())
                if "R" in self.mode:
                    rect.setRight(rect.right() + delta.x())
                rect = rect.normalized()
                rect.setWidth(max(rect.width(), 60))
                rect.setHeight(max(rect.height(), 60))
            self.data()[device] = [
                rect.x(), rect.y(), rect.width(), rect.height()
            ]

        self.panel.refresh_numbers()
        self.refresh()

    def mouseReleaseEvent(self, event):
        self.mode = None

    def refresh(self):
        self.update_mask()
        self.update()
def make_card():
    card = QFrame()
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(8)
    return card, layout


def make_label(text, name=None):
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    return label


class Panel(QWidget):
    """Окно настроек. Обычное окно, можно тащить и закрывать."""

    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumWidth(460)
        self.setStyleSheet(STYLE)

        self.layout_data = load_layout()
        self.processes = {}
        self.overlay = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # --- Шапка ---
        root.addWidget(make_label("TAP", "title"))
        root.addWidget(make_label("PHONE  ·  TABLET", "subtitle"))
        line = QFrame()
        line.setObjectName("line")
        root.addWidget(line)

        # --- Запуск ---
        card, box = make_card()
        box.addWidget(make_label("ЗАПУСК", "section"))
        self.tablet_check = QCheckBox("Планшет (Google)")
        self.phone_check = QCheckBox("Телефон (Telegram)")
        self.tablet_check.toggled.connect(
            lambda on: self.set_running("tablet", TABLET_SCRIPT, on)
        )
        self.phone_check.toggled.connect(
            lambda on: self.set_running("phone", PHONE_SCRIPT, on)
        )
        box.addWidget(self.tablet_check)
        box.addWidget(self.phone_check)

        self.restart_button = QPushButton("Перезапустить")
        self.restart_button.clicked.connect(self.restart_scripts)
        box.addWidget(self.restart_button)
        root.addWidget(card)

        # --- Настройка ---
        card, box = make_card()
        box.addWidget(make_label("НАСТРОЙКА ПОЛОЖЕНИЯ", "section"))

        self.device_box = QComboBox()
        self.device_box.addItem("Планшет", "tablet")
        self.device_box.addItem("Телефон", "phone")
        self.device_box.currentIndexChanged.connect(self.on_device_changed)
        box.addWidget(self.device_box)

        self.edit_button = QPushButton("Включить режим подгонки на экране")
        self.edit_button.setCheckable(True)
        self.edit_button.toggled.connect(self.toggle_overlay)
        box.addWidget(self.edit_button)

        box.addWidget(make_label(
            "Рамку тяни за верхнюю полоску или за края, иконку тяни на место.\n"
            "Размер иконки меняй за тёмный уголок в её правом нижнем углу.\n"
            "Середина рамки пропускает клики, игрой можно пользоваться.",
            "hint",
        ))

        # Числа рамки
        box.addWidget(make_label("РАМКА ОКНА", "hint"))
        row = QHBoxLayout()
        self.frame_spins = []
        for name in ("x", "y", "ширина", "высота"):
            row.addWidget(QLabel(name))
            spin = QSpinBox()
            spin.setRange(-5000, 10000)
            spin.valueChanged.connect(self.on_spin_changed)
            row.addWidget(spin)
            self.frame_spins.append(spin)
        box.addLayout(row)

        self.refresh_button = QPushButton("Обновить (новое разрешение)")
        self.refresh_button.clicked.connect(self.refresh_screen)
        box.addWidget(self.refresh_button)
        root.addWidget(card)

        # --- Сохранить ---
        self.save_button = QPushButton("СОХРАНИТЬ")
        self.save_button.setObjectName("save")
        self.save_button.clicked.connect(self.save)
        root.addWidget(self.save_button)

        self.status = make_label("", "status")
        root.addWidget(self.status)

        self.refresh_numbers()

    def device(self):
        return self.device_box.currentData()

    # Числа из данных в полях
    def refresh_numbers(self):
        device = self.device()
        frame = self.layout_data[device]
        for spin, value in zip(self.frame_spins, frame):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    # Числа из полей в данные
    def on_spin_changed(self):
        device = self.device()
        self.layout_data[device] = [s.value() for s in self.frame_spins]
        if self.overlay is not None:
            self.overlay.refresh()

    def on_device_changed(self):
        self.refresh_numbers()
        if self.overlay is not None:
            self.overlay.refresh()

    def toggle_overlay(self, on):
        if on:
            self.overlay = Overlay(self)
            self.overlay.show()
            self.edit_button.setText("Выключить режим подгонки")
        else:
            if self.overlay is not None:
                self.overlay.close()
                self.overlay = None
            self.edit_button.setText("Включить режим подгонки на экране")

    def refresh_screen(self):
        # Кнопка «Обновить»: перечитываем размер экрана и файл layout.json
        self.layout_data = load_layout()
        self.refresh_numbers()
        if self.overlay is not None:
            self.overlay.fit_to_screen()
            self.overlay.refresh()
        screen = QApplication.primaryScreen().geometry()
        self.status.setText(
            "Обновлено. Экран: %d × %d" % (screen.width(), screen.height())
        )

    def save(self):
        save_layout(self.layout_data)
        self.status.setText(
            "Сохранено. Чтобы скрипты приняли новые значения, нажми «Перезапустить»."
        )

    # ===== Запуск и остановка скриптов =====
    def is_running(self, key):
        process = self.processes.get(key)
        return process is not None and process.poll() is None

    def start_script(self, key, script):
        # Защита от двойного запуска: второй процесс не создаём
        if self.is_running(key):
            return True
        if FROZEN:
            # В exe запускаем сам exe с режимом tablet или phone
            command = [sys.executable, key]
        else:
            path = os.path.join(BASE_DIR, script)
            if not os.path.exists(path):
                self.status.setText("Не нашёл файл " + script)
                return False
            command = [sys.executable, path]
        self.processes[key] = subprocess.Popen(
            command,
            cwd=BASE_DIR,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True

    def stop_script(self, key):
        process = self.processes.pop(key, None)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except Exception:
                process.kill()

    def set_running(self, key, script, on):
        if on:
            if self.start_script(key, script):
                self.status.setText("Запущен " + script)
        else:
            self.stop_script(key)
            self.status.setText("Остановлен " + script)

    def restart_scripts(self):
        # Сохраняем настройки, останавливаем всё и запускаем заново только включённые
        save_layout(self.layout_data)
        self.stop_script("tablet")
        self.stop_script("phone")
        QTimer.singleShot(700, self.start_enabled)
        self.status.setText("Перезапуск...")

    def start_enabled(self):
        if self.tablet_check.isChecked():
            self.start_script("tablet", TABLET_SCRIPT)
        if self.phone_check.isChecked():
            self.start_script("phone", PHONE_SCRIPT)
        self.status.setText("Перезапущено, новые настройки применены.")

    def stop_all(self):
        for key in list(self.processes.keys()):
            self.stop_script(key)

    def closeEvent(self, event):
        # Крестик только прячет окно в трей, скрипты продолжают работать
        if self.overlay is not None:
            self.edit_button.setChecked(False)
        event.ignore()
        self.hide()


def make_app_icon():
    # Сначала аватарка tap.png, потом telegram.png, последний вариант — белый квадрат
    for name in (APP_ICON_FILE, TRAY_ICON_FILE):
        path = os.path.join(ICONS_DIR, name)
        if os.path.exists(path):
            return QIcon(path)
    pixmap = QPixmap(32, 32)
    pixmap.fill(WHITE)
    return QIcon(pixmap)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    icon = make_app_icon()
    app.setWindowIcon(icon)

    panel = Panel()
    panel.setWindowIcon(icon)
    panel.show()

    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip(APP_NAME)

    menu = QMenu()
    open_action = QAction("Открыть настройки")
    open_action.triggered.connect(lambda: (panel.show(), panel.raise_(), panel.activateWindow()))
    quit_action = QAction("Выход")

    def quit_app():
        panel.stop_all()
        tray.hide()
        app.quit()

    quit_action.triggered.connect(quit_app)
    menu.addAction(open_action)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)

    def on_tray_click(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            panel.show()
            panel.raise_()
            panel.activateWindow()

    tray.activated.connect(on_tray_click)
    tray.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    if MODE == "tablet":
        import browser
        browser.run()
    elif MODE == "phone":
        import telegram_browser
        telegram_browser.run()
    else:
        main()