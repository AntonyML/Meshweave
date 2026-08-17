"""Pestaña Diagnóstico: verificaciones del sistema, gestor de cloudflared y
exportación de diagnóstico (con secretos enmascarados)."""
from __future__ import annotations

import threading
import os
import platform
import shutil

import customtkinter as ctk

from meshweave import sync as sync_mod
from meshweave.config import load_config
from meshweave.logging_setup import redact
from meshweave.process_runner import CREATE_NO_WINDOW
from meshweave.readiness import is_admin
from meshweave.services import cloudflared_manager
from meshweave.ui.theme import FONT_UI, C
from meshweave.ui.widgets import append_line, btn, card, h2, mono_box, tag_configure


class DiagnosticsView:
    def __init__(self, parent, app):
        self.app = app
        self._build(parent)

    def _build(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        top = card(parent)
        top.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 3))
        h2(top, "Verificaciones").pack(anchor="w", padx=14, pady=(10, 4))
        brow = ctk.CTkFrame(top, fg_color="transparent")
        brow.pack(fill="x", padx=10, pady=(0, 6))
        btn(brow, "Ejecutar verificaciones", self.run_checks, "info", icon="search").pack(side="left", padx=4)
        btn(brow, "Exportar diagnóstico (sin secretos)", self.export, "border", icon="upload").pack(side="left", padx=4)
        self.checks_box = mono_box(top)
        self.checks_box.pack(fill="x", padx=10, pady=(0, 10))
        self.checks_box.configure(state="disabled", height=130)
        tag_configure(self.checks_box)

        cf = card(parent)
        cf.grid(row=1, column=0, sticky="ew", padx=6, pady=3)
        h2(cf, "Componente cloudflared").pack(anchor="w", padx=14, pady=(10, 4))
        ctk.CTkLabel(cf, text="El binario se descarga desde GitHub Releases a "
                              "%ProgramData%\\Meshweave\\bin\\ (fuera del repo), con verificación.",
                     font=ctk.CTkFont(*FONT_UI), text_color=C["sub"], wraplength=640,
                     anchor="w", justify="left").pack(anchor="w", padx=14)
        crow = ctk.CTkFrame(cf, fg_color="transparent")
        crow.pack(fill="x", padx=10, pady=(4, 10))
        self.cf_lbl = ctk.CTkLabel(crow, text="cloudflared: verificando…",
                                   font=ctk.CTkFont(*FONT_UI), text_color=C["warn"])
        self.cf_lbl.pack(side="left", padx=4)
        self.btn_download = btn(crow, "Descargar / instalar", self.download, "ok", icon="download")
        self.btn_download.pack(side="right", padx=4)
        btn(crow, "Verificar versión", self._check_version, "border", icon="refresh").pack(side="right", padx=4)

        out = card(parent)
        out.grid(row=2, column=0, sticky="nsew", padx=6, pady=(3, 6))
        out.columnconfigure(0, weight=1)
        out.rowconfigure(1, weight=1)
        head = ctk.CTkFrame(out, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 2))
        h2(head, "Observabilidad y recursos").pack(side="left", padx=4)
        btn(head, "Actualizar recursos", self._load_resources, "border", icon="refresh").pack(side="right")
        self.output = mono_box(out)
        self.output.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.output.configure(state="disabled")
        tag_configure(self.output)
        self._load_resources()

    def _load_resources(self):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        def _go():
            lines = []
            try:
                import psutil
                lines += [(f"CPU: {psutil.cpu_percent(interval=1)}%", "info"),
                          (f"RAM: {psutil.virtual_memory().percent}% usados ({psutil.virtual_memory().used // 1024**2} MB de {psutil.virtual_memory().total // 1024**2} MB)", "info")]
            except ImportError:
                lines.append(("(instala psutil para ver CPU y RAM)", "warn"))
            total, _used, free = shutil.disk_usage("C:\\")
            lines += [(f"Disco C: {free / 1024**3:.1f} GB libres de {total / 1024**3:.1f} GB", "info"),
                      (f"OS: {platform.version()}", "info")]
            self.app.post(lambda: [append_line(self.output, text, level) for text, level in lines])
        threading.Thread(target=_go, daemon=True).start()
        self._check_version()

    def append(self, line: str, level: str = "info"):
        append_line(self.output, line, level)

    # ── Checks ──

    def run_checks(self):
        self.checks_box.configure(state="normal")
        self.checks_box.delete("1.0", "end")
        self.checks_box.configure(state="disabled")
        append_line(self.checks_box, "Ejecutando verificaciones…", "info")

        def _go():
            lines = []
            lines.append(("Admin: " + ("sí" if is_admin() else "NO (install de servicios bloqueado)"),
                          "ok" if is_admin() else "warn"))
            cfg = load_config()
            lines.append(("Tunnel ID configurado: " + ("sí" if cfg.get("tunnel_id") else "no"),
                          "ok" if cfg.get("tunnel_id") else "warn"))
            ver = cloudflared_manager.installed_version()
            lines.append(("cloudflared: " + (ver or "NO instalado"),
                          "ok" if ver else "err"))
            try:
                res = sync_mod.check_connections(cfg)
                for name, info in res.items():
                    if info.get("ok"):
                        lines.append((f"Conexión {name}: OK (PG {info['version']} | {info['size']})", "ok"))
                    else:
                        lines.append((f"Conexión {name}: {info.get('error', '')}", "err"))
            except Exception as e:  # noqa: BLE001
                lines.append((f"Conexiones: {redact(str(e))}", "err"))
            try:
                import shutil
                total, used, free = shutil.disk_usage(cfg.get("supabase_env", "C:\\")[:3] + "\\")
                lines.append((f"Disco {cfg.get('supabase_env', 'C:')[:3]}: "
                              f"{free / 1024 ** 3:.1f} GB libres de {total / 1024 ** 3:.1f} GB", "ok"))
            except Exception:  # noqa: BLE001
                pass
            self.app.post(lambda: self._apply_checks(lines))

        threading.Thread(target=_go, daemon=True).start()

    def _apply_checks(self, lines):
        self.checks_box.configure(state="normal")
        self.checks_box.delete("1.0", "end")
        for text, level in lines:
            tag = {"ok": "ok", "err": "err"}.get(level, "warn")
            tb = getattr(self.checks_box, "_textbox", None)
            if tb:
                tb.insert("end", "• " + text + "\n", tag)
            else:
                self.checks_box.insert("end", "• " + text + "\n")
        self.checks_box.configure(state="disabled")

    # ── cloudflared manager ──

    def _check_version(self):
        def _go():
            ver = cloudflared_manager.installed_version()
            latest = None
            try:
                latest = cloudflared_manager.latest_release().get("tag_name")
            except Exception:  # noqa: BLE001
                pass
            self.app.post(lambda: self._apply_version(ver, latest))

        threading.Thread(target=_go, daemon=True).start()

    def _apply_version(self, ver, latest):
        if ver:
            text = f"cloudflared {ver}"
            if latest and latest.lstrip("v") != ver:
                text += f" (disponible: {latest})"
            self.cf_lbl.configure(text=text, text_color=C["ok"])
        else:
            self.cf_lbl.configure(text="cloudflared NO instalado — descárgalo",
                                  text_color=C["err"])

    def download(self):
        self.btn_download.configure(state="disabled", text="⏳ Descargando…")

        def _go():
            ok, msg = cloudflared_manager.download()
            self.app.post(lambda: (self.btn_download.configure(state="normal", text="Descargar / instalar"),
                                   self._check_version(),
                                   self.app.toast(msg, "ok" if ok else "err")))

        threading.Thread(target=_go, daemon=True).start()

    # ── Export ──

    def export(self):
        def _go():
            lines = ["MESHWEAVE DIAGNÓSTICO (secretos enmascarados)", "=" * 40]
            cfg = load_config()
            for k in sorted(cfg):
                if "password" in k.lower() or "secret" in k.lower() or "key" in k.lower():
                    continue
                lines.append(f"{k} = {redact(str(cfg.get(k)))}")
            lines.append("")
            try:
                res = sync_mod.check_connections(cfg)
                for name, info in res.items():
                    lines.append(f"{name}: {info if info.get('ok') else info.get('error', '?')}")
            except Exception as e:  # noqa: BLE001
                lines.append(f"conexiones: {redact(str(e))}")
            lines.append("")
            lines.append(f"cloudflared: {cloudflared_manager.installed_version() or 'no instalado'}")
            report = "\n".join(lines)
            self.app.post(lambda: (self.append("Diagnóstico exportado al portapapeles:", "ok"),
                                   self.append(redact(report), "dim")))
            try:
                import subprocess
                subprocess.run(["clip"], input=report.encode("utf-16le"),
                               check=True, timeout=5, creationflags=CREATE_NO_WINDOW)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_go, daemon=True).start()
