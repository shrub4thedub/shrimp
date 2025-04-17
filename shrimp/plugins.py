"""
shrimp/plugins.py  —  v2.0  (2025‑04‑18)
• multi‑bind plugins with title/description
• log()/status() helpers injected
• per‑bind + plugin‑level enable state in plugins.conf
• hierarchical key/command maps
"""

from __future__ import annotations
import os, json, typing as _t
from dataclasses import dataclass, field
from shrimp import logger

PLUGIN_DIR = os.path.expanduser("~/shrimp/config/plugins")
CONF_PATH  = os.path.join(PLUGIN_DIR, "plugins.conf")
os.makedirs(PLUGIN_DIR, exist_ok=True)

# ─────────── dataclasses ───────────
@dataclass
class Bind:
    key     : str
    mode    : str
    func    : typing.Callable
    enabled : bool = True
    title   : str  = ""
    desc    : str  = ""

    # ←────────── add this block ──────────
    @property
    def key_or_cmd(self):
        """Back‑compat for older UI code that still expects .key_or_cmd"""
        return self.key
    # ─────────────────────────────────────


@dataclass
class Plugin:
    name     : str
    title    : str = ""
    desc     : str = ""
    binds    : list[Bind] = field(default_factory=list)
    enabled  : bool = True
    expanded : bool = False        # UI state only

    # quick lookup helpers
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

# ─────────── manager ───────────
class PluginManager:
    def __init__(self):
        self.plugins : list[Plugin] = []
        self._kmap: dict[str, dict[int, Bind]] = {}
        self._cmap: dict[str, Bind]            = {}
        self._load_all()

    # persistence ---------------------------------------------------------
    def _load_state(self):
        try:  return json.load(open(CONF_PATH))
        except Exception: return {}

    def _save_state(self):
        try:
            data = {
                p.name: {
                    "__enabled": p.enabled,
                    "__binds"  : {b.key: b.enabled for b in p.binds}
                } for p in self.plugins
            }
            json.dump(data, open(CONF_PATH,"w"), indent=2)
        except Exception as e:
            logger.log(f"[plugins] save_state: {e}")

    # loading -------------------------------------------------------------
    def _load_all(self):
        state = self._load_state()
        self.plugins.clear()
        for fn in os.listdir(PLUGIN_DIR):
            if fn.endswith(".plug"):
                try:  self._parse_file(os.path.join(PLUGIN_DIR,fn))
                except Exception as e: logger.log(f"[plugins] {fn}: {e}")

        for p in self.plugins:
            if p.name in state:
                info = state[p.name]
                p.enabled = info.get("__enabled", True)
                for b in p.binds:
                    if b.key in info.get("__binds", {}):
                        b.enabled = info["__binds"][b.key]
        self._rebuild_maps()

    def _parse_file(self, path):
        with open(path,encoding="utf-8") as f: lines = f.readlines()
        pl: Plugin|None = None; cur=None; body=[]
        def flush_bind():
            nonlocal cur, body, pl
            if not cur: return
            src = ["def _a(ctx,log,status):"]+["    "+l for l in (body or ["pass"])]
            ns={}
            try: exec("\n".join(src),ns); fn=ns["_a"]
            except Exception as e:
                logger.log(f"[plugins] compile {pl.name}:{cur['key']}: {e}")
                cur, body = None,[]
                return
            pl.binds.append(Bind(cur['key'],cur['mode'],fn,
                                 title=cur.get('title',''),
                                 desc=cur.get('desc','')))
            cur, body = None,[]
        def flush_plugin():
            nonlocal pl
            if pl: self.plugins.append(pl); pl=None
        for raw in lines+["\n"]:
            ln=raw.rstrip("\n")
            if not ln.strip(): continue
            if ln.startswith("def "):
                flush_bind(); flush_plugin()
                pl = Plugin(name=ln[4:].strip()); continue
            if pl is None: continue
            s = ln.strip()
            if s.startswith("title "):      pl.title=s[6:].strip(); continue
            if s.startswith("description "):pl.desc =s[12:].strip();continue
            if s.startswith("bind "):
                flush_bind()
                parts=s[5:].split()
                cur={"key":parts[0],"mode":"normal"}
                if len(parts)>=3 and parts[1]=="mode": cur["mode"]=parts[2]
                continue
            if cur and s.startswith("title "):       cur["title"]=s[6:].strip(); continue
            if cur and s.startswith("description "): cur["desc"]=s[12:].strip();continue
            if cur: body.append(ln)
        flush_bind(); flush_plugin()

    # maps ----------------------------------------------------------------
    def _rebuild_maps(self):
        self._kmap.clear(); self._cmap.clear()
        for p in self.plugins:
            for m,d in p.key_map().items(): self._kmap.setdefault(m,{}).update(d)
            self._cmap.update(p.cmd_map())

    # dispatch ------------------------------------------------------------
    def handle_key(self, mode, key, ctx):
        b=self._kmap.get(mode,{}).get(key); 
        if b: self._run(b,ctx); return bool(b)
        return False
    def handle_command(self, cmd, ctx):
        b=self._cmap.get(cmd.lower()); 
        if b: self._run(b,ctx); return bool(b)
        return False
    handle_key_event=handle_key       # back‑compat
    execute_command =handle_command

    # toggles -------------------------------------------------------------
    def toggle_plugin(self,i):
        if 0<=i<len(self.plugins):
            p=self.plugins[i]; p.enabled=not p.enabled
            for b in p.binds: b.enabled=p.enabled
            self._rebuild_maps(); self._save_state()
    def toggle_bind(self,pi,bi):
        p=self.plugins[pi]; b=p.binds[bi]
        b.enabled=not b.enabled
        p.enabled=any(x.enabled for x in p.binds)
        self._rebuild_maps(); self._save_state()

    # run -----------------------------------------------------------------
    def _run(self,b,ctx):
        try: b.func(ctx, lambda m: ctx.log_command(m),
                         lambda m: setattr(ctx,"status_message",m))
        except Exception as e:
            msg=f"plugin '{b.key}' error: {e}"
            ctx.log_command(msg); ctx.status_message=msg; logger.log("[plugins] "+msg)

# singleton
_mgr: PluginManager|None=None
def get_plugin_manager():
    global _mgr
    if _mgr is None: _mgr=PluginManager()
    return _mgr
