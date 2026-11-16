"""Light and dark colour schemes for the ttk widgets (and the few classic Tk widgets we use)."""

from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import dataclass
from typing import Optional
from tkinter import ttk

from .assets import BUTTON_IMAGES


@dataclass(frozen=True)
class Palette:
    bg: str  # window background
    surface: str  # inputs, lists, text areas
    surface_alt: str  # hover / selected rows
    border: str
    text: str
    muted: str
    accent: str  # primary button, selection
    accent_text: str
    accent_hover: str
    success: str  # same as accent: status text uses the brand blue
    warning: str
    error: str


DARK = Palette(
    bg="#1b1d22",
    surface="#24272e",
    surface_alt="#2d313a",
    border="#3a3f4a",
    text="#e8eaf0",
    muted="#8b93a3",
    accent="#00ADEF",
    accent_text="#ffffff",
    accent_hover="#22BDF7",
    success="#00ADEF",
    warning="#e0a742",
    error="#ef6b6b",
)

LIGHT = Palette(
    bg="#f3f4f7",
    surface="#ffffff",
    surface_alt="#e9ecf2",
    border="#cfd4de",
    text="#1d2330",
    muted="#6b7280",
    accent="#00ADEF",
    accent_text="#ffffff",
    accent_hover="#0098d4",
    success="#00ADEF",
    warning="#b45309",
    error="#b91c1c",
)

FONT_FAMILY = "Segoe UI" if sys.platform == "win32" else ("SF Pro Text" if sys.platform == "darwin" else "TkDefaultFont")


class Theme:
    """Applies a palette to a Tk root and remembers it so new windows can pick it up."""

    def __init__(self, root: tk.Tk, dark: bool = True) -> None:
        self.root = root
        self.palette = DARK if dark else LIGHT
        self.dark = dark
        self.style = ttk.Style(root)
        self._apply()

    # ---- styles -----------------------------------------------------------------

    def _apply(self) -> None:
        p = self.palette
        style = self.style
        try:
            style.theme_use("clam")  # the only built-in theme whose colours can be fully overridden
        except tk.TclError:
            pass
        self.root.configure(background=p.bg)
        self.root.option_add("*TCombobox*Listbox.background", p.surface)
        self.root.option_add("*TCombobox*Listbox.foreground", p.text)
        self.root.option_add("*TCombobox*Listbox.selectBackground", p.accent)
        self.root.option_add("*TCombobox*Listbox.selectForeground", p.accent_text)
        self.root.option_add("*TCombobox*Listbox.borderWidth", 0)

        base_font = (FONT_FAMILY, 11)
        style.configure(".", background=p.bg, foreground=p.text, fieldbackground=p.surface, bordercolor=p.border,
                        lightcolor=p.bg, darkcolor=p.bg, troughcolor=p.surface, font=base_font, focuscolor=p.accent)
        style.configure("TFrame", background=p.bg)
        style.configure("TLabel", background=p.bg, foreground=p.text)
        style.configure("Muted.TLabel", foreground=p.muted)
        style.configure("Small.TLabel", foreground=p.muted, font=(FONT_FAMILY, 9))
        style.configure("Heading.TLabel", font=(FONT_FAMILY, 15, "bold"))
        style.configure("Field.TLabel", foreground=p.muted, font=(FONT_FAMILY, 9))
        style.configure("Primary.TLabel", foreground=p.accent, font=(FONT_FAMILY, 10, "bold"))
        style.configure("Warning.TLabel", foreground=p.warning)
        style.configure("Error.TLabel", foreground=p.error)
        style.configure("Success.TLabel", foreground=p.success)
        style.configure("TLabelframe", background=p.bg, bordercolor=p.border)
        style.configure("TLabelframe.Label", background=p.bg, foreground=p.muted)
        style.configure("TSeparator", background=p.border)

        style.configure("TEntry", fieldbackground=p.surface, foreground=p.text, insertcolor=p.text, bordercolor=p.border, padding=5)
        style.map("TEntry", bordercolor=[("focus", p.accent)], lightcolor=[("focus", p.accent)], darkcolor=[("focus", p.accent)])
        style.configure("Primary.TEntry", padding=8, bordercolor=p.accent, lightcolor=p.accent, darkcolor=p.accent)
        style.configure("TSpinbox", fieldbackground=p.surface, foreground=p.text, insertcolor=p.text, arrowcolor=p.text, bordercolor=p.border, padding=4)
        style.configure("TCombobox", fieldbackground=p.surface, foreground=p.text, arrowcolor=p.text, bordercolor=p.border, padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", p.surface)], foreground=[("readonly", p.text)],
                  selectbackground=[("readonly", p.surface)], selectforeground=[("readonly", p.text)],
                  bordercolor=[("focus", p.accent)])

        self._rounded_buttons()
        style.configure("Link.TButton", background=p.bg, foreground=p.text, bordercolor=p.bg, padding=(4, 2), relief="flat")
        style.map("Link.TButton", background=[("active", p.bg)], foreground=[("active", p.accent)])

        style.configure("TCheckbutton", background=p.bg, foreground=p.text)
        style.map("TCheckbutton", background=[("active", p.bg)], indicatorcolor=[("selected", p.accent)])
        style.configure("TNotebook", background=p.bg, bordercolor=p.bg, lightcolor=p.bg, darkcolor=p.bg)
        style.configure("TScrollbar", background=p.surface_alt, troughcolor=p.bg, bordercolor=p.bg, arrowcolor=p.muted)
        style.map("TScrollbar", background=[("active", p.border)])
        style.configure("Treeview", background=p.surface, fieldbackground=p.surface, foreground=p.text, bordercolor=p.surface, lightcolor=p.surface, darkcolor=p.surface, rowheight=26)
        style.configure("Treeview.Heading", background=p.surface_alt, foreground=p.text, bordercolor=p.border)
        style.map("Treeview", background=[("selected", p.accent)], foreground=[("selected", p.accent_text)])

    def _rounded_buttons(self) -> None:
        """Rounded corners come from 9-slice PNGs; ttk's built-in themes can't draw them."""
        p = self.palette
        style = self.style
        images = BUTTON_IMAGES["dark" if self.dark else "light"]
        self._images = {key: tk.PhotoImage(data=value) for key, value in images.items()}  # keep references alive
        for name, prefix in (("Rounded.button", "btn"), ("RoundedAccent.button", "accent")):
            try:
                style.element_create(
                    name, "image", self._images[prefix],
                    ("disabled", self._images[prefix + "_disabled"]),
                    ("pressed", self._images[prefix + "_hover"]),
                    ("active", self._images[prefix + "_hover"]),
                    border=10, sticky="nsew", padding=(10, 3),
                )
            except tk.TclError:
                pass  # already created (theme re-applied in the same process)
        style.layout("TButton", [("Rounded.button", {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})])
        style.layout("Accent.TButton", [("RoundedAccent.button", {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})])
        style.configure("TButton", foreground=p.text, padding=(6, 1), anchor="center")
        style.map("TButton", foreground=[("disabled", p.muted)], background=[])
        style.configure("Accent.TButton", foreground=p.accent_text, font=(FONT_FAMILY, 11, "bold"), padding=(8, 1), anchor="center")
        style.map("Accent.TButton", foreground=[("disabled", p.muted)])

        # Rounded panel ("card") used behind lists and text areas, and rounded notebook tabs.
        for name, key in (("Card.border", "card"), ("RoundedTab.tab", "tab")):
            try:
                if key == "tab":
                    style.element_create(name, "image", self._images["tab"], ("selected", self._images["tab_selected"]),
                                         border=10, sticky="nsew", padding=(12, 5))
                else:
                    style.element_create(name, "image", self._images[key], border=12, sticky="nsew")
            except tk.TclError:
                pass
        style.layout("Card.TFrame", [("Card.border", {"sticky": "nsew", "children": [("Frame.padding", {"sticky": "nsew"})]})])
        style.configure("Card.TFrame", padding=6)
        style.layout("TNotebook.Tab", [("RoundedTab.tab", {"sticky": "nsew", "children": [
            ("Notebook.padding", {"side": "top", "sticky": "nsew", "children": [("Notebook.label", {"side": "top", "sticky": ""})]})]})])
        style.configure("TNotebook", borderwidth=0, tabmargins=(0, 0, 4, 0))
        style.configure("TNotebook.Tab", padding=(6, 1), foreground=p.muted)
        style.map("TNotebook.Tab", foreground=[("selected", p.text)])

    # ---- classic widgets --------------------------------------------------------

    def style_text(self, widget: tk.Text) -> None:
        p = self.palette
        widget.configure(background=p.surface, foreground=p.text, insertbackground=p.text, selectbackground=p.accent,
                         selectforeground=p.accent_text, relief="flat", highlightthickness=0, borderwidth=0, padx=6, pady=4)

    def style_listbox(self, widget: tk.Listbox) -> None:
        p = self.palette
        widget.configure(background=p.surface, foreground=p.text, selectbackground=p.accent, selectforeground=p.accent_text,
                         relief="flat", highlightthickness=0, borderwidth=0, font=(FONT_FAMILY, 11))

    def style_toplevel(self, window: tk.Toplevel) -> None:
        window.configure(background=self.palette.bg)


def get_theme(widget: tk.Misc) -> Theme:
    """The theme attached to the widget's root window (see :func:`attach`)."""
    root = widget.winfo_toplevel()
    while getattr(root, "master", None) is not None and not hasattr(root, "_oneclick_theme"):
        root = root.master.winfo_toplevel()
    theme = getattr(root, "_oneclick_theme", None)
    if theme is None:
        theme = Theme(root, dark=True)
        root._oneclick_theme = theme  # type: ignore[attr-defined]
    return theme


def attach(root: tk.Tk, dark: bool) -> Theme:
    theme = Theme(root, dark=dark)
    root._oneclick_theme = theme  # type: ignore[attr-defined]
    return theme


def center_window(window: tk.Misc, parent: Optional[tk.Misc] = None) -> None:
    """Place ``window`` in the middle of ``parent`` (or of the screen), after its size is known."""
    window.update_idletasks()
    width = max(window.winfo_width(), window.winfo_reqwidth())
    height = max(window.winfo_height(), window.winfo_reqheight())
    if parent is not None and parent.winfo_viewable():
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x, y = px + (pw - width) // 2, py + (ph - height) // 2
    else:
        x = (window.winfo_screenwidth() - width) // 2
        y = (window.winfo_screenheight() - height) // 2
    x = max(0, min(x, window.winfo_screenwidth() - width))
    y = max(0, min(y, window.winfo_screenheight() - height))
    window.geometry(f"+{x}+{y}")
