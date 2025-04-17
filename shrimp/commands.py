"""
Command parsing and execution for Shrimp text editor.

This module handles parsing of command-line mode input (':' mode) and dispatches
to the appropriate actions on the editor context.
"""
import os
import time
from shrimp import logger, filetree, buffer

def process_command(context, command: str):
    """Parse and execute a command-line (':' mode) command string."""
    cmd = command.strip()
    if not cmd:
        return
    cmd_lower = cmd.lower()

    if context.plugin_manager.execute_command(cmd_lower, context):
        return

    if cmd_lower == "plug":
        context.ui.show_plugin_menu(context)          # user toggles plugins
        context.status_message = "plugin menu closed."
        return

    # Single commands
    if cmd_lower == "tb":
        # Open buffer switch menu
        if context.zen_mode:
            context.status_message = "buffer menu disabled in zen mode."
        else:
            selection = context.ui.show_buffer_menu(context)
            if selection is not None:
                context.switch_to_buffer(selection)
                context.log_command("tb: buffer menu")
        return

    if cmd_lower in ("m", "menu"):
        # Show main menu (title screen)
        choice = context.ui.show_main_menu(context)
        if choice == "n":
            new_fn = context.ui.prompt_input(context, "enter new filename:")
            if new_fn:
                new_buf = buffer.Buffer(new_fn, [""])
                new_buf.modified = False
                context.add_buffer(new_buf)
                context.log_command("n: new file")
        elif choice == "t":
            context.ui.show_full_filetree(context)
        elif choice == "d":
            directory = context.ui.prompt_input(context, "enter directory path:")
            if directory and os.path.isdir(directory):
                try:
                    os.chdir(directory)
                    context.file_tree_root = filetree.FileNode(
                        os.path.basename(directory) or directory,
                        directory,
                        True
                    )
                    context.file_tree_root.expanded = True
                    filetree.load_children(context.file_tree_root, context.show_hidden, context)
                    context.flat_file_list = filetree.flatten_tree(context.file_tree_root)
                    # Open a new untitled file
                    new_path = os.path.join(directory, "untitled.txt")
                    new_buffer = buffer.Buffer(new_path, [""])
                    new_buffer.modified = True
                    context.add_buffer(new_buffer)
                    context.mode = "normal"
                    context.sidebar_visible = True
                    context.log_command("dir: changed directory to " + os.getcwd())
                except Exception as e:
                    context.status_message = "error changing directory: " + str(e)
                    context.log_command("dir error: " + str(e))
            else:
                context.status_message = "invalid directory."
        elif choice == "f":
            query = context.ui.prompt_input(context, "enter search query:")
            if query:
                context.start_search(query)
            else:
                context.status_message = "search string empty."
        elif choice == "q":
            context.graceful_exit()
        return

    if cmd_lower in ("write", "w"):
        # Save file
        if context.current_buffer.filename is None:
            name = context.ui.prompt_input(context, "enter filename to save:")
            if not name:
                context.status_message = "save cancelled."
                return
            context.current_buffer.filename = name
        success = context.current_buffer.save_to_file()
        if success:
            num_bytes = sum(len(line) for line in context.current_buffer.lines) + (len(context.current_buffer.lines) - 1)
            context.log_command(f"w: write ({num_bytes} bytes)")
        else:
            context.status_message = f"error saving file: {context.current_buffer.filename}"
        return

    if cmd_lower in ("wq"):
        # Save and quit
        if context.current_buffer.filename is None:
            name = context.ui.prompt_input(context, "enter filename to save:")
            if not name:
                context.log_command("wq: quit without filename")
                context.graceful_exit()
                return
            context.current_buffer.filename = name
        context.current_buffer.save_to_file()
        context.graceful_exit()
        return

    if cmd_lower in ("quit", "q"):
        context.log_command("q: quit")
        context.graceful_exit()
        return

    if cmd_lower == "zen":
        if not context.zen_mode:
            context.sidebar_visible_before_zen = context.sidebar_visible
            context.sidebar_visible = False
            context.zen_mode = True
            if context.mode == "filetree":
                context.mode = "normal"
            context.sidebar_help_mode = False
            context.log_command("zen: on")
            context.status_message = "zen mode on."
        else:
            context.zen_mode = False
            context.sidebar_visible = getattr(context, "sidebar_visible_before_zen", True)
            context.log_command("zen: off")
            context.status_message = "zen mode off."
        return

    if cmd_lower == "th":
        # Open theme selection menu
        context.ui.show_theme_menu(context)
        return

    if cmd_lower.startswith("dir "):
        path = cmd[4:].strip()
        if os.path.isdir(path):
            try:
                os.chdir(path)
                context.file_tree_root = filetree.FileNode(
                    os.path.basename(path) or path, path, True
                )
                context.file_tree_root.expanded = True
                filetree.load_children(context.file_tree_root, context.show_hidden, context)
                context.flat_file_list = filetree.flatten_tree(context.file_tree_root)
                new_path = os.path.join(path, "untitled.txt")
                new_buf = buffer.Buffer(new_path, [""])
                new_buf.modified = True
                context.add_buffer(new_buf)
                context.mode = "normal"
                context.sidebar_visible = True
                context.status_message = f"dir: changed directory to {path}"
                context.log_command("dir: changed directory to " + path)
            except Exception as e:
                context.status_message = "error changing directory: " + str(e)
                context.log_command("dir error: " + str(e))
        else:
            context.status_message = "invalid directory."
        return

    if cmd_lower.startswith("f "):
        query = cmd[2:].strip()
        if not query:
            context.status_message = "search string empty."
        else:
            context.start_search(query)
        return

    if cmd_lower.startswith("fn "):
        new_name = cmd[3:].strip()
        if not new_name:
            context.status_message = "no filename provided."
            return
        try:
            with open(new_name, 'w', encoding='utf-8'):
                pass
        except Exception as e:
            context.status_message = f"error creating file: {e}"
            return
        new_buf = buffer.Buffer(new_name, [""])
        new_buf.modified = False
        context.add_buffer(new_buf)
        context.status_message = f"fn: created new file {new_name}"
        context.log_command(f"fn: file created: {new_name}")
        return

    if cmd_lower.startswith("fr "):
        new_name = cmd[3:].strip()
        if not new_name:
            context.status_message = "no new filename provided."
            return
        current_filename = context.current_buffer.filename
        if not current_filename:
            context.status_message = "no file open to rename."
            return
        try:
            os.rename(current_filename, new_name)
            context.current_buffer.filename = new_name
            context.current_buffer.save_to_file()
            context.status_message = f"fr: renamed file to {new_name}"
            context.log_command(f"fr: file renamed to {new_name}")
        except Exception as e:
            context.status_message = f"error renaming file: {e}"
            context.log_command(f"fr: error renaming file: {e}")
        return

    if cmd_lower.startswith("fd"):
        current_filename = context.current_buffer.filename
        if not current_filename:
            context.status_message = "no file open to delete."
            return
        try:
            os.remove(current_filename)
            context.current_buffer.filename = None
            context.current_buffer.lines = [""]
            context.current_buffer.cursor_line = 0
            context.current_buffer.cursor_col = 0
            context.current_buffer.scroll = 0
            context.current_buffer.modified = False
            context.status_message = f"fd: deleted file {current_filename}"
            context.log_command(f"fd: file deleted {current_filename}")
        except Exception as e:
            context.status_message = f"error deleting file: {e}"
            context.log_command(f"fd: error deleting file: {e}")
        return

    # Interpret multiple tokens as quick commands
    tokens = cmd_lower.split()
    for token in tokens:
        if token in ('c', 'clear'):
            context.current_buffer.lines = [""]
            context.current_buffer.cursor_line = 0
            context.current_buffer.cursor_col = 0
            context.current_buffer.modified = True
            context.log_command("c: clear")
            context.status_message = "file cleared."
        elif token == 'w':
            if context.current_buffer.filename is None:
                name = context.ui.prompt_input(context, "enter filename to save:")
                if not name:
                    continue
                context.current_buffer.filename = name
            context.current_buffer.save_to_file()
            num_bytes = sum(len(line) for line in context.current_buffer.lines) + (len(context.current_buffer.lines) - 1)
            context.log_command(f"w: write ({num_bytes} bytes)")
        elif token == 's':
            if context.zen_mode:
                context.status_message = "sidebar disabled in zen mode."
            else:
                context.sidebar_visible = not context.sidebar_visible
                mode_str = "on" if context.sidebar_visible else "off"
                context.log_command(f"s: sidebar {mode_str}")
                context.status_message = f"sidebar {mode_str}."
        elif token == 'h':
            if context.zen_mode:
                context.status_message = "help disabled in zen mode."
            else:
                context.sidebar_help_mode = True
                context.help_mode_expiry = time.time() + 3
                context.log_command("h: help on")
                context.status_message = "help on."
        elif token == 't':
            if context.zen_mode:
                context.status_message = "file tree disabled in zen mode."
            else:
                if context.mode != "filetree":
                    context.mode = "filetree"
                    root_path = os.getcwd()
                    context.file_tree_root = filetree.FileNode(
                        os.path.basename(root_path) or root_path,
                        root_path,
                        True
                    )
                    context.file_tree_root.expanded = True
                    filetree.load_children(context.file_tree_root, context.show_hidden, context)
                    context.flat_file_list = filetree.flatten_tree(context.file_tree_root)
                    context.filetree_selection_index = 0
                    context.filetree_scroll_offset = 0
                    context.log_command("t: file tree")
                    context.status_message = "file tree activated."
                else:
                    context.mode = "normal"
                    context.log_command("t: normal")
                    context.status_message = "normal mode."
        elif token == 'q':
            context.log_command("q: quit")
            context.graceful_exit()
            return
        elif token == 'z':
            if len(context.buffers) > 1:
                context.buffers[context.current_buffer_index].cursor_line = context.current_buffer.cursor_line
                context.buffers[context.current_buffer_index].cursor_col = context.current_buffer.cursor_col
                context.buffers[context.current_buffer_index].scroll = context.current_buffer.scroll
                context.current_buffer_index = (context.current_buffer_index - 1) % len(context.buffers)
                context.current_buffer = context.buffers[context.current_buffer_index]
                context.status_message = f"goto[{context.current_buffer.cursor_line+1}]"
        elif token == 'x':
            if len(context.buffers) > 1:
                context.buffers[context.current_buffer_index].cursor_line = context.current_buffer.cursor_line
                context.buffers[context.current_buffer_index].cursor_col = context.current_buffer.cursor_col
                context.buffers[context.current_buffer_index].scroll = context.current_buffer.scroll
                context.current_buffer_index = (context.current_buffer_index + 1) % len(context.buffers)
                context.current_buffer = context.buffers[context.current_buffer_index]
                context.status_message = f"goto[{context.current_buffer.cursor_line+1}]"

