"""Regenerate src/oneclick/ui/assets.py (rounded button images) and branding.py (logo).

Run from the project root:  python packaging/make_assets.py [path/to/logo.png ...]
Needs Pillow. PNGs passed on the command line are embedded as-is, named by size:
KAL_MOTION_LOGO_<size> for the Kal-Motion mark and APP_ICON_<size> for the app icon
(use --app before an app icon file).
"""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src" / "oneclick" / "ui"

CARDS = {  # panels behind lists / text areas, and notebook tabs
    "dark": {"card": ("#24272e", "#3a3f4a"), "tab": ("#1b1d22", "#1b1d22"), "tab_selected": ("#24272e", "#3a3f4a")},
    "light": {"card": ("#ffffff", "#cfd4de"), "tab": ("#f3f4f7", "#f3f4f7"), "tab_selected": ("#ffffff", "#cfd4de")},
}

VARIANTS = {
    "dark": {
        "btn": ("#2d313a", "#3a3f4a"), "btn_hover": ("#363b46", "#4a5060"), "btn_disabled": ("#24272e", "#2d313a"),
        "accent": ("#00ADEF", "#00ADEF"), "accent_hover": ("#22BDF7", "#22BDF7"), "accent_disabled": ("#2d313a", "#3a3f4a"),
    },
    "light": {
        "btn": ("#e9ecf2", "#cfd4de"), "btn_hover": ("#dfe3ea", "#b8bfcc"), "btn_disabled": ("#f3f4f7", "#e3e6ec"),
        "accent": ("#00ADEF", "#00ADEF"), "accent_hover": ("#0098d4", "#0098d4"), "accent_disabled": ("#e9ecf2", "#cfd4de"),
    },
}


def rounded(fill: str, border: str, size: int = 32, radius: int = 8) -> str:
    scale = 4
    im = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, size * scale - 1, size * scale - 1), radius * scale, fill=fill, outline=border, width=scale)
    im = im.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def write_buttons() -> None:
    lines = ['"""Rounded button backgrounds (9-slice PNGs) generated with Pillow; see packaging/make_assets.py."""\n', "BUTTON_IMAGES = {"]
    for mode, items in VARIANTS.items():
        lines.append(f'    "{mode}": {{')
        for key, (fill, border) in items.items():
            lines.append(f'        "{key}": "{rounded(fill, border)}",')
        for key, (fill, border) in CARDS[mode].items():
            lines.append(f'        "{key}": "{rounded(fill, border, size=40, radius=10)}",')
        lines.append("    },")
    lines.append("}\n")
    (UI / "assets.py").write_text("\n".join(lines), encoding="utf-8")


def write_logo(args: list[str]) -> None:
    lines = ['"""Logos embedded as base64 PNG so the frozen app needs no extra data files."""\n']
    prefix = "KAL_MOTION_LOGO"
    for arg in args:
        if arg == "--app":
            prefix = "APP_ICON"
            continue
        if arg == "--kal":
            prefix = "KAL_MOTION_LOGO"
            continue
        path = Path(arg)
        with Image.open(path) as im:
            size = im.size[0]
        data = base64.b64encode(path.read_bytes()).decode()
        chunks = [data[i : i + 96] for i in range(0, len(data), 96)]
        lines.append(f"{prefix}_{size} = (\n" + "\n".join(f'    "{c}"' for c in chunks) + "\n)\n")
    (UI / "branding.py").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    write_buttons()
    if len(sys.argv) > 1:
        write_logo(sys.argv[1:])
    print("done")
