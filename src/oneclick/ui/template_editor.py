"""Template editor: rename a template and add, rename, delete or reorder its folders."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Callable, Optional

from .. import APP_NAME
from ..core.errors import OneClickError
from ..core.sanitize import sanitize_name, validate_component
from ..core.settings import Library
from ..core.templates import Template
from .theme import center_window, get_theme


class TemplateEditor:
    """Edit one template. Built-in and folder templates are opened as a new editable copy."""

    def __init__(self, parent: tk.Misc, library: Library, template: Template, on_saved: Optional[Callable[[Template], None]] = None) -> None:
        self.library = library
        self.on_saved = on_saved
        self.theme = get_theme(parent)
        p = self.theme.palette

        self.is_copy = template.builtin or template.is_folder_template
        self.source = template
        self.template_id: Optional[str] = None if self.is_copy else template.id
        self.files = {} if template.is_folder_template else dict(template.files)
        self.description = template.description
        self.dirty = False

        self.win = tk.Toplevel(parent)
        self.theme.style_toplevel(self.win)
        self.win.title(f"{APP_NAME} – Edit template")
        self.win.transient(parent)
        self.win.minsize(520, 520)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda _e: self.close())

        outer = ttk.Frame(self.win, padding=16)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        ttk.Label(outer, text="Template name", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        initial_name = library.unique_template_name(f"{template.name} copy") if self.is_copy else template.name
        self.name_var = tk.StringVar(value=initial_name)
        self.name_var.trace_add("write", lambda *_: self._mark_dirty())
        name_entry = ttk.Entry(outer, textvariable=self.name_var)
        name_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 8))

        if self.is_copy:
            what = "built-in preset" if template.builtin else "folder template"
            note = f"'{template.name}' is a {what} and stays as it is. Your changes are saved as a new template."
            if template.is_folder_template:
                note += " Only its folder structure is copied, not the files inside."
            ttk.Label(outer, text=note, style="Muted.TLabel", wraplength=480, justify="left").grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 8))

        card = ttk.Frame(outer, style="Card.TFrame")
        card.grid(row=3, column=0, columnspan=2, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(card, show="tree", selectmode="browse")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", lambda _e: self.rename_folder())
        self.tree.bind("<F2>", lambda _e: self.rename_folder())
        self.tree.bind("<Delete>", lambda _e: self.delete_folder())
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_buttons())

        side = ttk.Frame(outer)
        side.grid(row=3, column=2, sticky="ns", padx=(10, 0))
        self.btn_add = ttk.Button(side, text="Add folder", command=self.add_folder)
        self.btn_add.pack(fill="x")
        self.btn_add_sub = ttk.Button(side, text="Add subfolder", command=self.add_subfolder)
        self.btn_add_sub.pack(fill="x", pady=(6, 0))
        self.btn_rename = ttk.Button(side, text="Rename", command=self.rename_folder)
        self.btn_rename.pack(fill="x", pady=(14, 0))
        self.btn_delete = ttk.Button(side, text="Delete", command=self.delete_folder)
        self.btn_delete.pack(fill="x", pady=(6, 0))
        self.btn_up = ttk.Button(side, text="Move up", command=lambda: self.move(-1))
        self.btn_up.pack(fill="x", pady=(14, 0))
        self.btn_down = ttk.Button(side, text="Move down", command=lambda: self.move(1))
        self.btn_down.pack(fill="x", pady=(6, 0))

        ttk.Label(outer, text="Double-click a folder to rename it.  Files in the template (if any) are kept as they are.",
                  style="Small.TLabel", wraplength=480, justify="left").grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(outer)
        buttons.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        buttons.columnconfigure(0, weight=1)
        ttk.Button(buttons, text="Cancel", command=self.close).grid(row=0, column=1, padx=(0, 6))
        self.btn_save = ttk.Button(buttons, text="Save as new template" if self.is_copy else "Save", style="Accent.TButton", command=self.save)
        self.btn_save.grid(row=0, column=2)

        self._populate(template)
        self._update_buttons()
        self.dirty = False
        name_entry.focus_set()
        name_entry.selection_range(0, "end")
        center_window(self.win, parent)
        self.win.grab_set()

    # ---- tree <-> folder list -----------------------------------------------------

    def _populate(self, template: Template) -> None:
        folders = [e.rel for e in template.entries() if e.is_dir] if template.is_folder_template else list(template.folders)
        files = set(self.files)
        nodes: dict[str, str] = {}
        for rel in sorted(set(folders) | {f.rsplit("/", 1)[0] for f in files if "/" in f}, key=lambda r: (r.count("/"), folders.index(r) if r in folders else 10_000)):
            parts = rel.split("/")
            parent = ""
            for i in range(1, len(parts) + 1):
                key = "/".join(parts[:i])
                if key not in nodes:
                    nodes[key] = self.tree.insert(nodes.get(parent, ""), "end", text=parts[i - 1], open=True)
                parent = key
        # files are shown greyed, not editable
        for rel in sorted(files):
            parent_key = rel.rsplit("/", 1)[0] if "/" in rel else ""
            self.tree.insert(nodes.get(parent_key, ""), "end", text=rel.rsplit("/", 1)[-1], tags=("file",), values=(rel,))
        self.tree.tag_configure("file", foreground=self.theme.palette.muted)

    def _is_file(self, item: str) -> bool:
        return "file" in self.tree.item(item, "tags")

    def _path_of(self, item: str) -> str:
        parts = []
        while item:
            parts.append(self.tree.item(item, "text"))
            item = self.tree.parent(item)
        return "/".join(reversed(parts))

    def folders(self) -> list[str]:
        out: list[str] = []

        def walk(parent: str) -> None:
            for item in self.tree.get_children(parent):
                if self._is_file(item):
                    continue
                out.append(self._path_of(item))
                walk(item)

        walk("")
        return out

    def _current_files(self) -> dict[str, str]:
        """Files follow their (possibly renamed) folders; each file node remembers its original path."""
        result: dict[str, str] = {}
        for item in self._all_items():
            if self._is_file(item):
                original = self.tree.item(item, "values")[0]
                result[self._path_of(item)] = self.files.get(original, "")
        return result

    def _all_items(self, parent: str = "") -> list[str]:
        items = []
        for item in self.tree.get_children(parent):
            items.append(item)
            items.extend(self._all_items(item))
        return items

    # ---- actions ----------------------------------------------------------------

    def _selected(self) -> Optional[str]:
        selection = self.tree.selection()
        return selection[0] if selection else None

    def _ask_name(self, title: str, initial: str = "") -> Optional[str]:
        while True:
            answer = simpledialog.askstring(title, "Folder name:", initialvalue=initial, parent=self.win)
            if answer is None:
                return None
            cleaned = sanitize_name(answer)
            try:
                validate_component(cleaned)
            except OneClickError as problem:
                messagebox.showwarning(APP_NAME, str(problem), parent=self.win)
                initial = answer
                continue
            return cleaned

    def _sibling_exists(self, parent: str, name: str, ignore: Optional[str] = None) -> bool:
        return any(c != ignore and self.tree.item(c, "text").casefold() == name.casefold() for c in self.tree.get_children(parent))

    def _insert_folder(self, parent: str) -> None:
        name = self._ask_name("New folder")
        if name is None:
            return
        if self._sibling_exists(parent, name):
            messagebox.showwarning(APP_NAME, f"There is already an item called '{name}' there.", parent=self.win)
            return
        # keep folders before files
        index = len([c for c in self.tree.get_children(parent) if not self._is_file(c)])
        item = self.tree.insert(parent, index, text=name, open=True)
        if parent:
            self.tree.item(parent, open=True)
        self.tree.selection_set(item)
        self.tree.see(item)
        self._mark_dirty()

    def add_folder(self) -> None:
        current = self._selected()
        parent = self.tree.parent(current) if current else ""
        self._insert_folder(parent)

    def add_subfolder(self) -> None:
        current = self._selected()
        if current is None or self._is_file(current):
            self.add_folder()
            return
        self._insert_folder(current)

    def rename_folder(self) -> None:
        current = self._selected()
        if current is None or self._is_file(current):
            return
        name = self._ask_name("Rename folder", self.tree.item(current, "text"))
        if name is None or name == self.tree.item(current, "text"):
            return
        if self._sibling_exists(self.tree.parent(current), name, ignore=current):
            messagebox.showwarning(APP_NAME, f"There is already an item called '{name}' there.", parent=self.win)
            return
        self.tree.item(current, text=name)
        self._mark_dirty()

    def delete_folder(self) -> None:
        current = self._selected()
        if current is None or self._is_file(current):
            return
        children = self._all_items(current)
        if children and not messagebox.askyesno(APP_NAME, f"Delete '{self.tree.item(current, 'text')}' and the {len(children)} item(s) inside it from the template?", parent=self.win):
            return
        nxt = self.tree.next(current) or self.tree.prev(current) or self.tree.parent(current)
        self.tree.delete(current)
        if nxt:
            self.tree.selection_set(nxt)
        self._mark_dirty()
        self._update_buttons()

    def move(self, delta: int) -> None:
        current = self._selected()
        if current is None or self._is_file(current):
            return
        parent = self.tree.parent(current)
        siblings = [c for c in self.tree.get_children(parent) if not self._is_file(c)]
        index = siblings.index(current)
        target = index + delta
        if 0 <= target < len(siblings):
            self.tree.move(current, parent, target)
            self._mark_dirty()
            self._update_buttons()

    def _update_buttons(self) -> None:
        current = self._selected()
        folder_selected = current is not None and not self._is_file(current)
        for button in (self.btn_rename, self.btn_delete, self.btn_up, self.btn_down):
            button.state(["!disabled"] if folder_selected else ["disabled"])
        self.btn_add_sub.state(["!disabled"] if folder_selected else ["disabled"])

    def _mark_dirty(self) -> None:
        self.dirty = True

    # ---- save / close --------------------------------------------------------------

    def save(self) -> None:
        folders = self.folders()
        if not folders and not self.files:
            messagebox.showwarning(APP_NAME, "Add at least one folder to the template.", parent=self.win)
            return
        try:
            saved = self.library.save_user_template(self.template_id, self.name_var.get(), folders, self._current_files(), self.description)
        except OneClickError as problem:
            messagebox.showerror(APP_NAME, str(problem), parent=self.win)
            return
        self.dirty = False
        self.win.grab_release()
        self.win.destroy()
        if self.on_saved:
            self.on_saved(saved)

    def close(self) -> None:
        if self.dirty and not messagebox.askyesno(APP_NAME, "Discard your changes to this template?", parent=self.win):
            return
        self.win.grab_release()
        self.win.destroy()
