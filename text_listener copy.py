# stable version so far

import sys
import time
import os
import pyperclip
import pyautogui
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt, QPoint, QThread, pyqtSignal
from pynput import mouse
import google.generativeai as genai

# ------------------ CONFIG ------------------
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("Please set GEMINI_API_KEY in your environment variables.")

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash-lite")

POPUP_WIDTH = 260
POPUP_PADDING = 8
DEFAULT_MODE = "bullets"


# ------------------ SUMMARIZATION ------------------
def summarize_bullets(text):
    prompt = f"Summarize the following text in bulletien, use no text formating and start bullets with thier number indices:\n\n{text}"
    resp = model.generate_content(prompt)
    return resp.text.strip()


def summarize_text(text):
    prompt = f"Summarize the following text in one short, clear paragraph:\n\n{text}"
    resp = model.generate_content(prompt)
    return resp.text.strip()


# ------------------ THREAD WORKER ------------------
class SummarizeWorker(QThread):
    finished = pyqtSignal(str)

    def __init__(self, text, mode):
        super().__init__()
        self.text = text
        self.mode = mode

    def run(self):
        try:
            if self.mode == "bullets":
                summary = summarize_bullets(self.text)
            else:
                summary = summarize_text(self.text)
        except Exception as e:
            summary = f"Error: {e}"
        self.finished.emit(summary)


# ------------------ POPUP ------------------
class Popup(QtWidgets.QWidget):
    def __init__(self, raw_text, position):
        super().__init__()
        self.raw_text = raw_text
        self.current_mode = DEFAULT_MODE
        self.worker = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Container
        container = QtWidgets.QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(255, 255, 255, 240);
                border-radius: 8px;
                padding: {POPUP_PADDING}px;
            }}
            QLabel {{
                color: #222;
                font-size: 9pt;
            }}
            QLabel#title {{
                font-size: 10pt;
                font-weight: bold;
                color: #1a73e8;
            }}
            QPushButton {{
                border: none;
                color: #1a73e8;
                padding: 2px 6px;
                background-color: transparent;
            }}
            QPushButton:hover {{
                background-color: rgba(26, 115, 232, 0.1);
            }}
        """)

        layout = QtWidgets.QVBoxLayout(container)
        layout.setSpacing(4)

        self.title_label = QtWidgets.QLabel("Summary")
        self.title_label.setObjectName("title")

        self.text_label = QtWidgets.QLabel("Loading…")
        self.text_label.setWordWrap(True)
        self.text_label.setFixedWidth(POPUP_WIDTH)
        self.text_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.bullets_btn = QtWidgets.QPushButton("Bullets")
        self.text_btn = QtWidgets.QPushButton("Text")
        btn_layout.addWidget(self.bullets_btn)
        btn_layout.addWidget(self.text_btn)

        layout.addWidget(self.title_label)
        layout.addWidget(self.text_label)
        layout.addLayout(btn_layout)

        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(container)

        self.move(position)
        self.show()

        # Events
        self.bullets_btn.clicked.connect(lambda: self.update_summary("bullets"))
        self.text_btn.clicked.connect(lambda: self.update_summary("text"))

        # Initial summary
        self.update_summary(DEFAULT_MODE)

    def update_summary(self, mode):
        self.current_mode = mode
        self.text_label.setText("Loading…")

        if self.worker:
            self.worker.quit()

        self.worker = SummarizeWorker(self.raw_text, mode)
        self.worker.finished.connect(self.display_summary)
        self.worker.start()

    def display_summary(self, summary):
        self.text_label.setText(summary)


# ------------------ EVENT DISPATCHER ------------------
class EventDispatcher(QtCore.QObject):
    show_popup_signal = QtCore.pyqtSignal(int, int)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.show_popup_signal.connect(self.handle_show_popup)

    def handle_show_popup(self, x, y):
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.1)
        text = pyperclip.paste().strip() or "No text found."

        if self.parent.popup:
            self.parent.popup.close()
            self.parent.popup = None

        # Prevent going off-screen
        screen = QtWidgets.QApplication.primaryScreen().geometry()
        px = min(x + 10, screen.width() - POPUP_WIDTH - 20)
        py = min(y + 10, screen.height() - 100)

        self.parent.popup = Popup(text, QPoint(px, py))
        self.parent.popup.raise_()
        self.parent.popup.activateWindow()


# ------------------ MAIN APP ------------------
class TextListener:
    def __init__(self):
        self.app = None
        self.popup = None
        self.dispatcher = None

    def on_click(self, x, y, button, pressed):
        if pressed and button == mouse.Button.middle:
            self.dispatcher.show_popup_signal.emit(x, y)

    def start(self):
        self.app = QtWidgets.QApplication(sys.argv)

        # Tray icon
        tray = QtWidgets.QSystemTrayIcon()
        tray.setToolTip("Text Summarizer")
        menu = QtWidgets.QMenu()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.app.quit)
        tray.setContextMenu(menu)
        tray.show()

        self.dispatcher = EventDispatcher(self)

        listener = mouse.Listener(on_click=self.on_click, suppress=False)
        listener.start()
        self.app.aboutToQuit.connect(listener.stop)

        sys.exit(self.app.exec_())


if __name__ == "__main__":
    TextListener().start()
