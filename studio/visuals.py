"""Visuels des posts (style carrousel d'actu type HugoDécrypte, tweet photo type AlertesInfos).

Carrousel (Instagram / TikTok, 3 images) :
  1. couverture : photo plein cadre, logo, fort dégradé noir, bandeau (🚨 DERNIÈRE MINUTE…), phrase-chapeau
  2. l'essentiel : fond papier quadrillé, titre, 3 à 6 bulles blanches avec mots clés en gras
  3. abonnement : la photo recadrée + « Abonne-toi… 🔔 »
Image X (16:9) : la photo seule (ou 2 photos côte à côte), petit logo et crédit, sans texte.
"""
from __future__ import annotations

import random
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .draw import (arrow, cover, draw_block, emoji_sized, fit, font, layout, mix, rgb, rounded_shadow, text_w,
                   vgradient)

WHITE = (255, 255, 255)
INK = (17, 17, 24)
NAVY = (22, 21, 58)


# ------------------------------------------------------------------ identité
def logo(media: dict, height: int = 58) -> Image.Image:
    """Logo épuré : nom en minuscules, Poppins ExtraBold blanc, pastille arrondie couleur du média."""
    name = media["name"].lower()
    size = int(height * 0.56)
    f = font("black", size)
    pad_x = int(height * 0.36)
    w = text_w(name, f) + pad_x * 2
    img = Image.new("RGBA", (w, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, height - 1), radius=int(height * 0.28), fill=rgb(media["color"]))
    d.text((w // 2, height // 2 + int(height * 0.03)), name, font=f, fill=WHITE, anchor="mm")
    return img


def avatar(media: dict, size: int = 800) -> Image.Image:
    """Photo de profil : fond couleur du média, nom en blanc."""
    c = rgb(media["color"])
    img = Image.new("RGBA", (size, size), (*c, 255))
    img.alpha_composite(vgradient(size, size, mix(c, (0, 0, 0), 0.45), 0, 150))
    name = media["name"].lower()
    s = 200
    while text_w(name, font("black", s)) > size * 0.8 and s > 40:
        s -= 4
    ImageDraw.Draw(img).text((size // 2, size // 2 + s // 20), name, font=font("black", s), fill=WHITE, anchor="mm")
    return img.convert("RGB")


def _arrow_button(img: Image.Image, dark: bool) -> None:
    W, H = img.size
    box = (W - 128, H - 102, W - 46, H - 40)
    ImageDraw.Draw(img).rounded_rectangle(box, radius=18, fill=NAVY if dark else WHITE)
    arrow(img, (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, 40, WHITE if dark else INK, width=6)


def _emoji_art(img: Image.Image, emoji: str, cx: int, cy: int, size: int) -> None:
    e = emoji_sized(emoji[:2], size) if emoji else None
    if e is None:
        return
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    glow.alpha_composite(e, (cx - e.width // 2, cy - e.height // 2))
    glow = glow.filter(ImageFilter.GaussianBlur(size // 7))
    glow.putalpha(glow.getchannel("A").point(lambda a: int(a * 0.5)))
    img.alpha_composite(glow)
    img.alpha_composite(e, (cx - e.width // 2, cy - e.height // 2))


def _photo_bg(photo, size, media: dict, focus: float = 0.3, zoom: float = 1.0, emoji: str = "",
              emoji_pos=(0.5, 0.3)) -> Image.Image:
    W, H = size
    if photo is None:   # ultime recours : grand emoji du thème sur fond couleur
        c = rgb(media["color"])
        img = Image.new("RGBA", size, (*mix(c, (0, 0, 0), 0.25), 255))
        img.alpha_composite(vgradient(W, H, mix(c, (0, 0, 0), 0.8), 0, 255))
        _emoji_art(img, emoji, int(W * emoji_pos[0]), int(H * emoji_pos[1]), int(min(W, H) * 0.36))
        return img
    if photo.width / photo.height > 2.0:   # panorama : fond flou + photo entière
        bg = cover(photo, W // 6, H // 6).filter(ImageFilter.GaussianBlur(4)).resize(size)
        fg = photo.resize((W, int(photo.height * W / photo.width)), Image.LANCZOS)
        bg.paste(fg, (0, int((H - fg.height) * 0.3)))
        return bg.convert("RGBA")
    return cover(photo, W, H, focus_y=focus, zoom=zoom).convert("RGBA")


# ------------------------------------------------------------------ carrousel
def slide_cover(media: dict, post: dict, photo, credit: str, size=(1080, 1350)) -> Image.Image:
    W, H = size
    img = _photo_bg(photo, size, media, focus=0.25, emoji=post.get("label_emoji", ""), emoji_pos=(0.5, 0.28))
    img.alpha_composite(vgradient(W, int(H * 0.2), (0, 0, 0), 110, 0), (0, 0))
    g0 = int(H * 0.20)                                  # dégradé noir derrière le texte, comme les comptes d'actu
    img.alpha_composite(vgradient(W, H - g0, (0, 0, 0), 0, 252, power=0.62), (0, g0))
    img.alpha_composite(logo(media, 60), (44, 40))

    text = fit(post["cover_text"], W - 116, int(H * 0.40), 50, 34, base="semibold", bold="black", spacing=1.3)
    y = H - 140 - text.h
    label = f"{post.get('label_emoji', '')} {post.get('label', 'INFO').upper()}".strip()
    lb = layout(label, 900, 38, base="bold", bold="bold", spacing=1.0)
    bw, bh = lb.w + 48, 72
    by = y - bh - 34
    zone = max(0, by - 140)                             # voile sombre supplémentaire sous le bandeau et le texte
    img.alpha_composite(vgradient(W, H - zone, (0, 0, 0), 0, 150, power=0.5), (0, zone))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((58, by, 58 + bw, by + bh), radius=16, fill=WHITE)
    draw_block(img, 58 + 24, by + 12, lb, INK)
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))     # ombre douce du texte pour la lisibilité sur photo claire
    draw_block(shadow, 60, y + 3, text, (0, 0, 0))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(4)))
    draw_block(img, 58, y, text, WHITE)
    if credit:
        d.text((58, H - 58), credit, font=font("regular", 18), fill=(190, 190, 190))
    _arrow_button(img, dark=False)
    return img.convert("RGB")


def _paper_bg(size, media: dict) -> Image.Image:
    W, H = size
    base = mix(rgb(media["color"]), (238, 239, 243), 0.94)
    img = Image.new("RGBA", size, (*base, 255))
    noise = Image.effect_noise((W // 2, H // 2), 22).resize(size).convert("RGBA")
    noise.putalpha(18)
    img.alpha_composite(noise)
    d = ImageDraw.Draw(img)
    line = (*mix(base, (140, 145, 160), 0.22), 255)
    for x in range(0, W, 48):
        d.line((x, 0, x, H), fill=line, width=2)
    for y in range(0, H, 48):
        d.line((0, y, W, y), fill=line, width=2)
    img.alpha_composite(vgradient(W, H, WHITE, 70, 0))
    return img


def slide_points(media: dict, post: dict, size=(1080, 1350)) -> Image.Image:
    W, H = size
    img = _paper_bg(size, media)
    img.alpha_composite(logo(media, 60), (44, 40))
    title = fit(post["points_title"], W - 150, 330, 52, 34, base="black", bold="black", spacing=1.2)
    ty = 180
    draw_block(img, 75, ty, title, NAVY, align="center", box_w=W - 150)
    top, bottom = ty + title.h + 56, H - 140
    points = [p for p in post.get("points", []) if p][:6]
    pad_x, pad_y, gap_min = 38, 24, 22
    blocks = []
    for size_pt in range(36, 23, -2):
        blocks = [layout(p, W - 270, size_pt, base="medium", bold="bold", spacing=1.32) for p in points]
        if sum(b.h + 2 * pad_y for b in blocks) + gap_min * (len(blocks) - 1) <= bottom - top:
            break
    free = bottom - top - sum(b.h + 2 * pad_y for b in blocks)
    gap = min(38, free // max(1, len(blocks) - 1)) if len(blocks) > 1 else 0
    total = sum(b.h + 2 * pad_y for b in blocks) + gap * (len(blocks) - 1)
    y = top + max(0, (bottom - top - total) // 2)
    for b in blocks:
        bw = b.w + 2 * pad_x
        x0 = (W - bw) // 2
        box = (x0, y, x0 + bw, y + b.h + 2 * pad_y)
        rounded_shadow(img, box, 32, blur=14, alpha=34, dy=7)
        ImageDraw.Draw(img).rounded_rectangle(box, radius=32, fill=WHITE)
        draw_block(img, x0 + pad_x, y + pad_y - 2, b, (58, 58, 78), bold_color=NAVY, align="center", box_w=b.w)
        y = box[3] + gap
    _arrow_button(img, dark=True)
    return img.convert("RGB")


def slide_cta(media: dict, photo, size=(1080, 1350), emoji: str = "") -> Image.Image:
    """Image d'abonnement lisible sur n'importe quelle photo : photo très floutée et assombrie, texte blanc direct."""
    W, H = size
    c = rgb(media["color"])
    if photo is not None:
        bg = cover(photo, W // 8, H // 8, focus_y=0.4).filter(ImageFilter.GaussianBlur(3)).resize(size, Image.BICUBIC)
        img = bg.convert("RGBA")
        img.alpha_composite(Image.new("RGBA", size, (*mix(c, (0, 0, 0), 0.6), 195)))
    else:
        img = Image.new("RGBA", size, (*mix(c, (0, 0, 0), 0.3), 255))
        img.alpha_composite(vgradient(W, H, mix(c, (0, 0, 0), 0.8), 0, 255))
    img.alpha_composite(logo(media, 60), (44, 40))
    cta = media.get("cta") or "Abonne-toi pour rester informé"
    b = fit(cta, W - 160, 460, 92, 54, base="black", bold="black", spacing=1.12)
    lg = logo(media, 84)
    fh = font("bold", 38)
    pill_txt = "🔔 Active les notifications"
    pb = layout(pill_txt, W, 36, base="bold", bold="bold", spacing=1.0)
    total = lg.height + 50 + b.h + 36 + 46 + 56 + 80
    y = (H - total) // 2
    img.alpha_composite(lg, ((W - lg.width) // 2, y))
    y += lg.height + 50
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))          # ombre douce pour détacher le texte
    draw_block(shadow, 82, y + 4, b, (0, 0, 0), align="center", box_w=W - 160)
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(6)))
    y = draw_block(img, 80, y, b, WHITE, align="center", box_w=W - 160)
    y += 36
    d = ImageDraw.Draw(img)
    d.text((W // 2, y + 23), media.get("handle", ""), font=fh, fill=(225, 225, 235), anchor="mm")
    y += 46 + 56
    pw_, ph_ = pb.w + 64, 80
    px0 = (W - pw_) // 2
    d.rounded_rectangle((px0, y, px0 + pw_, y + ph_), radius=ph_ // 2, fill=WHITE)
    draw_block(img, px0 + 32, y + 18, pb, mix(c, (0, 0, 0), 0.25))
    return img.convert("RGB")


# ------------------------------------------------------------------ image X
def x_image(media: dict, photos: list, credits: list[str], size=(1600, 900), emoji: str = "") -> Image.Image:
    W, H = size
    if len(photos) >= 2:
        img = Image.new("RGBA", size, WHITE)
        half = (W - 8) // 2
        img.paste(cover(photos[0], half, H, focus_y=0.22), (0, 0))
        img.paste(cover(photos[1], half, H, focus_y=0.22), (W - half, 0))
    elif photos and photos[0].width / photos[0].height < 1.2:   # portrait : fond flou + photo entière
        p = photos[0]
        img = cover(p, W // 5, H // 5).filter(ImageFilter.GaussianBlur(5)).resize(size).convert("RGBA")
        img = Image.alpha_composite(img, Image.new("RGBA", size, (0, 0, 0, 70)))
        fg = p.resize((int(p.width * H / p.height), H), Image.LANCZOS)
        img.paste(fg, ((W - fg.width) // 2, 0))
    else:
        img = _photo_bg(photos[0] if photos else None, size, media, focus=0.3, emoji=emoji, emoji_pos=(0.5, 0.5))
    img = img.convert("RGBA")
    if credits:
        txt = " · ".join(credits)
        f = font("regular", 17)
        strip = Image.new("RGBA", (text_w(txt, f) + 20, 28), (0, 0, 0, 125))
        img.alpha_composite(strip, (0, H - 28))
        ImageDraw.Draw(img).text((10, H - 25), txt, font=f, fill=(232, 232, 232))
    lg = logo(media, 40)
    img.alpha_composite(lg, (W - lg.width - 16, H - lg.height - 14))
    return img.convert("RGB")


def render_post(media: dict, post: dict, photos: list, credits: list[str], out_dir: Path,
                carousel_size=(1080, 1350)) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    p1 = photos[0] if photos else None
    credit_main = credits[0] if credits else ""
    emoji = post.get("label_emoji", "")
    slides = [slide_cover(media, post, p1, credit_main, tuple(carousel_size)),
              slide_points(media, post, tuple(carousel_size)),
              slide_cta(media, p1, tuple(carousel_size), emoji)]
    paths = []
    for i, s in enumerate(slides, 1):
        p = out_dir / f"slide_{i}.jpg"
        s.save(p, "JPEG", quality=92)
        paths.append(p)
    x_path = out_dir / "x.jpg"
    x_image(media, photos[:2], credits[:2], emoji=emoji).save(x_path, "JPEG", quality=92)
    zip_path = out_dir / "carrousel.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
        for p in paths:
            z.write(p, p.name)
    return {"slides": paths, "x": x_path, "zip": zip_path}


# ------------------------------------------------------------------ TikTok (plein écran 9:16)
def tiktok_frame(slide: Image.Image, size=(1080, 1920)) -> Image.Image:
    """Image du carrousel posée au centre d'un fond 9:16 : la même image très floutée et assombrie.
    Sur TikTok, l'image occupe tout l'écran (pas de bandes noires) et le texte reste hors des zones de l'appli."""
    W, H = size
    slide = slide.convert("RGB")
    bg = cover(slide, W // 10, H // 10).filter(ImageFilter.GaussianBlur(2.5)).resize(size, Image.BICUBIC).convert("RGBA")
    bg.alpha_composite(Image.new("RGBA", size, (0, 0, 0, 130)))
    fg = slide.resize((W, int(slide.height * W / slide.width)), Image.LANCZOS)
    y = max(0, int((H - fg.height) * 0.42))          # un peu au-dessus du centre : la légende TikTok occupe le bas
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle((0, y - 6, W, y + fg.height + 10), fill=(0, 0, 0, 120))
    bg.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))
    bg.paste(fg, (0, y))
    return bg.convert("RGB")


def make_tiktok(slide_paths: list[Path], out_dir: Path) -> dict:
    paths = []
    for i, sp in enumerate(slide_paths, 1):
        p = out_dir / f"tiktok_{i}.jpg"
        with Image.open(sp) as im:
            tiktok_frame(im).save(p, "JPEG", quality=90)
        paths.append(p)
    zip_path = out_dir / "tiktok.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
        for p in paths:
            z.write(p, p.name)
    return {"tiktok": paths, "tiktok_zip": zip_path}


# ------------------------------------------------------------------ « L'essentiel du jour »
# Même modèle que la 1re image d'un post : photo plein cadre, fort dégradé noir, bandeau blanc, texte blanc par-dessus.
def _photo_of(item: dict):
    try:
        if not item.get("photo"):
            return None
        im = Image.open(item["photo"]).convert("RGB")
        return im.crop((0, 0, im.width // 2 - 4, im.height)) if item.get("crop_left") else im
    except Exception:
        return None


def render_recap(media: dict, items: list[dict], date_txt: str, out_dir: Path, carousel_size=(1080, 1350)) -> dict:
    """Couverture = la photo de l'info la plus forte ; puis 1 image par info, au même format ; puis l'abonnement."""
    out_dir.mkdir(parents=True, exist_ok=True)
    size = tuple(carousel_size)
    photos = [_photo_of(it) for it in items]
    top, top_credit = photos[0], items[0].get("credit", "")
    slides = [slide_cover(media, {"label": "L'ESSENTIEL DU JOUR", "label_emoji": "📰",
                                  "cover_text": f"Les **{len(items)} infos** à retenir ce {date_txt} ⬇️"},
                          top, top_credit, size)]
    for i, (it, ph) in enumerate(zip(items, photos), 1):
        label = f"{i}/{len(items)} · {it.get('label') or 'INFO'}"
        slides.append(slide_cover(media, {"label": label, "label_emoji": it.get("emoji", ""), "cover_text": it["text"]},
                                  ph, it.get("credit", ""), size))
    slides.append(slide_cta(media, top, size))
    paths = []
    for i, s in enumerate(slides, 1):
        p = out_dir / f"slide_{i}.jpg"
        s.save(p, "JPEG", quality=92)
        paths.append(p)
    x_path = out_dir / "x.jpg"
    x_image(media, [top] if top is not None else [], [top_credit] if top_credit else [], emoji="📰").save(
        x_path, "JPEG", quality=92)
    zip_path = out_dir / "carrousel.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
        for p in paths:
            z.write(p, p.name)
    return {"slides": paths, "x": x_path, "zip": zip_path}
