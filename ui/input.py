"""
Input handling for Shrimp text editor.

Processes key events for each mode (normal, insert, command, filetree, search)
and updates the context accordingly.
"""
import curses
import time
from shrimp import commands, filetree

def handle_normal_mode(context, key: int):
    """Handle a key press in normal mode."""
    # ESC cancels partial input
    if key == 27:  # ESC
        context.command_buffer = ""
        context.status_message = ""
        return

    # If user typed a numeric prefix and presses Enter, jump to that line
    if context.normal_number_buffer and key in (curses.KEY_ENTER, 10):
        try:
            line_number = int(context.normal_number_buffer) - 1
        except ValueError:
            line_number = None
        context.normal_number_buffer = ""
        if line_number is not None and 0 <= line_number < len(context.current_buffer.lines):
            context.current_buffer.cursor_line = line_number
            context.current_buffer.cursor_col = min(
                context.current_buffer.cursor_col,
                len(context.current_buffer.lines[line_number])
            )
        return

    # If we are in "word mode" (w pressed), then the next character picks an action
    if context.word_mode:
        ch = chr(key) if 32 <= key < 127 else None
        if ch == 'j':
            context.current_buffer.jump_word()
            context.log_command("wj: jump word")
        elif ch == 'h':
            context.current_buffer.jump_back_word()
            context.log_command("wh: jump back")
        elif ch == 'd':
            context.current_buffer.delete_word()
            context.log_command("wd: delete word")
        elif ch == 'y':
            word = context.current_buffer.copy_word_inline()
            context.word_clipboard = word
            context.log_command("wy: copy word")
        elif ch == 'p':
            context.pending_word_change = True
            context.current_buffer.delete_word()
            context.mode = "insert"
            context.log_command("wp: word change")
        else:
            context.log_command(f"w{ch or '?'}: unknown")
        context.word_mode = False
        return

    # Accumulate numeric prefix
    if 48 <= key <= 57:
        context.normal_number_buffer += chr(key)
        context.last_digit_time = time.time()
        return

    # If we have a numeric prefix, handle certain commands (d, y, D, x)
    if context.normal_number_buffer:
        ch = chr(key) if 32 <= key < 127 else None
        if ch in ('d','y','D','x'):
            try:
                count = int(context.normal_number_buffer)
            except (ValueError, OverflowError):
                count = 1
            context.normal_number_buffer = ""
            if ch == 'd':
                context.current_buffer.delete_multiple_lines(count)
            elif ch == 'y':
                context.clipboard = context.current_buffer.copy_multiple_lines(count)
            elif ch == 'D':
                context.current_buffer.delete_paragraph()
            elif ch == 'x':
                # Switch buffers
                if len(context.buffers) > 1:
                    new_index = (context.current_buffer_index + 1) % len(context.buffers)
                    context.switch_to_buffer(new_index)
                    context.status_message = f"switched to buffer {context.current_buffer_index + 1}"
            return
        else:
            # If not a recognized count command, treat number as line jump
            try:
                line_number = int(context.normal_number_buffer) - 1
            except ValueError:
                line_number = None
            context.normal_number_buffer = ""
            if line_number is not None and 0 <= line_number < len(context.current_buffer.lines):
                context.current_buffer.cursor_line = line_number
                context.current_buffer.cursor_col = min(
                    context.current_buffer.cursor_col,
                    len(context.current_buffer.lines[line_number])
                )
            # Fall through to normal key handling

    # Single-char normal mode actions
    if key == ord('m'):
        # Mark set/jump
        if context.current_buffer.mark_line is None:
            context.current_buffer.mark_line = context.current_buffer.cursor_line
            context.status_message = f"mark set on line {context.current_buffer.cursor_line + 1}"
            context.log_command("m: mark set")
        else:
            target = context.current_buffer.mark_line
            if target < len(context.current_buffer.lines):
                context.current_buffer.cursor_line = target
                context.current_buffer.cursor_col = min(
                    context.current_buffer.cursor_col,
                    len(context.current_buffer.lines[target])
                )
            context.current_buffer.mark_line = None
            context.status_message = f"jumped to line {target + 1}"
            context.log_command("m: jump to mark")
        return

    if key == ord('d'):
        context.current_buffer.delete_line()
        context.log_command("d: delete line")
        return

    if key == ord('i'):
        context.mode = "insert"
        context.log_command("i: insert")
        return

    if key == ord('o'):
        context.mode = "command"
        context.command_buffer = ""
        context.log_command("o: command")
        return

    if key == ord('D'):
        context.current_buffer.delete_paragraph()
        context.log_command("d: delete paragraph")
        return

    if key == ord('y'):
        context.clipboard = context.current_buffer.copy_line()
        context.log_command("y: copy line")
        return

    if key == ord('Y'):
        context.clipboard = context.current_buffer.copy_paragraph()
        context.log_command("y: copy paragraph")
        return

    if key == ord('u'):
        # If there's a word in word_clipboard, paste inline
        if context.word_clipboard:
            line = context.current_buffer.lines[context.current_buffer.cursor_line]
            new_line = (line[:context.current_buffer.cursor_col] +
                        context.word_clipboard +
                        line[context.current_buffer.cursor_col:])
            context.current_buffer.lines[context.current_buffer.cursor_line] = new_line
            context.current_buffer.cursor_col += len(context.word_clipboard)
            context.word_clipboard = ""
            context.current_buffer.modified = True
            context.log_command("u: paste word")
        else:
            # Paste line(s) from normal clipboard
            if context.clipboard:
                context.current_buffer.paste_lines(context.clipboard)
                context.log_command("u: paste line")
        return

    if key == ord('x'):
        if len(context.buffers) > 1:
            new_index = (context.current_buffer_index + 1) % len(context.buffers)
            context.switch_to_buffer(new_index)
            context.status_message = f"switched to buffer {context.current_buffer_index + 1}"
        return

    # Standard arrow/home/end navigation
    if key == curses.KEY_UP and context.current_buffer.cursor_line > 0:
        context.current_buffer.cursor_line -= 1
        return
    if key == curses.KEY_DOWN and context.current_buffer.cursor_line < len(context.current_buffer.lines) - 1:
        context.current_buffer.cursor_line += 1
        context.current_buffer.cursor_col = min(
            context.current_buffer.cursor_col,
            len(context.current_buffer.lines[context.current_buffer.cursor_line])
        )
        return
    if key == curses.KEY_LEFT and context.current_buffer.cursor_col > 0:
        context.current_buffer.cursor_col -= 1
        return
    if key == curses.KEY_RIGHT:
        if context.current_buffer.cursor_col < len(context.current_buffer.lines[context.current_buffer.cursor_line]):
            context.current_buffer.cursor_col += 1
        return
    if key == curses.KEY_HOME:
        context.current_buffer.cursor_col = 0
        return
    if key == curses.KEY_END:
        context.current_buffer.cursor_col = len(context.current_buffer.lines[context.current_buffer.cursor_line])
        return
    if key == curses.KEY_PPAGE:
        visible_height = max(1, context.height - 1)
        context.current_buffer.scroll = max(0, context.current_buffer.scroll - visible_height)
        context.current_buffer.cursor_line = max(0, context.current_buffer.cursor_line - visible_height)
        return
    if key == curses.KEY_NPAGE:
        visible_height = max(1, context.height - 1)
        if context.current_buffer.scroll < len(context.current_buffer.lines) - visible_height:
            context.current_buffer.scroll = min(
                len(context.current_buffer.lines) - visible_height,
                context.current_buffer.scroll + visible_height
            )
        context.current_buffer.cursor_line = min(
            len(context.current_buffer.lines) - 1,
            context.current_buffer.cursor_line + visible_height
        )
        return

    # Space moves cursor forward one character
    if key == ord(' '):
        line_len = len(context.current_buffer.lines[context.current_buffer.cursor_line])
        if context.current_buffer.cursor_col < line_len:
            context.current_buffer.cursor_col += 1
        return

    # Additional single-letter commands
    if key == ord('h'):
        # Move to start of line
        context.current_buffer.cursor_col = 0
        context.log_command("h: startline")
        return
    if key == ord('j'):
        # Move to end of line
        line_str = context.current_buffer.lines[context.current_buffer.cursor_line]
        context.current_buffer.cursor_col = len(line_str)
        context.log_command("j: endline")
        return
    if key == ord('w'):
        # Next keystroke is word action
        context.word_mode = True
        return
    if key == ord('p'):
        # Replace entire line
        context.pending_line_change = True
        context.current_buffer.lines[context.current_buffer.cursor_line] = ""
        context.current_buffer.modified = True
        context.mode = "insert"
        context.log_command("p: line change")
        return

def handle_insert_mode(context, key: int):
    """Handle a key press in insert mode."""
    # Ensure cursor_line is valid
    if context.current_buffer.cursor_line < 0:
        context.current_buffer.cursor_line = 0
    if context.current_buffer.cursor_line >= len(context.current_buffer.lines):
        context.current_buffer.cursor_line = len(context.current_buffer.lines) - 1

    # If user ended line change by pressing Enter
    if context.pending_line_change and key in (curses.KEY_ENTER, 10):
        context.mode = "normal"
        context.pending_line_change = False
        return

    # If user ended word change by pressing space
    if context.pending_word_change and key == 32:
        context.mode = "normal"
        context.pending_word_change = False
        return

    # ESC -> normal mode
    if key == 27:  # ESC
        context.mode = "normal"
        return

    if key in (curses.KEY_ENTER, 10):
        # Split line
        context.current_buffer.split_line()
        return

    if key in (8, curses.KEY_BACKSPACE, 127):
        # Backspace handling
        if context.current_buffer.cursor_col > 0:
            line = context.current_buffer.lines[context.current_buffer.cursor_line]
            new_line = line[:context.current_buffer.cursor_col - 1] + line[context.current_buffer.cursor_col:]
            context.current_buffer.lines[context.current_buffer.cursor_line] = new_line
            context.current_buffer.cursor_col -= 1
            context.current_buffer.modified = True
        else:
            # Merge with previous line if possible
            if context.current_buffer.cursor_line > 0:
                prev_line_index = context.current_buffer.cursor_line - 1
                prev_line = context.current_buffer.lines[prev_line_index]
                curr_line = context.current_buffer.lines.pop(context.current_buffer.cursor_line)
                context.current_buffer.cursor_line -= 1
                context.current_buffer.cursor_col = len(prev_line)
                context.current_buffer.lines[context.current_buffer.cursor_line] = prev_line + curr_line
                context.current_buffer.modified = True
        return

    # Insert a printable character
    if 32 <= key <= 126:
        ch = chr(key)
        line = context.current_buffer.lines[context.current_buffer.cursor_line]
        new_line = line[:context.current_buffer.cursor_col] + ch + line[context.current_buffer.cursor_col:]
        context.current_buffer.lines[context.current_buffer.cursor_line] = new_line
        context.current_buffer.cursor_col += 1
        context.current_buffer.modified = True
        return

def handle_command_mode(context, key: int):
    """Handle a key press in command (:) mode."""
    if key == 27:  # ESC
        context.mode = "normal"
        context.command_buffer = ""
        return
    if key in (curses.KEY_ENTER, 10):
        cmd = context.command_buffer.strip()
        context.mode = "normal"
        context.command_buffer = ""
        commands.process_command(context, cmd)
        return

    # Basic text input in command mode
    if key in (8, curses.KEY_BACKSPACE, 127):
        context.command_buffer = context.command_buffer[:-1]
    elif 32 <= key <= 126:
        context.command_buffer += chr(key)

def handle_filetree_mode(context, key: int):
    """Handle a key press in filetree (sidebar or full-screen) mode."""
    if key == curses.KEY_UP:
        if context.filetree_selection_index > 0:
            context.filetree_selection_index -= 1
    elif key == curses.KEY_DOWN:
        if context.filetree_selection_index < len(context.flat_file_list) - 1:
            context.filetree_selection_index += 1
    elif key in (curses.KEY_ENTER, 10, curses.KEY_RIGHT):
        node, depth = context.flat_file_list[context.filetree_selection_index]
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
                context.current_buffer.cursor_line = 0
                context.current_buffer.cursor_col = 0
                context.current_buffer.scroll = 0
                new_buf = context.BufferClass(node.path, content)
                new_buf.modified = False
                context.add_buffer(new_buf)
                context.log_command("file opened: " + node.path)
                context.mode = "normal"
    elif key == curses.KEY_LEFT:
        node, depth = context.flat_file_list[context.filetree_selection_index]
        if node.is_dir and node.expanded:
            node.toggle_expanded()
            context.flat_file_list = filetree.flatten_tree(context.file_tree_root)
        else:
            if node.parent is not None:
                # Move selection to the parent node
                for i, (n, d) in enumerate(context.flat_file_list):
                    if n == node.parent:
                        context.filetree_selection_index = i
                        break
    elif key == ord('a'):
        context.show_hidden = not context.show_hidden
        root_path = context.file_tree_root.path
        context.file_tree_root = filetree.FileNode(
            context.file_tree_root.name, root_path, True, parent=None
        )
        context.file_tree_root.expanded = True
        filetree.load_children(context.file_tree_root, context.show_hidden, context)
        context.flat_file_list = filetree.flatten_tree(context.file_tree_root)
        context.filetree_selection_index = 0
        context.status_message = f"hidden {'shown' if context.show_hidden else 'hidden'}."
    elif key == 27:  # ESC
        context.mode = "normal"
        context.status_message = "exited file tree mode."

#########################################
# NEW: handle_search_mode for arrow nav
#########################################
def handle_search_mode(context, key: int):
    """
    Handle a key press in search (f) mode.
    Up/Down moves context.search_selected_index,
    Enter jumps to that line and returns to normal mode.
    Esc cancels search mode.
    """
    if key == curses.KEY_UP:
        if context.search_selected_index > 0:
            context.search_selected_index -= 1
    elif key == curses.KEY_DOWN:
        if context.search_selected_index < len(context.search_results) - 1:
            context.search_selected_index += 1
    elif key in (curses.KEY_ENTER, 10):
        if context.search_results:
            line_num = context.search_results[context.search_selected_index]
            # Jump cursor
            context.current_buffer.cursor_line = line_num
            context.current_buffer.cursor_col = 0
        context.mode = "normal"
    elif key == 27:  # ESC
        context.mode = "normal"
    else:
        # Optional: pass other keys to normal mode
        handle_normal_mode(context, key)

