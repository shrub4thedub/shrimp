"""
Main entry point and editor context for the Shrimp text editor.
"""
import curses
import os
import time
from shrimp import buffer, filetree, logger, commands, ui

class EditorContext:
    """
    Holds the state of the editor and provides methods to manage global state.
    This includes list of buffers, file tree data, search mode, etc.
    """
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.height, self.width = stdscr.getmaxyx()

        # Buffer management
        self.buffers = []
        self.current_buffer_index = 0
        self.current_buffer = None

        # Create an initial buffer
        initial_buffer = buffer.Buffer()
        self.buffers.append(initial_buffer)
        self.current_buffer = initial_buffer

        # Editor modes: "normal", "insert", "command", "filetree", "search"
        self.mode = "normal"

        # File tree state
        root_path = os.getcwd()
        name = os.path.basename(root_path) or root_path
        self.file_tree_root = filetree.FileNode(name, root_path, True)
        self.file_tree_root.expanded = True
        filetree.load_children(self.file_tree_root, True, self)
        self.flat_file_list = filetree.flatten_tree(self.file_tree_root)
        self.filetree_selection_index = 0
        self.filetree_scroll_offset = 0
        self.show_hidden = True

        # Search
        self.search_mode = False
        self.search_results = []
        self.search_query = ""
        self.search_selected_index = 0

        # UI states
        self.sidebar_visible = True
        self.sidebar_help_mode = False
        self.help_mode_expiry = None
        self.zen_mode = False
        self.sidebar_visible_before_zen = True
        self.current_theme = "boring"

        # Input states
        self.normal_number_buffer = ""
        self.last_digit_time = 0
        self.normal_number_timeout = 0.5
        self.word_mode = False
        self.pending_line_change = False
        self.pending_word_change = False

        # Clipboards
        self.clipboard = ""
        self.word_clipboard = ""

        # Command-line buffer and status
        self.command_buffer = ""
        self.status_message = ""

        # Sidebar log
        self.sidebar_log = []

        # "ui" interface (screen drawing), plus a reference to the Buffer class
        self.ui = ui.screen
        self.BufferClass = buffer.Buffer

        # Mode icons for status bar
        self.mode_icons = {
            "normal": "",
            "insert": "",
            "command": "⌘",
            "filetree": "",
            "search": ""
        }

        # Color/theme detection
        self.extended_color_support = curses.can_change_color() and curses.COLORS >= 256
        self.apply_theme(self.current_theme)

        # Load theme from config if present
        self.load_theme_config()

        # Running flag
        self.exit_flag = False

    def log_command(self, msg: str):
        """
        Log a command or action to the sidebar log (and debug log file).
        """
        self.sidebar_log.append(msg)
        if len(self.sidebar_log) > 5:
            self.sidebar_log = self.sidebar_log[-5:]
        logger.log(msg)

    def switch_to_buffer(self, index: int):
        """Switch current buffer to the buffer at the given index."""
        if 0 <= index < len(self.buffers):
            self.current_buffer_index = index
            self.current_buffer = self.buffers[index]

    def add_buffer(self, buf: buffer.Buffer):
        """Add a new buffer and make it current."""
        self.buffers.append(buf)
        self.current_buffer_index = len(self.buffers) - 1
        self.current_buffer = buf
        self.current_buffer.cursor_line = 0
        self.current_buffer.cursor_col = 0
        self.current_buffer.scroll = 0

    def start_search(self, query: str):
        """Enter search mode for the given query string."""
        self.search_query = query
        self.search_results = []
        for i, line in enumerate(self.current_buffer.lines):
            if query.lower() in line.lower():
                self.search_results.append(i)
        if not self.search_results:
            self.status_message = f"No matches for '{query}'."
        else:
            self.search_mode = True
            self.search_selected_index = 0
            self.mode = "search"

    def graceful_exit(self):
        """
        Gracefully exit the editor. We do NOT call curses.endwin() here,
        because curses.wrapper(main) will handle that automatically.
        """
        logger.log("Editor exited.")
        self.exit_flag = True

    def apply_theme(self, theme_name: str):
        """Apply a color theme by initializing color pairs."""
        theme_name = theme_name or "boring"
        self.current_theme = theme_name

        if self.extended_color_support:
            if theme_name == 'boring':
                bg = (40, 42, 54); fg = (248, 248, 242)
                sel = (68, 71, 90); accent = (98, 114, 164)
                ft_bg = (51, 54, 71); sidebar = (52, 55, 70); highlight = (52, 55, 70)
            elif theme_name == 'shrimp':
                bg = (30, 30, 30); fg = (250, 240, 230)
                sel = (80, 60, 50); accent = (255, 165, 125)
                ft_bg = (45, 40, 35); sidebar = (50, 45, 40); highlight = (50, 45, 40)
            elif theme_name == 'catpuccin':
                bg = (30, 30, 46); fg = (205, 214, 244)
                sel = (69, 71, 90); accent = (137, 180, 250)
                ft_bg = (49, 50, 68); highlight = (69, 71, 90); sidebar = (24, 24, 37)
            else:
                return

            def to_curses(r, g, b):
                return int(r/255*1000), int(g/255*1000), int(b/255*1000)

            try:
                curses.init_color(16, *to_curses(*bg))
                curses.init_color(17, *to_curses(*fg))
                curses.init_color(18, *to_curses(*sel))
                curses.init_color(19, *to_curses(*accent))
                curses.init_color(20, *to_curses(*ft_bg))
                curses.init_color(21, *to_curses(*highlight))
                curses.init_color(22, *to_curses(*sidebar))
            except curses.error:
                pass

            curses.init_pair(1, 17, 18)
            curses.init_pair(2, 17, 16)
            curses.init_pair(3, 19, 16)
            curses.init_pair(4, 17, 22)
            curses.init_pair(5, 17, 19)
            curses.init_pair(6, 17, 16)
            curses.init_pair(7, 17, 20)
            curses.init_pair(8, 19, 20)
            curses.init_pair(9, 20, 16)
            curses.init_pair(10, 17, 21)
        else:
            # Fallback color pairs
            curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
            curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)
            curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)
            curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLUE)
            curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_BLUE)
            curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLACK)
            curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLUE)
            curses.init_pair(8, curses.COLOR_BLUE, curses.COLOR_BLUE)
            curses.init_pair(9, curses.COLOR_BLUE, curses.COLOR_BLACK)
            curses.init_pair(10, curses.COLOR_WHITE, curses.COLOR_BLACK)

    def get_current_filename(self):
        """Return the current buffer's filename or None."""
        return self.current_buffer.filename

    def get_current_lines(self):
        """Return the current buffer's lines."""
        return self.current_buffer.lines

    def process_filetree_mode(self, key: int):
        """Delegate filetree key handling to the input module."""
        ui.input.handle_filetree_mode(self, key)

    ##########################################
    # THEME PERSISTENCE
    ##########################################
    def load_theme_config(self):
        """
        Loads theme from file: ~/shrimp/config/themes/theme.conf
        If found, applies that theme immediately.
        """
        config_path = os.path.expanduser("~/shrimp/config/themes/theme.conf")
        if not os.path.isfile(config_path):
            return  # no config file yet
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith("theme="):
                        theme_name = line.split("=",1)[1].strip()
                        if theme_name:
                            self.apply_theme(theme_name)
        except:
            pass

    def save_theme_config(self):
        """
        Saves the current theme to: ~/shrimp/config/themes/theme.conf
        Creates directories if necessary.
        """
        config_path = os.path.expanduser("~/shrimp/config/themes/theme.conf")
        try:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(f"theme={self.current_theme}\n")
        except:
            pass

def main(stdscr):
    curses.start_color()
    context = EditorContext(stdscr)

    # If started with a filename argument, try to open it
    if len(os.sys.argv) > 1:
        fname = os.sys.argv[1]
        try:
            with open(fname, 'r', encoding='utf-8') as f:
                content = f.read().splitlines()
        except FileNotFoundError:
            context.status_message = f"file not found: {fname}"
        except Exception as e:
            context.status_message = f"error opening file: {e}"
        else:
            context.buffers[0].filename = fname
            context.buffers[0].lines = content if content else [""]
            context.buffers[0].modified = False
            context.current_buffer = context.buffers[0]

    # If no file was opened, show the main menu
    if context.current_buffer.filename is None:
        choice = context.ui.show_main_menu(context)
        if choice is None or choice == "q":
            context.graceful_exit()
        elif choice == "n":
            filename = context.ui.prompt_input(context, "enter new filename:")
            if filename:
                new_buf = buffer.Buffer(filename, [""])
                new_buf.modified = False
                context.add_buffer(new_buf)
                context.log_command("n: new file")
        elif choice == "t":
            context.ui.show_full_filetree(context)
        elif choice == "d":
            directory = context.ui.prompt_input(context, "enter directory path:")
            if directory and os.path.isdir(directory):
                os.chdir(directory)
                context.file_tree_root = filetree.FileNode(os.path.basename(directory) or directory,
                                                           directory,
                                                           True)
                context.file_tree_root.expanded = True
                filetree.load_children(context.file_tree_root, context.show_hidden, context)
                context.flat_file_list = filetree.flatten_tree(context.file_tree_root)
            else:
                context.status_message = "invalid directory."
        elif choice == "f":
            query = context.ui.prompt_input(context, "enter search query:")
            if query:
                context.start_search(query)
            else:
                context.status_message = "search string empty."

    # Main loop
    while not context.exit_flag:
        ui.screen.display(context)
        key = context.stdscr.getch()
        if context.mode == "normal":
            ui.input.handle_normal_mode(context, key)
        elif context.mode == "insert":
            ui.input.handle_insert_mode(context, key)
        elif context.mode == "command":
            ui.input.handle_command_mode(context, key)
        elif context.mode == "filetree":
            ui.input.handle_filetree_mode(context, key)
        elif context.mode == "search":
            ui.input.handle_search_mode(context, key)

        if (context.normal_number_buffer and
            (time.time() - context.last_digit_time) > context.normal_number_timeout):
            context.normal_number_buffer = ""

def run():
    """
    Simple convenience function to start the curses wrapper with main().
    """
    curses.wrapper(main)

if __name__ == "__main__":
    run()

