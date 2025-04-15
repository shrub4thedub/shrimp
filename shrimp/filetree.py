"""
File tree management for the Shrimp text editor.

This module defines the FileNode class representing files and directories in the file browser,
and provides functions to build and flatten a directory tree structure. It also includes 
functions to load directory contents with optional hidden file filtering.
"""
import os
from shrimp import logger

# Icon definitions for file tree display (requires a Nerd Font for proper rendering)
FOLDER_ICON_CLOSED = " "   # Collapsed folder arrow
FOLDER_ICON_OPEN   = " "   # Expanded folder arrow
FOLDER_SYMBOL      = ""    # Folder icon
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

class FileNode:
    """Node in a file tree, representing a file or directory."""
    def __init__(self, name: str, path: str, is_dir: bool, parent=None):
        self.name = name
        self.path = path
        self.is_dir = is_dir
        self.parent = parent
        self.children = []     # List of FileNode children (for directories).
        self.expanded = False  # Whether this directory node is expanded in the UI.

    def toggle_expanded(self) -> None:
        """Toggle this directory node between expanded and collapsed."""
        if self.is_dir:
            self.expanded = not self.expanded

def flatten_tree(node: FileNode, depth: int = 0) -> list:
    """
    Flatten the file tree rooted at `node` into a list of (FileNode, depth) tuples.
    Uses a breadth-first approach so that expansions reflect in the UI.
    """
    result = []
    stack = [(node, depth)]
    while stack:
        n, d = stack.pop(0)
        result.append((n, d))
        if n.is_dir and n.expanded:
            for child in n.children:
                stack.insert(0, (child, d + 1))
    return result

def load_children(node: FileNode, show_hidden: bool = True, context=None) -> None:
    """
    Load the direct children of the directory represented by `node`.
    If `context` is provided (EditorContext), display a loading progress on the status bar.
    """
    if not node.is_dir:
        return
    try:
        entries_iter = os.scandir(node.path)
    except OSError as e:
        node.children = []
        if context:
            context.status_message = f"error listing directory: {e}"
            logger.log(f"Error listing directory {node.path}: {e}")
        return

    entries = []
    for entry in entries_iter:
        if not show_hidden and entry.name.startswith('.'):
            continue
        entries.append(entry)
    entries.sort(key=lambda e: e.name)

    node.children = []
    total = len(entries)
    if context:
        # Initial loading message
        status_y = context.height - 1
        msg = f" loading... 0/{total} "
        logger.safe_addstr(context.stdscr, status_y, max(0, context.width - len(msg)), msg)
        context.stdscr.refresh()

    for i, entry in enumerate(entries):
        if context:
            msg = f" loading... {i+1}/{total} "
            logger.safe_addstr(context.stdscr, context.height - 1, max(0, context.width - len(msg)), msg)
            context.stdscr.refresh()
        child_path = os.path.join(node.path, entry.name)
        is_child_dir = entry.is_dir()
        child_node = FileNode(entry.name, child_path, is_child_dir, parent=node)
        node.children.append(child_node)

    if context:
        # Final loading message
        msg = f" loading... {total}/{total} "
        logger.safe_addstr(context.stdscr, context.height - 1, max(0, context.width - len(msg)), msg)
        context.stdscr.refresh()

def build_tree_iter(root_path: str, show_hidden: bool = True) -> FileNode:
    """
    Build the entire file tree for the given root path using an iterative approach.
    Returns the root FileNode. 
    """
    name = os.path.basename(root_path) or root_path
    root_node = FileNode(name, root_path, os.path.isdir(root_path))
    queue = [root_node]
    while queue:
        current = queue.pop(0)
        if current.is_dir:
            try:
                entries = os.scandir(current.path)
            except OSError:
                entries = []
            children_nodes = []
            for entry in entries:
                if not show_hidden and entry.name.startswith('.'):
                    continue
                child_node = FileNode(entry.name, entry.path, entry.is_dir(), parent=current)
                children_nodes.append(child_node)
                if child_node.is_dir:
                    queue.append(child_node)
            children_nodes.sort(key=lambda cn: cn.name)
            current.children = children_nodes
    return root_node

