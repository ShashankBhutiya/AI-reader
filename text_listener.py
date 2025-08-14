import sys
import time
import os
import pyperclip
import pyautogui
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt, QPoint
from pynput import mouse
import google.generativeai as genai


# ------------------ Gemini API Setup ------------------
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise ValueError("❌ GOOGLE_API_KEY not found in environment variables.")
genai.configure(api_key=API_KEY)


def summarize_with_gemini(text):
    """Send text to Gemini and get a short summary."""
    try:
        model = genai.GenerativeModel("gemini-2.5-flash-lite-preview-06-17")
        prompt = f"Summarize the following text in least possible number of simple bulletiens, add no additional text formating, use '-' this for :\n\n{text}"
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Error getting summary: {str(e)}"


# ------------------ Popup UI ------------------
class Popup(QtWidgets.QWidget):
    def __init__(self, text, position):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Drop shadow effect
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setOffset(3, 3)
        shadow.setColor(QtCore.Qt.black)

        # Container
        container = QtWidgets.QFrame()
        container.setGraphicsEffect(shadow)
        container.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 230);
                border-radius: 12px;
                padding: 12px;
            }
            QLabel {
                color: #222;
                font-size: 11pt;
            }
            QLabel#title {
                font-size: 13pt;
                font-weight: bold;
                color: #1a73e8;
                margin-bottom: 4px;
            }
            QPushButton {
                background-color: #f0f0f0;
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #ddd;
            }
        """)

        # Set fixed maximum width for the container
        max_width = 350
        container.setMaximumWidth(max_width)
        
        # Layout
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        title_label = QtWidgets.QLabel("Summary")
        title_label.setObjectName("title")
        
        # Create scroll area for long text
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        
        # Create content widget for the scroll area
        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        text_label = QtWidgets.QLabel(text)
        text_label.setWordWrap(True)
        text_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        
        content_layout.addWidget(text_label)
        scroll.setWidget(content)
        
        # --- NEW BUTTONS ---
        button_layout = QtWidgets.QHBoxLayout()
        btn_bullet = QtWidgets.QPushButton("Bulletin")
        btn_text = QtWidgets.QPushButton("Text")
        button_layout.addWidget(btn_bullet)
        button_layout.addWidget(btn_text)
        # -------------------
        
        layout.addWidget(title_label)
        layout.addWidget(scroll, 1)
        layout.addLayout(button_layout)  # Add buttons below scroll area
        
        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(container)
        
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.adjustSize()

        self.move(position)

        # Fade-in animation
        self.setWindowOpacity(0)
        self.show()
        self.fade_anim = QtCore.QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(200)
        self.fade_anim.setStartValue(0)
        self.fade_anim.setEndValue(1)
        self.fade_anim.start()


# ------------------ Worker to run in separate thread ------------------
class GeminiSummarizerWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(str, QPoint)  # Signal to emit when done

    def __init__(self, text, position):
        super().__init__()
        self._text = text
        self._position = position

    @QtCore.pyqtSlot()
    def run(self):
        """The main method to be executed by the thread."""
        summary = summarize_with_gemini(self._text)
        self.finished.emit(summary, self._position)


# ------------------ Event Dispatcher ------------------
class EventDispatcher(QtCore.QObject):
    show_popup_signal = QtCore.pyqtSignal(int, int)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.show_popup_signal.connect(self.handle_show_popup)

    def handle_show_popup(self, x, y):
        # 1. First, get the selected text from the clipboard
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.05)
        text = pyperclip.paste().strip()

        if not text:
            display_text = "No text found in clipboard."
            if self.parent.popup:
                self.parent.popup.close()
            self.parent.popup = Popup(display_text, QPoint(x + 10, y + 10))
            QtCore.QTimer.singleShot(3000, self.parent.popup.close)
            return

        if self.parent.popup:
            self.parent.popup.close()

        self.parent.popup = Popup("Fetching summary...", QPoint(x + 10, y + 10))

        # Create QThread for Gemini
        self.thread = QtCore.QThread()
        self.worker = GeminiSummarizerWorker(text, QPoint(x + 10, y + 10))
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.handle_summary_ready)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.thread.start()

    def handle_summary_ready(self, summary_text, position):
        if self.parent.popup:
            self.parent.popup.close()
        
        display_text = f"{summary_text}"
        self.parent.popup = Popup(display_text, position)
        QtCore.QTimer.singleShot(5000, self.parent.popup.close)


# ------------------ Mouse Listener ------------------
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
        self.dispatcher = EventDispatcher(self)

        self.mouse_listener = mouse.Listener(on_click=self.on_click)
        self.mouse_listener.start()

        self.app.aboutToQuit.connect(self.cleanup)
        self.app.exec_()

    def cleanup(self):
        if hasattr(self, 'mouse_listener'):
            self.mouse_listener.stop()
            self.mouse_listener.join()


if __name__ == "__main__":
    listener = TextListener()
    listener.start()
