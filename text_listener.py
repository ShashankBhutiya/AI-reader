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
        """)

        # Set fixed maximum width for the container
        max_width = 350
        container.setMaximumWidth(max_width)
        
        # Layout
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)  # Add some padding
        layout.setSpacing(8)  # Add some spacing between widgets
        
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
        
        # Add widgets to layouts
        content_layout.addWidget(text_label)
        scroll.setWidget(content)
        
        layout.addWidget(title_label)
        layout.addWidget(scroll, 1)  # Make the scroll area take remaining space
        
        # Outer layout for transparent background
        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(container)
        
        # Set size policy and adjust size
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
# This new class is a QObject that performs the Gemini API call.
# It lives in a separate thread so the GUI doesn't freeze.
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
# This class now manages the QThread and the worker.
class EventDispatcher(QtCore.QObject):
    show_popup_signal = QtCore.pyqtSignal(int, int)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.show_popup_signal.connect(self.handle_show_popup)

    def handle_show_popup(self, x, y):
        # 1. First, get the selected text from the clipboard
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.05)  # Give the system a moment to process the copy command
        text = pyperclip.paste().strip()

        if not text:
            # If no text is selected, just show a simple message
            display_text = "No text found in clipboard."
            if self.parent.popup:
                self.parent.popup.close()
            self.parent.popup = Popup(display_text, QPoint(x + 10, y + 10))
            QtCore.QTimer.singleShot(3000, self.parent.popup.close)
            return

        # 2. Close any existing popup and show a "loading" message immediately
        if self.parent.popup:
            self.parent.popup.close()

        # Display a loading message while waiting for the summary
        self.parent.popup = Popup("Fetching summary...", QPoint(x + 10, y + 10))

        # 3. Create a QThread and the worker object to handle the API call
        self.thread = QtCore.QThread()
        self.worker = GeminiSummarizerWorker(text, QPoint(x + 10, y + 10))
        self.worker.moveToThread(self.thread)

        # 4. Connect signals to manage the thread and worker lifecycle
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.handle_summary_ready)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        # 5. Start the thread
        self.thread.start()

    def handle_summary_ready(self, summary_text, position):
        """This slot is called when the worker has finished."""
        # Close the "loading" popup
        if self.parent.popup:
            self.parent.popup.close()
        
        # Display the final summary
        display_text = f"{summary_text}"
        self.parent.popup = Popup(display_text, position)
        QtCore.QTimer.singleShot(5000, self.parent.popup.close)  # Close after 5 seconds


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
        # We need to make sure QApplication is created before any widgets
        # or signals are used. This is correctly placed.
        self.app = QtWidgets.QApplication(sys.argv)
        self.dispatcher = EventDispatcher(self)

        self.mouse_listener = mouse.Listener(on_click=self.on_click)
        self.mouse_listener.start()

        self.app.aboutToQuit.connect(self.cleanup)
        # This starts the PyQt event loop, which is essential for processing signals and events.
        self.app.exec_()

    def cleanup(self):
        # This ensures the pynput listener is stopped gracefully when the application exits.
        if hasattr(self, 'mouse_listener'):
            self.mouse_listener.stop()
            self.mouse_listener.join()


if __name__ == "__main__":
    listener = TextListener()
    listener.start()