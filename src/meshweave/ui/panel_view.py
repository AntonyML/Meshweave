"""Panel combinado: resumen del túnel y checklist de preparación."""
from __future__ import annotations

import customtkinter as ctk

from meshweave.ui.dashboard_view import DashboardView
from meshweave.ui.estado_view import EstadoView


class PanelView:
    def __init__(self, parent, app):
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        host = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        host.grid(row=0, column=0, sticky="nsew")
        dashboard_host = ctk.CTkFrame(host, fg_color="transparent")
        dashboard_host.pack(fill="x")
        estado_host = ctk.CTkFrame(host, fg_color="transparent", height=320)
        estado_host.pack(fill="both", expand=True)
        self.dashboard = DashboardView(dashboard_host, app)
        self.estado_view = EstadoView(estado_host, app)
        self.dashboard_frame = self.dashboard
        self.estado = self.estado_view
        self._last_items = []
        self._build = host

    def set_checklist(self, *args):
        return self.dashboard.set_checklist(*args)

    def apply_items(self, items):
        return self.estado_view.apply_items(items)

    def append(self, *args):
        return self.dashboard.append(*args)

    def refresh(self):
        self.dashboard.refresh()
