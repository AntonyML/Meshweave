"""Diálogo «Acerca de»: información, metadatos técnicos y términos de uso.

Se abre desde la cabecera de la app (botón «ℹ️ Acerca de»). Es un modal
independiente: no toca configuración ni servicios. Los textos legales viven
en este módulo para poder editarlos sin tocar la lógica.
"""
from __future__ import annotations

import sys

import customtkinter as ctk

from meshweave import APP_ID, APP_NAME, __version__
from meshweave.paths import data_dir
from meshweave.ui import icons
from meshweave.ui.theme import FONT_MONO, FONT_UI, C
from meshweave.ui.widgets import btn, card, h2

ABOUT_TEXT = (
    "Meshweave es tu centro de control local: levanta el túnel Cloudflare hacia tu "
    "backend, lo inicia y vigila, sincroniza tu base local (Docker/Supabase) con la "
    "nube, hace backups del dump y te avisa por email si algo falla. Todo desde tu PC, "
    "sin tocar terminales: la configuración vive en %ProgramData%\\Meshweave y los "
    "secretos se guardan cifrados con DPAPI de Windows."
)

# Términos de uso y condiciones (editable aquí).
TERMS: list[tuple[str, str]] = [
    ("1. Uso del software",
     "Meshweave se ofrece para gestionar tu propio túnel, backend, sincronización de "
     "bases de datos y backups. Queda prohibido revender, sublicenciar o redistribuir "
     "el software sin autorización expresa del autor."),
    ("2. Datos y privacidad",
     "La configuración y los registros se guardan localmente en tu PC "
     "(%ProgramData%\\Meshweave); los secretos (TunnelSecret, contraseñas) se cifran "
     "con DPAPI de Windows y nunca se escriben en texto plano. La aplicación solo envía "
     "datos a los servicios que TÚ configuras (Cloudflare, Supabase, Resend, Docker) y "
     "a la nube que indiques. Eres responsable de la seguridad de tus credenciales y de "
     "mantener tus propias copias de seguridad."),
    ("3. Servicios de terceros",
     "El funcionamiento depende de servicios externos (Cloudflare Tunnels, Supabase, "
     "Resend, Docker). Sus términos, precios y disponibilidad no dependen de Meshweave "
     "ni de su autor."),
    ("4. Sin garantía",
     "El software se distribuye «tal cual», sin garantías de ningún tipo, expresas o "
     "implícitas, incluidas —sin limitación— las de comerciabilidad, idoneidad para un "
     "fin particular y no infracción. El uso es bajo tu propia responsabilidad."),
    ("5. Limitación de responsabilidad",
     "En ningún caso el autor será responsable de daños directos, indirectos, "
     "incidentales, especiales o consecuentes derivados del uso o la imposibilidad de "
     "uso del software, incluida, sin limitación, la pérdida de datos o de beneficios."),
    ("6. Modificaciones",
     "Estos términos pueden actualizarse en futuras versiones. El uso continuado de la "
     "aplicación tras un cambio implica la aceptación de los nuevos términos."),
]


class AboutDialog(ctk.CTkToplevel):
    """Modal con información, metadatos y términos de uso."""

    def __init__(self, master):
        super().__init__(master)
        self.title(f"Acerca de {APP_NAME}")
        self.geometry("660x620")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(100, self._center)

    def _center(self):
        try:
            self.update_idletasks()
            mx = self.master.winfo_rootx() + (self.master.winfo_width() - self.winfo_width()) // 2
            my = self.master.winfo_rooty() + (self.master.winfo_height() - self.winfo_height()) // 2
            self.geometry(f"+{max(mx, 0)}+{max(my, 0)}")
        except Exception:  # noqa: BLE001 — centrar es cosmético
            pass

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=C["darker"], corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text=f"{APP_NAME} — Acerca de", image=icons.photo("brand", 18),
                     compound="left", font=ctk.CTkFont("Segoe UI Semibold", 15),
                     text_color=C["ondark"]).pack(anchor="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(hdr, text="Centro de control local · túnel, backend, sync, backups y alertas",
                     font=ctk.CTkFont(*FONT_UI), text_color=C["sub"]).pack(anchor="w", padx=18, pady=(0, 12))

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(6, 0))

        # ── Sobre Meshweave ──
        c1 = card(body)
        c1.pack(fill="x", padx=4, pady=(0, 8))
        h2(c1, "Sobre Meshweave").pack(anchor="w", padx=14, pady=(10, 4))
        ctk.CTkLabel(c1, text=ABOUT_TEXT, font=ctk.CTkFont(*FONT_UI),
                     text_color=C["text"], wraplength=580, justify="left",
                     anchor="w").pack(anchor="w", padx=14, pady=(0, 10))

        # ── Detalles (metadatos) ──
        c2 = card(body)
        c2.pack(fill="x", padx=4, pady=(0, 8))
        h2(c2, "Detalles").pack(anchor="w", padx=14, pady=(10, 4))
        meta = [
            ("Versión", f"v{__version__}"),
            ("ID de aplicación", APP_ID),
            ("Carpeta de datos", str(data_dir())),
            ("Python", sys.version.split()[0]),
            ("Interfaz", f"Tk {self.tk.call('info', 'patchlevel')} · "
                         f"CustomTkinter {ctk.__version__}"),
        ]
        for k, v in meta:
            row = ctk.CTkFrame(c2, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=1)
            ctk.CTkLabel(row, text=k, width=150, font=ctk.CTkFont(*FONT_UI),
                         text_color=C["sub"], anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=v, font=ctk.CTkFont(*FONT_MONO),
                         text_color=C["text"], anchor="w", justify="left").pack(
                side="left", fill="x", expand=True)
        ctk.CTkLabel(c2, text="", height=4).pack()

        # ── Términos de uso ──
        c3 = card(body)
        c3.pack(fill="x", padx=4, pady=(0, 8))
        h2(c3, "Términos de uso y condiciones").pack(anchor="w", padx=14, pady=(10, 4))
        for title, text in TERMS:
            ctk.CTkLabel(c3, text=title, font=ctk.CTkFont("Segoe UI Semibold", 12),
                         text_color=C["text"], anchor="w").pack(anchor="w", padx=14, pady=(6, 0))
            ctk.CTkLabel(c3, text=text, font=ctk.CTkFont(*FONT_UI), text_color=C["sub"],
                         wraplength=580, justify="left", anchor="w").pack(anchor="w", padx=14, pady=(0, 2))
        ctk.CTkLabel(c3, text="", height=6).pack()

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=14, pady=10)
        btn(foot, "Cerrar", self.destroy, "info").pack(side="right", padx=4)
