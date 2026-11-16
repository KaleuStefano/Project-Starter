"""Settings window: templates, naming schemes and general options."""

from __future__ import annotations

import datetime as dt
import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable, Optional

from .. import APP_NAME, __version__
from ..core.errors import OneClickError
from ..core.naming import CASE_STYLES, COUNTER_SCOPES, TOKEN_HELP, NamingScheme, apply_case, render_folder_name
from ..system.context_menu import get_context_menu
from ..system.opener import open_folder
from ..system.paths import user_data_dir
from .controller import AppController
from .template_editor import TemplateEditor
from .theme import center_window, get_theme

log = logging.getLogger("oneclick")


class SettingsDialog:
    def __init__(
        self,
        parent: tk.Misc,
        controller: AppController,
        start_tab: Optional[str] = None,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        self.c = controller
        self.on_close = on_close
        self.win = tk.Toplevel(parent)
        self.theme = get_theme(parent)
        self.theme.style_toplevel(self.win)
        self.win.title(f"{APP_NAME} – Settings")
        self.win.transient(parent)
        self.win.minsize(640, 480)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda _e: self.close())

        self.notebook = ttk.Notebook(self.win)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(10, 4))
        self.tabs = {
            "Templates": self._build_templates_tab(),
            "Naming": self._build_naming_tab(),
            "General": self._build_general_tab(),
        }
        for title, frame in self.tabs.items():
            self.notebook.add(frame, text=title)
        if start_tab in self.tabs:
            self.notebook.select(self.tabs[start_tab])

        ttk.Button(self.win, text="Done", style="Accent.TButton", command=self.close).pack(anchor="e", padx=12, pady=(0, 10))
        center_window(self.win, parent)
        self.win.grab_set()

    def close(self) -> None:
        self.c.store.save(self.c.settings)
        self.win.grab_release()
        self.win.destroy()
        if self.on_close:
            self.on_close()

    # ---------------------------------------------------------------- templates

    def _build_templates_tab(self) -> ttk.Frame:
        frame = ttk.Frame(self.notebook, padding=12)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        card = ttk.Frame(frame, style="Card.TFrame")
        card.grid(row=0, column=0, sticky="nsew")
        self.template_list = tk.Listbox(card, exportselection=False, activestyle="none")
        self.theme.style_listbox(self.template_list)
        self.template_list.pack(fill="both", expand=True)
        self.template_list.bind("<<ListboxSelect>>", lambda _e: self._show_template_details())
        self.template_list.bind("<Double-1>", lambda _e: self._edit_template())

        side = ttk.Frame(frame)
        side.grid(row=0, column=1, sticky="ns", padx=(10, 0))
        self.edit_template_btn = ttk.Button(side, text="Edit…", command=self._edit_template)
        self.edit_template_btn.pack(fill="x")
        ttk.Button(side, text="Duplicate", command=self._duplicate_template).pack(fill="x", pady=(6, 0))
        self.rename_template_btn = ttk.Button(side, text="Rename…", command=self._rename_template)
        self.rename_template_btn.pack(fill="x", pady=(6, 0))
        self.remove_template_btn = ttk.Button(side, text="Remove", command=self._remove_template)
        self.remove_template_btn.pack(fill="x", pady=(6, 0))
        self.default_template_btn = ttk.Button(side, text="Set as default", command=self._set_default_template)
        self.default_template_btn.pack(fill="x", pady=(16, 0))
        ttk.Button(side, text="Add folder template…", command=self._add_template).pack(fill="x", pady=(16, 0))

        self.template_details = ttk.Label(frame, text="", wraplength=560, justify="left")
        self.template_details.grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self._fill_template_list()
        return frame

    def _fill_template_list(self, select_id: Optional[str] = None) -> None:
        self._listed_templates = list(self.c.library.templates)
        self.template_list.delete(0, "end")
        default_id = self.c.settings.default_template_id
        for t in self._listed_templates:
            tags = []
            if t.id == default_id:
                tags.append("default")
            if t.is_folder_template:
                tags.append("folder" if t.available else "folder missing")
            elif not t.builtin:
                tags.append("mine")
            self.template_list.insert("end", t.name + (f"   [{', '.join(tags)}]" if tags else ""))
        wanted = select_id or self.c.template_id
        index = next((i for i, t in enumerate(self._listed_templates) if t.id == wanted), 0)
        self.template_list.selection_set(index)
        self._show_template_details()

    def _selected_template(self):
        selection = self.template_list.curselection()
        return self._listed_templates[selection[0]] if selection else None

    def _show_template_details(self) -> None:
        t = self._selected_template()
        if t is None:
            self.template_details.configure(text="")
            return
        lines = [t.description] if t.description else []
        if t.source is not None:
            lines.append(f"Folder: {t.source}")
        problem = t.problem()
        if problem:
            lines.append(problem)
        else:
            lines.append(f"Creates {len(t.entries())} items.")
        if t.builtin:
            lines.append("Built-in preset. 'Edit' or 'Duplicate' makes your own copy to change.")
        self.template_details.configure(text="\n".join(lines))
        editable = not t.builtin
        self.remove_template_btn.state(["!disabled"] if editable else ["disabled"])
        self.rename_template_btn.state(["!disabled"] if editable else ["disabled"])
        self.edit_template_btn.state(["!disabled"] if t.available else ["disabled"])
        self.default_template_btn.state(["!disabled"] if t.available else ["disabled"])

    def _add_template(self) -> None:
        chosen = filedialog.askdirectory(parent=self.win, title="Choose a folder to use as a template", mustexist=True)
        if not chosen:
            return
        try:
            template = self.c.library.add_folder_template(Path(chosen))
        except OneClickError as problem:
            messagebox.showerror(APP_NAME, str(problem), parent=self.win)
            return
        self._fill_template_list(select_id=template.id)

    def _remove_template(self) -> None:
        t = self._selected_template()
        if t is None or t.builtin:
            return
        what = "Remove the folder template" if t.is_folder_template else "Delete the template"
        note = " (the folder on disk is not touched)" if t.is_folder_template else ""
        if not messagebox.askyesno(APP_NAME, f"{what} '{t.name}'{note}?", parent=self.win):
            return
        self.c.library.remove_template(t.id)
        self._fill_template_list()

    def _edit_template(self) -> None:
        t = self._selected_template()
        if t is None or not t.available:
            return
        TemplateEditor(self.win, self.c.library, t, on_saved=lambda saved: self._fill_template_list(select_id=saved.id))

    def _duplicate_template(self) -> None:
        t = self._selected_template()
        if t is None:
            return
        try:
            copy = self.c.library.duplicate_template(t.id)
        except OneClickError as problem:
            messagebox.showerror(APP_NAME, str(problem), parent=self.win)
            return
        self._fill_template_list(select_id=copy.id)

    def _rename_template(self) -> None:
        t = self._selected_template()
        if t is None or t.builtin:
            return
        name = simpledialog.askstring("Rename template", "Template name:", initialvalue=t.name, parent=self.win)
        if not name:
            return
        try:
            self.c.library.rename_template(t.id, name)
        except OneClickError as problem:
            messagebox.showerror(APP_NAME, str(problem), parent=self.win)
            return
        self._fill_template_list(select_id=t.id)

    def _set_default_template(self) -> None:
        t = self._selected_template()
        if t is None:
            return
        self.c.settings.default_template_id = t.id
        self._fill_template_list(select_id=t.id)

    # ---------------------------------------------------------------- naming

    def _build_naming_tab(self) -> ttk.Frame:
        frame = ttk.Frame(self.notebook, padding=12)
        frame.columnconfigure(1, weight=1)

        scheme_card = ttk.Frame(frame, style="Card.TFrame")
        scheme_card.grid(row=0, column=0, rowspan=8, sticky="ns", padx=(0, 12))
        self.scheme_list = tk.Listbox(scheme_card, exportselection=False, height=6, activestyle="none")
        self.theme.style_listbox(self.scheme_list)
        self.scheme_list.pack(fill="both", expand=True)
        self.scheme_list.bind("<<ListboxSelect>>", lambda _e: self._load_scheme_into_form())

        self.s_label = tk.StringVar()
        self.s_pattern = tk.StringVar()
        self.s_sep = tk.StringVar()
        self.s_pad = tk.StringVar()
        self.s_case = tk.StringVar()
        self.s_scope = tk.StringVar()
        self.s_example = tk.StringVar()

        def row(r: int, text: str, widget: tk.Widget) -> None:
            ttk.Label(frame, text=text).grid(row=r, column=1, sticky="w", pady=(0, 2))
            widget.grid(row=r + 1, column=1, sticky="ew", pady=(0, 8))

        self.s_label_entry = ttk.Entry(frame, textvariable=self.s_label)
        row(0, "Name", self.s_label_entry)
        self.s_pattern_entry = ttk.Entry(frame, textvariable=self.s_pattern)
        row(2, "Pattern", self.s_pattern_entry)

        options = ttk.Frame(frame)
        options.grid(row=4, column=1, sticky="ew", pady=(0, 8))
        options.columnconfigure(3, weight=1)
        ttk.Label(options, text="Separator").grid(row=0, column=0, sticky="w")
        ttk.Label(options, text="Counter digits").grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Label(options, text="Case style").grid(row=0, column=2, sticky="w", padx=(12, 0))
        self.s_sep_entry = ttk.Entry(options, textvariable=self.s_sep, width=4)
        self.s_sep_entry.grid(row=1, column=0, sticky="w")
        self.s_pad_spin = ttk.Spinbox(options, from_=1, to=8, textvariable=self.s_pad, width=4)
        self.s_pad_spin.grid(row=1, column=1, sticky="w", padx=(12, 0))
        self.s_case_combo = ttk.Combobox(options, textvariable=self.s_case, state="readonly", values=list(CASE_STYLES.values()), width=16)
        self.s_case_combo.grid(row=1, column=2, sticky="w", padx=(12, 0))

        ttk.Label(frame, text="Counter").grid(row=5, column=1, sticky="w", pady=(0, 2))
        self.s_scope_combo = ttk.Combobox(frame, textvariable=self.s_scope, state="readonly", values=list(COUNTER_SCOPES.values()))
        self.s_scope_combo.grid(row=6, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(frame, textvariable=self.s_example, font="TkDefaultFont").grid(row=7, column=1, sticky="w")
        help_text = "Tokens: " + "   ".join(f"{{{k}}} {v}" for k, v in TOKEN_HELP.items())
        ttk.Label(frame, text=help_text, wraplength=420, justify="left", style="Muted.TLabel").grid(row=8, column=0, columnspan=2, sticky="w", pady=(6, 8))

        buttons = ttk.Frame(frame)
        buttons.grid(row=9, column=0, columnspan=2, sticky="w")
        self.s_save_btn = ttk.Button(buttons, text="Save changes", command=self._save_scheme)
        self.s_save_btn.pack(side="left")
        ttk.Button(buttons, text="Save as new", command=self._save_scheme_as_new).pack(side="left", padx=(6, 0))
        self.s_delete_btn = ttk.Button(buttons, text="Delete", command=self._delete_scheme)
        self.s_delete_btn.pack(side="left", padx=(6, 0))

        for var in (self.s_pattern, self.s_sep, self.s_pad, self.s_case, self.s_scope):
            var.trace_add("write", lambda *_: self._update_example())
        self._fill_scheme_list(select_id=self.c.scheme_id)
        return frame

    def _fill_scheme_list(self, select_id: Optional[str] = None) -> None:
        self._listed_schemes = list(self.c.library.schemes)
        self.scheme_list.delete(0, "end")
        for s in self._listed_schemes:
            self.scheme_list.insert("end", s.label + ("" if not s.builtin else "  (built-in)"))
        index = next((i for i, s in enumerate(self._listed_schemes) if s.id == select_id), 0)
        self.scheme_list.selection_clear(0, "end")
        self.scheme_list.selection_set(index)
        self._load_scheme_into_form()

    def _selected_scheme(self) -> NamingScheme:
        selection = self.scheme_list.curselection()
        return self._listed_schemes[selection[0] if selection else 0]

    def _load_scheme_into_form(self) -> None:
        s = self._selected_scheme()
        self.s_label.set(s.label)
        self.s_pattern.set(s.pattern)
        self.s_sep.set(s.sep)
        self.s_pad.set(str(s.pad))
        self.s_case.set(CASE_STYLES.get(s.case, CASE_STYLES["keep"]))
        self.s_scope.set(COUNTER_SCOPES.get(s.counter_scope, COUNTER_SCOPES["continue"]))
        state = ["disabled"] if s.builtin else ["!disabled"]
        self.s_save_btn.state(state)
        self.s_delete_btn.state(state)
        self._update_example()

    def _form_scheme(self, scheme_id: str) -> NamingScheme:
        case = next((k for k, v in CASE_STYLES.items() if v == self.s_case.get()), "keep")
        scope = next((k for k, v in COUNTER_SCOPES.items() if v == self.s_scope.get()), "continue")
        try:
            pad = int(self.s_pad.get())
        except ValueError:
            pad = 0  # fails validation with a clear message
        return NamingScheme(
            id=scheme_id,
            label=self.s_label.get().strip(),
            pattern=self.s_pattern.get(),
            sep=self.s_sep.get(),
            pad=pad,
            case=case,
            counter_scope=scope,
        )

    def _update_example(self) -> None:
        scheme = self._form_scheme("preview")
        try:
            scheme.validate()
            example = render_folder_name(scheme, apply_case("My Project", scheme.case), 5, dt.datetime.now())
            self.s_example.set(f"Example:  {example}")
        except OneClickError as problem:
            self.s_example.set(f"⚠ {problem}")

    def _save_scheme(self) -> None:
        current = self._selected_scheme()
        if current.builtin:
            return
        self._store_scheme(self._form_scheme(current.id))

    def _save_scheme_as_new(self) -> None:
        scheme = self._form_scheme("")
        if any(s.label.casefold() == scheme.label.casefold() for s in self.c.library.schemes):
            messagebox.showinfo(APP_NAME, "A naming scheme with this name already exists. Give the new one a different name.", parent=self.win)
            return
        scheme = scheme.with_changes(id=self.c.library.new_scheme_id(scheme.label))
        self._store_scheme(scheme)

    def _store_scheme(self, scheme: NamingScheme) -> None:
        try:
            saved = self.c.library.save_scheme(scheme)
        except OneClickError as problem:
            messagebox.showerror(APP_NAME, str(problem), parent=self.win)
            return
        self._fill_scheme_list(select_id=saved.id)

    def _delete_scheme(self) -> None:
        current = self._selected_scheme()
        if current.builtin:
            return
        if messagebox.askyesno(APP_NAME, f"Delete the naming scheme '{current.label}'?", parent=self.win):
            self.c.library.delete_scheme(current.id)
            self._fill_scheme_list(select_id="default")

    # ---------------------------------------------------------------- general

    def _build_general_tab(self) -> ttk.Frame:
        frame = ttk.Frame(self.notebook, padding=12)
        settings = self.c.settings
        self.v_open = tk.BooleanVar(value=settings.open_after_create)
        self.v_close = tk.BooleanVar(value=settings.close_after_create)
        self.v_remember = tk.BooleanVar(value=settings.remember_last_choices)
        self.v_dark = tk.BooleanVar(value=settings.dark_mode)

        def bind(var: tk.BooleanVar, attribute: str) -> None:
            var.trace_add("write", lambda *_: setattr(settings, attribute, bool(var.get())))

        bind(self.v_open, "open_after_create")
        bind(self.v_close, "close_after_create")
        bind(self.v_remember, "remember_last_choices")
        bind(self.v_dark, "dark_mode")
        ttk.Checkbutton(frame, text="Open the new folder after creating it", variable=self.v_open).pack(anchor="w")
        ttk.Checkbutton(frame, text="Close this window after creating a project", variable=self.v_close).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(
            frame,
            text="Remember the last template and naming scheme (otherwise start with the default template)",
            variable=self.v_remember,
        ).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(frame, text="Dark mode (takes effect next time the app opens)", variable=self.v_dark).pack(anchor="w", pady=(4, 0))

        menu = get_context_menu()
        box = ttk.LabelFrame(frame, text="Right-click menu", padding=10)
        box.pack(fill="x", pady=(16, 0))
        self.menu_status = ttk.Label(box, text="", wraplength=520, justify="left")
        self.menu_status.pack(anchor="w")
        row = ttk.Frame(box)
        row.pack(anchor="w", pady=(8, 0))
        self.menu_install_btn = ttk.Button(row, text="Add 'New project here'", command=lambda: self._menu_action(menu, True))
        self.menu_install_btn.pack(side="left")
        self.menu_remove_btn = ttk.Button(row, text="Remove", command=lambda: self._menu_action(menu, False))
        self.menu_remove_btn.pack(side="left", padx=(6, 0))
        self._refresh_menu_status(menu)

        undo_box = ttk.LabelFrame(frame, text="Last project", padding=10)
        undo_box.pack(fill="x", pady=(16, 0))
        record = self.c.last_record()
        ttk.Label(undo_box, text=(f"{record.folder_name}  ·  created {record.created_at}" if record else "Nothing to undo."), wraplength=520).pack(anchor="w")
        undo_btn = ttk.Button(undo_box, text="Undo (delete it if still untouched)", command=self._undo_last)
        undo_btn.pack(anchor="w", pady=(8, 0))
        undo_btn.state(["!disabled"] if record else ["disabled"])
        ttk.Label(undo_box, text="Also available anywhere with Ctrl+Z.", style="Small.TLabel").pack(anchor="w", pady=(4, 0))

        about = ttk.Frame(frame)
        about.pack(fill="x", pady=(16, 0))
        ttk.Button(about, text="Open settings & log folder", command=lambda: open_folder(user_data_dir())).pack(side="left")
        ttk.Label(about, text=f"{APP_NAME} {__version__}  ·  Created by Kal-Motion", style="Muted.TLabel").pack(side="right")
        return frame

    def _undo_last(self) -> None:
        record, problems = self.c.undo_info()
        if record is None:
            return
        if problems:
            messagebox.showinfo(APP_NAME, f"'{record.folder_name}' can't be undone safely:\n\n- " + "\n- ".join(problems) + "\n\nNothing was deleted.", parent=self.win)
            return
        if not messagebox.askyesno(APP_NAME, f"Delete this folder?\n\n{record.path}", parent=self.win):
            return
        try:
            self.c.undo()
        except OneClickError as problem:
            messagebox.showerror(APP_NAME, str(problem), parent=self.win)
            return
        messagebox.showinfo(APP_NAME, f"Removed {record.folder_name}.", parent=self.win)
        self.close()

    def _refresh_menu_status(self, menu) -> None:
        try:
            status = menu.status()
        except Exception:
            log.exception("Could not read the right-click menu status")
            self.menu_status.configure(text="Could not check the right-click menu status.")
            return
        if not status.supported:
            self.menu_status.configure(text=status.detail)
            self.menu_install_btn.state(["disabled"])
            self.menu_remove_btn.state(["disabled"])
            return
        text = "Installed. " if status.installed else "Not installed. "
        self.menu_status.configure(text=text + status.detail)
        self.menu_install_btn.state(["disabled"] if status.installed else ["!disabled"])
        self.menu_remove_btn.state(["!disabled"] if status.installed else ["disabled"])

    def _menu_action(self, menu, install: bool) -> None:
        try:
            menu.install() if install else menu.uninstall()
        except Exception as problem:
            log.exception("Right-click menu change failed")
            messagebox.showerror(APP_NAME, f"Could not change the right-click menu:\n{problem}", parent=self.win)
        self._refresh_menu_status(menu)
