import sys
import time
import os
import random
import html
import re
import pyperclip
import pyautogui
import requests
from bs4 import BeautifulSoup
from difflib import SequenceMatcher
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt, QPoint
from pynput import mouse
import google.generativeai as genai
import ctypes
import platform
from ctypes import wintypes


# ------------------ Gemini API Setup ------------------
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise ValueError("❌ GOOGLE_API_KEY not found in environment variables.")
genai.configure(api_key=API_KEY)


# ------------------ Utility: text helpers ------------------
def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def similarity(a: str, b: str) -> float:
    """Return fuzzy similarity ratio [0..1]."""
    a_norm = normalize_whitespace(a).lower()
    b_norm = normalize_whitespace(b).lower()
    if not a_norm or not b_norm:
        return 0.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def extract_snippets(text: str, words_per=14, max_snippets=4):
    """Pick multiple representative snippets from the text:
       start, middle, end, and one random (if long enough)."""
    words = text.split()
    if len(words) < 8:
        return [" ".join(words)] if words else []

    # indices for start, middle, end
    positions = [0,
                 max(0, len(words)//2 - words_per//2),
                 max(0, len(words) - words_per)]
    snippets = []
    for i in positions:
        snippets.append(" ".join(words[i:i+words_per]))

    # add one random snippet if long
    if len(words) > words_per * 3 and len(snippets) < max_snippets:
        start = random.randint(words_per, max(words_per*2, len(words)-words_per))
        start = min(start, max(0, len(words)-words_per))
        snippets.append(" ".join(words[start:start+words_per]))

    # Deduplicate and clean
    seen = set()
    clean = []
    for s in snippets:
        s = normalize_whitespace(s)
        if s and s not in seen:
            clean.append(s)
            seen.add(s)
    return clean[:max_snippets]


# ------------------ Windows 11 Mica helper ------------------
def enable_mica(widget) -> bool:
    """Enable Windows 11 Mica backdrop on a top-level Qt widget.

    Returns True if successfully enabled. Safe no-op on non-Windows or if API unsupported.
    """
    try:
        if sys.platform != "win32":
            return False

        # Ensure HWND is available (widget should be shown or created)
        hwnd = int(widget.winId())

        # DWM attribute constants
        DWMWA_SYSTEMBACKDROP_TYPE = 38  # Windows 11 22H2+
        DWMSBT_MAINWINDOW = 2           # Mica
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # Optional: match dark mode

        dwm = ctypes.windll.dwmapi

        # Set Mica backdrop
        value = ctypes.c_int(DWMSBT_MAINWINDOW)
        res = dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd),
                                        ctypes.c_uint(DWMWA_SYSTEMBACKDROP_TYPE),
                                        ctypes.byref(value),
                                        ctypes.sizeof(value))

        # Try to enable dark mode for better contrast (optional)
        try:
            dark = ctypes.c_int(1)
            dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd),
                                      ctypes.c_uint(DWMWA_USE_IMMERSIVE_DARK_MODE),
                                      ctypes.byref(dark),
                                      ctypes.sizeof(dark))
        except Exception:
            pass

        return res == 0
    except Exception:
        return False

# ------------------ Summary ------------------
def summarize_with_gemini(text):
    """Send text to Gemini and get a short summary."""
    try:
        model = genai.GenerativeModel("gemini-2.5-flash-lite-preview-06-17")
        prompt = (
            "Summarize the following text in least possible number of simple bulletiens, "
            "add no additional text formating, use '-' this for :\n\n"
            f"{text}"
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Error getting summary: {str(e)}"


# ------------------ Search scraping (free approximation) ------------------
class SearchClient:
    def __init__(self, timeout=6):
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

    def _safe_get(self, url, params=None, retries=2):
        last_exc = None
        for _ in range(retries + 1):
            try:
                r = requests.get(url, params=params, headers=self.headers, timeout=self.timeout)
                if r.status_code == 200 and r.text:
                    return r.text
            except Exception as e:
                last_exc = e
            time.sleep(0.3)
        if last_exc:
            raise last_exc
        return ""

    def duckduckgo_snippets(self, query):
        """Use DuckDuckGo HTML endpoint (simple layout)."""
        try:
            # DDG "html" endpoint with simple markup
            url = "https://html.duckduckgo.com/html/"
            html_text = self._safe_get(url, params={"q": query})
            soup = BeautifulSoup(html_text, "html.parser")
            # Snippets are inside result blocks
            snippets = []
            for res in soup.select(".result__snippet"):
                txt = res.get_text(separator=" ")
                if txt:
                    snippets.append(normalize_whitespace(html.unescape(txt)))
            # Fallback: full result blocks
            if not snippets:
                for res in soup.select(".result__a, .result"):
                    txt = res.get_text(separator=" ")
                    if txt:
                        snippets.append(normalize_whitespace(html.unescape(txt)))
            return snippets[:10]
        except Exception:
            return []

    def google_snippets(self, query):
        """Best-effort Google parsing (brittle; used as secondary)."""
        try:
            url = "https://www.google.com/search"
            html_text = self._safe_get(url, params={"q": query, "hl": "en"})
            soup = BeautifulSoup(html_text, "html.parser")
            snippets = []

            # Common snippet containers (may change over time)
            for res in soup.select("div.BNeawe.s3v9rd.AP7Wnd, div.VwiC3b, span.aCOpRe"):
                txt = res.get_text(separator=" ")
                if txt:
                    snippets.append(normalize_whitespace(html.unescape(txt)))

            # Fallback generic divs
            if not snippets:
                for res in soup.find_all("div"):
                    classes = " ".join(res.get("class", []))
                    if "BNeawe" in classes or "VwiC3b" in classes:
                        txt = res.get_text(separator=" ")
                        if txt:
                            snippets.append(normalize_whitespace(html.unescape(txt)))
                            if len(snippets) >= 10:
                                break
            return snippets[:10]
        except Exception:
            return []

    def search_snippets(self, query):
        # Try DDG first, then add Google if available
        ddg = self.duckduckgo_snippets(query)
        # If DDG gave something, it's often enough. Still try Google and combine (unique).
        ggl = self.google_snippets(query) if len(ddg) < 6 else []
        combined = []
        seen = set()
        for s in ddg + ggl:
            if s and s not in seen:
                combined.append(s)
                seen.add(s)
            if len(combined) >= 12:
                break
        return combined


def score_snippet_against_results(snippet, results):
    """Return a score [0..1] for a snippet based on matches in result snippets."""
    if not snippet or not results:
        return 0.0

    sn = normalize_whitespace(snippet).lower()
    if len(sn) < 20:
        # Very short snippets create false positives—cap the impact
        short_penalty = 0.75
    else:
        short_penalty = 1.0

    matches = 0
    best_sim = 0.0

    for r in results:
        r_norm = normalize_whitespace(r).lower()
        # Exact-ish containment
        contain = sn in r_norm
        # Fuzzy similarity
        sim = similarity(sn, r_norm)
        best_sim = max(best_sim, sim)
        if contain or sim >= 0.9:
            matches += 1

    # Convert to a snippet score:
    # - primary via normalized match count
    # - boosted by best similarity
    # - limited by short snippet penalty
    base = min(1.0, matches / 3.0)  # 3+ matches saturate snippet score
    boost = max(0.0, best_sim - 0.85) * 2.0  # small boost if very similar anywhere
    snippet_score = max(base, min(1.0, base + boost))
    return snippet_score * short_penalty


def aggregate_plagiarism_score(text):
    """Compute overall plagiarism percentage [0..100] using multiple snippets and searches."""
    client = SearchClient()
    snippets = extract_snippets(text, words_per=14, max_snippets=4)

    if not snippets:
        return 0

    per_snippet_scores = []
    for snip in snippets:
        # Use quoted query to force exact phrase search where possible
        query = f"\"{snip}\""
        results = client.search_snippets(query)
        score = score_snippet_against_results(snip, results)
        per_snippet_scores.append(score)

    # Weighted aggregation:
    # Give slightly more weight to the middle snippet(s) which often represent core text.
    weights = []
    for i in range(len(per_snippet_scores)):
        if i == 1 or i == 2:
            weights.append(1.2)
        else:
            weights.append(1.0)
    total_w = sum(weights) or 1.0
    weighted = sum(s * w for s, w in zip(per_snippet_scores, weights)) / total_w

    # Convert to 0..100 percentage, clamp
    percent = int(round(max(0.0, min(1.0, weighted)) * 100))
    return percent


# ------------------ Popup UI ------------------
class Popup(QtWidgets.QWidget):
    def __init__(self, text, position):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Track if mouse is pressed
        self.mouse_press_event = None

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
            QLabel#plagLabel {
                font-size: 10pt;
                color: #666;
            }
            QPushButton#closeButton {
                background-color: #ff6b6b;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 2px 8px;
            }
            QPushButton#closeButton:hover {
                background-color: #ff5252;
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

        # Bottom row (plagiarism %)
        bottom_row = QtWidgets.QHBoxLayout()
        bottom_row.setSpacing(8)

        self.plag_label = QtWidgets.QLabel("Plagiarism: Checking…")
        self.plag_label.setObjectName("plagLabel")

        # Close button in header
        btn_close = QtWidgets.QPushButton("✕")
        btn_close.setObjectName("closeButton")
        btn_close.setFixedSize(28, 24)
        btn_close.clicked.connect(self.close)

        # Header layout (title + close)
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(btn_close)
        header_layout.setContentsMargins(0, 0, 0, 10)

        layout.addLayout(header_layout)
        layout.addWidget(scroll, 1)

        bottom_row.addWidget(self.plag_label)
        layout.addLayout(bottom_row)

        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(container)

        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.adjustSize()

        # Ensure popup stays within screen bounds
        screen_rect = QtWidgets.QApplication.desktop().availableGeometry()
        x = min(max(0, position.x()), screen_rect.width() - self.width() - 10)
        y = min(max(0, position.y()), screen_rect.height() - self.height() - 10)
        self.move(x, y)

        # Install event filter for click-outside detection
        self.setMouseTracking(True)
        self.installEventFilter(self)

        # Fade-in animation
        self.setWindowOpacity(0)
        self.show()
        # Attempt to enable Windows 11 Mica effect (no-op on unsupported systems)
        enable_mica(self)
        self.fade_anim = QtCore.QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(200)
        self.fade_anim.setStartValue(0)
        self.fade_anim.setEndValue(1)
        self.fade_anim.start()

    def set_plagiarism_score(self, percent):
        """Update the plagiarism percentage shown in the bottom row."""
        try:
            p = int(round(float(percent)))
            p = max(0, min(100, p))
        except Exception:
            p = None

        if p is None:
            self.plag_label.setText("Plagiarism: — %")
            self.plag_label.setStyleSheet("font-size: 10pt; color: #666;")
            return

        self.plag_label.setText(f"Plagiarism: {p}%")

        # Color code: green <20, amber 20–59, red 60+
        if p < 20:
            color = "#2ecc71"
        elif p < 60:
            color = "#f39c12"
        else:
            color = "#e74c3c"

        self.plag_label.setStyleSheet("font-size: 10pt; color: %s;" % color)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if not self.rect().contains(event.pos()):
                self.close()
                return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        self.mouse_press_event = event.globalPos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.mouse_press_event = None
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.mouse_press_event is not None:
            delta = event.globalPos() - self.mouse_press_event
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.mouse_press_event = event.globalPos()
        super().mouseMoveEvent(event)


# ------------------ Workers ------------------
class GeminiSummarizerWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(str, QPoint)  # summary, position

    def __init__(self, text, position):
        super().__init__()
        self._text = text
        self._position = position

    @QtCore.pyqtSlot()
    def run(self):
        summary = summarize_with_gemini(self._text)
        self.finished.emit(summary, self._position)


class PlagiarismCheckWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(int)  # percent

    def __init__(self, text):
        super().__init__()
        self._text = text

    @QtCore.pyqtSlot()
    def run(self):
        try:
            score = aggregate_plagiarism_score(self._text)
        except Exception:
            score = 0
        self.finished.emit(score)


# ------------------ Event Dispatcher ------------------
class EventDispatcher(QtCore.QObject):
    show_popup_signal = QtCore.pyqtSignal(int, int)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.show_popup_signal.connect(self.handle_show_popup)

    def handle_show_popup(self, x, y):
        # Copy selection
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.05)
        text = pyperclip.paste().strip()

        if not text:
            display_text = "No text found in clipboard."
            if self.parent.popup:
                self.parent.popup.close()
            self.parent.popup = Popup(display_text, QPoint(x + 10, y + 10))
            return

        if self.parent.popup:
            self.parent.popup.close()

        # Show placeholder popup
        self.parent.popup = Popup("Fetching summary...", QPoint(x + 10, y + 10))

        if not hasattr(self.parent, "active_threads"):
            self.parent.active_threads = []

        # --- Summary Thread ---
        thread = QtCore.QThread()
        worker = GeminiSummarizerWorker(text, QPoint(x + 10, y + 10))
        worker.moveToThread(thread)

        def on_summary(summary_text, position):
            if self.parent.popup:
                self.parent.popup.close()
            self.parent.popup = Popup(summary_text, position)
            # Kick off plagiarism check
            self.start_plagiarism_check(text)

        def cleanup():
            worker.deleteLater()
            thread.deleteLater()
            if thread in self.parent.active_threads:
                self.parent.active_threads.remove(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(on_summary)
        worker.finished.connect(thread.quit)
        thread.finished.connect(cleanup)

        self.parent.active_threads.append(thread)
        thread.start()

    def start_plagiarism_check(self, text):
        # Threaded plagiarism check
        thread = QtCore.QThread()
        worker = PlagiarismCheckWorker(text)
        worker.moveToThread(thread)

        def update_score(score):
            if hasattr(self.parent, "popup") and self.parent.popup:
                self.parent.popup.set_plagiarism_score(score)

        def cleanup():
            worker.deleteLater()
            thread.deleteLater()
            if hasattr(self.parent, "active_threads") and thread in self.parent.active_threads:
                self.parent.active_threads.remove(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(update_score)
        worker.finished.connect(thread.quit)
        thread.finished.connect(cleanup)

        if not hasattr(self.parent, "active_threads"):
            self.parent.active_threads = []
        self.parent.active_threads.append(thread)
        thread.start()


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
