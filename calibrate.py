import os
import sys
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from PyQt6.QtWidgets import QApplication, QWidget

from layout_config import load_layout, save_layout, LAYOUT_FILE

NAMES = {"phone": "Телефон (Telegram)", "tablet": "Планшет (Google)"}
COLORS = {"phone": QColor(33, 161, 228), "tablet": QColor(66, 133, 244)}

GRIP = 14  # толщина зоны, за которую тянут край


class Calibrator(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        # Окно настройщика закрывает весь основной экран
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        self.layout_data = load_layout()
        self.current = "phone"
        self.mode = None        # что делаем мышкой: двигать или край
        self.start_pos = QPoint()
        self.start_rect = QRect()
        self.message = ""

    # ----- рамка текущего устройства -----
    def rect_of(self, key=None):
        x, y, w, h = self.layout_data[key or self.current]
        return QRect(x, y, w, h)

    def set_rect(self, rect):
        if rect.width() < 60:
            rect.setWidth(60)
        if rect.height() < 60:
            rect.setHeight(60)
        self.layout_data[self.current] = [
            rect.x(), rect.y(), rect.width(), rect.height()
        ]
        self.update()

    # ----- рисование -----
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Почти прозрачная заливка, чтобы окно ловило мышь
        painter.fillRect(self.rect(), QColor(0, 0, 0, 2))

        for key in ("phone", "tablet"):
            rect = self.rect_of(key)
            color = COLORS[key]
            active = key == self.current

            fill = QColor(color)
            fill.setAlpha(70 if active else 25)
            painter.fillRect(rect, fill)

            pen = QPen(color, 3 if active else 1)
            painter.setPen(pen)
            painter.drawRect(rect)

            if active:
                # Ручки по углам
                painter.setBrush(color)
                for corner in (
                    rect.topLeft(), rect.topRight(),
                    rect.bottomLeft(), rect.bottomRight(),
                ):
                    painter.drawEllipse(corner, 6, 6)
                painter.setBrush(Qt.BrushStyle.NoBrush)

        # Подсказка и текущие числа
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI", 11))
        x, y, w, h = self.layout_data[self.current]
        lines = [
            NAMES[self.current] + f":  x={x}  y={y}  ширина={w}  высота={h}",
            "1 телефон   2 планшет   S сохранить   Esc выход",
            "Мышь: тяни середину, чтобы двигать, края и углы, чтобы менять размер",
            "Стрелки: сдвиг на 1 пиксель.  Shift и стрелки: размер на 1 пиксель",
        ]
        if self.message:
            lines.append(self.message)

        box = QRect(20, 20, 640, 24 * len(lines) + 16)
        painter.fillRect(box, QColor(0, 0, 0, 190))
        for i, text in enumerate(lines):
            painter.drawText(32, 46 + i * 24, text)

    # ----- мышь -----
    def edge_at(self, pos):
        """Какой край или угол под курсором. M если середина."""
        rect = self.rect_of()
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
        if edge:
            return edge
        if rect.contains(pos):
            return "M"  # середина, двигаем
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position().toPoint()
        self.mode = self.edge_at(pos)
        self.start_pos = pos
        self.start_rect = self.rect_of()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()

        # Курсор подсказывает, что будет при перетаскивании
        if self.mode is None:
            edge = self.edge_at(pos)
            if edge in ("TL", "BR"):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif edge in ("TR", "BL"):
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif edge in ("T", "B"):
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            elif edge in ("L", "R"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif edge == "M":
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        delta = pos - self.start_pos
        rect = QRect(self.start_rect)

        if self.mode == "M":
            rect.translate(delta)
        else:
            if "T" in self.mode:
                rect.setTop(self.start_rect.top() + delta.y())
            if "B" in self.mode:
                rect.setBottom(self.start_rect.bottom() + delta.y())
            if "L" in self.mode:
                rect.setLeft(self.start_rect.left() + delta.x())
            if "R" in self.mode:
                rect.setRight(self.start_rect.right() + delta.x())
        self.set_rect(rect.normalized())

    def mouseReleaseEvent(self, event):
        self.mode = None

    # ----- клавиатура -----
    def keyPressEvent(self, event):
        key = event.key()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if key == Qt.Key.Key_Escape:
            self.close()
            return
        if key == Qt.Key.Key_1:
            self.current = "phone"
            self.message = ""
            self.update()
            return
        if key == Qt.Key.Key_2:
            self.current = "tablet"
            self.message = ""
            self.update()
            return
        if key == Qt.Key.Key_S:
            save_layout(self.layout_data)
            self.message = "Сохранено в layout.json рядом со скриптами"
            self.update()
            return

        step = {
            Qt.Key.Key_Left: (-1, 0),
            Qt.Key.Key_Right: (1, 0),
            Qt.Key.Key_Up: (0, -1),
            Qt.Key.Key_Down: (0, 1),
        }.get(key)
        if step is None:
            return

        rect = self.rect_of()
        if shift:
            rect.setWidth(rect.width() + step[0])
            rect.setHeight(rect.height() + step[1])
        else:
            rect.translate(step[0], step[1])
        self.set_rect(rect)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Calibrator()
    window.show()
    window.activateWindow()
    window.setFocus()
    sys.exit(app.exec())