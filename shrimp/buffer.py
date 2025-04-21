"""
Buffer module for Shrimp text editor.

Defines the Buffer class to manage text content and operations on the text (inserting, deleting, copying, etc.).
Each Buffer represents an open file or unsaved document with its own cursor position and modification state.
"""
import os

class Buffer:
    """Represents a text buffer (file content) with editing operations."""
    def __init__(self, filename: str = None, lines=None):
        self.filename = filename  # Path to file or None for new/unsaved
        self.lines = lines if lines is not None else [""]

        # FIX: ensure there's always at least one line, even if lines=[]
        if not self.lines:
            self.lines = [""]

        self.modified = False
        self.mark_line = None
        # Cursor position within this buffer (line and column)
        self.cursor_line = 0
        self.cursor_col = 0
        # Scroll offset (top line index visible in the window for this buffer)
        self.scroll = 0

    def ensure_not_empty(self):
        """Ensure buffer has at least one empty line (called after deletions)."""
        if len(self.lines) == 0:
            self.lines = [""]
            self.cursor_line = 0
            self.cursor_col = 0

    def insert_line_below(self):
        """Insert a new blank line below the current line and move cursor to it."""
        self.lines.insert(self.cursor_line + 1, "")
        self.modified = True
        self.cursor_line += 1
        self.cursor_col = 0

    def split_line(self):
        """Split the current line at the cursor position, moving the remainder to a new line below."""
        line = self.lines[self.cursor_line]
        before = line[:self.cursor_col]
        after = line[self.cursor_col:]
        self.lines[self.cursor_line] = before
        self.lines.insert(self.cursor_line + 1, after)
        self.modified = True
        self.cursor_line += 1
        self.cursor_col = 0

    def delete_line(self):
        """Delete the current line from the buffer."""
        if not self.lines:
            self.lines = [""]
            self.cursor_line = 0
            self.cursor_col = 0
            return
        self.lines.pop(self.cursor_line)
        self.modified = True
        self.ensure_not_empty()
        if self.cursor_line >= len(self.lines):
            self.cursor_line = len(self.lines) - 1
        self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))

    def delete_multiple_lines(self, count: int):
        """Delete multiple lines starting from the current line."""
        start = self.cursor_line
        end = min(start + count, len(self.lines))
        del self.lines[start:end]
        self.modified = True
        self.ensure_not_empty()
        if self.cursor_line >= len(self.lines):
            self.cursor_line = len(self.lines) - 1
        self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))

    def delete_paragraph(self):
        """Delete the paragraph (continuous non-blank lines) around the cursor line."""
        if not self.lines:
            return
        start = self.cursor_line
        while start > 0 and self.lines[start-1].strip() != "":
            start -= 1
        end = self.cursor_line
        while end < len(self.lines) and self.lines[end].strip() != "":
            end += 1
        del self.lines[start:end]
        self.modified = True
        self.ensure_not_empty()
        if start < len(self.lines):
            self.cursor_line = start
        else:
            self.cursor_line = len(self.lines) - 1
        self.cursor_col = 0

    def copy_line(self) -> str:
        """Copy the current line and return it."""
        if not self.lines:
            return ""
        return self.lines[self.cursor_line]

    def copy_multiple_lines(self, count: int) -> str:
        """
        Copy the specified number of lines starting at current line,
        returning them joined by newline.
        """
        start = self.cursor_line
        end = min(start + count, len(self.lines))
        return "\n".join(self.lines[start:end])

    def copy_paragraph(self) -> str:
        """Copy the paragraph around the current line and return it."""
        if not self.lines:
            return ""
        start = self.cursor_line
        while start > 0 and self.lines[start-1].strip() != "":
            start -= 1
        end = self.cursor_line
        while end < len(self.lines) and self.lines[end].strip() != "":
            end += 1
        return "\n".join(self.lines[start:end])

    def paste_lines(self, text: str):
        if not text:
            return
        clip_lines = text.splitlines()
        insertion_index = self.cursor_line + 1
        # Insert all the new lines at once for efficiency
        self.lines[insertion_index:insertion_index] = clip_lines
        self.modified = True
        # Move cursor to the last inserted line, at start of line
        self.cursor_line = insertion_index + len(clip_lines) - 1
        self.cursor_col = 0


    def delete_word(self):
        """Delete the word at or after the cursor position on the current line."""
        if not self.lines or self.cursor_line >= len(self.lines):
            return
        line = self.lines[self.cursor_line]
        if not line:
            return
        pos = self.cursor_col
        while pos < len(line) and not line[pos].isalnum():
            pos += 1
        if pos >= len(line):
            return
        start = pos
        while start > 0 and line[start-1].isalnum():
            start -= 1
        end = pos
        while end < len(line) and line[end].isalnum():
            end += 1
        new_line = line[:start] + line[end:]
        self.lines[self.cursor_line] = new_line
        self.modified = True
        self.cursor_col = start
        if self.cursor_col > len(new_line):
            self.cursor_col = len(new_line)

    def copy_word_inline(self) -> str:
        """Copy the word at the cursor position (or next word if cursor on whitespace)."""
        if not self.lines or self.cursor_line >= len(self.lines):
            return ""
        line = self.lines[self.cursor_line]
        if not line:
            return ""
        pos = self.cursor_col
        while pos < len(line) and not line[pos].isalnum():
            pos += 1
        if pos >= len(line):
            return ""
        start = pos
        while start > 0 and line[start-1].isalnum():
            start -= 1
        end = pos
        while end < len(line) and line[end].isalnum():
            end += 1
        return line[start:end]

    def jump_word(self):
        """Move cursor to the end of the current or next word."""
        if not self.lines:
            return
        line = self.lines[self.cursor_line]
        if not line:
            return
        pos = self.cursor_col
        while pos < len(line) and not line[pos].isalnum():
            pos += 1
        if pos >= len(line):
            self.cursor_col = pos
            return
        while pos < len(line) and line[pos].isalnum():
            pos += 1
        self.cursor_col = pos

    def jump_back_word(self):
        """Move cursor to the beginning of the current or previous word."""
        if not self.lines:
            return
        line = self.lines[self.cursor_line]
        if not line:
            return
        pos = self.cursor_col
        while pos > 0 and not line[pos-1].isalnum():
            pos -= 1
        while pos > 0 and line[pos-1].isalnum():
            pos -= 1
        self.cursor_col = pos

    def save_to_file(self) -> bool:
        """
        Write the buffer contents to self.filename, if any.
        Returns True on success, False on error or if no filename is set.
        """
        if not self.filename:
            return False
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                f.write("\n".join(self.lines))
            self.modified = False
            return True
        except Exception:
            return False

