"""Build the 1920x1080 project thumbnail, and the 960x540 repository preview.

Everything it needs is committed: an in-game capture with the minimap on screen
in assets/background.png, the player skin in assets/skin.png and Passion One in
tools/fonts/.

    python tools/make_thumbnail.py
    python tools/make_thumbnail.py --no-preview
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

import skin_render

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONT = os.path.join(HERE, "fonts", "PassionOne-Black.ttf")

W, H = 1920, 1080

STYLES = {
    "white": dict(top=(255, 255, 255), bot=(180, 184, 188), side=(138, 142, 146)),
    "gold":  dict(top=(255, 224, 90), bot=(255, 164, 14), side=(184, 105, 12)),
    "yellow": dict(top=(255, 238, 92), bot=(255, 200, 0), side=(190, 140, 0)),
    # Warm against the river scene's blues and greens, and nothing like the
    # white-and-yellow the skyblock thumbnail uses.
    "flame":  dict(top=(255, 184, 58), bot=(227, 58, 12), side=(138, 31, 3)),
}

# Ragged left, the way One Chunk Challenge and One Block are set. The earlier
# justified block came from Four Sticks alone; across the rest of the author's
# thumbnails each line keeps its natural width.
TITLE = [
    dict(text="MINIMAP", style="flame", cap=152, arc=7),
    dict(text="BEDROCK", style="white", cap=100, arc=-10),
]

# Where the minimap sits in assets/background.png, its compass letters included. It is
# lifted out and blown up, because at its real size it is unreadable in a thumbnail.
# The map is round, so only the map and its letters are lifted, not the sky round them.
MINIMAP_BOX = (1693, 1, 1920, 228)
PLATE_CROP = (0, 0, 1920, 1080)       # 16:9, above the taskbar

STROKE, DEPTH, EXTRUDE_DEG, TRACK = 13, 8, 90, 5


# --------------------------------------------------------------------------- type

def _cap_ratio(path):
    f = ImageFont.truetype(path, 400)
    box = f.getbbox("H")
    return (box[3] - box[1]) / 400.0


def _layout(font, text, track):
    xs, x = [], 0.0
    for ch in text:
        xs.append(x)
        x += font.getlength(ch) + track
    return xs, max(0.0, x - track)


def _advances(cap, text):
    font = ImageFont.truetype(FONT, int(round(cap / _cap_ratio(FONT))))
    return sum(font.getlength(c) for c in text)


def _track_for(cap, text, width):
    """Letter spacing that makes this word exactly `width` wide. Justifying on
    tracking keeps the letterforms; stretching the bitmap would not."""
    n = len(text)
    if n < 2:
        return TRACK
    return (width - _advances(cap, text)) / (n - 1)


def render_line(text, cap, style, track=TRACK, hscale=1.0, arc=0.0):
    """One word with the outline, extrude, gradient face and drop shadow."""
    pal = STYLES[style]
    size = int(round(cap / _cap_ratio(FONT)))
    font = ImageFont.truetype(FONT, size)
    xs, natural = _layout(font, text, track)

    rad = math.radians(EXTRUDE_DEG)
    dx, dy = math.cos(rad), math.sin(rad)
    pad = STROKE + DEPTH + 60
    cw = int(natural + pad * 2)
    ch = int(cap + size * 0.6 + pad * 2)
    base_y = pad + cap

    def draw_pass(img, fill, stroke_fill, stroke_w, ox, oy):
        d = ImageDraw.Draw(img)
        for ch_, x in zip(text, xs):
            d.text((pad + x + ox, base_y + oy), ch_, font=font, fill=fill,
                   anchor="ls", stroke_width=stroke_w, stroke_fill=stroke_fill)

    # the black shell around the whole extruded solid
    shell = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    for d_ in range(DEPTH, -1, -1):
        draw_pass(shell, (11, 11, 11, 255), (11, 11, 11, 255), STROKE,
                  dx * d_, dy * d_)

    # side faces
    sides = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    for d_ in range(DEPTH, 0, -1):
        draw_pass(sides, pal["side"] + (255,), None, 0, dx * d_, dy * d_)

    # top face, masked so the gradient runs down the cap height
    face_mask = Image.new("L", (cw, ch), 0)
    draw_pass(face_mask, 255, None, 0, 0, 0)
    grad = Image.new("RGB", (1, ch))
    gp = grad.load()
    for y in range(ch):
        t = (y - (base_y - cap)) / max(1.0, cap)
        t = min(1.0, max(0.0, t))
        k = t / 0.78 if t < 0.78 else (1.0 - t) / 0.22
        k = min(1.0, max(0.0, k))
        gp[0, y] = tuple(int(a + (b - a) * k) for a, b in zip(pal["top"], pal["bot"]))
    face = grad.resize((cw, ch), Image.NEAREST).convert("RGBA")
    face.putalpha(face_mask)

    line = Image.alpha_composite(shell, sides)
    line = Image.alpha_composite(line, face)

    # drop shadow, cast off the far face
    sh = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    sh.putalpha(line.split()[3])
    sh = Image.new("RGBA", (cw, ch), (0, 0, 0, 150))
    sh.putalpha(ImageChops.multiply(line.split()[3],
                                    Image.new("L", (cw, ch), 150)))
    sh = sh.filter(ImageFilter.GaussianBlur(11))
    out = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    out.alpha_composite(sh, (9, 13))
    out = Image.alpha_composite(out, line)

    if hscale != 1.0:
        out = out.resize((max(1, int(cw * hscale)), ch), Image.LANCZOS)
    if arc:
        out = _arc(out, arc)
    return out, natural


def _arc(img, bend):
    """Slide every column along a parabola, zero at both ends."""
    w, h = img.size
    pad = int(abs(bend)) + 2
    out = Image.new("RGBA", (w, h + pad * 2), (0, 0, 0, 0))
    for x in range(w):
        t = (x / (w - 1)) * 2 - 1 if w > 1 else 0.0
        off = bend * (1 - t * t)
        out.paste(img.crop((x, 0, x + 1, h)), (x, int(round(pad + off))))
    return out


def render_title():
    """Three lines set left, each at its natural width."""
    pieces, widths = [], []
    for ln in TITLE:
        piece, natural = render_line(ln["text"], ln["cap"], ln["style"],
                                     track=TRACK, arc=ln["arc"])
        pieces.append(piece)
        widths.append(natural)

    gap = 6
    total = sum(ln["cap"] for ln in TITLE) + gap * (len(TITLE) - 1)
    pad = 190
    block = Image.new("RGBA", (int(max(widths)) + pad * 2, int(total) + pad * 2),
                      (0, 0, 0, 0))
    y = pad
    for ln, piece in zip(TITLE, pieces):
        inner_pad = STROKE + DEPTH + 60
        arc_pad = int(abs(ln["arc"])) + 2
        block.alpha_composite(piece, (pad - inner_pad, int(y - inner_pad - arc_pad)))
        y += ln["cap"] + gap
    return block, pad, int(max(widths)), int(total)


# ------------------------------------------------------------------------ scene


def _grade(img, sat=1.5, contrast=1.14, bright=1.03):
    img = ImageEnhance.Color(img).enhance(sat)
    img = ImageEnhance.Contrast(img).enhance(contrast)
    return ImageEnhance.Brightness(img).enhance(bright)


def _vignette(img, strength=0.3):
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w]
    nx = (xx / (w - 1)) * 2 - 1
    ny = (yy / (h - 1)) * 2 - 1
    r = np.sqrt(nx ** 2 + ny ** 2) / math.sqrt(2)
    k = 1.0 - strength * np.clip((r - 0.55) / 0.45, 0, 1) ** 1.6
    arr = np.asarray(img.convert("RGB")).astype(np.float32) * k[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def _card(img, rim=9, shadow=30):
    """The white rim and drop shadow the author's thumbnails give anything
    lifted out of the scene."""
    pad = rim + shadow + 20
    out = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    sh.paste((0, 0, 0, 155), (pad, pad), Image.new("L", img.size, 255))
    out = Image.alpha_composite(out, sh.filter(ImageFilter.GaussianBlur(shadow * 0.55)))
    ring = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ring.paste((255, 255, 255, 255), (pad - rim, pad - rim),
               Image.new("L", (img.width + rim * 2, img.height + rim * 2), 255))
    out = Image.alpha_composite(out, ring)
    out.alpha_composite(img.convert("RGBA"), (pad, pad))
    return out


def _lift(img):
    """The map as an RGBA image: everything in the box that is not sky. That keeps the disc, whose stepped
    pixel edge a true circle would cut into, and the compass letters, which stand half out of the frame.
    Nothing the map draws is sky coloured: water is a deeper blue and ice a greyer one."""
    arr = np.asarray(img.convert("RGB")).astype(np.int16)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    sky = (b >= 225) & (r >= 110) & (r < 225) & (g >= 170)
    alpha = np.where(sky, 0, 255).astype(np.uint8)
    out = img.convert("RGBA")
    out.putalpha(Image.fromarray(alpha, "L"))
    return out


def _shaped_card(img, rim=9, shadow=30):
    """_card for something that is not a rectangle: the white rim and the shadow follow its alpha."""
    pad = rim + shadow + 20
    alpha = Image.new("L", (img.width + pad * 2, img.height + pad * 2), 0)
    alpha.paste(img.getchannel("A"), (pad, pad))
    ring = alpha.filter(ImageFilter.MaxFilter(rim * 2 + 1))
    out = Image.new("RGBA", alpha.size, (0, 0, 0, 0))
    sh = Image.new("RGBA", alpha.size, (0, 0, 0, 0))
    sh.putalpha(ring.point(lambda v: v * 155 // 255).filter(ImageFilter.GaussianBlur(shadow * 0.55)))
    out = Image.alpha_composite(out, sh)
    white = Image.new("RGBA", alpha.size, (255, 255, 255, 0))
    white.putalpha(ring)
    out = Image.alpha_composite(out, white)
    out.alpha_composite(img, (pad, pad))
    return out


def _patch_out(plate, box):
    """Paint the real minimap out of the plate before it becomes the backdrop.

    The blown-up copy sits roughly where the original is, and any sliver of the
    original showing past its edge reads as a seam. Mirroring the strip beside
    it is enough once the backdrop is blurred."""
    left, top, right, bottom = box
    width = right - left
    donor = plate.crop((max(0, left - width), top, left, bottom)).transpose(Image.FLIP_LEFT_RIGHT)
    out = plate.copy()
    out.paste(donor.resize((width, bottom - top), Image.LANCZOS), (left, top))
    return out


def build():
    plate = Image.open(os.path.join(ROOT, "assets", "background.png")).convert("RGB")

    # the world behind, softened and pushed back so the map and the title carry
    backdrop = _patch_out(plate, MINIMAP_BOX).crop(PLATE_CROP).resize((W, H), Image.LANCZOS)
    backdrop = backdrop.filter(ImageFilter.GaussianBlur(2.2))
    canvas = _grade(backdrop, sat=1.34, contrast=1.08, bright=0.97).convert("RGBA")

    # the minimap, lifted straight out of the capture and kept pixel sharp
    mm = _lift(plate.crop(MINIMAP_BOX))
    SCALE = 3.6
    mm = mm.resize((int(mm.width * SCALE), int(mm.height * SCALE)), Image.NEAREST)
    shaded = _grade(mm.convert("RGB"), sat=1.28, contrast=1.10, bright=1.04).convert("RGBA")
    shaded.putalpha(mm.getchannel("A"))
    canvas.alpha_composite(_shaped_card(shaded), (1020, 92))

    # the player, big in the corner and cropped by the frame the way Crossy Road
    # places him, turned toward the map with the near arm raised at it
    pointing = {
        "head":      (-4, 28, 0),
        "body":      (0, 10, 0),
        "arm_right": (-4, 0, -9),
        "arm_left":  (-58, 0, 30),
        "leg_right": (7, 0, -7),
        "leg_left":  (-8, 0, 8),
    }
    char = skin_render.render(os.path.join(ROOT, "assets", "skin.png"),
                              height=860, yaw=20, pitch=3, outline=11, pose=pointing)
    canvas.alpha_composite(char, (34, H - char.height + 232))

    block, pad, tw, th = render_title()
    block = block.rotate(-2.0, expand=True, resample=Image.BICUBIC)
    canvas.alpha_composite(block, (86 - pad, 74 - pad))

    out = _vignette(canvas.convert("RGB"), 0.28)
    return _grade(out, sat=1.06, contrast=1.04, bright=1.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(ROOT, "assets", "thumbnail.png"))
    ap.add_argument("--no-preview", action="store_true")
    args = ap.parse_args()

    img = build()
    img.save(args.out)
    print(f"wrote {args.out} {img.size[0]}x{img.size[1]}")

    if not args.no_preview:
        # the repository preview is 960x540, written by the project's own tool
        dest = os.path.join(ROOT, "minimap-bedrock.png")
        subprocess.check_call([sys.executable,
                               os.path.join(HERE, "make_preview.py"),
                               args.out, dest])


if __name__ == "__main__":
    main()
