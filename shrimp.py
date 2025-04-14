#!/usr/bin/env python3
# Note: To properly view icons, please use a Nerd Font–enabled terminal.

import locale
locale.setlocale(locale.LC_ALL, '')

import curses
import sys
import os
import time

def wrap_text(text, width):
    """A simple word-wrap function (not used in this version)."""
    words = text.split()
    if not words:
        return [""]
    lines = []
    current_line = words[0]
    for word in words[1:]:
        if len(current_line) + 1 + len(word) <= width:
            current_line += " " + word
        else:
            lines.append(current_line)
            current_line = word
    lines.append(current_line)
    return lines

# ---------------------------------------------------------------------------
# Nerd Font Icon Definitions.
FOLDER_ICON_CLOSED = " "   # Collapsed folder arrow.
FOLDER_ICON_OPEN   = " "   # Expanded folder arrow.
FOLDER_SYMBOL      = ""    # Folder icon.

FILE_ICONS = {
    ".py": "",
    ".md": "",
    ".txt": "",
    ".sh": "",
    ".yaml": "",
    ".yml": "",
    ".json": "",
    ".lua": "",
}
DEFAULT_FILE_ICON = ""

CMD_ARROW = "󰘍"

# Menu icons:
MENU_NEW_FILE  = ""
MENU_FILE_TREE = ""
MENU_DIRECTORY = ""
MENU_FIND_FILE = ""
MENU_QUIT      = ""

# ---------------------------------------------------------------------------
# FileNode represents a node in the file tree.
class FileNode:
    def __init__(self, name, path, is_dir, parent=None):
        self.name = name
        self.path = path
        self.is_dir = is_dir
        self.parent = parent
        self.children = []  # List of FileNode objects.
        self.expanded = False

    def toggle_expanded(self):
        if self.is_dir:
            self.expanded = not self.expanded

# ---------------------------------------------------------------------------
def build_tree(root_path, parent=None, show_hidden=True):
    """Recursively build a file tree from a root path."""
    name = os.path.basename(root_path) or root_path
    is_dir = os.path.isdir(root_path)
    node = FileNode(name, root_path, is_dir, parent)
    if is_dir:
        try:
            entries = os.listdir(root_path)
        except OSError:
            entries = []
        if not show_hidden:
            entries = [e for e in entries if not e.startswith(".")]
        entries.sort()
        for entry in entries:
            child_path = os.path.join(root_path, entry)
            child_node = build_tree(child_path, node, show_hidden)
            node.children.append(child_node)
    return node

# ---------------------------------------------------------------------------
def flatten_tree(node, depth=0, result=None):
    """Flatten the file tree into (node, depth) tuples."""
    if result is None:
        result = []
    result.append((node, depth))
    if node.is_dir and node.expanded:
        for child in node.children:
            flatten_tree(child, depth + 1, result)
    return result

# ---------------------------------------------------------------------------
def fuzzy_match(query, candidate):
    """
    Simple fuzzy matching: return True if all characters of query appear in candidate in order.
    """
    query = query.lower()
    candidate = candidate.lower()
    i = 0
    for ch in candidate:
        if i < len(query) and ch == query[i]:
            i += 1
        if i == len(query):
            return True
    return False

# ---------------------------------------------------------------------------
class CursesTextEditor:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.height, self.width = stdscr.getmaxyx()
        self.show_hidden = True  # Toggle for showing hidden files in tree

        # Multi-buffer support.
        self.buffers = []
        self.current_buffer_index = 0
        self._ensure_buffer()
        
        self.mode = "normal"  # Modes: normal, insert, command, filetree.
        self.cursor_line = 0
        self.cursor_col = 0
        self.clipboard = ""
        self.word_clipboard = ""
        self.command_buffer = ""
        self.status_message = ""
        self.scroll_offset = 0
        self.sidebar_visible = True
        self.sidebar_help_mode = False
        self.sidebar_log = []
        self.normal_number_buffer = ""
        self.last_digit_time = 0
        self.normal_number_timeout = 0.5
        self.word_mode = False
        # New attribute to expire help mode after a few seconds.
        self.help_mode_expiry = None

        self.file_tree_root = build_tree(os.getcwd(), show_hidden=self.show_hidden)
        if self.file_tree_root.is_dir:
            self.file_tree_root.expanded = True  # start with root expanded
        self.flat_file_list = flatten_tree(self.file_tree_root)
        self.filetree_selection_index = 0
        self.filetree_current_path = os.getcwd()
        self._update_filetree_entries()
        self.filetree_scroll_offset = 0
        self.mode_icons = {
            "normal": "",
            "insert": "",
            "command": "⌘",
            "filetree": ""
        }

    def _ensure_buffer(self):
        if not self.buffers:
            self.buffers.append({'filename': None, 'lines': [""],
                                 'cursor_line': 0, 'cursor_col': 0,
                                 'scroll': 0, 'modified': False})
            self.current_buffer_index = 0

    def get_current_lines(self):
        self._ensure_buffer()
        return self.buffers[self.current_buffer_index]['lines']

    def set_current_lines(self, new_lines):
        self._ensure_buffer()
        self.buffers[self.current_buffer_index]['lines'] = new_lines

    def get_current_filename(self):
        self._ensure_buffer()
        return self.buffers[self.current_buffer_index]['filename']

    def set_current_filename(self, filename):
        self._ensure_buffer()
        self.buffers[self.current_buffer_index]['filename'] = filename

    def syntax_highlight_line(self, line):
        # Main text is rendered uniformly using pair 2.
        return [(line, curses.color_pair(2))]

    def _update_dimensions(self):
        self.height, self.width = self.stdscr.getmaxyx()

    def _update_filetree_entries(self):
        try:
            self.filetree_entries = sorted(os.listdir(self.filetree_current_path))
        except OSError as e:
            self.filetree_entries = []
            self.status_message = f"error listing directory: {e}"

    def validate_cursor(self):
        lines = self.get_current_lines()
        if not lines:
            lines = [""]
            self.set_current_lines(lines)
        if self.cursor_line < 0:
            self.cursor_line = 0
        elif self.cursor_line >= len(lines):
            self.cursor_line = len(lines) - 1
        if self.cursor_col < 0:
            self.cursor_col = 0
        elif self.cursor_col > len(lines[self.cursor_line]):
            self.cursor_col = len(lines[self.cursor_line])

    def log_command(self, msg):
        self.sidebar_log.append(msg)
        if len(self.sidebar_log) > 5:
            self.sidebar_log = self.sidebar_log[-5:]

    def get_user_input(self, prompt):
        """
        Old blocking input method—used only for quick prompts.
        """
        self.stdscr.clear()
        self._update_dimensions()
        y = self.height // 2
        x = (self.width - len(prompt)) // 2
        try:
            self.stdscr.addstr(y, x, prompt, curses.color_pair(2))
        except curses.error:
            pass
        self.stdscr.refresh()
        curses.echo()
        try:
            user_input = self.stdscr.getstr(y+1, x).decode('utf-8')
        except Exception:
            user_input = ""
        curses.noecho()
        return user_input.strip()

    def draw_segment(self, y, x, text, color_pair, arrow=""):
        try:
            self.stdscr.attron(curses.color_pair(color_pair))
            self.stdscr.addstr(y, x, text)
            self.stdscr.attroff(curses.color_pair(color_pair))
        except curses.error:
            pass
        x += len(text)
        if arrow:
            try:
                self.stdscr.attron(curses.color_pair(color_pair))
                self.stdscr.addstr(y, x, arrow)
                self.stdscr.attroff(curses.color_pair(color_pair))
            except curses.error:
                pass
            x += len(arrow)
        return x

    def main_menu(self):
        menu_items = [
            {"label": "new file ", "shortcut": "n", "icon": MENU_NEW_FILE},
            {"label": "open filetree", "shortcut": "t", "icon": MENU_FILE_TREE},
            {"label": "open directory", "shortcut": "d", "icon": MENU_DIRECTORY},
            {"label": "search", "shortcut": "f", "icon": MENU_FIND_FILE},
            {"label": "quit", "shortcut": "q", "icon": MENU_QUIT},
        ]
        selected = 0
        for y in range(self.height):
            try:
                self.stdscr.addstr(y, 0, " " * self.width, curses.color_pair(7))
            except curses.error:
                pass
        while True:
            self.stdscr.clear()
            for y in range(self.height):
                try:
                    self.stdscr.addstr(y, 0, " " * self.width, curses.color_pair(7))
                except curses.error:
                    pass
            ascii_logo = r"""
                    _          _             
        \ \     ___| |__  _ __(_)_ __ ___  _ __  
-==-_    / /   / __| '_ \| '__| | '_ ` _ \| '_ \ 
  ==== =/_/    \__ \ | | | |  | | | | | | | |_) |
    ==== *     |___/_| |_|_|  |_|_| |_| |_| .__/
 ////||\\\\                               |_|
"""
            logo_lines = ascii_logo.splitlines()
            start_y = max(0, (self.height - len(logo_lines)) // 2 - 4)
            for i, line in enumerate(logo_lines):
                x = (self.width - len(line)) // 2
                try:
                    self.stdscr.addstr(start_y + i, x, line, curses.color_pair(6))
                except curses.error:
                    pass
            current_time = time.strftime("%H:%M:%S")
            time_line = f" {current_time} "
            try:
                self.stdscr.addstr(start_y - 2, (self.width - len(time_line)) // 2, time_line, curses.color_pair(2))
            except curses.error:
                pass
            menu_title = "menu..."
            try:
                self.stdscr.addstr(start_y + len(logo_lines) + 1,
                                   (self.width - len(menu_title)) // 2,
                                   menu_title,
                                   curses.color_pair(2) | curses.A_BOLD)
            except curses.error:
                pass
            start_y_menu = start_y + len(logo_lines) + 3
            for idx, item in enumerate(menu_items):
                line = f" {item['icon']} {item['label']}  [{item['shortcut'].upper()}] "
                x = (self.width - len(line)) // 2
                if idx == selected:
                    self.stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
                    self.stdscr.addstr(start_y_menu + idx, x, line)
                    self.stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)
                else:
                    self.stdscr.addstr(start_y_menu + idx, x, line, curses.color_pair(2))
            self.stdscr.refresh()
            key = self.stdscr.getch()
            if key in (curses.KEY_UP, ord('k')):
                selected = (selected - 1) % len(menu_items)
            elif key in (curses.KEY_DOWN, ord('j')):
                selected = (selected + 1) % len(menu_items)
            elif key in (10, curses.KEY_ENTER):
                return menu_items[selected]["shortcut"]
            elif key >= 0 and chr(key).lower() in [item["shortcut"] for item in menu_items]:
                for idx, item in enumerate(menu_items):
                    if chr(key).lower() == item["shortcut"]:
                        return item["shortcut"]

    def draw_filetree_fullscreen(self, scroll_offset):
        ft_width = 60
        x_offset = max(0, (self.width - ft_width) // 2)
        for y in range(self.height):
            try:
                self.stdscr.addstr(y, x_offset, " " * ft_width, curses.color_pair(7))
            except curses.error:
                pass
        visible_items = self.flat_file_list[scroll_offset: scroll_offset + self.height]
        y = 0
        for idx, (node, depth) in enumerate(visible_items):
            indent = "  " * depth
            if node.is_dir:
                arrow_icon = FOLDER_ICON_OPEN if node.expanded else FOLDER_ICON_CLOSED
                node_icon = FOLDER_SYMBOL
                display_line = f"{indent}{arrow_icon}{node_icon} {node.name}"
            else:
                _, ext = os.path.splitext(node.name)
                file_icon = FILE_ICONS.get(ext.lower(), DEFAULT_FILE_ICON)
                display_line = f"{indent}   {file_icon} {node.name}"
            display_line = display_line[:ft_width].ljust(ft_width)
            if idx + scroll_offset == self.filetree_selection_index:
                try:
                    self.stdscr.addstr(y, x_offset, display_line, curses.color_pair(1) | curses.A_BOLD)
                except curses.error:
                    pass
            else:
                try:
                    self.stdscr.addstr(y, x_offset, display_line, curses.color_pair(7))
                except curses.error:
                    pass
            y += 1

    def full_filetree_mode(self):
        self.mode = "filetree"
        prev_sidebar = self.sidebar_visible
        self.sidebar_visible = False
        ft_scroll_offset = 0
        self.flat_file_list = flatten_tree(self.file_tree_root)
        while self.mode == "filetree":
            self.stdscr.clear()
            visible_count = self.height
            if self.filetree_selection_index < ft_scroll_offset:
                ft_scroll_offset = self.filetree_selection_index
            elif self.filetree_selection_index >= ft_scroll_offset + visible_count:
                ft_scroll_offset = self.filetree_selection_index - visible_count + 1
            self.draw_filetree_fullscreen(ft_scroll_offset)
            self.stdscr.refresh()
            key = self.stdscr.getch()
            self.process_filetree_mode(key)
            if key == 27:
                self.mode = "normal"
        self.sidebar_visible = prev_sidebar

    def fuzzy_file_finder(self, query):
        matches = []
        for node, depth in self.flat_file_list:
            if not node.is_dir and fuzzy_match(query, node.name):
                matches.append(node)
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]
        selected_index = 0
        while True:
            self.stdscr.clear()
            header = f"fuzzy finder: {query} (use j/k, enter to select, esc to cancel)"
            try:
                self.stdscr.addstr(0, 0, header, curses.color_pair(2))
            except curses.error:
                pass
            for idx, node in enumerate(matches):
                line = f"{node.name} - {node.path}"
                if idx == selected_index:
                    try:
                        self.stdscr.addstr(idx + 1, 0, line, curses.color_pair(1) | curses.A_BOLD)
                    except curses.error:
                        pass
                else:
                    try:
                        self.stdscr.addstr(idx + 1, 0, line, curses.color_pair(2))
                    except curses.error:
                        pass
            self.stdscr.refresh()
            key = self.stdscr.getch()
            if key in (curses.KEY_UP, ord('k')):
                selected_index = (selected_index - 1) % len(matches)
            elif key in (curses.KEY_DOWN, ord('j')):
                selected_index = (selected_index + 1) % len(matches)
            elif key in (10, curses.KEY_ENTER):
                return matches[selected_index]
            elif key == 27:
                return None

    def choose_buffer_menu(self):
        """
        Opens a menu in the sidebar listing all open buffers.
        Use arrow keys to navigate and Enter to select one.
        """
        selected = 0
        while True:
            self.stdscr.clear()
            sidebar_w = 30
            for i in range(self.height):
                try:
                    self.stdscr.addstr(i, 0, " " * sidebar_w, curses.color_pair(4))
                except curses.error:
                    pass
            self.stdscr.addstr(0, 1, " buffers ", curses.color_pair(5) | curses.A_BOLD)
            for idx, buf in enumerate(self.buffers):
                fname = buf.get('filename') or "new file"
                display = os.path.basename(fname)
                if idx == selected:
                    try:
                        self.stdscr.addstr(idx+2, 1, f"> {display}", curses.color_pair(1) | curses.A_BOLD)
                    except curses.error:
                        pass
                else:
                    try:
                        self.stdscr.addstr(idx+2, 1, f"  {display}", curses.color_pair(4))
                    except curses.error:
                        pass
            self.stdscr.refresh()
            key = self.stdscr.getch()
            if key in (curses.KEY_UP, ord('k')):
                selected = (selected - 1) % len(self.buffers)
            elif key in (curses.KEY_DOWN, ord('j')):
                selected = (selected + 1) % len(self.buffers)
            elif key in (10, curses.KEY_ENTER):
                return selected
            elif key == 27:
                return None

    def title_screen(self):
        choice = self.main_menu()
        if choice in ["n"]:
            new_fn = self.get_user_input("enter new filename:")
            if new_fn:
                self.buffers[self.current_buffer_index]['cursor_line'] = self.cursor_line
                self.buffers[self.current_buffer_index]['cursor_col'] = self.cursor_col
                self.buffers[self.current_buffer_index]['scroll'] = self.scroll_offset
                new_buffer = {'filename': new_fn, 'lines': [""],
                              'cursor_line': 0, 'cursor_col': 0, 'scroll': 0,
                              'modified': False}
                self.buffers.append(new_buffer)
                self.current_buffer_index = len(self.buffers) - 1
                self.cursor_line = self.buffers[self.current_buffer_index]['cursor_line']
                self.cursor_col = self.buffers[self.current_buffer_index]['cursor_col']
                self.scroll_offset = self.buffers[self.current_buffer_index]['scroll']
        elif choice in ["t"]:
            self.full_filetree_mode()
        elif choice in ["d"]:
            directory = self.get_user_input("enter directory path:")
            if os.path.isdir(directory):
                os.chdir(directory)
                self.file_tree_root = build_tree(directory, show_hidden=self.show_hidden)
                if self.file_tree_root.is_dir:
                    self.file_tree_root.expanded = True
                self.flat_file_list = flatten_tree(self.file_tree_root)
                new_path = os.path.join(directory, "untitled.txt")
                self.buffers[self.current_buffer_index]['cursor_line'] = self.cursor_line
                self.buffers[self.current_buffer_index]['cursor_col'] = self.cursor_col
                self.buffers[self.current_buffer_index]['scroll'] = self.scroll_offset
                new_buffer = {'filename': new_path, 'lines': [""],
                              'cursor_line': 0, 'cursor_col': 0, 'scroll': 0,
                              'modified': True}
                self.buffers.append(new_buffer)
                self.current_buffer_index = len(self.buffers) - 1
                self.cursor_line = self.buffers[self.current_buffer_index]['cursor_line']
                self.cursor_col = self.buffers[self.current_buffer_index]['cursor_col']
                self.scroll_offset = self.buffers[self.current_buffer_index]['scroll']
                self.mode = "normal"
                self.sidebar_visible = True
            else:
                self.status_message = "invalid directory."
        elif choice in ["f"]:
            query = self.get_user_input("enter fuzzy search query:")
            selected_node = self.fuzzy_file_finder(query)
            if selected_node:
                try:
                    with open(selected_node.path, 'r', encoding='utf-8') as f:
                        content = f.read().splitlines()
                except Exception as e:
                    self.status_message = f"error opening file: {e}"
                else:
                    self.buffers[self.current_buffer_index]['cursor_line'] = self.cursor_line
                    self.buffers[self.current_buffer_index]['cursor_col'] = self.cursor_col
                    self.buffers[self.current_buffer_index]['scroll'] = self.scroll_offset
                    new_buffer = {'filename': selected_node.path, 'lines': content,
                                  'cursor_line': 0, 'cursor_col': 0, 'scroll': 0,
                                  'modified': False}
                    self.buffers.append(new_buffer)
                    self.current_buffer_index = len(self.buffers) - 1
                    self.cursor_line = self.buffers[self.current_buffer_index]['cursor_line']
                    self.cursor_col = self.buffers[self.current_buffer_index]['cursor_col']
                    self.scroll_offset = self.buffers[self.current_buffer_index]['scroll']
                    self.log_command("󰘍f: search")
            else:
                self.status_message = "no matching file found."
        elif choice in ["q"]:
            sys.exit()

    def draw_filetree(self, sidebar_width):
        for i in range(self.height):
            try:
                self.stdscr.addstr(i, 0, " " * sidebar_width, curses.color_pair(4))
            except curses.error:
                pass
        available = self.height - 2
        if self.filetree_selection_index < self.filetree_scroll_offset:
            self.filetree_scroll_offset = self.filetree_selection_index
        elif self.filetree_selection_index >= self.filetree_scroll_offset + available:
            self.filetree_scroll_offset = self.filetree_selection_index - available + 1
        y = 0
        x = 1
        heading = f"{self.mode_icons.get('filetree','')} file tree"
        x = self.draw_segment(y, x, f" {heading} ", 4)
        y += 1
        x = self.draw_segment(y, 1, f" root: {self.file_tree_root.path} ", 4)
        y += 1
        for idx, (node, depth) in enumerate(self.flat_file_list[self.filetree_scroll_offset:]):
            if y >= self.height:
                break
            is_selected = (idx + self.filetree_scroll_offset == self.filetree_selection_index)
            indent = "  " * depth
            if node.is_dir:
                arrow_icon = FOLDER_ICON_OPEN if node.expanded else FOLDER_ICON_CLOSED
                display_text = f"{indent}{arrow_icon}{FOLDER_SYMBOL} {node.name}"
            else:
                _, ext = os.path.splitext(node.name)
                file_icon = FILE_ICONS.get(ext.lower(), DEFAULT_FILE_ICON)
                display_text = f"{indent}   {file_icon} {node.name}"
            try:
                if is_selected:
                    self.stdscr.addstr(y, 1, display_text[:sidebar_width-2],
                                       curses.color_pair(1) | curses.A_BOLD)
                else:
                    self.stdscr.addstr(y, 1, display_text[:sidebar_width-2],
                                       curses.color_pair(4))
            except curses.error:
                pass
            y += 1

    def draw_sidebar(self, sidebar_width):
        for i in range(self.height):
            try:
                self.stdscr.addstr(i, 0, " " * sidebar_width, curses.color_pair(4))
            except curses.error:
                pass
        if self.mode == "filetree":
            self.draw_filetree(sidebar_width)
        else:
            # Check if temporary help mode has expired.
            if self.help_mode_expiry and time.time() > self.help_mode_expiry:
                self.sidebar_help_mode = False
                self.help_mode_expiry = None

            y = 0
            x = 1
            current_time = time.strftime("%H:%M:%S")
            x = self.draw_segment(y, x, f" {current_time} ", 4)
            y += 1
            header = " shrimp "
            x = self.draw_segment(y, 1, header, 4)
            y += 1
            # If help mode is on, show help; otherwise, show log.
            if self.sidebar_help_mode:
                help_list = [
                    "i: insert",
                    "o: cmd",
                    "d: delete",
                    "y: copy",
                    "u: paste",
                    "j: jumpline",
                    "h: startline",
                    "goto[num]",
                    "[num]y: copy",
                    "[num]d: delete",
                    "󰘍w: write",
                    "󰘍c: clearfile",
                    "󰘍wq: write+quit",
                    "󰘍q: quit",
                    "󰘍fd: file delete",
                    "󰘍fr: file rename",
                    "󰘍fn: file new",
                    "󰘍f: search",
                    "󰘍tb: tab menu",
                    "󰘍x: next tab",
                    "󰘍z: prev tab"
                ]
                messages = help_list
            else:
                messages = self.sidebar_log
            for msg in messages:
                if y >= self.height:
                    break
                try:
                    self.stdscr.addstr(y, 1, msg[:sidebar_width-2], curses.color_pair(4))
                except curses.error:
                    pass
                y += 1

    def draw_status_bar(self):
        """
        Draw a full-width powerline-style status bar on the bottom row.
        """
        status_y = self.height - 1
        mode_seg = f" {self.mode_icons.get(self.mode, '')} {self.mode.upper()} "
        x = 0
        try:
            self.stdscr.addstr(status_y, x, mode_seg, curses.color_pair(5))
        except curses.error:
            pass
        x += len(mode_seg)
        arrow = ""
        try:
            self.stdscr.addstr(status_y, x, arrow, curses.color_pair(7))
        except curses.error:
            pass
        x += len(arrow)
        filename = self.get_current_filename() or "new file"
        name_display = os.path.basename(filename)
        dirty_mark = '*' if self.buffers[self.current_buffer_index].get('modified', False) else ''
        buf_info = f" [{self.current_buffer_index+1}/{len(self.buffers)}]" if len(self.buffers) > 1 else ""
        file_seg = f" {name_display}{dirty_mark}{buf_info} "
        try:
            self.stdscr.addstr(status_y, x, file_seg, curses.color_pair(7))
        except curses.error:
            pass
        x += len(file_seg)
        arrow2 = ""
        try:
            self.stdscr.addstr(status_y, x, arrow2, curses.color_pair(3))
        except curses.error:
            pass
        x += len(arrow2)
        time_seg = f" {time.strftime('%H:%M:%S')} "
        time_seg_len = len(time_seg)
        for pos in range(x, self.width - time_seg_len):
            try:
                self.stdscr.addch(status_y, pos, ' ', curses.color_pair(3))
            except curses.error:
                pass
        try:
            self.stdscr.addstr(status_y, self.width - time_seg_len, time_seg, curses.color_pair(3))
        except curses.error:
            pass

    def draw_centered_cmdline(self):
        """
        Draw a larger fixed command box (with top and bottom borders) that does not move the UI.
        """
        box_width = max(40, len(self.command_buffer) + 10)
        box_height = 5
        start_y = (self.height - box_height) // 2
        start_x = (self.width - box_width) // 2

        top_border = "┌" + "─" * (box_width - 2) + "┐"
        bottom_border = "└" + "─" * (box_width - 2) + "┘"
        title = " cmdline "
        if len(title) < box_width - 2:
            title_start = (box_width - 2 - len(title)) // 2
            top_line = "┌" + " " * title_start + title + " " * (box_width - 2 - title_start - len(title)) + "┐"
        else:
            top_line = top_border

        content = f"{CMD_ARROW} {self.command_buffer}"
        content = content[:box_width - 4].ljust(box_width - 4)
        content_line = "│ " + content + " │"

        try:
            self.stdscr.addstr(start_y, start_x, top_line, curses.color_pair(3) | curses.A_BOLD)
            self.stdscr.addstr(start_y+1, start_x, content_line, curses.color_pair(3) | curses.A_BOLD)
            self.stdscr.addstr(start_y+2, start_x, bottom_border, curses.color_pair(3) | curses.A_BOLD)
        except curses.error:
            pass

    def display(self):
        self._update_dimensions()
        # Reserve bottom row for status bar.
        visible_height = self.height - 1
        sidebar_width = 30 if self.sidebar_visible and self.width >= 80 else (20 if self.sidebar_visible else 0)
        self.stdscr.clear()
        if self.sidebar_visible:
            self.draw_sidebar(sidebar_width)
        x_offset = sidebar_width
        text_area_width = self.width - x_offset
        for i in range(visible_height):
            try:
                self.stdscr.addstr(i, x_offset, " " * text_area_width, curses.color_pair(2))
            except curses.error:
                pass
        lines = self.get_current_lines()
        if self.cursor_line < self.scroll_offset:
            self.scroll_offset = self.cursor_line
        if self.cursor_line >= self.scroll_offset + visible_height:
            self.scroll_offset = self.cursor_line - visible_height + 1
        if self.scroll_offset < 0:
            self.scroll_offset = 0
        if self.scroll_offset > max(0, len(lines) - visible_height):
            self.scroll_offset = max(0, len(lines) - visible_height)
        for i in range(visible_height):
            line_index = self.scroll_offset + i
            if line_index < len(lines):
                indicator = "-> " if line_index == self.cursor_line else "   "
                line_number = f"{line_index+1:<3}"
                safe_line = lines[line_index][:max(0, text_area_width-7)]
                text = f"{indicator}{line_number} {safe_line}"
                try:
                    self.stdscr.addstr(i, x_offset, text, curses.color_pair(2))
                except curses.error:
                    pass
        if len(lines) > visible_height:
            thumb_height = max(1, int(visible_height * (visible_height / len(lines))))
            max_scroll = len(lines) - visible_height
            thumb_pos = int((self.scroll_offset / max_scroll) * (visible_height - thumb_height)) if max_scroll > 0 else 0
            for i in range(visible_height):
                try:
                    if thumb_pos <= i < thumb_pos + thumb_height:
                        self.stdscr.attron(curses.color_pair(3))
                        self.stdscr.addstr(i, self.width - 1, " ")
                        self.stdscr.attroff(curses.color_pair(3))
                    else:
                        self.stdscr.addstr(i, self.width - 1, " ")
                except curses.error:
                    pass
        self.draw_status_bar()
        if self.mode == "command":
            self.draw_centered_cmdline()
        self.validate_cursor()
        cursor_y = self.cursor_line - self.scroll_offset
        cursor_x = self.cursor_col + x_offset + 7
        try:
            self.stdscr.move(cursor_y, cursor_x)
        except curses.error:
            pass
        self.stdscr.refresh()

    def jump_word(self):
        line = self.get_current_lines()[self.cursor_line]
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
        line = self.get_current_lines()[self.cursor_line]
        if not line:
            return
        pos = self.cursor_col
        while pos > 0 and not line[pos-1].isalnum():
            pos -= 1
        while pos > 0 and line[pos-1].isalnum():
            pos -= 1
        self.cursor_col = pos

    def copy_word_inline(self):
        line = self.get_current_lines()[self.cursor_line]
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

    def delete_word(self):
        line = self.get_current_lines()[self.cursor_line]
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
        lines = self.get_current_lines()
        lines[self.cursor_line] = new_line
        self.set_current_lines(lines)
        self.buffers[self.current_buffer_index]['modified'] = True
        self.cursor_col = start

    def save_file(self):
        filename = self.get_current_filename()
        if not filename:
            new_name = self.get_user_input('enter filename to save:')
            if not new_name:
                self.status_message = "save cancelled."
                return
            self.set_current_filename(new_name)
            filename = new_name
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("\n".join(self.get_current_lines()))
            self.status_message = f"{CMD_ARROW}w: write ({len(self.get_current_lines())} lines)"
            self.buffers[self.current_buffer_index]['modified'] = False
        except Exception as e:
            self.status_message = f"error saving file: {e}"

    def delete_line(self):
        lines = self.get_current_lines()
        if not lines:
            self.set_current_lines([""])
            self.cursor_line = 0
            self.cursor_col = 0
            return
        del lines[self.cursor_line]
        if not lines:
            lines = [""]
        if self.cursor_line >= len(lines):
            self.cursor_line = len(lines) - 1
        self.cursor_col = min(self.cursor_col, len(lines[self.cursor_line]))
        self.set_current_lines(lines)
        self.buffers[self.current_buffer_index]['modified'] = True

    def delete_multiple_lines(self, count):
        lines = self.get_current_lines()
        start = self.cursor_line
        end = min(start + count, len(lines))
        del lines[start:end]
        if not lines:
            lines = [""]
        if self.cursor_line >= len(lines):
            self.cursor_line = len(lines) - 1
        self.cursor_col = min(self.cursor_col, len(lines[self.cursor_line]))
        self.set_current_lines(lines)
        self.buffers[self.current_buffer_index]['modified'] = True

    def copy_line(self):
        lines = self.get_current_lines()
        if lines:
            self.clipboard = lines[self.cursor_line]

    def copy_multiple_lines(self, count):
        lines = self.get_current_lines()
        start = self.cursor_line
        end = min(start + count, len(lines))
        self.clipboard = "\n".join(lines[start:end])

    def paste_line(self):
        if self.clipboard:
            clip_lines = self.clipboard.split("\n")
            lines = self.get_current_lines()
            insertion_index = self.cursor_line + 1
            for i, line in enumerate(clip_lines):
                lines.insert(insertion_index + i, line)
            self.cursor_line = insertion_index + len(clip_lines) - 1
            self.cursor_col = 0
            self.set_current_lines(lines)
            self.buffers[self.current_buffer_index]['modified'] = True

    def cut_line(self):
        self.copy_line()
        self.delete_line()

    def delete_paragraph(self):
        lines = self.get_current_lines()
        if not lines:
            return
        start = self.cursor_line
        while start > 0 and lines[start-1].strip() != "":
            start -= 1
        end = self.cursor_line
        while end < len(lines) and lines[end].strip() != "":
            end += 1
        del lines[start:end]
        if not lines:
            lines = [""]
        self.cursor_line = start if start < len(lines) else len(lines) - 1
        self.cursor_col = 0
        self.set_current_lines(lines)
        self.buffers[self.current_buffer_index]['modified'] = True

    def copy_paragraph(self):
        lines = self.get_current_lines()
        if not lines:
            return
        start = self.cursor_line
        while start > 0 and lines[start-1].strip() != "":
            start -= 1
        end = self.cursor_line
        while end < len(lines) and lines[end].strip() != "":
            end += 1
        self.clipboard = "\n".join(lines[start:end])

    def process_command_line(self, command, prefix=""):
        cmd = command.strip()
        cmd_lower = cmd.lower()
        # Command-mode commands are logged with the prefix.
        if cmd_lower == "tb":
            selection = self.choose_buffer_menu()
            if selection is not None:
                self.buffers[self.current_buffer_index]['cursor_line'] = self.cursor_line
                self.buffers[self.current_buffer_index]['cursor_col'] = self.cursor_col
                self.buffers[self.current_buffer_index]['scroll'] = self.scroll_offset
                self.current_buffer_index = selection
                self.cursor_line = self.buffers[self.current_buffer_index].get('cursor_line', 0)
                self.cursor_col = self.buffers[self.current_buffer_index].get('cursor_col', 0)
                self.scroll_offset = self.buffers[self.current_buffer_index].get('scroll', 0)
                self.log_command(prefix + "tb: bufmenu")
            return
        elif cmd_lower in ["m", "menu"]:
            self.title_screen()
            return
        elif cmd_lower in ["write", "w"]:
            self.save_file()
            bytes_written = len("\n".join(self.get_current_lines()))
            self.log_command(prefix + f"w: write ({bytes_written} bytes)")
            return
        elif cmd_lower in ["wq"]:
            self.save_file()
            sys.exit()
        elif cmd_lower in ["quit", "q"]:
            sys.exit()
        elif cmd_lower.startswith("fd") or cmd_lower.startswith("file delete"):
            filename = self.get_current_filename()
            if filename and os.path.exists(filename):
                try:
                    os.remove(filename)
                    self.buffers[self.current_buffer_index]['filename'] = None
                    self.buffers[self.current_buffer_index]['lines'] = [""]
                    self.cursor_line = 0
                    self.cursor_col = 0
                    self.scroll_offset = 0
                    self.buffers[self.current_buffer_index]['modified'] = False
                    self.status_message = prefix + "fd: fdelete"
                except Exception as e:
                    self.status_message = f"error deleting file: {e}"
            else:
                self.status_message = "no file to delete."
            return
        elif cmd_lower.startswith("fr") or cmd_lower.startswith("file rename"):
            parts = cmd.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                self.status_message = "no new filename provided."
                return
            new_filename = parts[1].strip()
            if not self.get_current_filename():
                self.status_message = "no file to rename."
            else:
                try:
                    os.rename(self.get_current_filename(), new_filename)
                    self.buffers[self.current_buffer_index]['filename'] = new_filename
                    try:
                        with open(new_filename, 'w', encoding='utf-8') as f:
                            f.write("\n".join(self.get_current_lines()))
                        self.status_message = prefix + "fr: rename"
                        self.buffers[self.current_buffer_index]['modified'] = False
                    except Exception as e:
                        self.status_message = f"error renaming file: {e}"
                        self.buffers[self.current_buffer_index]['modified'] = True
                except Exception as e:
                    self.status_message = f"error renaming file: {e}"
            return
        elif cmd_lower.startswith("fn") or cmd_lower.startswith("file new"):
            parts = cmd.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                self.status_message = "no filename provided."
                return
            new_filename = parts[1].strip()
            try:
                with open(new_filename, 'w', encoding='utf-8') as f:
                    pass
            except Exception as e:
                self.status_message = f"error creating file: {e}"
            else:
                self.buffers[self.current_buffer_index]['cursor_line'] = self.cursor_line
                self.buffers[self.current_buffer_index]['cursor_col'] = self.cursor_col
                self.buffers[self.current_buffer_index]['scroll'] = self.scroll_offset
                new_buf = {'filename': new_filename, 'lines': [""],
                           'cursor_line': 0, 'cursor_col': 0, 'scroll': 0,
                           'modified': False}
                self.buffers.append(new_buf)
                self.current_buffer_index = len(self.buffers) - 1
                self.cursor_line = self.buffers[self.current_buffer_index]['cursor_line']
                self.cursor_col = self.buffers[self.current_buffer_index]['cursor_col']
                self.scroll_offset = self.buffers[self.current_buffer_index]['scroll']
                self.status_message = prefix + "fn: new"
            return
        elif cmd_lower.startswith("f "):
            search_str = cmd[2:].strip()
            if not search_str:
                self.status_message = "search string empty."
                return
            selected_node = self.fuzzy_file_finder(search_str)
            if selected_node:
                try:
                    with open(selected_node.path, 'r', encoding='utf-8') as f:
                        content = f.read().splitlines()
                    self.buffers[self.current_buffer_index]['cursor_line'] = self.cursor_line
                    self.buffers[self.current_buffer_index]['cursor_col'] = self.cursor_col
                    self.buffers[self.current_buffer_index]['scroll'] = self.scroll_offset
                    new_buffer = {'filename': selected_node.path, 'lines': content,
                                  'cursor_line': 0, 'cursor_col': 0, 'scroll': 0,
                                  'modified': False}
                    self.buffers.append(new_buffer)
                    self.current_buffer_index = len(self.buffers) - 1
                    self.cursor_line = self.buffers[self.current_buffer_index]['cursor_line']
                    self.cursor_col = self.buffers[self.current_buffer_index]['cursor_col']
                    self.scroll_offset = self.buffers[self.current_buffer_index]['scroll']
                    self.log_command(prefix + "f: search")
                except Exception as e:
                    self.status_message = f"error opening file: {e}"
            else:
                self.status_message = f"no match for '{search_str}'."
            return
        else:
            for token in cmd_lower.split():
                if token == 'c' or token == "clear":
                    self.set_current_lines([""])
                    self.cursor_line = 0
                    self.cursor_col = 0
                    self.log_command(prefix + "c: clear")
                    self.status_message = "file cleared."
                elif token == 'w':
                    self.save_file()
                    bytes_written = len("\n".join(self.get_current_lines()))
                    self.log_command(prefix + f"w: write ({bytes_written} bytes)")
                elif token == 's':
                    self.sidebar_visible = not self.sidebar_visible
                    self.log_command(prefix + f"s: sidebar {'on' if self.sidebar_visible else 'off'}")
                    self.status_message = f"sidebar {'on' if self.sidebar_visible else 'off'}."
                elif token == 'h':
                    self.sidebar_help_mode = True
                    self.help_mode_expiry = time.time() + 3  # show help for 3 seconds
                    self.log_command(prefix + "h: help on")
                    self.status_message = "help on."
                elif token == 't':
                    if self.mode != "filetree":
                        self.mode = "filetree"
                        self.file_tree_root = build_tree(os.getcwd(), show_hidden=self.show_hidden)
                        if self.file_tree_root.is_dir:
                            self.file_tree_root.expanded = True
                        self.flat_file_list = flatten_tree(self.file_tree_root)
                        self.filetree_selection_index = 0
                        self.filetree_scroll_offset = 0
                        self.log_command(prefix + "t: filetree")
                        self.status_message = "file tree activated."
                    else:
                        self.mode = "normal"
                        self.log_command(prefix + "t: normal")
                        self.status_message = "normal mode."
                elif token == 'q':
                    self.log_command(prefix + "q: quit")
                    sys.exit()
                elif token == 'z':
                    if len(self.buffers) > 1:
                        self.buffers[self.current_buffer_index]['cursor_line'] = self.cursor_line
                        self.buffers[self.current_buffer_index]['cursor_col'] = self.cursor_col
                        self.buffers[self.current_buffer_index]['scroll'] = self.scroll_offset
                        self.current_buffer_index = (self.current_buffer_index - 1) % len(self.buffers)
                        self.cursor_line = self.buffers[self.current_buffer_index].get('cursor_line', 0)
                        self.cursor_col = self.buffers[self.current_buffer_index].get('cursor_col', 0)
                        self.scroll_offset = self.buffers[self.current_buffer_index].get('scroll', 0)
                        self.status_message = prefix + f"goto[{self.cursor_line+1}]"
                elif token == 'x':
                    if len(self.buffers) > 1:
                        self.buffers[self.current_buffer_index]['cursor_line'] = self.cursor_line
                        self.buffers[self.current_buffer_index]['cursor_col'] = self.cursor_col
                        self.buffers[self.current_buffer_index]['scroll'] = self.scroll_offset
                        self.current_buffer_index = (self.current_buffer_index + 1) % len(self.buffers)
                        self.cursor_line = self.buffers[self.current_buffer_index].get('cursor_line', 0)
                        self.cursor_col = self.buffers[self.current_buffer_index].get('cursor_col', 0)
                        self.scroll_offset = self.buffers[self.current_buffer_index].get('scroll', 0)
                        self.status_message = prefix + "x: movebuf"
                elif token.isdigit():
                    self.cursor_line = int(token) - 1
                    self.cursor_col = min(self.cursor_col, len(self.get_current_lines()[self.cursor_line]))
                    self.log_command(prefix + f"goto[{token}]")
                elif len(token) >= 2 and token[:-1].isdigit() and token[-1] in ['y','d']:
                    count = int(token[:-1])
                    if token[-1] == 'y':
                        self.copy_multiple_lines(count)
                        self.log_command(prefix + f"y: copy[{count}]")
                    elif token[-1] == 'd':
                        self.delete_multiple_lines(count)
                        self.log_command(prefix + f"d: delete[{count}]")
                elif token == "tb":
                    selection = self.choose_buffer_menu()
                    if selection is not None:
                        self.buffers[self.current_buffer_index]['cursor_line'] = self.cursor_line
                        self.buffers[self.current_buffer_index]['cursor_col'] = self.cursor_col
                        self.buffers[self.current_buffer_index]['scroll'] = self.scroll_offset
                        self.current_buffer_index = selection
                        self.cursor_line = self.buffers[self.current_buffer_index].get('cursor_line', 0)
                        self.cursor_col = self.buffers[self.current_buffer_index].get('cursor_col', 0)
                        self.scroll_offset = self.buffers[self.current_buffer_index].get('scroll', 0)
                        self.log_command(prefix + "tb: bufmenu")
                # End token loop.
    
    def process_filetree_mode(self, key):
        if key == curses.KEY_UP:
            if self.filetree_selection_index > 0:
                self.filetree_selection_index -= 1
        elif key == curses.KEY_DOWN:
            if self.filetree_selection_index < len(self.flat_file_list) - 1:
                self.filetree_selection_index += 1
        elif key in (10, curses.KEY_ENTER, curses.KEY_RIGHT):
            node, depth = self.flat_file_list[self.filetree_selection_index]
            if node.is_dir:
                node.toggle_expanded()
                self.flat_file_list = flatten_tree(self.file_tree_root)
            else:
                try:
                    with open(node.path, 'r', encoding='utf-8') as f:
                        content = f.read().splitlines()
                except Exception as e:
                    self.status_message = f"error opening file: {e}"
                else:
                    self.buffers[self.current_buffer_index]['cursor_line'] = self.cursor_line
                    self.buffers[self.current_buffer_index]['cursor_col'] = self.cursor_col
                    self.buffers[self.current_buffer_index]['scroll'] = self.scroll_offset
                    new_buffer = {'filename': node.path, 'lines': content,
                                  'cursor_line': 0, 'cursor_col': 0, 'scroll': 0,
                                  'modified': False}
                    self.buffers.append(new_buffer)
                    self.current_buffer_index = len(self.buffers) - 1
                    self.cursor_line = self.buffers[self.current_buffer_index]['cursor_line']
                    self.cursor_col = self.buffers[self.current_buffer_index]['cursor_col']
                    self.scroll_offset = self.buffers[self.current_buffer_index]['scroll']
                    self.mode = "normal"
                    self.log_command("󰘍f: opened")
        elif key == curses.KEY_LEFT:
            node, depth = self.flat_file_list[self.filetree_selection_index]
            if node.is_dir and node.expanded:
                node.toggle_expanded()
                self.flat_file_list = flatten_tree(self.file_tree_root)
            else:
                if node.parent is not None:
                    for i, (n, d) in enumerate(self.flat_file_list):
                        if n == node.parent:
                            self.filetree_selection_index = i
                            break
        elif key == ord('a'):
            self.show_hidden = not self.show_hidden
            self.file_tree_root = build_tree(self.file_tree_root.path, parent=None, show_hidden=self.show_hidden)
            if self.file_tree_root.is_dir:
                self.file_tree_root.expanded = True
            self.flat_file_list = flatten_tree(self.file_tree_root)
            self.filetree_selection_index = 0
            self.status_message = f"hidden {'shown' if self.show_hidden else 'hidden'}."
        elif key == 27:
            self.mode = "normal"
            self.status_message = "exited file tree mode."

    def process_normal_mode(self, key):
        if self.normal_number_buffer and key in (10, curses.KEY_ENTER):
            line_number = int(self.normal_number_buffer) - 1
            if 0 <= line_number < len(self.get_current_lines()):
                self.cursor_line = line_number
                self.cursor_col = min(self.cursor_col, len(self.get_current_lines()[self.cursor_line]))
            self.normal_number_buffer = ""
            return

        if key == ord(' '):
            if self.cursor_col < len(self.get_current_lines()[self.cursor_line]):
                self.cursor_col += 1
            return
        if key in (10, curses.KEY_ENTER):
            lines = self.get_current_lines()
            lines.insert(self.cursor_line+1, "")
            self.set_current_lines(lines)
            self.buffers[self.current_buffer_index]['modified'] = True
            self.cursor_line += 1
            self.cursor_col = 0
            return
        if self.word_mode:
            sub = chr(key)
            if sub == 'j':
                self.jump_word()
                self.log_command("wj: jump word")
            elif sub == 'h':
                self.jump_back_word()
                self.log_command("wh: jump back")
            elif sub == 'd':
                self.delete_word()
                self.log_command("wd: delete word")
            elif sub == 'y':
                word = self.copy_word_inline()
                self.word_clipboard = word
                self.log_command("wy: copy word")
            else:
                self.log_command(f"w{sub}: unknown")
            self.word_mode = False
            return
        if key == ord('w'):
            self.word_mode = True
            return
        if 48 <= key <= 57:
            self.normal_number_buffer += chr(key)
            self.last_digit_time = time.time()
            return
        if self.normal_number_buffer:
            count_commands = ('d', 'y', 'D', 'x')
            try:
                ch = chr(key)
                if ch in count_commands:
                    count = int(self.normal_number_buffer)
                    self.normal_number_buffer = ""
                    if ch == 'd':
                        self.delete_multiple_lines(count)
                        return
                    elif ch == 'y':
                        self.copy_multiple_lines(count)
                        return
                    elif ch == 'D':
                        self.delete_paragraph()
                        return
                    elif ch == 'x':
                        if len(self.buffers) > 1:
                            self.buffers[self.current_buffer_index]['cursor_line'] = self.cursor_line
                            self.buffers[self.current_buffer_index]['cursor_col'] = self.cursor_col
                            self.buffers[self.current_buffer_index]['scroll'] = self.scroll_offset
                            self.current_buffer_index = (self.current_buffer_index + 1) % len(self.buffers)
                            self.cursor_line = self.buffers[self.current_buffer_index].get('cursor_line', 0)
                            self.cursor_col = self.buffers[self.current_buffer_index].get('cursor_col', 0)
                            self.scroll_offset = self.buffers[self.current_buffer_index].get('scroll', 0)
                            self.status_message = f"switched to buffer {self.current_buffer_index + 1}"
                        return
                else:
                    line_number = int(self.normal_number_buffer) - 1
                    self.normal_number_buffer = ""
                    if 0 <= line_number < len(self.get_current_lines()):
                        self.cursor_line = line_number
                        self.cursor_col = min(self.cursor_col, len(self.get_current_lines()[self.cursor_line]))
            except (ValueError, OverflowError):
                self.normal_number_buffer = ""
        if key == ord('j'):
            self.cursor_col = len(self.get_current_lines()[self.cursor_line])
            self.log_command("j: jumpline")
            return
        elif key == ord('h'):
            self.cursor_col = 0
            self.log_command("h: startline")
            return
        elif key == ord('i'):
            self.mode = "insert"
            self.log_command("i: insert")
        elif key == ord('o'):
            self.mode = "command"
            self.command_buffer = ""
            self.log_command("o: command")
        elif key == ord('d'):
            self.delete_line()
            self.log_command("d: delete line")
        elif key == ord('D'):
            self.delete_paragraph()
            self.log_command("d: delete para")
        elif key == ord('y'):
            self.copy_line()
            self.log_command("y: copy line")
        elif key == ord('Y'):
            self.copy_paragraph()
            self.log_command("y: copy para")
        elif key == ord('u'):
            if self.word_clipboard:
                line = self.get_current_lines()[self.cursor_line]
                new_line = line[:self.cursor_col] + self.word_clipboard + line[self.cursor_col:]
                lines = self.get_current_lines()
                lines[self.cursor_line] = new_line
                self.set_current_lines(lines)
                self.cursor_col += len(self.word_clipboard)
                self.log_command("u: paste word")
                self.word_clipboard = ""
                self.buffers[self.current_buffer_index]['modified'] = True
            else:
                self.paste_line()
                self.log_command("u: paste")
        elif key == ord('x'):
            if len(self.buffers) > 1:
                self.buffers[self.current_buffer_index]['cursor_line'] = self.cursor_line
                self.buffers[self.current_buffer_index]['cursor_col'] = self.cursor_col
                self.buffers[self.current_buffer_index]['scroll'] = self.scroll_offset
                self.current_buffer_index = (self.current_buffer_index + 1) % len(self.buffers)
                self.cursor_line = self.buffers[self.current_buffer_index].get('cursor_line', 0)
                self.cursor_col = self.buffers[self.current_buffer_index].get('cursor_col', 0)
                self.scroll_offset = self.buffers[self.current_buffer_index].get('scroll', 0)
                self.status_message = "switched to buffer " + str(self.current_buffer_index + 1)
        elif key == curses.KEY_UP and self.cursor_line > 0:
            self.cursor_line -= 1
        elif key == curses.KEY_DOWN and self.cursor_line < len(self.get_current_lines()) - 1:
            self.cursor_line += 1
            self.cursor_col = min(self.cursor_col, len(self.get_current_lines()[self.cursor_line]))
        elif key == curses.KEY_LEFT and self.cursor_col > 0:
            self.cursor_col -= 1
        elif key == curses.KEY_RIGHT and self.cursor_col < len(self.get_current_lines()[self.cursor_line]):
            self.cursor_col += 1
        elif key == curses.KEY_HOME:
            self.cursor_col = 0
            return
        elif key == curses.KEY_END:
            self.cursor_col = len(self.get_current_lines()[self.cursor_line])
            return
        elif key == curses.KEY_PPAGE:
            visible_height = max(1, self.height)
            self.scroll_offset = max(0, self.scroll_offset - visible_height)
            self.cursor_line = max(0, self.cursor_line - visible_height)
        elif key == curses.KEY_NPAGE:
            visible_height = max(1, self.height)
            if self.scroll_offset < len(self.get_current_lines()) - visible_height:
                self.scroll_offset = min(len(self.get_current_lines()) - visible_height, self.scroll_offset + visible_height)
            self.cursor_line = min(len(self.get_current_lines()) - 1, self.cursor_line + visible_height)
        if self.mode == "normal" and self.normal_number_buffer:
            if time.time() - self.last_digit_time > self.normal_number_timeout:
                try:
                    line_number = int(self.normal_number_buffer) - 1
                    if 0 <= line_number < len(self.get_current_lines()):
                        self.cursor_line = line_number
                        self.cursor_col = min(self.cursor_col, len(self.get_current_lines()[self.cursor_line]))
                except Exception:
                    pass
                self.normal_number_buffer = ""

    def process_insert_mode(self, key):
        self.validate_cursor()
        if key == 27:
            self.mode = "normal"
        elif key in (10, curses.KEY_ENTER):
            lines = self.get_current_lines()
            lines.insert(self.cursor_line+1, lines[self.cursor_line][self.cursor_col:])
            lines[self.cursor_line] = lines[self.cursor_line][:self.cursor_col]
            self.set_current_lines(lines)
            self.buffers[self.current_buffer_index]['modified'] = True
            self.cursor_line += 1
            self.cursor_col = 0
        elif key in (8, 127, curses.KEY_BACKSPACE):
            lines = self.get_current_lines()
            if self.cursor_col > 0:
                lines[self.cursor_line] = (lines[self.cursor_line][:self.cursor_col-1] +
                                           lines[self.cursor_line][self.cursor_col:])
                self.cursor_col -= 1
            elif self.cursor_line > 0:
                prev_len = len(lines[self.cursor_line-1])
                lines[self.cursor_line-1] += lines[self.cursor_line]
                del lines[self.cursor_line]
                self.cursor_line -= 1
                self.cursor_col = prev_len
            self.set_current_lines(lines)
            self.buffers[self.current_buffer_index]['modified'] = True
        elif key == 9:
            lines = self.get_current_lines()
            lines[self.cursor_line] = (lines[self.cursor_line][:self.cursor_col] +
                                       '\t' +
                                       lines[self.cursor_line][self.cursor_col:])
            self.cursor_col += 1
            self.set_current_lines(lines)
            self.buffers[self.current_buffer_index]['modified'] = True
        elif 32 <= key <= 126:
            lines = self.get_current_lines()
            lines[self.cursor_line] = (lines[self.cursor_line][:self.cursor_col] +
                                       chr(key) +
                                       lines[self.cursor_line][self.cursor_col:])
            self.cursor_col += 1
            self.set_current_lines(lines)
            self.buffers[self.current_buffer_index]['modified'] = True
        elif key == curses.KEY_LEFT and self.cursor_col > 0:
            self.cursor_col -= 1
        elif key == curses.KEY_RIGHT and self.cursor_col < len(self.get_current_lines()[self.cursor_line]):
            self.cursor_col += 1
        elif key == curses.KEY_UP and self.cursor_line > 0:
            self.cursor_line -= 1
            self.cursor_col = min(self.cursor_col, len(self.get_current_lines()[self.cursor_line]))
        elif key == curses.KEY_DOWN and self.cursor_line < len(self.get_current_lines()) - 1:
            self.cursor_line += 1
            self.cursor_col = min(self.cursor_col, len(self.get_current_lines()[self.cursor_line]))
        elif key == curses.KEY_HOME:
            self.cursor_col = 0
        elif key == curses.KEY_END:
            self.cursor_col = len(self.get_current_lines()[self.cursor_line])
        self.validate_cursor()

    def process_command_mode(self, key):
        if key == 27:
            self.mode = "normal"
            self.command_buffer = ""
        elif key in (10, curses.KEY_ENTER):
            self.mode = "normal"
            cmd = self.command_buffer.strip()
            self.command_buffer = ""
            self.process_command_line(cmd, "󰘍")
        elif key in (8, curses.KEY_BACKSPACE, 127):
            self.command_buffer = self.command_buffer[:-1]
        elif 32 <= key <= 126:
            self.command_buffer += chr(key)

    def run(self):
        if self.get_current_filename() is None:
            self.title_screen()
        self.stdscr.clear()
        try:
            curses.curs_set(2)
        except Exception:
            try:
                curses.curs_set(1)
            except Exception:
                pass
        self.stdscr.timeout(-1)
        while True:
            self.display()
            key = self.stdscr.getch()
            if key == 27:
                if self.mode != "filetree":
                    self.mode = "normal"
                    self.command_buffer = ""
                    self.status_message = ""
            if self.mode == "normal":
                self.process_normal_mode(key)
            elif self.mode == "insert":
                self.process_insert_mode(key)
            elif self.mode == "command":
                self.process_command_mode(key)
            elif self.mode == "filetree":
                self.process_filetree_mode(key)
            self.status_message = ""

def main(stdscr):
    """
    Main entry point.
    Initializes extended colors for a modern dark theme if supported.
    """
    if curses.has_colors():
        curses.start_color()
        extended = curses.can_change_color() and curses.COLORS >= 256
        if extended:
            def to_curses(r, g, b):
                return int(r/255*1000), int(g/255*1000), int(b/255*1000)
            # dracula-inspired palette:
            bg_color     = to_curses(40, 42, 54)      # main background
            fg_color     = to_curses(248, 248, 242)   # main foreground
            sel_color    = to_curses(68, 71, 90)      # selection
            accent_color = to_curses(98, 114, 164)    # accent
            ft_bg_color  = to_curses(51, 54, 71)      # file tree background
            sidebar_bg   = to_curses(52, 55, 70)      # sidebar background

            try:
                curses.init_color(16, *bg_color)
                curses.init_color(17, *fg_color)
                curses.init_color(18, *sel_color)
                curses.init_color(19, *accent_color)
                curses.init_color(20, *ft_bg_color)
                curses.init_color(22, *sidebar_bg)

                curses.init_pair(1, 17, 18)  # selections
                curses.init_pair(2, 17, 16)  # main text
                curses.init_pair(3, 19, 16)  # scrollbar/right status & cmd box
                curses.init_pair(4, 17, 22)  # sidebar text
                curses.init_pair(5, 17, 19)  # powerline segments (status/cmd box)
                curses.init_pair(6, 17, 16)  # ascii logo
                curses.init_pair(7, 17, 20)  # menu background / file tree
            except curses.error:
                curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
                curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)
                curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)
                curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLUE)
                curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_BLUE)
                curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLACK)
                curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLUE)
        else:
            curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
            curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)
            curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)
            curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLUE)
            curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_BLUE)
            curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLACK)
            curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLUE)
    else:
        pass

    editor = CursesTextEditor(stdscr)
    if len(sys.argv) > 1:
        editor.set_current_filename(sys.argv[1])
        try:
            with open(editor.get_current_filename(), 'r', encoding='utf-8') as f:
                editor.set_current_lines(f.read().splitlines())
        except FileNotFoundError:
            editor.status_message = f"file not found: {editor.get_current_filename()}"
        except Exception as e:
            editor.status_message = f"error opening file: {e}"
    if editor.get_current_filename() is not None and not editor.buffers:
        editor.buffers.append({'filename': editor.get_current_filename(), 'lines': editor.get_current_lines()})
    editor.run()

if __name__ == "__main__":
    curses.wrapper(main)
