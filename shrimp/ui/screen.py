"""
shrimp/ui/screen.py

Implements all UI–drawing functionality for the Shrimp text editor,
while respecting the user-selected theme for a multi-colored Powerline status bar,
and including the original sidebar, file tree, and dialog methods.
"""

import os
import curses
import time
import subprocess
from shrimp import logger, filetree
from shrimp import plugins
from wcwidth import wcswidth

# Icons and symbols
FOLDER_ICON_CLOSED = " "
FOLDER_ICON_OPEN   = " "
FOLDER_SYMBOL      = ""
FILE_ICONS = {
    ".py": "",
    ".md": "",
    ".txt": "",
    ".sh": "",
    ".yaml": "",
    ".conf": "",
    ".yml": "",
    ".json": "",
    ".lua": "",
}
DEFAULT_FILE_ICON = ""

# Command/menu icons and symbols
CMD_ARROW = "󰘍"
MENU_NEW_FILE  = ""
MENU_FILE_TREE = ""
MENU_DIRECTORY = ""
MENU_FIND_FILE = ""
MENU_QUIT      = ""

# Powerline arrow symbol (classic shape)
POWERLINE_ARROW = ""

###############################################################################
# POWERLINE & THEME FUNCTIONS (New Features)
###############################################################################

def get_git_branch(filename: str) -> str or None:
    """
    Returns the current Git branch for the directory containing `filename`,
    or None if not in a Git repo or if filename is empty.
    """
    if not filename:
        return None
    directory = os.path.dirname(os.path.abspath(filename))
    try:
        branch_bytes = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=directory,
            stderr=subprocess.STDOUT
        )
        return branch_bytes.decode("utf-8").strip()
    except Exception:
        return None

def apply_powerline_theme(context):
    """
    Sets up dynamic curses color pairs for the Powerline status bar using user theme data.
    
    Uses four theme colors (from the user's current theme):
      - seg1: For the mode segment (from theme_data["accent"])
      - seg2: For the filename segment (from theme_data["highlight"])
      - seg3: For the Git branch segment (from theme_data["sel"])
      - seg4: For the time segment (from theme_data["sidebar"])
    
    Also sets up arrow transition pairs:
      - arrow1_2: from seg1 to seg2
      - arrow2_3: from seg2 to seg3
      - arrow3_4: from seg3 to seg4
    
    If extended color support is available, custom RGB colors are defined.
    Otherwise, we fallback to basic curses colors by mapping theme strings (if available).
    """
    theme_data = context.available_themes.get(context.current_theme)
    if not theme_data:
        return

    if context.extended_color_support:
        def to_curses(rgb):
            return int(rgb[0]/255*1000), int(rgb[1]/255*1000), int(rgb[2]/255*1000)
        seg1_bg = theme_data["accent"]
        seg2_bg = theme_data["highlight"]
        seg3_bg = theme_data["sel"]
        seg4_bg = theme_data["sidebar"]
        text_fg = theme_data["fg"]
        # Use arbitrary free color indexes
        seg1_idx = 250
        seg2_idx = 251
        seg3_idx = 252
        seg4_idx = 253
        fg_idx   = 254
        try:
            curses.init_color(seg1_idx, *to_curses(seg1_bg))
            curses.init_color(seg2_idx, *to_curses(seg2_bg))
            curses.init_color(seg3_idx, *to_curses(seg3_bg))
            curses.init_color(seg4_idx, *to_curses(seg4_bg))
            curses.init_color(fg_idx,   *to_curses(text_fg))
        except curses.error:
            pass
        curses.init_pair(100, fg_idx, seg1_idx)
        curses.init_pair(101, seg1_idx, seg2_idx)
        curses.init_pair(102, fg_idx, seg2_idx)
        curses.init_pair(103, seg2_idx, seg3_idx)
        curses.init_pair(104, fg_idx, seg3_idx)
        curses.init_pair(105, seg3_idx, seg4_idx)
        curses.init_pair(106, fg_idx, seg4_idx)
        context.powerline_pairs = {
            "seg1": 100,
            "arrow1_2": 101,
            "seg2": 102,
            "arrow2_3": 103,
            "seg3": 104,
            "arrow3_4": 105,
            "seg4": 106
        }
    else:
        # Fallback: use basic curses colors with theme data if provided.
        def get_basic_color(color_value, default):
            if isinstance(color_value, str):
                mapping = {
                    "black": curses.COLOR_BLACK,
                    "red": curses.COLOR_RED,
                    "green": curses.COLOR_GREEN,
                    "yellow": curses.COLOR_YELLOW,
                    "blue": curses.COLOR_BLUE,
                    "magenta": curses.COLOR_MAGENTA,
                    "cyan": curses.COLOR_CYAN,
                    "white": curses.COLOR_WHITE
                }
                return mapping.get(color_value.lower(), default)
            elif isinstance(color_value, int):
                return color_value
            else:
                return default

        if theme_data:
            seg1_color = get_basic_color(theme_data.get("accent"), curses.COLOR_RED)
            seg2_color = get_basic_color(theme_data.get("highlight"), curses.COLOR_GREEN)
            seg3_color = get_basic_color(theme_data.get("sel"), curses.COLOR_YELLOW)
            seg4_color = get_basic_color(theme_data.get("sidebar"), curses.COLOR_BLUE)
            fg_color   = get_basic_color(theme_data.get("fg"), curses.COLOR_WHITE)
        else:
            seg1_color = curses.COLOR_RED
            seg2_color = curses.COLOR_GREEN
            seg3_color = curses.COLOR_YELLOW
            seg4_color = curses.COLOR_BLUE
            fg_color   = curses.COLOR_WHITE

        curses.init_pair(100, fg_color, seg1_color)
        curses.init_pair(101, seg1_color, seg2_color)
        curses.init_pair(102, fg_color, seg2_color)
        curses.init_pair(103, seg2_color, seg3_color)
        curses.init_pair(104, fg_color, seg3_color)
        curses.init_pair(105, seg3_color, seg4_color)
        curses.init_pair(106, fg_color, seg4_color)
        context.powerline_pairs = {
            "seg1": 100,
            "arrow1_2": 101,
            "seg2": 102,
            "arrow2_3": 103,
            "seg3": 104,
            "arrow3_4": 105,
            "seg4": 106
        }

def draw_powerline_segment(stdscr, y, x, text, seg_pair, arrow_pair=None):
    """
    Draw a segment with text using color pair seg_pair; if arrow_pair is provided,
    draw the Powerline arrow afterward.
    Returns the new x position.
    """
    try:
        stdscr.attron(curses.color_pair(seg_pair))
        stdscr.addstr(y, x, text)
        stdscr.attroff(curses.color_pair(seg_pair))
    except curses.error:
        pass
    x += len(text)
    if arrow_pair is not None:
        try:
            stdscr.attron(curses.color_pair(arrow_pair))
            stdscr.addstr(y, x, POWERLINE_ARROW)
            stdscr.attroff(curses.color_pair(arrow_pair))
        except curses.error:
            pass
        x += len(POWERLINE_ARROW)
    return x

def draw_status_bar(context):
    """
    Draw a Powerline-style status bar that spans the entire width of the screen.
    Left segments display mode, filename, and (if available) the Git branch.
    The remaining area is filled with the background color for the time segment,
    and the time is drawn flush to the right.

    Now, the theme is updated each time this function is called so that dynamic theme
    changes are immediately reflected in the status bar.
    """
    # Always update the powerline color pairs on each draw
    apply_powerline_theme(context)
    pairs = context.powerline_pairs
    status_y = context.height - 1

    if context.zen_mode:
        mode_seg = f" {context.mode.upper()} "
        x = 0
        try:
            context.stdscr.addstr(status_y, x, mode_seg, curses.color_pair(5))
        except curses.error:
            pass
        x += len(mode_seg)
        arrow = ""
        try:
            context.stdscr.addstr(status_y, x, arrow, curses.color_pair(3))
        except curses.error:
            pass
        x += len(arrow)
        time_seg = f" {time.strftime('%H:%M:%S')} "
        time_seg_len = len(time_seg)
        for pos in range(x, context.width - time_seg_len):
            try:
                context.stdscr.addch(status_y, pos, ' ', curses.color_pair(3))
            except curses.error:
                pass
        try:
            context.stdscr.addstr(status_y, context.width - time_seg_len, time_seg, curses.color_pair(3))
        except curses.error:
            pass
        return

    x = 0
    # Draw Mode Segment
    mode_text = f" {context.mode_icons.get(context.mode, '')} {context.mode.upper()} "
    x = draw_powerline_segment(context.stdscr, status_y, x,
                               text=mode_text,
                               seg_pair=pairs["seg1"],
                               arrow_pair=pairs["arrow1_2"])
    # Draw Filename Segment
    fname = context.get_current_filename() or "new file"
    dirty_mark = "*" if context.current_buffer.modified else ""
    buf_info = f" [{context.current_buffer_index+1}/{len(context.buffers)}]" if len(context.buffers) > 1 else ""
    file_text = f" {os.path.basename(fname)}{dirty_mark}{buf_info} "
    x = draw_powerline_segment(context.stdscr, status_y, x,
                               text=file_text,
                               seg_pair=pairs["seg2"],
                               arrow_pair=pairs["arrow2_3"])
    # Optionally draw Git branch segment if available.
    branch = get_git_branch(context.get_current_filename())
    if branch:
        branch_text = f"  {branch} "
        x = draw_powerline_segment(context.stdscr, status_y, x,
                                   text=branch_text,
                                   seg_pair=pairs["seg3"],
                                   arrow_pair=pairs["arrow3_4"])
    # Prepare Time Segment to be right-aligned.
    time_text = f" {time.strftime('%H:%M:%S')} "
    time_text_len = len(time_text)
    if x < context.width - time_text_len:
        filler_length = context.width - time_text_len - x
        filler_text = " " * filler_length
        try:
            context.stdscr.attron(curses.color_pair(pairs["seg4"]))
            context.stdscr.addstr(status_y, x, filler_text)
            context.stdscr.attroff(curses.color_pair(pairs["seg4"]))
        except curses.error:
            pass
        x = context.width - time_text_len
    else:
        x = context.width - time_text_len
    # Draw Time Segment flush right.
    try:
        context.stdscr.attron(curses.color_pair(pairs["seg4"]))
        context.stdscr.addstr(status_y, x, time_text)
        context.stdscr.attroff(curses.color_pair(pairs["seg4"]))
    except curses.error:
        pass

def draw_centered_cmdline(context):
    """
    Draw a centered command-line dialog box.
    """
    box_width = max(40, len(context.command_buffer) + 10)
    box_height = 5
    start_y = (context.height - box_height) // 2
    start_x = (context.width - box_width) // 2

    top_border    = "┌" + "─" * (box_width - 2) + "┐"
    bottom_border = "└" + "─" * (box_width - 2) + "┘"
    title = " cmdline "

    if len(title) < box_width - 2:
        title_start = (box_width - 2 - len(title)) // 2
        top_line = ("┌" + " " * title_start + title +
                    " " * (box_width - 2 - title_start - len(title)) + "┐")
    else:
        top_line = top_border

    content = f"{CMD_ARROW} {context.command_buffer}"
    content = content[:box_width - 4].ljust(box_width - 4)
    content_line = "│ " + content + " │"

    try:
        context.stdscr.addstr(start_y, start_x, top_line, curses.color_pair(3) | curses.A_BOLD)
        context.stdscr.addstr(start_y + 1, start_x, content_line, curses.color_pair(3) | curses.A_BOLD)
        context.stdscr.addstr(start_y + 2, start_x, bottom_border, curses.color_pair(3) | curses.A_BOLD)
    except curses.error:
        pass

###############################################################################
# ORIGINAL SIDEBAR & FILETREE FUNCTIONS (From Original Version)
###############################################################################

def draw_segment(context, y, x, text, color_pair, arrow=""):
    """Helper for drawing a colored text segment with an optional arrow."""
    try:
        context.stdscr.attron(curses.color_pair(color_pair))
        context.stdscr.addstr(y, x, text)
        context.stdscr.attroff(curses.color_pair(color_pair))
    except curses.error:
        pass
    x += len(text)
    if arrow:
        try:
            context.stdscr.attron(curses.color_pair(color_pair))
            context.stdscr.addstr(y, x, arrow)
            context.stdscr.attroff(curses.color_pair(color_pair))
        except curses.error:
            pass
        x += len(arrow)
    return x

def draw_sidebar(context, sidebar_width):
    """
    Draw the left sidebar if context.sidebar_visible is True.
    In normal mode, displays current time, title, and help or log messages.
    In filetree or search mode, delegates to respective methods.
    """
    for i in range(context.height):
        try:
            context.stdscr.addstr(i, 0, " " * sidebar_width, curses.color_pair(4))
        except curses.error:
            pass

    if context.mode == "search":
        draw_search_sidebar(context, sidebar_width)
        return
    if context.mode == "filetree":
        draw_filetree(context, sidebar_width)
        return

    if context.help_mode_expiry and time.time() > context.help_mode_expiry:
        context.sidebar_help_mode = False
        context.help_mode_expiry = None

    y = 0
    x = 1
    current_time = time.strftime("%H:%M:%S")
    x = draw_segment(context, y, x, f" {current_time} ", 4)
    y += 1
    header = " shrimp "
    x = draw_segment(context, y, 1, header, 4)
    y += 1

    if context.sidebar_help_mode:
        help_list = [
            "",
            "help!",
            "",
            "i: insert",
            "o: cmd",
            "w: act on word",
            "d: delete",
            "y: copy",
            "u: paste",
            "h: line start",
            "j: line end",
            "p: line change",
            "wp: word change",
            "[num]: goto",
            "[num]y: copy",
            "[num]d: delete",
            f"{CMD_ARROW}w: write",
            f"{CMD_ARROW}c: clearfile",
            f"{CMD_ARROW}wq: write+quit",
            f"{CMD_ARROW}q: quit",
            f"{CMD_ARROW}dir <path>: cd",
            f"{CMD_ARROW}f: search",
            f"{CMD_ARROW}tb: tab menu",
            f"{CMD_ARROW}th: theme menu",
            f"{CMD_ARROW}x: next tab",
            f"{CMD_ARROW}z: prev tab",
        ]
        messages = help_list
    else:
        messages = context.sidebar_log

    for msg in messages:
        if y >= context.height:
            break
        try:
            context.stdscr.addstr(y, 1, msg[:sidebar_width-2], curses.color_pair(4))
        except curses.error:
            pass
        y += 1

    mark_line = context.current_buffer.mark_line
    if mark_line is not None:
        mark_text = f"mark on line {mark_line+1}"
        mark_y = context.height - 2
        try:
            context.stdscr.addstr(mark_y, 0, " " * sidebar_width, curses.color_pair(4))
        except curses.error:
            pass
        try:
            context.stdscr.addstr(mark_y, 1, mark_text[:sidebar_width-2],
                                  curses.color_pair(4) | curses.A_BOLD)
        except curses.error:
            pass

def draw_filetree(context, sidebar_width):
    """
    Draw the file tree in the sidebar for filetree mode.
    """
    for i in range(context.height):
        try:
            context.stdscr.addstr(i, 0, " " * sidebar_width, curses.color_pair(4))
        except curses.error:
            pass

    available = context.height - 2
    if context.filetree_selection_index < context.filetree_scroll_offset:
        context.filetree_scroll_offset = context.filetree_selection_index
    elif context.filetree_selection_index >= context.filetree_scroll_offset + available:
        context.filetree_scroll_offset = context.filetree_selection_index - available + 1

    y = 0
    x = 1
    heading = f"{context.mode_icons.get('filetree','')} file tree"
    x = draw_segment(context, y, x, f" {heading} ", 4)
    y += 1
    x = draw_segment(context, y, 1, f" root: {context.file_tree_root.path} ", 4)
    y += 1

    for idx, (node, depth) in enumerate(context.flat_file_list[context.filetree_scroll_offset:]):
        if y >= context.height:
            break
        is_selected = (idx + context.filetree_scroll_offset == context.filetree_selection_index)
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
                context.stdscr.addstr(y, 1, display_text[:sidebar_width-2],
                                      curses.color_pair(1) | curses.A_BOLD)
            else:
                context.stdscr.addstr(y, 1, display_text[:sidebar_width-2],
                                      curses.color_pair(4))
        except curses.error:
            pass
        y += 1

def draw_search_sidebar(context, sidebar_width):
    """
    Draw the sidebar for search mode, showing match lines and snippets.
    """
    for i in range(context.height):
        try:
            context.stdscr.addstr(i, 0, " " * sidebar_width, curses.color_pair(4))
        except curses.error:
            pass

    header = f" search: '{context.search_query}' "
    try:
        context.stdscr.addstr(0, 1, header, curses.color_pair(5) | curses.A_BOLD)
    except curses.error:
        pass

    for idx, line_num in enumerate(context.search_results):
        lines = context.get_current_lines()
        snippet = lines[line_num] if line_num < len(lines) else ""
        snippet = snippet.strip()
        display = f"{line_num+1}: {snippet}"
        if idx == context.search_selected_index:
            try:
                context.stdscr.addstr(idx+1, 1, display[:sidebar_width-2],
                                      curses.color_pair(1) | curses.A_BOLD)
            except curses.error:
                pass
        else:
            try:
                context.stdscr.addstr(idx+1, 1, display[:sidebar_width-2],
                                      curses.color_pair(4))
            except curses.error:
                pass

###############################################################################
# OTHER UI FUNCTIONS (Menus, Fullscreen Filetree, Editor Display and Prompt)
###############################################################################

def show_buffer_menu(context):
    """
    Display a vertical buffer menu and return the selected buffer index or None if canceled.
    """
    items = []
    for i, buf in enumerate(context.buffers):
        star = "*" if buf.modified else " "
        label = f"{i+1:2d}{star} {os.path.basename(buf.filename or 'new file')}"
        items.append(label)

    selected = 0
    height = len(items) + 4
    width = max(len(x) for x in items) + 6
    height = min(height, context.height)
    width = min(width, context.width)
    start_y = max(0, (context.height - height) // 2)
    start_x = max(0, (context.width - width) // 2)

    while True:
        try:
            for r in range(height):
                context.stdscr.addstr(start_y + r, start_x, " " * width, curses.color_pair(3))
        except curses.error:
            pass

        title = "Switch buffer"
        border_top = "┌" + "─" * (width - 2) + "┐"
        border_bottom = "└" + "─" * (width - 2) + "┘"
        try:
            context.stdscr.addstr(start_y, start_x, border_top, curses.color_pair(3) | curses.A_BOLD)
            context.stdscr.addstr(start_y, start_x + (width - len(title)) // 2, title,
                                  curses.color_pair(3) | curses.A_BOLD)
            context.stdscr.addstr(start_y + height - 1, start_x, border_bottom,
                                  curses.color_pair(3) | curses.A_BOLD)
        except curses.error:
            pass


        for idx, label in enumerate(items):
            row_y = start_y + 1 + idx
            if row_y >= start_y + height - 1:
                break
            if idx == selected:
                try:
                    context.stdscr.addstr(row_y, start_x + 1, label.ljust(width - 2),
                                          curses.color_pair(1) | curses.A_BOLD)
                except curses.error:
                    pass
            else:
                try:
                    context.stdscr.addstr(row_y, start_x + 1, label.ljust(width - 2),
                                          curses.color_pair(3))
                except curses.error:
                    pass

        context.stdscr.refresh()
        key = context.stdscr.getch()
        if key == curses.KEY_UP:
            selected = (selected - 1) % len(items)
        elif key == curses.KEY_DOWN:
            selected = (selected + 1) % len(items)
        elif key in (curses.KEY_ENTER, 10):
            return selected
        elif key == 27:
            return None

import time
import curses
from wcwidth import wcswidth

def pad_line(text, width):
    """Pad or trim a string to match the visual width."""
    visual_width = wcswidth(text)
    if visual_width >= width:
        return text[:width]
    return text + " " * (width - visual_width)

def show_main_menu(context):
    """
    Full-screen main menu for new file, filetree, directory, search, or quit.
    Returns the chosen shortcut as a string or None if canceled.
    """
    menu_items = [
        {"label": "new file",      "shortcut": "n", "icon": MENU_NEW_FILE},
        {"label": "open filetree", "shortcut": "t", "icon": MENU_FILE_TREE},
        {"label": "open directory","shortcut": "d", "icon": MENU_DIRECTORY},
        {"label": "search",        "shortcut": "f", "icon": MENU_FIND_FILE},
        {"label": "quit",          "shortcut": "q", "icon": MENU_QUIT},
    ]

    selected = 0
    ascii_logo = (
    "               _          _             \n"
    "        \\ \\     ___| |__  _ __(_)_ __ ___  _ __  \n"
    "-==-_    / /   / __| '_ \\| '__| | '_ ` _ \\| '_ \\ \n"
    "  ==== =/_/    \\__ \\ | | | |  | | | | | | | |_) |\n"
    "    ==== *    |___/_| |_|_|  |_|_| |_| |_| .__/\n"
    " ////||\\\\\\\\                             |_|  "
)



    while True:
        context.stdscr.clear()
        height, width = context.height, context.width

        # Background fill
        for y in range(height):
            try:
                context.stdscr.addstr(y, 0, " " * width, curses.color_pair(7))
            except curses.error:
                pass

        # Display logo
        from wcwidth import wcswidth

        logo_lines = ascii_logo.strip("\n").splitlines()
        start_y = max(0, (context.height - len(logo_lines)) // 2)

        for i, line in enumerate(logo_lines):
            x = max(0, (context.width - wcswidth(line)) // 2)
            try:
                context.stdscr.addstr(start_y + i, x, line, curses.color_pair(7))
            except curses.error:
                pass

        # Clock display
        current_time = time.strftime("%H:%M:%S")
        time_line = f" {current_time} "
        try:
            context.stdscr.addstr(start_y - 2,
                                  max(0, (width - wcswidth(time_line)) // 2),
                                  time_line, curses.color_pair(7))
        except curses.error:
            pass

        # Title
        menu_title = "menu..."
        try:
            context.stdscr.addstr(start_y + len(logo_lines) + 1,
                                  max(0, (width - wcswidth(menu_title)) // 2),
                                  menu_title, curses.color_pair(7) | curses.A_BOLD)
        except curses.error:
            pass

        # Menu entries
        start_y_menu = start_y + len(logo_lines) + 3
        for idx, item in enumerate(menu_items):
            line = f" {item['icon']} {item['label']} [{item['shortcut'].upper()}] "
            x = max(0, (width - wcswidth(line)) // 2)
            try:
                if idx == selected:
                    context.stdscr.attron(curses.color_pair(7) | curses.A_BOLD)
                    context.stdscr.addstr(start_y_menu + idx * 2, x, pad_line(line, width))
                    context.stdscr.attroff(curses.color_pair(7) | curses.A_BOLD)
                else:
                    context.stdscr.addstr(start_y_menu + idx * 2, x, pad_line(line, width), curses.color_pair(7))
            except curses.error:
                pass

        context.stdscr.refresh()
        key = context.stdscr.getch()

        if key in (curses.KEY_UP, ord('k')):
            selected = (selected - 1) % len(menu_items)
        elif key in (curses.KEY_DOWN, ord('j')):
            selected = (selected + 1) % len(menu_items)
        elif key in (curses.KEY_ENTER, 10, 13):
            return menu_items[selected]["shortcut"]
        elif key >= 0:
            c = chr(key).lower()
            for item in menu_items:
                if c == item["shortcut"]:
                    return item["shortcut"]


def show_theme_menu(context):
    """
    Show a small box with available themes for the user to select.
    """
    themes = sorted(context.available_themes.keys())
    if context.current_theme in themes:
        selected = themes.index(context.current_theme)
    else:
        selected = 0
    height = len(themes) + 4
    width = 30
    start_y = max(0, (context.height - height) // 2)
    start_x = max(0, (context.width - width) // 2)
    while True:
        try:
            for r in range(height):
                context.stdscr.addstr(start_y + r, start_x, " " * width, curses.color_pair(3))
        except curses.error:
            pass
        title = " Theme Menu "
        border_top = "┌" + "─" * (width - 2) + "┐"
        border_bottom = "└" + "─" * (width - 2) + "┘"
        try:
            context.stdscr.addstr(start_y, start_x, border_top, curses.color_pair(3) | curses.A_BOLD)
            pos_title = start_x + (width - len(title)) // 2
            context.stdscr.addstr(start_y, pos_title, title, curses.color_pair(3) | curses.A_BOLD)
            context.stdscr.addstr(start_y + height - 1, start_x, border_bottom, curses.color_pair(3) | curses.A_BOLD)
        except curses.error:
            pass
        for i, th in enumerate(themes):
            row_y = start_y + 1 + i
            if i == selected:
                line = f"> {th}"
                style = curses.color_pair(1) | curses.A_BOLD
            else:
                line = f"  {th}"
                style = curses.color_pair(3)
            try:
                context.stdscr.addstr(row_y, start_x + 1, line.ljust(width - 2), style)
            except curses.error:
                pass
        context.stdscr.refresh()
        key = context.stdscr.getch()
        if key == curses.KEY_UP:
            selected = (selected - 1) % len(themes)
        elif key == curses.KEY_DOWN:
            selected = (selected + 1) % len(themes)
        elif key in (curses.KEY_ENTER, 10):
            chosen = themes[selected]
            context.apply_theme(chosen)
            context.log_command(f"theme changed to {chosen}")
            context.save_theme_config()
            return
        elif key == 27:
            return

def show_plugin_menu(context):
    """
    Hierarchical plugin manager:

      ↑/↓        move
      Enter      toggle (plugin or individual bind)
      Tab        expand/collapse plugin
      d          show title/description (bottom line)
      Esc        close
    """
    import curses

    pm = context.plugin_manager
    if not pm.plugins:
        context.status_message = "no plugins found."
        return

    sel_p, sel_b = 0, None          # selected plugin / bind
    detail_text = ""                # text shown on bottom line

    while True:
        h, w = context.height, context.width

        # ── themed background ────────────────────────────────────────────
        for y in range(h):
            try:
                context.stdscr.addstr(y, 0, " " * w, curses.color_pair(7))
            except curses.error:
                pass

        # ── header ──────────────────────────────────────────────────────
        title = " Plugin Manager (Enter toggle • Tab expand • d details) "
        try:
            context.stdscr.addstr(
                0, max(0, (w - len(title)) // 2),
                title, curses.color_pair(5) | curses.A_BOLD)
        except curses.error:
            pass

        # ── list ────────────────────────────────────────────────────────
        row = 2
        for p_idx, pl in enumerate(pm.plugins):
            arrow = "▾" if pl.expanded else "▸"
            state = "✔" if pl.enabled else "✖"
            line = f"{arrow} [{state}] {pl.name}"
            style = curses.color_pair(1) | curses.A_BOLD \
                    if (p_idx == sel_p and sel_b is None) else curses.color_pair(3)
            try:
                context.stdscr.addstr(row, 2, line.ljust(w - 4), style)
            except curses.error:
                pass
            row += 1

            if pl.expanded:
                for b_idx, bd in enumerate(pl.binds):
                    state_b = "✔" if bd.enabled else "✖"
                    line_b = f"    [{state_b}] {bd.key_or_cmd} ({bd.mode})"
                    style_b = curses.color_pair(1) | curses.A_BOLD \
                              if (p_idx == sel_p and sel_b == b_idx) else curses.color_pair(3)
                    try:
                        context.stdscr.addstr(row, 2, line_b.ljust(w - 4), style_b)
                    except curses.error:
                        pass
                    row += 1

        # ── detail line (bottom) ────────────────────────────────────────
        if detail_text:
            try:
                context.stdscr.addstr(
                    h - 1, 2, detail_text[:w - 4],
                    curses.color_pair(5) | curses.A_BOLD)
            except curses.error:
                pass

        context.stdscr.refresh()
        k = context.stdscr.getch()

        # ── navigation ─────────────────────────────────────────────────
        if k in (curses.KEY_UP, ord('k')):
            if sel_b is not None:
                sel_b -= 1
                if sel_b < 0:
                    sel_b = None
            else:
                sel_p = (sel_p - 1) % len(pm.plugins)

        elif k in (curses.KEY_DOWN, ord('j')):
            if sel_b is None and pm.plugins[sel_p].expanded and pm.plugins[sel_p].binds:
                sel_b = 0
            elif sel_b is not None:
                sel_b += 1
                if sel_b >= len(pm.plugins[sel_p].binds):
                    sel_b = None
                    sel_p = (sel_p + 1) % len(pm.plugins)
            else:
                sel_p = (sel_p + 1) % len(pm.plugins)

        # ── toggle ─────────────────────────────────────────────────────
        elif k in (curses.KEY_ENTER, 10):
            if sel_b is None:
                pm.toggle_plugin(sel_p)
            else:
                pm.toggle_bind(sel_p, sel_b)
            detail_text = ""

        # ── expand/collapse ────────────────────────────────────────────
        elif k == ord('\t'):
            pm.plugins[sel_p].expanded = not pm.plugins[sel_p].expanded
            sel_b = None
            detail_text = ""

        # ── show details ───────────────────────────────────────────────
        elif k == ord('d'):
            if sel_b is None:
                pl = pm.plugins[sel_p]
                detail_text = f"{pl.title or pl.name}: {pl.desc or '(no description)'}"
            else:
                b = pm.plugins[sel_p].binds[sel_b]
                detail_text = f"{b.title or b.key_or_cmd}: {b.desc or '(no description)'}"

        # ── quit ───────────────────────────────────────────────────────
        elif k == 27:   # ESC
            return


def show_full_filetree(context):
    """
    Show a full-screen file tree browser and return once a file is selected.
    """
    scroll_offset = 0
    ft_width = 60
    while True:
        context.stdscr.clear()
        x_offset = max(0, (context.width - ft_width) // 2)
        for y in range(context.height):
            try:
                context.stdscr.addstr(y, x_offset, " " * ft_width, curses.color_pair(7))
            except curses.error:
                pass
        visible_items = context.flat_file_list[scroll_offset: scroll_offset + context.height]
        y = 0
        for idx, (node, depth) in enumerate(visible_items):
            indent = "  " * depth
            if node.is_dir:
                arrow_icon = FOLDER_ICON_OPEN if node.expanded else FOLDER_ICON_CLOSED
                display_text = f"{indent}{arrow_icon}{FOLDER_SYMBOL} {node.name}"
            else:
                _, ext = os.path.splitext(node.name)
                file_icon = FILE_ICONS.get(ext.lower(), DEFAULT_FILE_ICON)
                display_text = f"{indent}   {file_icon} {node.name}"
            if idx + scroll_offset == context.filetree_selection_index:
                try:
                    context.stdscr.addstr(y, x_offset + 1, display_text[:ft_width - 2],
                                          curses.color_pair(1) | curses.A_BOLD)
                except curses.error:
                    pass
            else:
                try:
                    context.stdscr.addstr(y, x_offset + 1, display_text[:ft_width - 2],
                                          curses.color_pair(7))
                except curses.error:
                    pass
            y += 1
        context.stdscr.refresh()
        key = context.stdscr.getch()
        if key == curses.KEY_UP:
            if context.filetree_selection_index > 0:
                context.filetree_selection_index -= 1
        elif key == curses.KEY_DOWN:
            if context.filetree_selection_index < len(context.flat_file_list) - 1:
                context.filetree_selection_index += 1
        elif key in (curses.KEY_ENTER, 10, curses.KEY_RIGHT):
            node, _ = context.flat_file_list[context.filetree_selection_index]
            if node.is_dir:
                node.toggle_expanded()
                if node.expanded and not node.children:
                    filetree.load_children(node, context.show_hidden, context)
                context.flat_file_list = filetree.flatten_tree(context.file_tree_root)
            else:
                try:
                    with open(node.path, 'r', encoding='utf-8') as f:
                        content = f.read().splitlines()
                except Exception as e:
                    context.status_message = f"error opening file: {e}"
                else:
                    new_buf = context.BufferClass(node.path, content)
                    new_buf.modified = False
                    context.add_buffer(new_buf)
                    context.log_command("file opened: " + node.path)
                context.mode = "normal"
                return
        elif key == curses.KEY_LEFT:
            node, _ = context.flat_file_list[context.filetree_selection_index]
            if node.is_dir and node.expanded:
                node.toggle_expanded()
                context.flat_file_list = filetree.flatten_tree(context.file_tree_root)
            elif node.parent is not None:
                for i, (n, _) in enumerate(context.flat_file_list):
                    if n == node.parent:
                        context.filetree_selection_index = i
                        break
        elif key == ord('a'):
            context.show_hidden = not context.show_hidden
            root_path = context.file_tree_root.path
            context.file_tree_root = filetree.FileNode(context.file_tree_root.name, root_path, True)
            context.file_tree_root.expanded = True
            filetree.load_children(context.file_tree_root, context.show_hidden, context)
            context.flat_file_list = filetree.flatten_tree(context.file_tree_root)
            context.filetree_selection_index = 0
        elif key == curses.KEY_PPAGE:
            if scroll_offset > 0:
                scroll_offset = max(0, scroll_offset - 1)
        elif key == curses.KEY_NPAGE:
            if scroll_offset < max(0, len(context.flat_file_list) - context.height):
                scroll_offset = min(len(context.flat_file_list) - 1, scroll_offset + 1)
        elif key == 27:
            context.mode = "normal"
            return

def draw_search_preview(context, x_offset, visible_height):
    """
    In search mode, highlight the currently selected line in the main text area.
    """
    lines = context.current_buffer.lines
    if context.current_buffer.cursor_line < context.current_buffer.scroll:
        context.current_buffer.scroll = context.current_buffer.cursor_line
    if context.current_buffer.cursor_line >= context.current_buffer.scroll + visible_height:
        context.current_buffer.scroll = context.current_buffer.cursor_line - visible_height + 1
    if context.current_buffer.scroll < 0:
        context.current_buffer.scroll = 0
    if context.current_buffer.scroll > max(0, len(lines) - visible_height):
        context.current_buffer.scroll = max(0, len(lines) - visible_height)
    for i in range(visible_height):
        line_index = context.current_buffer.scroll + i
        if line_index < len(lines):
            is_current_line = (line_index == context.current_buffer.cursor_line)
            indicator = "-> " if is_current_line else "   "
            line_number = f"{line_index+1:<3}"
            prefix_len = 6
            safe_line = lines[line_index][:max(0, context.width - x_offset - prefix_len)]
            text = f"{indicator}{line_number}{safe_line}"
            color = curses.color_pair(10) if is_current_line else curses.color_pair(2)
            text_display = text.ljust(context.width - x_offset)
            try:
                context.stdscr.addstr(i, x_offset, text_display, color)
            except curses.error:
                pass

def display(context):
    """
    Re-draw the entire screen: sidebar, main text area, status bar, and command-line dialog (if active).
    """
    context.height, context.width = context.stdscr.getmaxyx()
    visible_height = context.height - 1

    if context.sidebar_visible and context.width >= 80:
        sidebar_width = 30
    elif context.sidebar_visible:
        sidebar_width = 20
    else:
        sidebar_width = 0
    context.stdscr.clear()
    if context.sidebar_visible:
        draw_sidebar(context, sidebar_width)

    x_offset = sidebar_width
    text_area_width = context.width - x_offset
    for i in range(visible_height):
        try:
            context.stdscr.addstr(i, x_offset, " " * text_area_width, curses.color_pair(2))
        except curses.error:
            pass

    if context.mode == "search":
        draw_search_preview(context, x_offset, visible_height)
    else:
        lines = context.current_buffer.lines
        if context.current_buffer.cursor_line < context.current_buffer.scroll:
            context.current_buffer.scroll = context.current_buffer.cursor_line
        if context.current_buffer.cursor_line >= context.current_buffer.scroll + visible_height:
            context.current_buffer.scroll = context.current_buffer.cursor_line - visible_height + 1
        if context.current_buffer.scroll < 0:
            context.current_buffer.scroll = 0
        if context.current_buffer.scroll > max(0, len(lines) - visible_height):
            context.current_buffer.scroll = max(0, len(lines) - visible_height)
        for i in range(visible_height):
            line_index = context.current_buffer.scroll + i
            if line_index < len(lines):
                is_current_line = (line_index == context.current_buffer.cursor_line)
                indicator = "-> " if is_current_line else "   "
                if not context.zen_mode:
                    line_number = f"{line_index+1:<3}"
                    prefix_len = 7
                else:
                    line_number = ""
                    prefix_len = 0
                safe_line = lines[line_index][:max(0, text_area_width - prefix_len)]
                text = f"{indicator}{line_number}{safe_line}"
                color = curses.color_pair(10) if is_current_line else curses.color_pair(2)
                text_display = text.ljust(text_area_width)
                try:
                    context.stdscr.addstr(i, x_offset, text_display, color)
                except curses.error:
                    pass

    draw_status_bar(context)
    if context.mode == "command":
        draw_centered_cmdline(context)
    cursor_y = context.current_buffer.cursor_line - context.current_buffer.scroll
    cursor_x = context.current_buffer.cursor_col
    if not context.zen_mode:
        cursor_x += 6
    cursor_x += x_offset
    try:
        curses.curs_set(2)
        context.stdscr.move(cursor_y, cursor_x)
    except curses.error:
        pass

    # --- LAST thing drawn: let plugins add their UI -----------------
    context.plugin_manager.render(context)      # ← MUST be here
    # ----------------------------------------------------------------

    context.stdscr.refresh()


def prompt_input(context, prompt: str) -> str:
    """
    Prompt the user for input in a centered dialog box.
    Returns the entered string, or an empty string if canceled.
    """
    old_mode = context.mode
    context.mode = "command"
    saved_command_buffer = context.command_buffer
    context.command_buffer = ""
    curses.curs_set(1)
    try:
        while True:
            context.stdscr.clear()
            for y in range(context.height):
                try:
                    context.stdscr.addstr(y, 0, " " * context.width, curses.color_pair(0))
                except curses.error:
                    pass
            box_width = max(40, len(prompt) + 10, len(context.command_buffer) + 10)
            box_height = 5
            start_y = (context.height - box_height) // 2
            start_x = (context.width - box_width) // 2
            top_border = "┌" + "─" * (box_width - 2) + "┐"
            bottom_border = "└" + "─" * (box_width - 2) + "┘"
            title = f" {prompt} "
            if len(title) < box_width - 2:
                title_start = (box_width - 2 - len(title)) // 2
                top_line = ("┌" + " " * title_start + title +
                            " " * (box_width - 2 - title_start - len(title)) + "┐")
            else:
                top_line = top_border
            typed_str = context.command_buffer[:box_width - 4].ljust(box_width - 4)
            content_line = "│ " + typed_str + " │"
            try:
                context.stdscr.addstr(start_y, start_x, top_line, curses.color_pair(3) | curses.A_BOLD)
                context.stdscr.addstr(start_y + 1, start_x, content_line, curses.color_pair(3) | curses.A_BOLD)
                context.stdscr.addstr(start_y + 2, start_x, bottom_border, curses.color_pair(3) | curses.A_BOLD)
                context.stdscr.move(start_y + 1, start_x + 2 + len(context.command_buffer))
            except curses.error:
                pass
            context.stdscr.refresh()
            key = context.stdscr.getch()
            if key in (curses.KEY_ENTER, 10):
                return context.command_buffer.strip()
            elif key == 27:
                return ""
            elif key in (8, curses.KEY_BACKSPACE, 127):
                context.command_buffer = context.command_buffer[:-1]
            elif 32 <= key <= 126:
                context.command_buffer += chr(key)
    finally:
        context.mode = old_mode
        context.command_buffer = saved_command_buffer
        curses.curs_set(0)

