"""
Logger module for the Shrimp text editor.

Provides a simple file-based logger for debugging and error tracking, and safe wrappers
for curses screen output functions that catch and log curses errors.
"""
import curses
import datetime

# Define the log file path
LOG_FILE_PATH = "shrimp.log"

def log(message: str) -> None:
    """Append a timestamped message to the log file."""
    try:
        with open(LOG_FILE_PATH, 'a', encoding='utf-8') as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        # If logging fails (e.g., file not writable), ignore to avoid crashing the editor.
        pass

def safe_addstr(window, y: int, x: int, text: str, attr: int = 0) -> None:
    """
    Safely add a string to the curses window at the given position.
    Logs any curses.error exceptions that occur (e.g., writing off-screen).
    """
    try:
        window.addstr(y, x, text, attr)
    except curses.error:
        log(f"curses.error in addstr at ({y},{x}): '{text}'")

def safe_addch(window, y: int, x: int, ch: str, attr: int = 0) -> None:
    """
    Safely add a character to the curses window at the given position.
    Logs any curses.error exceptions that occur.
    """
    try:
        window.addch(y, x, ch, attr)
    except curses.error:
        log(f"curses.error in addch at ({y},{x}): char='{ch}'")

