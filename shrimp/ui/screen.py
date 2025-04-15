"""
shrimp/ui/screen.py

Implements all UI–drawing functionality for the Shrimp text editor.
Based on the original shrimp.py code, re-implemented for the new modular structure.
"""
import os
import curses
import time
from shrimp import logger, filetree

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
CMD_ARROW = "󰘍"
MENU_NEW_FILE  = ""
MENU_FILE_TREE = ""
MENU_DIRECTORY = ""
MENU_FIND_FILE = ""
MENU_QUIT      = ""

def draw_segment(context, y, x, text, color_pair, arrow=""):
    """Helper function for drawing a colored text segment with an optional arrow."""
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
    In normal mode, displays:
      - Current time on the first line
      - The title " shrimp "
      - Either help text if help_mode is on, or the recent sidebar_log messages
      - Info about a mark if set
    In filetree or search mode, draws the filetree or search UI instead.
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

    # Possibly disable help mode if time expired
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

    # Show mark info if set
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
                context.stdscr.addstr(y, 1,
                                      display_text[:sidebar_width-2],
                                      curses.color_pair(1) | curses.A_BOLD)
            else:
                context.stdscr.addstr(y, 1,
                                      display_text[:sidebar_width-2],
                                      curses.color_pair(4))
        except curses.error:
            pass
        y += 1

def draw_search_sidebar(context, sidebar_width):
    """
    Draw the sidebar for search mode, showing each match line and snippet.
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
                context.stdscr.addstr(idx+1, 1,
                                      display[:sidebar_width-2],
                                      curses.color_pair(1) | curses.A_BOLD)
            except curses.error:
                pass
        else:
            try:
                context.stdscr.addstr(idx+1, 1,
                                      display[:sidebar_width-2],
                                      curses.color_pair(4))
            except curses.error:
                pass

def draw_status_bar(context):
    """
    Draw the status bar at the bottom of the screen.

    In zen mode, only the mode + time are shown. Otherwise, display:
    mode + file name + dirty marker + buffer info + time.
    """
    status_y = context.height - 1
    if context.zen_mode:
        mode_seg = f" {context.mode_icons.get(context.mode, '')} {context.mode.upper()} "
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
            context.stdscr.addstr(status_y, context.width - time_seg_len,
                                  time_seg, curses.color_pair(3))
        except curses.error:
            pass
        return

    mode_seg = f" {context.mode_icons.get(context.mode, '')} {context.mode.upper()} "
    x = 0
    try:
        context.stdscr.addstr(status_y, x, mode_seg, curses.color_pair(5))
    except curses.error:
        pass
    x += len(mode_seg)

    arrow = ""
    try:
        context.stdscr.addstr(status_y, x, arrow, curses.color_pair(8))
    except curses.error:
        pass
    x += len(arrow)

    filename = context.get_current_filename() or "new file"
    dirty_mark = '*' if context.current_buffer.modified else ''
    buf_info = f" [{context.current_buffer_index+1}/{len(context.buffers)}]" if len(context.buffers) > 1 else ""
    file_seg = f" {os.path.basename(filename)}{dirty_mark}{buf_info} "
    try:
        context.stdscr.addstr(status_y, x, file_seg, curses.color_pair(7))
    except curses.error:
        pass
    x += len(file_seg)

    arrow2 = ""
    try:
        context.stdscr.addstr(status_y, x, arrow2, curses.color_pair(9))
    except curses.error:
        pass
    x += len(arrow2)

    time_seg = f" {time.strftime('%H:%M:%S')} "
    time_seg_len = len(time_seg)
    for pos in range(x, context.width - time_seg_len):
        try:
            context.stdscr.addch(status_y, pos, ' ', curses.color_pair(3))
        except curses.error:
            pass
    try:
        context.stdscr.addstr(status_y, context.width - time_seg_len,
                              time_seg, curses.color_pair(3))
    except curses.error:
        pass

def draw_centered_cmdline(context):
    """Draw a centered command-line dialog box for command mode."""
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
        context.stdscr.addstr(start_y,     start_x, top_line, curses.color_pair(3) | curses.A_BOLD)
        context.stdscr.addstr(start_y + 1, start_x, content_line, curses.color_pair(3) | curses.A_BOLD)
        context.stdscr.addstr(start_y + 2, start_x, bottom_border, curses.color_pair(3) | curses.A_BOLD)
    except curses.error:
        pass

def show_buffer_menu(context):
    """
    Display a simple buffer-switch menu (vertical list) for user to select from.
    Return the chosen buffer index or None if canceled.
    """
    # Build a list of buffer names
    items = []
    for i, buf in enumerate(context.buffers):
        star = "*" if buf.modified else " "
        label = f"{i+1:2d}{star} {os.path.basename(buf.filename or 'new file')}"
        items.append(label)

    selected = 0
    height = len(items) + 4
    width = max(len(x) for x in items) + 6
    if height > context.height:
        height = context.height
    if width > context.width:
        width = context.width

    start_y = max(0, (context.height - height) // 2)
    start_x = max(0, (context.width - width) // 2)

    while True:
        try:
            # Clear the pop-up area
            for r in range(height):
                context.stdscr.addstr(start_y + r, start_x, " " * width, curses.color_pair(3))
        except curses.error:
            pass

        title = "Switch buffer"
        border_top = "┌" + "─" * (width - 2) + "┐"
        border_bottom = "└" + "─" * (width - 2) + "┘"
        try:
            context.stdscr.addstr(start_y, start_x, border_top, curses.color_pair(3) | curses.A_BOLD)
            context.stdscr.addstr(start_y, start_x + (width - len(title))//2, title,
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
        elif key == 27:  # ESC
            return None

def show_main_menu(context):
    """
    Full-screen "title screen" main menu for new file, open filetree, directory, search, or quit.
    Returns the shortcut code of the chosen item (e.g. 'n', 't', 'd', 'f', 'q'), or None if canceled.
    """
    menu_items = [
        {"label": "new file",      "shortcut": "n", "icon": MENU_NEW_FILE},
        {"label": "open filetree", "shortcut": "t", "icon": MENU_FILE_TREE},
        {"label": "open directory","shortcut": "d", "icon": MENU_DIRECTORY},
        {"label": "search",        "shortcut": "f", "icon": MENU_FIND_FILE},
        {"label": "quit",          "shortcut": "q", "icon": MENU_QUIT},
    ]

    selected = 0
    ascii_logo = r"""
                    _          _             
        \ \     ___| |__  _ __(_)_ __ ___  _ __  
-==-_    / /   / __| '_ \| '__| | '_ ` _ \| '_ \ 
  ==== =/_/    \__ \ | | | |  | | | | | | | |_) |
    ==== *     |___/_| |_|_|  |_|_| |_| |_| .__/
 ////||\\\\                               |_|
"""

    while True:
        context.stdscr.clear()
        for y in range(context.height):
            try:
                context.stdscr.addstr(y, 0, " " * context.width, curses.color_pair(7))
            except curses.error:
                pass

        logo_lines = ascii_logo.splitlines()
        start_y = max(0, (context.height - len(logo_lines)) // 2 - 4)
        for i, line in enumerate(logo_lines):
            x = (context.width - len(line)) // 2
            try:
                context.stdscr.addstr(start_y + i, x, line, curses.color_pair(7))
            except curses.error:
                pass

        current_time = time.strftime("%H:%M:%S")
        time_line = f" {current_time} "
        try:
            context.stdscr.addstr(start_y - 2,
                                  (context.width - len(time_line)) // 2,
                                  time_line,
                                  curses.color_pair(7))
        except curses.error:
            pass

        menu_title = "menu..."
        try:
            context.stdscr.addstr(start_y + len(logo_lines) + 1,
                                  (context.width - len(menu_title)) // 2,
                                  menu_title,
                                  curses.color_pair(7) | curses.A_BOLD)
        except curses.error:
            pass

        start_y_menu = start_y + len(logo_lines) + 3
        for idx, item in enumerate(menu_items):
            line = f" {item['icon']} {item['label']} [{item['shortcut'].upper()}] "
            x = (context.width - len(line)) // 2
            if idx == selected:
                try:
                    context.stdscr.attron(curses.color_pair(7) | curses.A_BOLD)
                    context.stdscr.addstr(start_y_menu + idx * 2, x, line)
                    context.stdscr.attroff(curses.color_pair(7) | curses.A_BOLD)
                except curses.error:
                    pass
            else:
                try:
                    context.stdscr.addstr(start_y_menu + idx * 2, x, line, curses.color_pair(7))
                except curses.error:
                    pass

        context.stdscr.refresh()
        key = context.stdscr.getch()
        if key in (curses.KEY_UP, ord('k')):
            selected = (selected - 1) % len(menu_items)
        elif key in (curses.KEY_DOWN, ord('j')):
            selected = (selected + 1) % len(menu_items)
        elif key in (curses.KEY_ENTER, 10):
            return menu_items[selected]["shortcut"]
        elif key >= 0:
            c = chr(key).lower()
            for item in menu_items:
                if c == item["shortcut"]:
                    return c

def show_theme_menu(context):
    """
    Show a theme-selection menu in a small box.
    Currently supports 'boring','shrimp','catpuccin'.
    We'll save the chosen theme to ~/shrimp/config/themes/theme.conf
    """
    themes = ['boring','shrimp','catpuccin']
    selected = themes.index(context.current_theme) if context.current_theme in themes else 0
    height = len(themes) + 4
    width = 30
    start_y = max(0, (context.height - height)//2)
    start_x = max(0, (context.width - width)//2)

    while True:
        try:
            for r in range(height):
                context.stdscr.addstr(start_y + r, start_x, " " * width, curses.color_pair(3))
        except curses.error:
            pass

        title = " Theme Menu "
        border_top    = "┌" + "─"*(width-2) + "┐"
        border_bottom = "└" + "─"*(width-2) + "┘"
        try:
            context.stdscr.addstr(start_y, start_x, border_top,
                                  curses.color_pair(3) | curses.A_BOLD)
            pos_title = start_x + (width - len(title))//2
            context.stdscr.addstr(start_y, pos_title, title,
                                  curses.color_pair(3) | curses.A_BOLD)
            context.stdscr.addstr(start_y+height-1, start_x,
                                  border_bottom, curses.color_pair(3) | curses.A_BOLD)
        except curses.error:
            pass

        for i, th in enumerate(themes):
            row_y = start_y+1 + i
            if i == selected:
                line = f"> {th}"
                style = curses.color_pair(1) | curses.A_BOLD
            else:
                line = f"  {th}"
                style = curses.color_pair(3)
            try:
                context.stdscr.addstr(row_y, start_x+1, line.ljust(width-2), style)
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
            # Save this theme persistently
            context.save_theme_config()
            return
        elif key == 27: # ESC
            return

def show_full_filetree(context):
    """
    Show a fullscreen file tree in the middle, for selection of a file or directory.
    """
    scroll_offset = 0
    ft_width = 60
    while True:
        context.stdscr.clear()
        x_offset = max(0, (context.width - ft_width)//2)
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
                    context.stdscr.addstr(y, x_offset+1, display_text[:ft_width-2],
                                          curses.color_pair(1) | curses.A_BOLD)
                except curses.error:
                    pass
            else:
                try:
                    context.stdscr.addstr(y, x_offset+1, display_text[:ft_width-2],
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
            node, d = context.flat_file_list[context.filetree_selection_index]
            if node.is_dir:
                node.toggle_expanded()
                if node.expanded and not node.children:
                    filetree.load_children(node, context.show_hidden, context)
                context.flat_file_list = filetree.flatten_tree(context.file_tree_root)
            else:
                # Open file
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
            node, d = context.flat_file_list[context.filetree_selection_index]
            if node.is_dir and node.expanded:
                node.toggle_expanded()
                context.flat_file_list = filetree.flatten_tree(context.file_tree_root)
            else:
                if node.parent is not None:
                    for i, (n, dd) in enumerate(context.flat_file_list):
                        if n == node.parent:
                            context.filetree_selection_index = i
                            break
        elif key == ord('a'):
            context.show_hidden = not context.show_hidden
            root_path = context.file_tree_root.path
            context.file_tree_root = filetree.FileNode(
                context.file_tree_root.name,
                root_path,
                True
            )
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
        elif key == 27: # ESC
            context.mode = "normal"
            return

def draw_search_preview(context, x_offset, visible_height):
    """
    When in search mode, highlight the currently selected search result
    in the main text area. Replace references to context.cursor_line with
    context.current_buffer.cursor_line so we don't get attribute errors.
    """
    lines = context.current_buffer.lines

    # Use buffer-based cursor positions
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
            # Compare line_index to context.current_buffer.cursor_line
            is_current_line = (line_index == context.current_buffer.cursor_line)
            indicator = "-> " if is_current_line else "   "
            line_number = f"{line_index+1:<3}"
            prefix_len = 7
            safe_line = lines[line_index][:max(0, context.width - x_offset - prefix_len)]
            text = f"{indicator}{line_number}{safe_line}"
            if is_current_line:
                text_display = text.ljust(context.width - x_offset)
                color = curses.color_pair(10)
            else:
                text_display = text
                color = curses.color_pair(2)
            try:
                context.stdscr.addstr(i, x_offset, text_display, color)
            except curses.error:
                pass

def display(context):
    """
    Orchestrates redrawing the entire screen: sidebar, main text, status bar,
    plus command line if needed.
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

    # Fill text area background
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
                if context.zen_mode:
                    indicator = ""
                    line_number = ""
                    prefix_len = 0
                else:
                    indicator = "-> " if line_index == context.current_buffer.cursor_line else "   "
                    line_number = f"{line_index+1:<3}"
                    prefix_len = 7
                safe_line = lines[line_index][:max(0, text_area_width - prefix_len)]
                text = f"{indicator}{line_number}{(' ' if not context.zen_mode else '')}{safe_line}"
                if line_index == context.current_buffer.cursor_line:
                    text_display = text.ljust(text_area_width)
                    color = curses.color_pair(10)
                else:
                    text_display = text
                    color = curses.color_pair(2)
                try:
                    context.stdscr.addstr(i, x_offset, text_display, color)
                except curses.error:
                    pass

    draw_status_bar(context)

    # If in command mode, draw command line UI
    if context.mode == "command":
        draw_centered_cmdline(context)

    # Place the cursor based on current_buffer's cursor position
    cursor_y = context.current_buffer.cursor_line - context.current_buffer.scroll
    cursor_x = context.current_buffer.cursor_col
    if not context.zen_mode:
        cursor_x += 7  # skip indicator + line number
    cursor_x += x_offset
    try:
        curses.curs_set(2)
        context.stdscr.move(cursor_y, cursor_x)
    except:
        pass

    context.stdscr.refresh()

################################
# Prompt Input Function
################################
def prompt_input(context, prompt: str) -> str:
    """
    Prompt the user for a single line of text in a small dialog,
    returning the user input or an empty string if ESC is pressed.
    This is a simpler approach that mimics the style of the
    command-line box in the center of the screen.
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
                    context.stdscr.addstr(y, 0, " " * context.width, curses.color_pair(2))
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

            typed_str = context.command_buffer[: box_width - 4]
            typed_str = typed_str.ljust(box_width - 4)
            content_line = "│ " + typed_str + " │"

            try:
                context.stdscr.addstr(start_y,     start_x, top_line, curses.color_pair(3) | curses.A_BOLD)
                context.stdscr.addstr(start_y + 1, start_x, content_line, curses.color_pair(3) | curses.A_BOLD)
                context.stdscr.addstr(start_y + 2, start_x, bottom_border, curses.color_pair(3) | curses.A_BOLD)
                context.stdscr.move(start_y + 1, start_x + 2 + len(context.command_buffer))
            except curses.error:
                pass

            context.stdscr.refresh()
            key = context.stdscr.getch()

            if key in (curses.KEY_ENTER, 10):
                return context.command_buffer.strip()
            elif key == 27:  # ESC key
                return ""
            elif key in (8, curses.KEY_BACKSPACE, 127):
                context.command_buffer = context.command_buffer[:-1]
            elif 32 <= key <= 126:
                context.command_buffer += chr(key)
    finally:
        context.mode = old_mode
        context.command_buffer = saved_command_buffer
        curses.curs_set(0)

