"""Pestaña Backups: dumps disponibles, retención, backup ahora, validar."""
from __future__ import annotations

import shutil
import subprocess

import customtkinter as ctk

from meshweave.config import load_config
from meshweave.paths import backups_dir
from meshweave.process_runner import CREATE_NO_WINDOW
from meshweave.ui.theme import FONT_UI, C
from meshweave.ui.widgets import append_line, btn, card, h2, mono_box, tag_configure


class BackupsView:
    def __init__(self, parent, app):
        self.app = app
        self._build(parent)

    def _build(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        top = card(parent)
        top.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 3))
        h2(top, "Backups del dump de la nube").pack(anchor="w", padx=14, pady=(10, 4))
        self.info_lbl = ctk.CTkLabel(top, text="", font=ctk.CTkFont(*FONT_UI),
                                     text_color=C["sub"], anchor="w", justify="left")
        self.info_lbl.pack(fill="x", padx=14, pady=(0, 4))
        brow = ctk.CTkFrame(top, fg_color="transparent")
        brow.pack(fill="x", padx=10, pady=(2, 10))
        btn(brow, "Backup ahora", self.app.actions.sync_backup_now, "ok", icon="save").pack(side="left", padx=4)
        btn(brow, "Validar dumps", self._validate, "border", icon="search").pack(side="left", padx=4)
        btn(brow, "Abrir carpeta", self._open_dir, "border", icon="folder").pack(side="left", padx=4)
        self.dump_combo = ctk.CTkComboBox(brow, width=200, state="readonly")
        self.dump_combo.pack(side="left", padx=(14, 4))
        btn(brow, "Restaurar en local", self._restore, "err", icon="restore").pack(side="left", padx=4)
        ctk.CTkLabel(top, text="Restaurar reescribe la DB local (Docker) con el contenido del dump "
                                "de la nube — para arrancar una PC nueva o recuperar una DB local "
                                "dañada. No toca la nube.",
                     font=ctk.CTkFont(*FONT_UI), text_color=C["warn"], wraplength=860,
                     anchor="w", justify="left").pack(anchor="w", padx=14, pady=(0, 8))

        out = card(parent)
        out.grid(row=1, column=0, sticky="nsew", padx=6, pady=(3, 6))
        out.columnconfigure(0, weight=1)
        out.rowconfigure(1, weight=1)
        h2(out, "Dumps disponibles").grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))
        self.output = mono_box(out)
        self.output.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.output.configure(state="disabled")
        tag_configure(self.output)
        self.refresh()

    def append(self, line: str, level: str = "info"):
        append_line(self.output, line, level)

    def _open_dir(self):
        import os
        d = backups_dir()
        d.mkdir(parents=True, exist_ok=True)
        os.startfile(d)

    def _restore(self):
        from tkinter import messagebox

        dump = self.dump_combo.get()
        if not dump:
            self.append("Selecciona un dump de la lista para restaurar.", "warn")
            return
        if not messagebox.askyesno(
            "Restaurar en local",
            f"Se reescribirá la DB local (Docker) con «{dump}» del backup de la nube.\n\n"
            "Las tablas que ya existan se conservan; se cargan las que falten. "
            "Esta acción NO toca la nube. ¿Continuar?",
            parent=self.app,
        ):
            return
        self.append(f"▶ Restaurando {dump} en la DB local…", "info")

        def _go():
            from meshweave.config import load_config
            from meshweave.sync import restore_dump
            try:
                cfg = load_config()
                result = restore_dump(cfg, dump, emit=lambda msg, lvl: self.app._q.put(("backup", msg, lvl)))
                if result.get("status") != "ok":
                    self.app._q.put(("backup", f"Restauración FALLÓ: {result.get('error')}", "err"))
                else:
                    self.app._q.put(("backup", f"Restauración completada ({dump}).", "ok"))
            except Exception as e:  # noqa: BLE001
                self.app._q.put(("backup", f"ERROR restauración: {e}", "err"))

        import threading
        threading.Thread(target=_go, daemon=True).start()

    def _validate(self):
        self.append("Validación de dumps (solo lectura de cabecera):", "info")
        d = backups_dir()
        for f in sorted(d.glob("cloud-*.dump")):
            pg_restore = shutil.which("pg_restore")
            if pg_restore:
                r = subprocess.run([pg_restore, "-l", str(f)], capture_output=True,
                                   text=True, timeout=60, creationflags=CREATE_NO_WINDOW)
                ok, detail = r.returncode == 0, (r.stderr or r.stdout).splitlines()[0][:60] if r.returncode else ""
            else:
                ok = f.read_bytes()[:5] == b"PGDMP"
                detail = "sin pg_restore local, cabecera inválida" if not ok else "sin pg_restore local"
            self.append(f"  {f.name}: {'OK' if ok else 'CORRUPTO'} ({detail})",
                        "ok" if ok else "err")

    def refresh(self):
        cfg = load_config()
        self.info_lbl.configure(
            text=f"Directorio: {backups_dir()}\n"
                 f"Retención: {cfg.get('backup_retention_days', 7)} días | "
                 f"Tarea: {cfg.get('backup_time', '01:30')} diaria "
                 f"({cfg.get('backup_task_name', 'MeshweaveBackupService')})")
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        from meshweave.sync import read_backup_runs
        runs = read_backup_runs(10)
        d = backups_dir()
        files = sorted(d.glob("cloud-*.dump")) if d.exists() else []
        text = []
        if files:
            names = [f.name for f in files[-10:]]
            self.dump_combo.configure(values=names)
            if self.dump_combo.get() not in names:
                self.dump_combo.set(names[-1])
            for f in files[-10:]:
                text.append(f"{f.name:28s} {f.stat().st_size / 1024 / 1024:6.2f} MB")
        else:
            self.dump_combo.configure(values=[])
            self.dump_combo.set("")
            text.append("(sin dumps todavía)")
        text.append("")
        text.append("Últimas corridas:")
        for r in runs:
            text.append(f"  {str(r.get('started_at', '—'))[:19]}  {r.get('status', '?')}  "
                        f"{r.get('file', '—')}  {(r.get('size_bytes') or 0) / 1024 / 1024:.2f} MB")
        self.output.insert("1.0", "\n".join(text))
        self.output.configure(state="disabled")
