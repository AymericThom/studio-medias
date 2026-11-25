"""Outils de dessin : police Poppins, emojis 3D (style Apple, Microsoft Fluent, licence MIT), texte **gras**."""
from __future__ import annotations

import hashlib
import io
import re
import urllib.parse
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from .config import ASSETS, DATA

FD = ASSETS / "fonts"
FONTS = {
    "regular": [FD / "Poppins-Regular.ttf", "C:/Windows/Fonts/segoeui.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "medium": [FD / "Poppins-Medium.ttf", "C:/Windows/Fonts/segoeui.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "semibold": [FD / "Poppins-SemiBold.ttf", "C:/Windows/Fonts/seguisb.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "bold": [FD / "Poppins-Bold.ttf", "C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "black": [FD / "Poppins-ExtraBold.ttf", "C:/Windows/Fonts/seguibl.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "heavy": [FD / "Poppins-Black.ttf", "C:/Windows/Fonts/seguibl.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "emoji": ["C:/Windows/Fonts/seguiemj.ttf"],
}
FLAG_RE = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")
EMOJI_RE = re.compile(r"([\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2300-\u23FF\u2190-\u21FF\u2934\u2935\u3297\u3299])")
EMOJI_CACHE = DATA / "cache" / "emoji"


@lru_cache(maxsize=None)
def font_path(kind: str) -> str | None:
    for p in FONTS[kind]:
        if Path(p).exists():
            return str(p)
    return None


@lru_cache(maxsize=512)
def font(kind: str, size: int):
    p = font_path(kind)
    return ImageFont.truetype(p, size) if p else ImageFont.load_default(size=size)


def rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(c1, c2, t: float):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def cover(img: Image.Image, w: int, h: int, focus_y: float = 0.3, zoom: float = 1.0) -> Image.Image:
    scale = max(w / img.width, h / img.height) * zoom
    nw, nh = max(w, round(img.width * scale)), max(h, round(img.height * scale))
    im = img.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - w) // 2, int((nh - h) * focus_y)
    return im.crop((x, y, x + w, y + h))


def vgradient(w: int, h: int, color, a0: int, a1: int, power: float = 1.0) -> Image.Image:
    alpha = Image.linear_gradient("L").resize((w, h)).point(lambda v: int(a0 + (a1 - a0) * (v / 255) ** power))
    layer = Image.new("RGBA", (w, h), (*color, 0))
    layer.putalpha(alpha)
    return layer


def text_w(text: str, f) -> int:
    return int(f.getlength(text))


# ------------------------------------------------------------------ emojis 3D
@lru_cache(maxsize=256)
def emoji_image(ch: str) -> Image.Image | None:
    """Emoji 3D Microsoft Fluent (MIT) téléchargé une fois puis gardé en cache. None si indisponible."""
    ch = ch.replace("\uFE0F", "")
    EMOJI_CACHE.mkdir(parents=True, exist_ok=True)
    path = EMOJI_CACHE / (hashlib.md5(ch.encode()).hexdigest()[:12] + ".png")
    if path.exists():
        if path.stat().st_size <= 100:
            return None
        im = Image.open(path).convert("RGBA")
        box = im.getbbox()                      # retire la marge transparente des images Fluent
        return im.crop(box) if box else im
    try:
        import emoji as emoji_lib

        name = emoji_lib.demojize(ch).strip(":")
    except Exception:
        name = ""
    img = None
    if name and ch not in name:
        folder = name.replace("_", " ")
        folder = folder[0].upper() + folder[1:].lower()
        base = "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets/" + urllib.parse.quote(folder)
        for url in (f"{base}/3D/{name.lower()}_3d.png", f"{base}/Default/3D/{name.lower()}_3d_default.png"):
            try:
                r = requests.get(url, timeout=15)
                if r.status_code == 200:
                    img = Image.open(io.BytesIO(r.content)).convert("RGBA")
                    break
            except Exception:
                pass
    if img is None:
        path.write_bytes(b"")          # mémorise l'absence
        return None
    img.save(path)
    box = img.getbbox()
    return img.crop(box) if box else img


def _emoji_fallback(ch: str, size: int) -> Image.Image | None:
    if not font_path("emoji"):
        return None
    layer = Image.new("RGBA", (int(size * 1.4), int(size * 1.4)), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((layer.width // 2, layer.height // 2), ch, font=font("emoji", size),
                               embedded_color=True, anchor="mm")
    box = layer.getbbox()
    return layer.crop(box) if box else None


def emoji_sized(ch: str, size: int) -> Image.Image | None:
    img = emoji_image(ch) or _emoji_fallback(ch, size)
    if img is None:
        return None
    return img.resize((size, max(1, int(img.height * size / img.width))), Image.LANCZOS)


# ------------------------------------------------------------------ texte enrichi
@dataclass
class Word:
    runs: list            # [(texte, "base"|"emoji")]
    bold: bool
    width: int = 0
    glue: bool = False    # collé au mot précédent (ponctuation après un mot en gras, après une apostrophe)


@dataclass
class Block:
    lines: list = field(default_factory=list)
    size: int = 40
    base: str = "regular"
    bold: str = "bold"
    lh: int = 50

    @property
    def h(self) -> int:
        return len(self.lines) * self.lh

    @property
    def w(self) -> int:
        return max((lw for _, lw in self.lines), default=0)


def clean(text: str) -> str:
    text = FLAG_RE.sub("", text or "").replace("\uFE0F", "").replace("\u200D", "")
    return re.sub(r"[ \t]+", " ", text).strip()


def _words(text: str) -> list[Word]:
    out = []
    for i, seg in enumerate(re.split(r"\*\*", clean(text))):
        bold = i % 2 == 1
        for j, raw in enumerate(seg.split()):
            runs = [(p, "emoji" if EMOJI_RE.fullmatch(p) else "base") for p in EMOJI_RE.split(raw) if p]
            if runs:
                glue = j == 0 and bool(out) and not seg[:1].isspace() and (
                    raw[0] in ".,;:!?)»…" or out[-1].runs[-1][0][-1:] in "'’(«")
                out.append(Word(runs, bold, glue=glue))
    return out


def emoji_w(size: int) -> int:
    return int(size * 1.1)


def layout(text: str, max_w: int, size: int, base: str = "regular", bold: str = "bold", spacing: float = 1.25) -> Block:
    fb, fbold = font(base, size), font(bold, size)
    words = _words(text)
    for w in words:
        w.width = sum(emoji_w(size) if k == "emoji" else text_w(t, fbold if w.bold else fb) for t, k in w.runs)
    space = text_w(" ", fb)
    lines, cur, cur_w = [], [], 0
    for w in words:
        add = w.width + (space if cur and not w.glue else 0)
        if cur and cur_w + add > max_w:
            lines.append((cur, cur_w))
            cur, cur_w, add = [], 0, w.width
        cur.append(w)
        cur_w += add
    if cur:
        lines.append((cur, cur_w))
    return Block(lines, size, base, bold, int(size * spacing))


def fit(text: str, max_w: int, max_h: int, start: int, minimum: int, base: str = "regular", bold: str = "bold",
        spacing: float = 1.25) -> Block:
    size = start
    while True:
        b = layout(text, max_w, size, base, bold, spacing)
        if (b.h <= max_h and b.w <= max_w) or size <= minimum:
            return b
        size -= 2


def draw_block(img: Image.Image, x: int, y: int, b: Block, color, bold_color=None, align: str = "left",
               box_w: int = 0, stroke: int = 0, stroke_fill=(255, 255, 255)) -> int:
    d = ImageDraw.Draw(img)
    fb, fbold = font(b.base, b.size), font(b.bold, b.size)
    space = text_w(" ", fb)
    asc, desc = fb.getmetrics()
    for li, (words, lw) in enumerate(b.lines):
        cx = x + (box_w - lw) // 2 if align == "center" else x
        cy = y + li * b.lh
        for w in words:
            if w.glue:
                cx -= space
            for t, kind in w.runs:
                if kind == "emoji":
                    e = emoji_sized(t, emoji_w(b.size))
                    if e is not None:
                        ey = cy + (asc + desc - e.height) // 2 - int(b.size * 0.08)
                        img.alpha_composite(e, (int(cx), int(ey)))
                    cx += emoji_w(b.size)
                else:
                    f = fbold if w.bold else fb
                    d.text((cx, cy), t, font=f, fill=(bold_color or color) if w.bold else color,
                           stroke_width=stroke, stroke_fill=stroke_fill)
                    cx += text_w(t, f)
            cx += space
    return y + b.h


def rounded_shadow(img: Image.Image, box, radius: int, blur: int = 14, alpha: int = 50, dy: int = 6) -> None:
    from PIL import ImageFilter

    x0, y0, x1, y1 = box
    pad = blur * 3
    sh = Image.new("RGBA", (x1 - x0 + pad * 2, y1 - y0 + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad, pad + x1 - x0, pad + y1 - y0), radius=radius, fill=(0, 0, 0, alpha))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)), (x0 - pad, y0 - pad + dy))


def arrow(img: Image.Image, cx: int, cy: int, length: int, color, width: int = 7) -> None:
    """Flèche → dessinée (ne dépend d'aucun glyphe de police)."""
    d = ImageDraw.Draw(img)
    x0, x1 = cx - length // 2, cx + length // 2
    head = int(length * 0.42)
    d.line((x0, cy, x1 - head + 4, cy), fill=color, width=width)
    d.polygon([(x1, cy), (x1 - head, cy - int(head * 0.75)), (x1 - head, cy + int(head * 0.75))], fill=color)
