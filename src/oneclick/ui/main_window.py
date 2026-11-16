"""The main window: destination, name, template, naming scheme and a live preview."""

from __future__ import annotations

import logging
import sys
import webbrowser
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from .. import APP_NAME, __version__
from ..core.errors import OneClickError
from ..core.settings import SettingsStore
from ..core.templates import Template
from ..core.undo import UndoStore
from ..system.opener import open_folder
from ..system.paths import settings_file, undo_file
from .branding import APP_ICON_16, APP_ICON_32, APP_ICON_64, APP_ICON_256, KAL_MOTION_LOGO_32
from .controller import AppController
from .settings_dialog import SettingsDialog
from .template_editor import TemplateEditor
from .theme import FONT_FAMILY, attach, center_window

log = logging.getLogger("oneclick")

CREDIT_TEXT = "Created by Kal-Motion"
CREDIT_URL = "https://kal-motion.com"


class MainWindow:
    def __init__(self, root: tk.Tk, controller: AppController) -> None:
        self.root = root
        self.c = controller
        self.theme = attach(root, dark=controller.settings.dark_mode)
        self._template_ids: list[str] = []
        self._scheme_ids: list[str] = []
        self._can_create = False
        self._logo: Optional[tk.PhotoImage] = None

        root.title(APP_NAME)
        root.minsize(560, 600)

        self.dest_var = tk.StringVar(value=controller.destination)
        self.name_var = tk.StringVar(value=controller.name)
        self.template_var = tk.StringVar()
        self.scheme_var = tk.StringVar()
        self.status_var = tk.StringVar()

        self._build()
        self._load_choices()
        self.dest_var.trace_add("write", self.refresh)
        self.name_var.trace_add("write", self.refresh)

        root.bind("<Return>", self._on_return)
        root.bind("<Escape>", lambda _event: root.destroy())
        root.bind("<Control-z>", lambda _event: self.undo_last())
        root.bind("<Control-comma>", lambda _event: self.open_settings(None))
        root.bind("<Control-e>", lambda _event: self.edit_template())
        root.bind("<Control-o>", lambda _event: self.browse_destination())
        self._update_undo_button()
        self.refresh()
        self._focus_first_field()

    # ---- layout ------------------------------------------------------------

    def _build(self) -> None:
        p = self.theme.palette
        frame = ttk.Frame(self.root, padding=(20, 14, 20, 10))
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        row = 0

        header = ttk.Frame(frame)
        header.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Start New Project", style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Settings", style="Link.TButton", command=lambda: self.open_settings(None)).grid(row=0, column=1, sticky="e")
        row += 1

        ttk.Label(frame, text="DESTINATION", style="Field.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        dest_row = ttk.Frame(frame)
        dest_row.grid(row=row, column=0, sticky="ew", pady=(3, 12))
        dest_row.columnconfigure(0, weight=1)
        self.dest_entry = ttk.Combobox(dest_row, textvariable=self.dest_var)
        self.dest_entry.grid(row=0, column=0, sticky="ew")
        self.dest_entry.bind("<<ComboboxSelected>>", lambda _e: (self.c.refresh_listing(), self.refresh(), self.name_entry.focus_set()))
        self.browse_btn = ttk.Button(dest_row, text="Browse…", command=self.browse_destination)
        self.browse_btn.grid(row=0, column=1, padx=(6, 0))
        row += 1

        ttk.Label(frame, text="PROJECT NAME", style="Primary.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        self.name_entry = ttk.Entry(frame, textvariable=self.name_var, font=(FONT_FAMILY, 16), style="Primary.TEntry")
        self.name_entry.grid(row=row, column=0, sticky="ew", pady=(3, 14), ipady=4)
        row += 1

        two = ttk.Frame(frame)
        two.grid(row=row, column=0, sticky="ew", pady=(0, 2))
        two.columnconfigure(0, weight=3)
        two.columnconfigure(1, weight=2)
        row += 1

        ttk.Label(two, text="TEMPLATE", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        template_row = ttk.Frame(two)
        template_row.grid(row=1, column=0, sticky="ew", pady=(3, 0), padx=(0, 8))
        template_row.columnconfigure(0, weight=1)
        self.template_combo = ttk.Combobox(template_row, textvariable=self.template_var, state="readonly")
        self.template_combo.grid(row=0, column=0, sticky="ew")
        self.template_combo.bind("<<ComboboxSelected>>", self._on_template_selected)
        self.edit_template_btn = ttk.Button(template_row, text="Edit", width=5, command=self.edit_template)
        self.edit_template_btn.grid(row=0, column=1, padx=(6, 0))

        ttk.Label(two, text="NAMING", style="Field.TLabel").grid(row=0, column=1, sticky="w")
        scheme_row = ttk.Frame(two)
        scheme_row.grid(row=1, column=1, sticky="ew", pady=(3, 0))
        scheme_row.columnconfigure(0, weight=1)
        self.scheme_combo = ttk.Combobox(scheme_row, textvariable=self.scheme_var, state="readonly")
        self.scheme_combo.grid(row=0, column=0, sticky="ew")
        self.scheme_combo.bind("<<ComboboxSelected>>", self._on_scheme_selected)
        ttk.Button(scheme_row, text="Edit", width=5, command=lambda: self.open_settings("Naming")).grid(row=0, column=1, padx=(6, 0))

        desc_row = ttk.Frame(frame)
        desc_row.grid(row=row, column=0, sticky="ew", pady=(2, 10))
        desc_row.columnconfigure(0, weight=1)
        self.template_desc = ttk.Label(desc_row, text="", style="Small.TLabel", wraplength=380, justify="left")
        self.template_desc.grid(row=0, column=0, sticky="w")
        ttk.Button(desc_row, text="Use a folder as template…", style="Link.TButton", command=self.add_folder_template).grid(row=0, column=1, sticky="e")
        row += 1

        self.folder_label = ttk.Label(frame, text="", font=(FONT_FAMILY, 17, "bold"))
        self.folder_label.grid(row=row, column=0, sticky="w")
        row += 1
        self.number_label = ttk.Label(frame, text="", style="Small.TLabel")
        self.number_label.grid(row=row, column=0, sticky="w", pady=(0, 6))
        row += 1

        tree_frame = ttk.Frame(frame, style="Card.TFrame")
        tree_frame.grid(row=row, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        frame.rowconfigure(row, weight=1)
        self.tree_text = tk.Text(tree_frame, height=11, wrap="none", state="disabled", font=("Consolas" if sys.platform == "win32" else "Menlo" if sys.platform == "darwin" else "TkFixedFont", 11))
        self.theme.style_text(self.tree_text)
        self.tree_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree_text.configure(yscrollcommand=scroll.set)
        row += 1

        self.message_label = ttk.Label(frame, text="", wraplength=520, justify="left")
        self.message_label.grid(row=row, column=0, sticky="w", pady=(8, 0))
        row += 1

        bottom = ttk.Frame(frame)
        bottom.grid(row=row, column=0, sticky="ew", pady=(10, 0))
        bottom.columnconfigure(1, weight=1)
        row += 1

        # left: credit + version, on the same line as the buttons
        credit = ttk.Frame(bottom)
        credit.grid(row=0, column=0, sticky="w")
        credit_widgets = []
        try:
            self._logo = tk.PhotoImage(data=KAL_MOTION_LOGO_32)
            logo_label = ttk.Label(credit, image=self._logo)
            logo_label.pack(side="left", padx=(0, 8))
            credit_widgets.append(logo_label)
        except tk.TclError:
            log.warning("Could not load the embedded logo")
        text_label = ttk.Label(credit, text=CREDIT_TEXT, style="Muted.TLabel")
        text_label.pack(side="left")
        credit_widgets.append(text_label)
        for widget in credit_widgets:  # the whole credit is a link to the website
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda _e: webbrowser.open(CREDIT_URL))
            widget.bind("<Enter>", lambda _e, w=text_label: w.configure(foreground=p.accent))
            widget.bind("<Leave>", lambda _e, w=text_label: w.configure(foreground=p.muted))
        ttk.Label(credit, text=f"v{__version__}", style="Small.TLabel").pack(side="left", padx=(12, 0))

        # middle: status text; right: buttons
        ttk.Label(bottom, textvariable=self.status_var, style="Muted.TLabel").grid(row=0, column=1, sticky="w", padx=12)
        ttk.Button(bottom, text="Close", command=self.root.destroy).grid(row=0, column=2, padx=(0, 6))
        self.create_btn = ttk.Button(bottom, text="Create project  ⏎", style="Accent.TButton", command=self.create)
        self.create_btn.grid(row=0, column=3)

    # ---- choices -------------------------------------------------------------

    def _template_label(self, t: Template) -> str:
        if t.is_folder_template:
            return t.name + (" (folder)" if t.available else " (folder missing)")
        return t.name if t.builtin else t.name + " (mine)"

    def _load_choices(self) -> None:
        templates = self.c.library.templates
        self._template_ids = [t.id for t in templates]
        self.template_combo["values"] = [self._template_label(t) for t in templates]
        if self.c.template_id in self._template_ids:
            self.template_combo.current(self._template_ids.index(self.c.template_id))

        schemes = self.c.library.schemes
        self._scheme_ids = [s.id for s in schemes]
        self.scheme_combo["values"] = [s.label for s in schemes]
        if self.c.scheme_id in self._scheme_ids:
            self.scheme_combo.current(self._scheme_ids.index(self.c.scheme_id))

        self.dest_entry["values"] = self.c.recent_destinations()

    def _on_template_selected(self, _event=None) -> None:
        index = self.template_combo.current()
        if 0 <= index < len(self._template_ids):
            self.c.template_id = self._template_ids[index]
        self.refresh()

    def _on_scheme_selected(self, _event=None) -> None:
        index = self.scheme_combo.current()
        if 0 <= index < len(self._scheme_ids):
            self.c.scheme_id = self._scheme_ids[index]
        self.refresh()

    def _on_return(self, event) -> None:
        if isinstance(event.widget, ttk.Button):
            return  # Enter on a focused button should not also create a project
        self.create()

    def _focus_first_field(self) -> None:
        if self.dest_var.get().strip() and Path(self.dest_var.get()).expanduser().is_dir():
            self.name_entry.focus_set()
        else:
            self.browse_btn.focus_set()

    # ---- actions -------------------------------------------------------------

    def browse_destination(self) -> None:
        current = Path(self.dest_var.get().strip()).expanduser()
        chosen = filedialog.askdirectory(
            parent=self.root,
            title="Choose where to create the project",
            initialdir=str(current) if current.is_dir() else str(Path.home()),
            mustexist=True,
        )
        if chosen:
            self.dest_var.set(str(Path(chosen)))
            self.c.refresh_listing()
            self.name_entry.focus_set()

    def add_folder_template(self) -> None:
        chosen = filedialog.askdirectory(parent=self.root, title="Choose a folder to use as a template", mustexist=True)
        if not chosen:
            return
        try:
            template = self.c.add_folder_template(chosen)
        except OneClickError as problem:
            messagebox.showerror(APP_NAME, str(problem), parent=self.root)
            return
        self._load_choices()
        self.refresh()
        self.status_var.set(f"Added template '{template.name}'")

    def edit_template(self) -> None:
        TemplateEditor(self.root, self.c.library, self.c.template, on_saved=self._after_template_saved)

    def _after_template_saved(self, template: Template) -> None:
        self.c.template_id = template.id
        self.c.store.save(self.c.settings)
        self._load_choices()
        self.refresh()
        self.status_var.set(f"Saved template '{template.name}'")

    def open_settings(self, start_tab: Optional[str]) -> None:
        SettingsDialog(self.root, self.c, start_tab=start_tab, on_close=self._after_settings)

    def _after_settings(self) -> None:
        self.c.reload_library()
        self._load_choices()
        self.refresh()

    def create(self) -> None:
        self.refresh()
        if not self._can_create:
            return
        try:
            created = self.c.create()
        except OneClickError as problem:
            messagebox.showerror(APP_NAME, str(problem), parent=self.root)
            self.c.refresh_listing()
            self.refresh()
            return
        except Exception:  # pragma: no cover - defensive; shown to the user and logged
            log.exception("Unexpected error while creating a project")
            messagebox.showerror(APP_NAME, "Something went wrong while creating the project. Details were saved to the log file.", parent=self.root)
            return

        if self.c.settings.open_after_create:
            open_folder(created.path)
        if self.c.settings.close_after_create:
            self.root.destroy()
            return
        self.name_var.set("")
        self.status_var.set(f"Created {created.folder_name}")
        self._update_undo_button()
        self._load_choices()
        self.refresh()
        self.name_entry.focus_set()

    def undo_last(self) -> None:
        record, problems = self.c.undo_info()
        if record is None:
            self._update_undo_button()
            return
        if problems:
            messagebox.showinfo(
                APP_NAME,
                f"'{record.folder_name}' can't be undone safely:\n\n- " + "\n- ".join(problems) + "\n\nNothing was deleted.",
                parent=self.root,
            )
            return
        if not messagebox.askyesno(APP_NAME, f"Delete the folder created at {record.created_at}?\n\n{record.path}", parent=self.root):
            return
        try:
            removed = self.c.undo()
        except OneClickError as problem:
            messagebox.showerror(APP_NAME, str(problem), parent=self.root)
        else:
            self.status_var.set(f"Removed {removed.name}")
        self._update_undo_button()
        self.refresh()

    def _update_undo_button(self) -> None:
        pass  # undo lives in Settings and on Ctrl+Z; nothing to update on the home screen

    # ---- preview ---------------------------------------------------------------

    def refresh(self, *_args) -> None:
        self.c.destination = self.dest_var.get()
        self.c.name = self.name_var.get()
        preview = self.c.preview()
        self._can_create = preview.can_create
        p = self.theme.palette

        self.folder_label.configure(text=preview.folder_name or "—", foreground=p.muted if preview.is_placeholder else p.text)
        self.number_label.configure(text=preview.number_info)
        self.template_desc.configure(text=self.c.template.description)
        self.tree_text.configure(state="normal")
        self.tree_text.delete("1.0", "end")
        self.tree_text.insert("1.0", "\n".join(preview.tree_lines))
        self.tree_text.configure(state="disabled")

        if preview.error:
            self.message_label.configure(text=preview.error, style="Error.TLabel")
        elif preview.warnings:
            self.message_label.configure(text="\n".join(preview.warnings), style="Warning.TLabel")
        elif preview.hint:
            self.message_label.configure(text=preview.hint, style="Muted.TLabel")
        else:
            self.message_label.configure(text="Ready. Press Enter to create.", style="Success.TLabel")
        self.create_btn.state(["!disabled"] if preview.can_create else ["disabled"])


def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
    except Exception:  # older Windows or restricted environment: just look slightly blurry
        pass


def _center_and_raise(root: tk.Tk) -> None:
    root.update_idletasks()
    width, height = max(root.winfo_reqwidth(), 580), max(root.winfo_reqheight(), 620)
    root.geometry(f"{width}x{height}")
    center_window(root)
    root.lift()
    root.attributes("-topmost", True)  # launched from a right-click menu: make sure it is seen
    root.after(300, lambda: root.attributes("-topmost", False))


def run_gui(initial_destination: Optional[str] = None, initial_name: str = "") -> int:
    _enable_dpi_awareness()
    root = tk.Tk()

    def report(exc_type, exc, tb) -> None:  # Tk swallows callback errors by default
        log.error("Unhandled error in the window", exc_info=(exc_type, exc, tb))
        messagebox.showerror(APP_NAME, f"Unexpected error: {exc}\n\nDetails were saved to the log file.", parent=root)

    root.report_callback_exception = report
    try:
        root._app_icons = [tk.PhotoImage(data=d) for d in (APP_ICON_256, APP_ICON_64, APP_ICON_32, APP_ICON_16)]  # type: ignore[attr-defined]
        root.iconphoto(True, *root._app_icons)  # type: ignore[attr-defined]
    except tk.TclError:
        log.warning("Could not set the window icon")
    controller = AppController(
        SettingsStore(settings_file()),
        UndoStore(undo_file()),
        initial_destination=initial_destination,
        initial_name=initial_name,
    )
    MainWindow(root, controller)
    _center_and_raise(root)
    root.mainloop()
    return 0
