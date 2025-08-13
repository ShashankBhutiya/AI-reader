# AI Text Summarizer

A lightweight desktop application that provides instant text summarization using Google's Gemini AI. Simply select any text and middle-click to get an AI-generated summary in a clean, non-intrusive popup.

![Screenshot](screenshot.png)  
*Example of the AI summarizer in action*

## Features

- **One-Click Summarization**: Middle-click on any selected text to get an instant summary
- **Dual View Modes**: Toggle between bullet points and paragraph summaries
- **Clean UI**: Minimal, non-intrusive popup that appears near your cursor
- **Background Operation**: Runs quietly in the system tray
- **Fast & Lightweight**: Built with PyQt5 for smooth performance
- **Privacy-Focused**: No text data is stored or logged

## Installation

1. **Prerequisites**
   - Python 3.8 or higher
   - A Google Gemini API key

2. **Set up environment variables**
   Create a `.env` file in the project directory with your API key:
   ```
   GOOGLE_API_KEY=your_api_key_here
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Run the application:
   ```bash
   python text_listener.py
   ```

2. The application will start and appear in your system tray

3. To get a summary:
   - Select any text with your mouse
   - Press the middle mouse button
   - View the summary in the popup
   - Click "Text" to switch to paragraph view, or "Bullets" to return to bullet points

4. To exit:
   - Right-click the system tray icon and select "Quit"
   - Or use your system's application manager to close the app

## Requirements

- PyQt5
- pynput
- pyperclip
- pyautogui
- python-dotenv
- google-generativeai

## Configuration

You can customize the following in the code:
- Popup position offset
- Summary length (by modifying the prompt in `summarize_with_gemini`)
- Popup styling (colors, sizes, etc. in the `Popup` class)

## Troubleshooting

- If the popup doesn't appear, check if your system allows applications to display notifications
- Ensure you have an active internet connection for the Gemini API
- Make sure you've set the `GOOGLE_API_KEY` environment variable

## License

This project is open source and available under the [MIT License](LICENSE).

---

*Note: This application is not affiliated with or endorsed by Google or the Gemini AI team.*
