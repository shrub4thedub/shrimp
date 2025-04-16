"""
shrimp/plugins.py
──────────────────────────────────────────────────────────────────────────────
Dynamic plugin manager for the Shrimp text editor, with persistent on/off
state (plugins.conf) and indentation‑safe compilation.

Version: 1.2 · 2025‑04‑17
"""

from __future__ import annotations
import os, json, typing as _t
from shrimp import logger

# ──────────────────────────  paths  ──────────────────────────
PLUGIN_DIR = os.path.expanduser("~/shrimp/config/plugins")
CONF_PATH  = os.path.join(PLUGIN_DIR, "plugins.conf")
os.makedirs(PLUGIN_DIR, exist_ok=True)


# ─────────────────────────  data classes  ────────────────────────
class Plugin:
    def __init__(self, name: str, mode: str, bind: str, func,
                 enabled: bool = True):
        self.name    = name
        self.mode    = mode.lower()
        self.bind    = bind
        self.func    = func
        self.enabled = enabled

    def toggle(self):
        self.enabled = not self.enabled


# ───────────────────────  plugin manager  ───────────────────────
class PluginManager:
    def __init__(self):
        self.plugins  : list[Plugin]                = []
        self.key_maps : dict[str, dict[int, Plugin]] = {}
        self.cmd_map  : dict[str, Plugin]            = {}

        self.load_plugins()

    # ─────────────── persistence helpers ───────────────
    def _load_config(self) -> dict[str, bool]:
        try:
            with open(CONF_PATH, encoding="utf‑8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_config(self):
        try:
            data = {p.name: p.enabled for p in self.plugins}
            with open(CONF_PATH, "w", encoding="utf‑8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.log(f"[plugins] cannot save plugins.conf: {e}")

    # ─────────────── public API ───────────────
    def load_plugins(self):
        """Parse all .plug files and apply persisted enabled flags."""
        persisted = self._load_config()

        self.plugins.clear()
        for fname in os.listdir(PLUGIN_DIR):
            if fname.endswith(".plug"):
                try:
                    self._parse_file(os.path.join(PLUGIN_DIR, fname))
                except Exception as exc:
                    logger.log(f"[plugins] load '{fname}': {exc}")

        # restore saved enabled/disabled states
        for p in self.plugins:
            if p.name in persisted:
                p.enabled = bool(persisted[p.name])

        self._rebuild_maps()

    def handle_key(self, mode: str, key: int, ctx) -> bool:
        p = self.key_maps.get(mode, {}).get(key)
        if p:
            self._run_plugin(p, ctx)
            return True
        return False

    def handle_command(self, cmd: str, ctx) -> bool:
        p = self.cmd_map.get(cmd.lower())
        if p:
            self._run_plugin(p, ctx)
            return True
        return False

    # backward‑compat names (old code still calls these)
    def handle_key_event(self, mode: str, key: int, ctx):      # noqa: N802
        return self.handle_key(mode, key, ctx)

    def execute_command(self, cmd: str, ctx):                  # noqa: N802
        return self.handle_command(cmd, ctx)

    def toggle_plugin(self, index: int):
        if 0 <= index < len(self.plugins):
            self.plugins[index].toggle()
            self._rebuild_maps()
            self._save_config()

    # ───────────────  parsing / compiling  ───────────────
    def _parse_file(self, path: str):
        with open(path, encoding="utf‑8") as f:
            lines = f.readlines()

        spec, body = None, []

        def flush():
            if not spec:
                return
            self._build_plugin(spec, body[:])
            body.clear()

        for line in lines + ["\n"]:          # sentinel newline to flush last block
            txt = line.rstrip("\n")
            if not txt.strip():
                continue
            if txt.startswith("def "):
                flush()
                spec = {"name": txt[4:].strip(),
                        "mode": "normal",
                        "bind": None}
                continue
            if spec is None:
                continue
            stripped = txt.strip()
            if stripped.startswith("mode "):
                spec["mode"] = stripped[5:].strip()
            elif stripped.startswith("bind "):
                spec["bind"] = stripped[5:].strip()
            else:
                body.append(txt)             # keep original indentation
        flush()

    def _build_plugin(self, sp: dict, body: list[str]):
        name, mode, bind = sp["name"], sp["mode"], sp["bind"]
        if not bind:
            logger.log(f"[plugins] {name}: missing bind – skipped")
            return

        py_lines = ["def _plugin_action(context):"]
        if body:
            # KEEP indentation from the .plug file
            py_lines += ["    " + ln for ln in body]
        else:
            py_lines.append("    pass")

        namespace: dict[str, _t.Any] = {}
        try:
            exec("\n".join(py_lines), namespace)
            func = namespace["_plugin_action"]
        except Exception as exc:
            logger.log(f"[plugins] {name}: compile error {exc}")
            return

        self.plugins.append(Plugin(name, mode, bind, func))

    # ───────────────  map building / execution  ───────────────
    def _rebuild_maps(self):
        self.key_maps.clear()
        self.cmd_map.clear()
        for p in self.plugins:
            if not p.enabled:
                continue
            if p.mode == "command":
                self.cmd_map[p.bind.lower()] = p
            else:
                try:
                    keycode = ord(p.bind[0])
                    self.key_maps.setdefault(p.mode, {})[keycode] = p
                except Exception:
                    pass

    def _run_plugin(self, plugin: Plugin, ctx):
        try:
            plugin.func(ctx)
        except Exception as exc:
            msg = f"plugin '{plugin.name}' error: {exc}"
            ctx.status_message = msg
            ctx.log_command(msg)
            logger.log("[plugins] " + msg)


# ───────────────  singleton accessor  ───────────────
_manager: PluginManager | None = None
def get_plugin_manager() -> PluginManager:
    global _manager
    if _manager is None:
        _manager = PluginManager()
    return _manager

