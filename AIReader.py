# Copyright © 2025 ShashankBhutiya. All rights reserved.
import sys
import time
import pyperclip
import pyautogui
import keyboard
from PyQt5.QtWidgets import (
    QApplication, QWidget, QGraphicsDropShadowEffect, QFrame, QPushButton,
    QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QSystemTrayIcon, QMenu
)
from PyQt5.QtCore import (
    Qt, QPoint, QPropertyAnimation, QEvent, QObject, pyqtSignal, pyqtSlot, QTimer, QThread
)
from PyQt5.QtGui import QIcon, QColor
from pynput import mouse
import google.generativeai as genai

MAX_WIDTH = 350


# ------------------ Gemini API Setup ------------------
# Common Free api key for all users
API_KEY = "AIzaSyABEQYzLrI5KN8h-A9orAzBWG0lpbJACdU"
if API_KEY:
    genai.configure(api_key=API_KEY)


# A constant to define what we consider 'short' text.
MIN_TEXT_LENGTH = 50

def summarize_with_gemini(text):
    """Send text to Gemini and get a short summary."""
    # 1. Check for API Key
    if not API_KEY:
        return "❌ API Key Not Found\n\nPlease set the GOOGLE_API_KEY environment variable to use AI features."

    # 2. Check if the text is too short to be worth summarizing
    if len(text) < MIN_TEXT_LENGTH:
        return text  # Just return the original text if it's too short

    try:
        model = genai.GenerativeModel("gemini-2.5-flash-lite-preview-06-17")
        prompt = f"""Summarize the following text into concise, simple bullet points. Use '-' for each point. Do not add any extra formatting.\n\nText: {text}"""
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        # Provide a more user-friendly error message for common API issues.
        return f"Gemini API Error:\n{str(e)}"


# ------------------ Popup UI ------------------
class Popup(QWidget):
    def __init__(self, text, position):
        super().__init__()
        # Set window flags to make it a tool window (no taskbar entry)
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint | 
            Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        # If clicked outside the popup, close it
        
        # self.setAttribute(Qt.WA_TransparentForMouseEvents)
        
        # Drop shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setOffset(3, 3)
        shadow.setColor(QColor("black"))

        # Container with relative positioning for the close button
        container = QFrame()
        container.setGraphicsEffect(shadow)
        container.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 230);
                border-radius: 8px;
                padding: 8px 8px;
                position: relative;
            }
            QLabel {
                color: #222;
                font-size: 10pt;
            }
            QLabel#title {
                font-size: 11pt;
                font-weight: bold;
                color: #1a73e8;
                margin-bottom: 2px;
            }
        """)

        # Set fixed maximum width for the container
        max_width = MAX_WIDTH
        container.setMaximumWidth(max_width)
        
        # Create close button
        self.close_button = QPushButton("×", container)  # × is the multiplication sign (looks like an X)
        self.close_button.setFixedSize(20, 20)
        self.close_button.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888;
                border: none;
                font-size: 20px;
                font-weight: bold;
                padding: 0;
                margin: 0;
            }
            QPushButton:hover {
                color: #555;
                background: rgba(0,0,0,0.1);
                border-radius: 12px;
            }
        """)
        self.close_button.clicked.connect(self.hide)
        
        # Position the close button in the top-right corner
        self.close_button.move(container.width() - 30, 6)
        
        # Layout
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)  # Add some padding
        layout.setSpacing(8)  # Add some spacing between widgets
        
        # Title with close button
        title_widget = QWidget()
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(0, 0, 0, 0)
        
        title_label = QLabel("Summary")
        title_label.setObjectName("title")
        
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.close_button)
        
        layout.addWidget(title_widget)
        
        # Create scroll area for long text 
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        # Create content widget for the scroll area
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Add widgets to layouts
        content_layout.addWidget(text_label)
        scroll.setWidget(content)
        
        layout.addWidget(scroll, 1)  # Make the scroll area take remaining space
        
        # Outer layout for transparent background
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(container)
        
        # Set size policy and adjust size
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.adjustSize()

        self.move(position)

        # Fade-in animation
        self.setWindowOpacity(0)
        self.show()

        # Install a global event filter to detect clicks outside the popup
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        # Store the application instance for cleanup
        self._app = app
        
        # Set up fade animation
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(200)
        self.fade_anim.setStartValue(0)
        self.fade_anim.setEndValue(1)
        self.fade_anim.start()
        
    def eventFilter(self, obj, event):
        # Close if any mouse press happens outside the popup
        if event.type() == QEvent.MouseButtonPress:
            # Map the global click position to this widget's coordinates
            global_pos = event.globalPos()
            local_pos = self.mapFromGlobal(global_pos)
            if not self.rect().contains(local_pos):
                # Click is outside the popup; close it
                self.close()
        return False  # Do not consume the event; allow normal processing
        
    def closeEvent(self, event):
        # Clean up the global event filter
        if hasattr(self, '_app') and self._app is not None:
            try:
                self._app.removeEventFilter(self)
            except Exception:
                pass
        event.accept()
        event.accept()

# ------------------ Worker to run in separate thread ------------------
# This new class is a QObject that performs the Gemini API call.
# It lives in a separate thread so the GUI doesn't freeze.
class GeminiSummarizerWorker(QObject):
    finished = pyqtSignal(str, QPoint)  # Signal to emit when done

    def __init__(self, text, position):
        super().__init__()
        self._text = text
        self._position = position

    @pyqtSlot()
    def run(self):
        """The main method to be executed by the thread."""
        summary = summarize_with_gemini(self._text)
        self.finished.emit(summary, self._position)


# ------------------ Event Dispatcher ------------------
# This class now manages the QThread and the worker.
class EventDispatcher(QObject):
    show_popup_signal = pyqtSignal(int, int)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.thread = None
        self.worker = None
        self.show_popup_signal.connect(self.handle_show_popup)
        
    def cleanup_previous(self):
        # Clean up any existing thread
        try:
            if self.thread and self.thread.isRunning():
                self.thread.quit()
                self.thread.wait()
                self.thread.deleteLater()
                self.thread = None
        except:
            pass
            
        # Clean up any existing popup
        if hasattr(self.parent, 'popup') and self.parent.popup:
            try:
                self.parent.popup.close()
                self.parent.popup.deleteLater()
                self.parent.popup = None
            except:
                pass

    def handle_show_popup(self, x, y):
        # Clean up any existing threads and popups first
        self.cleanup_previous()
        
        # 1. First, get the selected text from the clipboard
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.05)  # Give the system a moment to process the copy command
        text = pyperclip.paste().strip()

        # Function to estimate popup width based on text
        def estimate_popup_width(text):
            # Base width + some padding
            char_width = 8  # Approximate width per character
            max_width = 400  # Same as MAX_WIDTH in Popup class
            estimated_width = min(len(text) * char_width + 20, max_width)
            return max(200, estimated_width)  # Minimum width of 200px

        if not text:
            # If no text is selected, just show a simple message
            display_text = "No text found in clipboard."
            estimated_width = estimate_popup_width(display_text)
            self.parent.popup = Popup(display_text, QPoint(x + 10, y + 10))
            QTimer.singleShot(3000, self.parent.popup.close)
            return

        # 2. Show a "loading" message
        # (Existing popups are already cleaned up by cleanup_previous)
        loading_text = "Fetching summary..."
        # estimated_width = estimate_popup_width(loading_text)
        popup_x = x + 10
        self.parent.popup = Popup(loading_text, QPoint(popup_x, y + 10))

        # 3. Create a QThread and the worker object to handle the API call
        self.thread = QThread()
        self.worker = GeminiSummarizerWorker(text, QPoint(popup_x, y + 10))
        self.worker.moveToThread(self.thread)

        # 4. Connect signals to manage the thread and worker lifecycle
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.handle_summary_ready)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        # Show startup notification
        self.show_startup_notification()
        
    def show_startup_notification(self):
        # This method is kept for backward compatibility
        # The notification is now shown from setup_tray_icon
        
        # 5. Start the thread
        self.thread.start()

    def handle_summary_ready(self, summary_text, position):
        """This slot is called when the worker has finished."""
        # Close any existing popup
        if hasattr(self.parent, 'popup') and self.parent.popup:
            try:
                self.parent.popup.close()
                self.parent.popup.deleteLater()
            except:
                pass
        
        # Display the final summary
        display_text = f"{summary_text}"
        self.parent.popup = Popup(display_text, position)
        QTimer.singleShot(30000, self.parent.popup.hide)  # hide after 30 seconds


# ------------------ Mouse Listener ------------------
class TextListener:
    def __init__(self):
        self.app = None
        self.popup = None
        self.dispatcher = None
        self.tray_icon = None

    def on_click(self, x, y, button, pressed):
        if pressed and button == mouse.Button.right and keyboard.is_pressed('ctrl'):
            self.dispatcher.show_popup_signal.emit(x, y)

    def setup_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
            
        # Create a tray icon
        self.tray_icon = QSystemTrayIcon(
            QIcon("icon.ico"),
            self.app
        )
        
        # Create a menu for the tray icon
        menu = QMenu()
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self.app.quit)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
        
        # Show startup notification
        self.tray_icon.showMessage(
            "AI Reader",
            "AI Reader is running in the background.\nPress Ctrl + Right-Click to summarize text.",
            QSystemTrayIcon.Information,
            3000  # Show for 3 seconds
        )
    
    def start(self):
        # Create application with application name and display name
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("AI Reader")
        self.app.setWindowIcon(QIcon("icon.ico"))
        
        # Setup system tray icon
        self.setup_tray_icon()
        
        # Initialize dispatcher
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
    