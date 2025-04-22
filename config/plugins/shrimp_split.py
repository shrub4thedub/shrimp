import curses
from dataclasses import dataclass
import shrimp.ui.screen as ui_screen

@dataclass
class PaneState:
    buf_index:   int
    cursor_line: int
    cursor_col:  int
    scroll:      int      # vertical scroll
    scroll_x:    int      # horizontal scroll

def _ensure_monkey_patch():
    if getattr(ui_screen, '_orig_display', None) is None:
        ui_screen._orig_display = ui_screen.display

        def split_display(ctx):
            # 1) fallback when not splitting
            if not getattr(ctx, 'split_active', False):
                return ui_screen._orig_display(ctx)

            # 2) sync focused pane from context.current_buffer
            ps = ctx.panes[ctx.split_focus]
            ps.cursor_line = ctx.current_buffer.cursor_line
            ps.cursor_col  = ctx.current_buffer.cursor_col
            ps.scroll      = ctx.current_buffer.scroll

            # 3) recompute sizes & geometry
            ctx.height, ctx.width = ctx.stdscr.getmaxyx()
            visible_height = ctx.height - 1

            # sidebar width (always log mode)
            if ctx.sidebar_visible and ctx.width >= 80:
                sidebar_w = 30
            elif ctx.sidebar_visible:
                sidebar_w = 20
            else:
                sidebar_w = 0
            x0     = sidebar_w
            full_w = ctx.width - x0
            half_w = full_w // 2
            mid    = x0 + half_w

            # reserve 5 cols for line numbers + space
            text_w = half_w - 6

            # 4) clamp vertical scroll so cursor is visible
            if ps.cursor_line < ps.scroll:
                ps.scroll = ps.cursor_line
            if ps.cursor_line >= ps.scroll + visible_height:
                ps.scroll = ps.cursor_line - visible_height + 1

            # clamp within file bounds
            lines = ctx.buffers[ps.buf_index].lines
            max_scroll = max(0, len(lines) - visible_height)
            ps.scroll = max(0, min(ps.scroll, max_scroll))
            ctx.current_buffer.scroll = ps.scroll

            # 5) clamp horizontal scroll so cursor is visible
            if ps.cursor_col < ps.scroll_x:
                ps.scroll_x = ps.cursor_col
            if ps.cursor_col >= ps.scroll_x + text_w:
                ps.scroll_x = ps.cursor_col - text_w + 1
            ps.scroll_x = max(0, ps.scroll_x)

            # 6) draw sidebar (log mode)
            ui_screen.draw_sidebar(ctx, sidebar_w)
            #6.5) allow plugins to render
            ctx.plugin_manager.render(ctx)

            # 7) clear both pane regions
            for y in range(visible_height):
                try:
                    ctx.stdscr.addstr(y, x0, " " * full_w,
                                      curses.color_pair(2))
                except curses.error:
                    pass

            # 8) draw text + line numbers in each pane
            for i, (x_start, pane) in enumerate(((x0, ctx.panes[0]),
                                                (mid, ctx.panes[1]))):
                buf    = ctx.buffers[pane.buf_index]
                lines  = buf.lines
                vscroll= pane.scroll
                hscroll= pane.scroll_x

                for row in range(visible_height):
                    idx = vscroll + row
                    if idx >= len(lines):
                        break

                    # line number
                    num = f"{idx+1:>4} "
                    # clipped & scrolled text
                    snippet = lines[idx]
                    txt = snippet[hscroll : hscroll + text_w]
                    # pad/truncate
                    txt = txt.ljust(text_w)

                    # highlight current line in focused pane
                    if i == ctx.split_focus and idx == pane.cursor_line:
                        color = curses.color_pair(10)
                    else:
                        color = curses.color_pair(2)

                    try:
                        # draw line number
                        ctx.stdscr.addstr(row,
                                          x_start,
                                          num,
                                          curses.color_pair(4))
                        # draw text
                        ctx.stdscr.addstr(row,
                                          x_start + len(num),
                                          txt,
                                          color)
                    except curses.error:
                        pass

            # 9) draw vertical divider _after_ both panes
            for y in range(visible_height):
                try:
                    ctx.stdscr.addch(y,
                                     mid - 1,
                                     curses.ACS_VLINE,
                                     curses.color_pair(3) | curses.A_BOLD)
                except curses.error:
                    pass

            # 10) single dot on the active pane, bright color
            dot_x = x0 if ctx.split_focus == 0 else ctx.width - 1
            try:
                ctx.stdscr.addstr(0,
                                  dot_x,
                                  "●",
                                  curses.color_pair(5) | curses.A_BOLD)
            except curses.error:
                pass

            # 11) status bar + cmdline
            ui_screen.draw_status_bar(ctx)
            if ctx.mode == "command":
                ui_screen.draw_centered_cmdline(ctx)

            # 12) move the real cursor into the focused pane
            prow = ps.cursor_line - ps.scroll
            pcol = ps.cursor_col  - ps.scroll_x
            if 0 <= prow < visible_height and 0 <= pcol < text_w:
                cx = (x0 if ctx.split_focus == 0 else mid) + 5 + pcol
                try:
                    ctx.stdscr.move(prow, cx)
                except curses.error:
                    pass
            curses.curs_set(1)

        ui_screen.display = split_display

def begin_split(ctx, log, status, api):
    if getattr(ctx, 'split_active', False):
        return status("Already in a split.")
    # turn on split
    ctx.split_active = True
    ctx.split_focus  = 0

    # pane #1 initial state
    ctx.panes = [PaneState(
        buf_index   = ctx.current_buffer_index,
        cursor_line = ctx.current_buffer.cursor_line,
        cursor_col  = ctx.current_buffer.cursor_col,
        scroll      = ctx.current_buffer.scroll,
        scroll_x    = 0
    )]

    # open filetree for pane #2
    ctx.ui.show_full_filetree(ctx)

    # pane #2 initial state
    ctx.panes.append(PaneState(
        buf_index   = ctx.current_buffer_index,
        cursor_line = ctx.current_buffer.cursor_line,
        cursor_col  = ctx.current_buffer.cursor_col,
        scroll      = ctx.current_buffer.scroll,
        scroll_x    = 0
    ))

    # install our monkey‑patch
    _ensure_monkey_patch()
    status("Split created. Press f/g to switch focus.")

def focus_left(ctx, log, status, api):
    if not getattr(ctx, 'split_active', False):
        return
    ctx.split_focus = 0
    ctx.switch_to_buffer(ctx.panes[0].buf_index)

def focus_right(ctx, log, status, api):
    if not getattr(ctx, 'split_active', False):
        return
    ctx.split_focus = 1
    ctx.switch_to_buffer(ctx.panes[1].buf_index)
