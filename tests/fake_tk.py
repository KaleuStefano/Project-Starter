"""A stand-in for tkinter so the window code can be exercised on machines without Tk.

This only checks that OUR code runs: that names exist, calls are wired and logic flows. It does
not prove anything about how the real widgets look or behave.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock


class Var:
    default = ""

    def __init__(self, master=None, value=None, **_):
        self._value = self.default if value is None else value
        self._callbacks = []

    def get(self):
        return self._value

    def set(self, value):
        self._value = value
        for callback in list(self._callbacks):
            callback("name", "", "write")

    def trace_add(self, _mode, callback):
        self._callbacks.append(callback)


class StringVar(Var):
    default = ""


class BooleanVar(Var):
    default = False


class Widget:
    def __init__(self, *args, **kwargs):
        self._items = {}
        self.args, self.kwargs = args, kwargs

    def __getattr__(self, name):  # any other method is an auto-recorded mock
        if name.startswith("__"):
            raise AttributeError(name)
        mock = MagicMock(name=name)
        setattr(self, name, mock)
        return mock

    def __setitem__(self, key, value):
        self._items[key] = value

    def __getitem__(self, key):
        return self._items[key]


class Combobox(Widget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._index = -1

    def current(self, index=None):
        if index is None:
            return self._index
        self._index = index


class Listbox(Widget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows, self.selected = [], ()

    def insert(self, _where, text):
        self.rows.append(text)

    def delete(self, *_):
        self.rows.clear()

    def curselection(self):
        return self.selected

    def selection_set(self, index):
        self.selected = (index,)

    def selection_clear(self, *_):
        self.selected = ()


class Treeview(Widget):
    """Enough of ttk.Treeview for the template editor: a real parent/child item store."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._nodes: dict[str, dict] = {"": {"children": [], "parent": None}}
        self._selection: tuple = ()
        self._n = 0

    def insert(self, parent, index, text="", open=False, tags=(), values=()):
        self._n += 1
        iid = f"I{self._n}"
        self._nodes[iid] = {"text": text, "open": open, "tags": tuple(tags), "values": tuple(values), "children": [], "parent": parent}
        children = self._nodes[parent]["children"]
        children.insert(len(children) if index == "end" else index, iid)
        return iid

    def item(self, iid, option=None, **kwargs):
        node = self._nodes[iid]
        if kwargs:
            node.update(kwargs)
            return None
        return node[option] if option else node

    def get_children(self, parent=""):
        return tuple(self._nodes[parent]["children"])

    def parent(self, iid):
        return self._nodes[iid]["parent"]

    def selection(self):
        return self._selection

    def selection_set(self, iid):
        self._selection = (iid,)

    def delete(self, iid):
        for child in list(self._nodes[iid]["children"]):
            self.delete(child)
        self._nodes[self._nodes[iid]["parent"]]["children"].remove(iid)
        del self._nodes[iid]
        if iid in self._selection:
            self._selection = ()

    def move(self, iid, parent, index):
        self._nodes[self._nodes[iid]["parent"]]["children"].remove(iid)
        self._nodes[parent]["children"].insert(index, iid)
        self._nodes[iid]["parent"] = parent

    def next(self, iid):
        siblings = self._nodes[self._nodes[iid]["parent"]]["children"]
        i = siblings.index(iid)
        return siblings[i + 1] if i + 1 < len(siblings) else ""

    def prev(self, iid):
        siblings = self._nodes[self._nodes[iid]["parent"]]["children"]
        i = siblings.index(iid)
        return siblings[i - 1] if i > 0 else ""


class PhotoImage(Widget):
    def subsample(self, *_):
        return self


class Text(Widget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.content = ""

    def delete(self, *_):
        self.content = ""

    def insert(self, _where, text):
        self.content = text


def install(monkeypatch) -> types.SimpleNamespace:
    """Register fake ``tkinter`` modules and return handles to the interesting parts."""
    tk = types.ModuleType("tkinter")
    ttk = types.ModuleType("tkinter.ttk")
    filedialog = types.ModuleType("tkinter.filedialog")
    messagebox = types.ModuleType("tkinter.messagebox")
    simpledialog = types.ModuleType("tkinter.simpledialog")
    font = types.ModuleType("tkinter.font")

    tk.StringVar, tk.BooleanVar = StringVar, BooleanVar
    tk.Tk = tk.Toplevel = Widget
    tk.Widget = object
    tk.Listbox, tk.Text, tk.PhotoImage = Listbox, Text, PhotoImage
    tk.Misc = Widget
    tk.TclError = type("TclError", (Exception,), {})
    for name in ("Frame", "Label", "Entry", "Button", "Separator", "Scrollbar", "Notebook", "Spinbox", "Checkbutton", "LabelFrame"):
        setattr(ttk, name, type(name, (Widget,), {}))
    ttk.Combobox, ttk.Treeview, ttk.Style = Combobox, Treeview, Widget
    filedialog.askdirectory = MagicMock(return_value="")
    for name in ("showerror", "showinfo", "showwarning", "askyesno"):
        setattr(messagebox, name, MagicMock(return_value=True))
    font.nametofont = MagicMock()
    simpledialog.askstring = MagicMock(return_value=None)

    tk.ttk, tk.filedialog, tk.messagebox, tk.font, tk.simpledialog = ttk, filedialog, messagebox, font, simpledialog
    for module_name, module in (
        ("tkinter", tk),
        ("tkinter.ttk", ttk),
        ("tkinter.filedialog", filedialog),
        ("tkinter.messagebox", messagebox),
        ("tkinter.simpledialog", simpledialog),
        ("tkinter.font", font),
    ):
        monkeypatch.setitem(sys.modules, module_name, module)
    purge_ui_modules()
    return types.SimpleNamespace(tk=tk, ttk=ttk, filedialog=filedialog, messagebox=messagebox, simpledialog=simpledialog)


def purge_ui_modules() -> None:
    """Forget the window modules so the next import binds to whichever tkinter is installed now."""
    import oneclick.ui as ui_package

    for name in ("main_window", "settings_dialog", "template_editor", "theme"):
        sys.modules.pop(f"oneclick.ui.{name}", None)
        if hasattr(ui_package, name):
            delattr(ui_package, name)
