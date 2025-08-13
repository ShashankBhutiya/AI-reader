import sys
import time
import os
import pyperclip
import pyautogui
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt, QPoint
from pynput import mouse
import google.generativeai as genai


# ------------------ GEMINI SETUP ------------------
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("Please set GEMINI_API_KEY in your environment variables.")

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")


def summarize_bullets(text):
    """Summarize in bullet points."""
    prompt = f"Summarize the following text in 4-6 concise bullet points:\n\n{text}"
    try:
        resp = model.generate_content(prompt)
        return resp.text.strip()
    except Exception as e:
        return f"Error generating bullet summary: {e}"


def summarize_text(text):
    """Summarize as a short paragraph."""
    prompt = f"Summarize the following text in a short, clear paragraph:\n\n{text}"
    try:
        resp = model.generate_content(prompt)
        return resp.text.strip()
    except Exception as e:
        return f"Error generating text summary: {e}"


# ------------------ POPUP CLASS ------------------
class Popup(QtWidgets.QWidget):
    def __init__(self, bullet_text, paragraph_text, position):
        super().__init__()
        self.bullet_text = bullet_text
        self.paragraph_text = paragraph_text
        self.current_mode = "bullets"

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Drop shadow
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setOffset(3, 3)
        shadow.setColor(QtCore.Qt.black)

        # Main container
        container = QtWidgets.QFrame()
        container.setGraphicsEffect(shadow)
        container.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 240);
                border-radius: 12px;
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
                padding: 4px 10px;
                border-radius: 6px;
                border: 1px solid #ccc;
                background-color: #f5f5f5;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:checked {
                background-color: #1a73e8;
                color: white;
                border: 1px solid #1a73e8;
            }
        """)

        # Scroll area for text
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        self.text_label = QtWidgets.QLabel(self.bullet_text)
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        content_widget = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)

        title_label = QtWidgets.QLabel("Summary")
        title_label.setObjectName("title")

        content_layout.addWidget(title_label)
        content_layout.addWidget(self.text_label)
        content_layout.addStretch()

        scroll.setWidget(content_widget)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_bullets = QtWidgets.QPushButton("Bullets")
        self.btn_text = QtWidgets.QPushButton("Text")

        self.btn_bullets.setCheckable(True)
        self.btn_text.setCheckable(True)

        self.btn_bullets.setChecked(True)
        self.btn_bullets.clicked.connect(lambda: self.switch_mode("bullets"))
        self.btn_text.clicked.connect(lambda: self.switch_mode("text"))

        btn_layout.addWidget(self.btn_bullets)
        btn_layout.addWidget(self.btn_text)

        # Layouts
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(scroll)
        layout.addLayout(btn_layout)

        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(container)

        # Size limits
        container.setMaximumWidth(350)
        container.setMaximumHeight(250)

        self.adjustSize()
        self.move(position)

        # Fade in animation
        self.setWindowOpacity(0)
        self.show()
        fade = QtCore.QPropertyAnimation(self, b"windowOpacity")
        fade.setDuration(200)
        fade.setStartValue(0)
        fade.setEndValue(1)
        fade.start()

    def switch_mode(self, mode):
        """Switch between bullet and text summary."""
        if mode == self.current_mode:
            return
        self.current_mode = mode
        if mode == "bullets":
            self.text_label.setText(self.bullet_text)
            self.btn_bullets.setChecked(True)
            self.btn_text.setChecked(False)
        else:
            self.text_label.setText(self.paragraph_text)
            self.btn_bullets.setChecked(False)
            self.btn_text.setChecked(True)


# ------------------ EVENT DISPATCHER ------------------
class EventDispatcher(QtCore.QObject):
    show_popup_signal = QtCore.pyqtSignal(int, int)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.show_popup_signal.connect(self.handle_show_popup)

    def handle_show_popup(self, x, y):
        # Copy selected text
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.05)
        text = pyperclip.paste().strip()
        if not text:
            text = "No text found in clipboard."

        # Generate summaries
        bullet_summary = summarize_bullets(text)
        paragraph_summary = summarize_text(text)

        # Close existing popup
        if self.parent.popup:
            self.parent.popup.close()

        # Show new popup
        self.parent.popup = Popup(bullet_summary, paragraph_summary, QPoint(x + 10, y + 10))
        self.parent.popup.show()


# ------------------ MAIN LISTENER ------------------
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

        # Start mouse listener in a separate thread
        self.mouse_listener = mouse.Listener(on_click=self.on_click)
        self.mouse_listener.start()
        
        # Show a system tray icon if needed (optional)
        self.tray_icon = QtWidgets.QSystemTrayIcon()
        self.tray_icon.show()
        
        # Ensure the application stays alive
        self.app.aboutToQuit.connect(self.cleanup)
        
        # Keep a reference to the listener to prevent garbage collection
        self.app.mouse_listener = self.mouse_listener
        
        # Start the application
        sys.exit(self.app.exec_())

    def cleanup(self):
        if hasattr(self, 'mouse_listener'):
            self.mouse_listener.stop()
            self.mouse_listener.join()


if __name__ == "__main__":
    listener = TextListener()
    listener.start()



if __name__ == "__main__":
    listener = TextListener()
    listener.start()

        # Show a system tray icon if needed (optional)
        self.tray_icon = QtWidgets.QSystemTrayIcon()
        self.tray_icon.show()
        
        # Ensure the application stays alive
        self.app.aboutToQuit.connect(self.cleanup)
        
        # Keep a reference to the listener to prevent garbage collection
        self.app.mouse_listener = self.mouse_listener
        
        # Start the application
        sys.exit(self.app.exec_())

    def cleanup(self):
        if hasattr(self, 'mouse_listener'):
            self.mouse_listener.stop()
            self.mouse_listener.join()


if __name__ == "__main__":
    listener = TextListener()
    listener.start()
