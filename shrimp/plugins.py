"""
shrimp/plugins.py ­– v4.0  (2025‑04‑18)
──────────────────────────────────────────────────────────────────────────────
• Keeps every feature shipped in v3 (multi‑bind, persistent enable flags,
  injected helpers, smart‑undo snapshot, full back‑compat) :contentReference[oaicite:2]{index=2}&#8203;:contentReference[oaicite:3]{index=3}
• NEW  ► draw‑hook framework   →  plugins can register functions that are
          called once per screen refresh (perfect for sidebars / HUDs).
        ► api.add_draw_hook(fn) / api.remove_draw_hook(fn)
• NEW  ► api.register_key_handler(fn) placeholder for future hot‑patching.
• NEW  ► render(ctx) entrypoint on the manager ‑‑ call this from screen.display
• Zero behavioural changes for existing plugins.
"""

from __future__ import annotations
import os, json, inspect, typing as _t
from types import SimpleNamespace
from dataclasses import dataclass, field
import curses

from shrimp import logger            # noqa: E402  (local import duty)

# ───────────────────────── paths ─────────────────────────
PLUGIN_DIR = os.path.expanduser("~/shrimp/config/plugins")
CONF_PATH  = os.path.join(PLUGIN_DIR, "plugins.conf")
os.makedirs(PLUGIN_DIR, exist_ok=True)

# ─────────────────── data structures ────────────────────
@dataclass
class Bind:
    key      : str
    mode     : str
    func     : _t.Callable
    enabled  : bool = True
    title    : str  = ""
    desc     : str  = ""
    # legacy attr
    @property
    def key_or_cmd(self): return self.key

@dataclass
class Plugin:
    name     : str
    title    : str = ""
    desc     : str = ""
    binds    : list[Bind] = field(default_factory=list)
    enabled  : bool = True
    expanded : bool = False                # UI only

    # helper maps ---------------------------------------------------------
    def key_map(self):
        m: dict[str, dict[int, Bind]] = {}
        for b in self.binds:
            if self.enabled and b.enabled and b.mode != "command":
                m.setdefault(b.mode, {})[ord(b.key[0])] = b
        return m

    def cmd_map(self):
        m: dict[str, Bind] = {}
        for b in self.binds:
            if self.enabled and b.enabled and b.mode == "command":
                m[b.key.lower()] = b
        return m

# ─────────────────── plugin manager ─────────────────────
class PluginManager:
    def __init__(self) -> None:
        self.plugins : list[Plugin]             = []
        self._kmap   : dict[str, dict[int, Bind]] = {}
        self._cmap   : dict[str, Bind]            = {}

        # NEW draw‑hooks (called every frame from UI)
        self._draw_hooks : list[_t.Callable[["EditorContext"], None]] = []

        self._load_all()

    # ── persistence ──────────────────────────────────────
    def _load_state(self):
        try:  return json.load(open(CONF_PATH, encoding="utf‑8"))
        except Exception: return {}

    def _save_state(self):
        try:
            data = {
                p.name: {"__enabled": p.enabled,
                         "__binds": {b.key: b.enabled for b in p.binds}}
                for p in self.plugins
            }
            json.dump(data, open(CONF_PATH, "w", encoding="utf‑8"), indent=2)
        except Exception as e:
            logger.log(f"[plugins] save_state: {e}")

    # ── loading / parsing  (.plug → Plugin/Bind objects) ─
    def _load_all(self):
        state = self._load_state()
        self.plugins.clear()

        for fn in os.listdir(PLUGIN_DIR):
            if fn.endswith(".plug"):
                try:  self._parse_file(os.path.join(PLUGIN_DIR, fn))
                except Exception as e:
                    logger.log(f"[plugins] {fn}: {e}")

        # restore enable flags
        for p in self.plugins:
            if p.name in state:
                info = state[p.name]
                p.enabled = info.get("__enabled", True)
                for b in p.binds:
                    if b.key in info.get("__binds", {}):
                        b.enabled = info["__binds"][b.key]

        self._rebuild_maps()

    def _parse_file(self, path: str):
        """Super‑simple ShrimpScript (.plug) compiler (indent‑safe)."""
        with open(path, encoding="utf‑8") as f:
            lines = f.readlines()

        pl: Plugin | None = None
        cur: dict | None  = None
        body: list[str]   = []

        def flush_bind():
            nonlocal cur, body, pl
            if not cur: return
            # compile body into _act
            code = ["def _act(ctx, log, status, api):"] + \
                   ["    " + ln for ln in (body or ["pass"])]
            ns: dict[str, _t.Any] = {}
            try:  exec("\n".join(code), ns)
            except Exception as e:
                logger.log(f"[plugins] compile {pl.name}:{cur['key']}: {e}")
                cur, body = None, []
                return
            pl.binds.append(
                Bind(cur["key"], cur["mode"], ns["_act"],
                     title=cur.get("title", ""),
                     desc=cur.get("desc", ""))
            )
            cur, body = None, []

        def flush_plugin():
            nonlocal pl
            if pl: self.plugins.append(pl)
            pl = None

        for raw in lines + ["\n"]:                       # sentinel
            ln = raw.rstrip("\n")
            if not ln.strip(): continue

            if ln.startswith("def "):
                flush_bind(); flush_plugin()
                pl = Plugin(name=ln[4:].strip())
                continue

            if pl is None: continue
            s = ln.strip()

            if s.startswith("title "):
                if cur: cur["title"] = s[6:].strip()
                else:    pl.title    = s[6:].strip()
                continue
            if s.startswith("description "):
                if cur: cur["desc"] = s[12:].strip()
                else:    pl.desc    = s[12:].strip()
                continue
            if s.startswith("bind "):
                flush_bind()
                parts = s[5:].split()
                cur   = {"key": parts[0], "mode": "normal"}
                if len(parts) >= 3 and parts[1] == "mode":
                    cur["mode"] = parts[2]
                continue

            if cur: body.append(ln)

        flush_bind(); flush_plugin()

    # ── maps ─────────────────────────────────────────────
    def _rebuild_maps(self):
        self._kmap.clear(); self._cmap.clear()
        for p in self.plugins:
            for mode, d in p.key_map().items():
                self._kmap.setdefault(mode, {}).update(d)
            self._cmap.update(p.cmd_map())

    # ── dispatch helpers  (called by UI input layer) ────
    def handle_key(self, mode: str, key: int, ctx) -> bool:
        # — allow default “[num] + Enter” line‑jump when our sidebar is closed
        if mode == "normal" and ord('0') <= key <= ord('9'):
            if not getattr(ctx, "clipbar_open", False):
                return False

        # now see if we really have a plugin bind
        b = self._kmap.get(mode, {}).get(key)
        if b:
            self._run(b, ctx)
            return True
        return False

    def handle_command(self, cmd: str, ctx) -> bool:
        b = self._cmap.get(cmd.lower())
        if b:
            self._run(b, ctx)
            return True
        return False

    # back‑compat aliases
    handle_key_event = handle_key
    execute_command  = handle_command

    # ── enable / disable toggles ─────────────────────────
    def toggle_plugin(self, idx: int):
        if 0 <= idx < len(self.plugins):
            p = self.plugins[idx]
            p.enabled = not p.enabled
            for b in p.binds: b.enabled = p.enabled
            self._rebuild_maps(); self._save_state()

    def toggle_bind(self, p_i: int, b_i: int):
        p = self.plugins[p_i]; b = p.binds[b_i]
        b.enabled = not b.enabled
        p.enabled = any(x.enabled for x in p.binds)
        self._rebuild_maps(); self._save_state()

    # ── runtime call ─────────────────────────────────────
    def _run(self, b: Bind, ctx):
        # convenience helpers injected into plugin call
        log    = ctx.log_command
        status = lambda m: setattr(ctx, "status_message", m)

        def draw(y: int, x: int, text: str, attr: int = 0):
            try: ctx.stdscr.addstr(y, x, text, attr)
            except curses.error:
                pass
            except Exception as e:
                logger.log(f"[plugins] draw error: {e}")

        # API object – growable
        api = SimpleNamespace(
            draw            = draw,
            snapshot        = lambda c=ctx: self._snapshot(c),
            add_draw_hook   = self._add_draw_hook,
            remove_draw_hook= self._remove_draw_hook,
            register_key_handler = lambda *_: None   # placeholder
        )

        try:
            if len(inspect.signature(b.func).parameters) == 3:
                # legacy (ctx, log, status)
                b.func(ctx, log, status)
            else:
                b.func(ctx, log, status, api)
        except Exception as e:
            msg = f"plugin '{b.key}' error: {e}"
            ctx.log_command(msg)
            logger.log("[plugins] " + msg)

    # ── draw‑hook management ─────────────────────────────
    def _add_draw_hook(self, fn):
        if fn not in self._draw_hooks:
            self._draw_hooks.append(fn)

    def _remove_draw_hook(self, fn):
        try: self._draw_hooks.remove(fn)
        except ValueError: pass

    def render(self, ctx):
        """Call from UI once per frame *after* the main text area is cleared."""
        for fn in list(self._draw_hooks):      # copy – allow hooks to self‑remove
            try: fn(ctx)
            except Exception as e:
                logger.log(f"[plugins] draw‑hook: {e}")

    # ── global snapshot helper (undo) ───────────────────
    def _snapshot(self, ctx, max_items: int = 100):
        hist = ctx.__dict__.setdefault("_undo_hist", [])
        clone = [l[:] for l in ctx.current_buffer.lines]
        if not hist or clone != hist[-1]:
            hist.append(clone)
            if len(hist) > max_items:
                hist.pop(0)
            ctx.__dict__.setdefault("_redo_hist", []).clear()

# ── singleton accessor ──────────────────────────────────
_mgr: PluginManager | None = None
def get_plugin_manager() -> PluginManager:
    global _mgr
    if _mgr is None:
        _mgr = PluginManager()
    return _mgr