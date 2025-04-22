# shrimp
do you love being different at the expense of your own productivity?
do you love using unfinished and poorly written software?
do you struggle to use vim but still want to flex that you use a modal editor?
will you try anything once?

then shrimp is for you!

shrimp is a really shitty python-based text editor with multiple modes for "efficient" text editing. 
we got user theming, and some commands i made up.

## Normal Mode Basics
- **i**: Enter insert mode (to type text).
- **d**: Delete the current line.
- **y**: Copy the current line.
- **p**: Replace the current line, then enter insert mode.
- **w**: Trigger “word actions” (jump, copy, delete word).
- **x**: Switch to the next buffer (if multiple files are open).

## Command Mode Basics
Press **o** in normal mode to enter command mode
- **`->w`** — Save (write) the current file.
- **`->q`** — Quit the editor.
- **`->wq`** — Save, then quit.
- **`->th`** — Open the theme menu to switch color schemes.
- **`->tb`** — Open the buffer menu to switch buffers
- **`->plug`** — Open the plugin menu to toggle plugins.
- **`->h`** — there are a few more commands - do this to see em all

## Theming
shrimp supports user-created themes. simply drop `.py` theme files in `~/shrimp/config/themes/`, then use **`->th`** to pick a color scheme on the fly. theres an example theme you can copy and tweak to your liking.

## Plugins
shrimp supports user-created plugins as well! put some .plug files in /shrimp/config/plugins. we've got some premade ones for you to copy and tweak and learn from as well!

## Installation
i havent thought about how to do this yet im still learning give it time.....