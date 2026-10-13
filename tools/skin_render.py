"""Render a posed Minecraft player from a 64x64 skin.

Six boxes, thirty-six faces, painter's algorithm. Each face is the skin's own
texture tile mapped onto the projected quad, so the result keeps the source
pixels rather than resampling them smooth. Used by tools/make_thumbnail.py.

    python tools/skin_render.py assets/skin.png out.png --height 900
"""

from __future__ import annotations

import argparse
import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

# Model units are skin pixels. The player is 32 units tall: legs 0-12,
# body 12-24, head 24-32. +x is the viewer's right, +y up, +z toward camera.
BOXES = {
    "head":      dict(center=(0, 28, 0), size=(8, 8, 8),   pivot=(0, 24, 0),  uv=(0, 0)),
    "body":      dict(center=(0, 18, 0), size=(8, 12, 4),  pivot=(0, 24, 0),  uv=(16, 16)),
    "arm_right": dict(center=(-6, 16, 0), size=(4, 12, 4), pivot=(-5, 22, 0), uv=(40, 16)),
    "arm_left":  dict(center=(6, 16, 0), size=(4, 12, 4),  pivot=(5, 22, 0),  uv=(32, 48)),
    "leg_right": dict(center=(-2, 6, 0), size=(4, 12, 4),  pivot=(-2, 12, 0), uv=(0, 16)),
    "leg_left":  dict(center=(2, 6, 0), size=(4, 12, 4),   pivot=(2, 12, 0),  uv=(16, 48)),
}

# Arms thrown wide, a half turn to camera: the pose both reference thumbnails use.
HERO_POSE = {
    "head":      (-7, 16, 0),
    "body":      (0, 0, 0),
    "arm_right": (-18, 0, -71),
    "arm_left":  (-30, 0, 43),
    "leg_right": (9, 0, -11),
    "leg_left":  (-11, 0, 12),
}


def _uv_faces(w: int, h: int, d: int, u: int, v: int) -> dict:
    """Standard Minecraft box unwrap: the six tiles in skin pixels."""
    return {
        "top":    (u + d, v, w, d),
        "bottom": (u + d + w, v, w, d),
        "right":  (u, v + d, d, h),
        "front":  (u + d, v + d, w, h),
        "left":   (u + d + w, v + d, d, h),
        "back":   (u + d + w + d, v + d, w, h),
    }


def _face_corners(c, s, face):
    """World-space quad for one face, ordered to match the texture tile's
    top-left, top-right, bottom-right, bottom-left."""
    cx, cy, cz = c
    hx, hy, hz = s[0] / 2, s[1] / 2, s[2] / 2
    x0, x1 = cx - hx, cx + hx
    y0, y1 = cy - hy, cy + hy
    z0, z1 = cz - hz, cz + hz
    return {
        "front":  [(x0, y1, z1), (x1, y1, z1), (x1, y0, z1), (x0, y0, z1)],
        "back":   [(x1, y1, z0), (x0, y1, z0), (x0, y0, z0), (x1, y0, z0)],
        "right":  [(x0, y1, z0), (x0, y1, z1), (x0, y0, z1), (x0, y0, z0)],
        "left":   [(x1, y1, z1), (x1, y1, z0), (x1, y0, z0), (x1, y0, z1)],
        "top":    [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],
        "bottom": [(x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0)],
    }[face]


def _rot(deg_x, deg_y, deg_z):
    rx, ry, rz = map(math.radians, (deg_x, deg_y, deg_z))
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return my @ mx @ mz


def _seal(img, rounds=3):
    """Close the hairline gaps rotation opens at the shoulders and hips, and
    grow neighbouring colour into them so nothing shows through the model."""
    arr = np.asarray(img).astype(np.float32)
    rgb, a = arr[..., :3], arr[..., 3]
    solid = (a > 128).astype(np.float32)

    closed = Image.fromarray((solid * 255).astype(np.uint8), "L")
    closed = closed.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    target = (np.asarray(closed) > 128).astype(np.float32)

    for _ in range(rounds):
        gap = (target > 0) & (solid < 0.5)
        if not gap.any():
            break
        num = np.zeros_like(rgb)
        den = np.zeros_like(solid)
        for sy in (-1, 0, 1):
            for sx in (-1, 0, 1):
                if sx == 0 and sy == 0:
                    continue
                w = np.roll(np.roll(solid, sy, 0), sx, 1)
                c = np.roll(np.roll(rgb, sy, 0), sx, 1)
                num += c * w[..., None]
                den += w
        fillable = gap & (den > 0)
        rgb[fillable] = (num[fillable] / den[fillable][..., None])
        solid[fillable] = 1.0

    out = np.empty_like(arr)
    out[..., :3] = rgb
    out[..., 3] = np.maximum(a, solid * 255)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def _perspective_coeffs(dst, src):
    """PIL PERSPECTIVE coefficients mapping destination pixels back to source."""
    rows, rhs = [], []
    for (x, y), (u, v) in zip(dst, src):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        rhs.extend((u, v))
    return np.linalg.solve(np.array(rows, float), np.array(rhs, float))


def render(skin_path, height=900, yaw=-26.0, pitch=6.0, pose=None,
           outline=0, outline_color=(255, 255, 255, 255), supersample=2):
    """Return an RGBA image of the posed player, trimmed to the ink."""
    pose = dict(HERO_POSE if pose is None else pose)
    skin = Image.open(skin_path).convert("RGBA")

    ss = max(1, int(supersample))
    unit = (height * ss) / 34.0          # a little headroom above the hat
    world = _rot(pitch, yaw, 0)
    light = np.array([-0.42, 0.74, 0.52])
    light /= np.linalg.norm(light)

    cam_z = 210.0                        # far enough that the perspective stays mild
    W = int(height * ss * 1.45)
    H = int(height * ss * 1.30)
    ox, oy = W / 2, H * 0.94             # model origin (between the feet) near the bottom

    def project(p):
        v = world @ np.asarray(p, float)
        depth = cam_z - v[2]
        k = unit * cam_z / depth
        return (ox + v[0] * k, oy - v[1] * k), depth

    quads = []
    for name, box in BOXES.items():
        rx, ry, rz = pose.get(name, (0, 0, 0))
        local = _rot(rx, ry, rz)
        pivot = np.asarray(box["pivot"], float)
        tiles = _uv_faces(*box["size"], *box["uv"])
        for face, tile in tiles.items():
            pts3 = []
            for p in _face_corners(box["center"], box["size"], face):
                q = local @ (np.asarray(p, float) - pivot) + pivot
                pts3.append(q)
            flat = [project(p) for p in pts3]
            pts2 = [f[0] for f in flat]
            depth = sum(f[1] for f in flat) / 4.0

            area = 0.0
            for i in range(4):
                ax, ay = pts2[i]
                bx, by = pts2[(i + 1) % 4]
                area += ax * by - bx * ay
            if area <= 0:                     # back face, never seen
                continue

            e1 = np.asarray(pts3[1]) - np.asarray(pts3[0])
            e2 = np.asarray(pts3[3]) - np.asarray(pts3[0])
            n = np.cross(e1, e2)
            ln = np.linalg.norm(n)
            n = n / ln if ln else n
            shade = 0.60 + 0.40 * max(0.0, float(np.dot(world @ n, light)))
            quads.append((depth, pts2, tile, shade))

    quads.sort(key=lambda q: -q[0])
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    for _, pts2, tile, shade in quads:
        u, v, tw, th = tile
        tex = skin.crop((u, v, u + tw, v + th))
        if tex.getextrema()[3][1] == 0:
            continue
        if shade != 1.0:
            arr = np.asarray(tex, dtype=np.float32)
            arr[..., :3] *= shade
            tex = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")

        xs = [p[0] for p in pts2]
        ys = [p[1] for p in pts2]
        bx0, by0 = int(math.floor(min(xs))) - 1, int(math.floor(min(ys))) - 1
        bx1, by1 = int(math.ceil(max(xs))) + 1, int(math.ceil(max(ys))) + 1
        bx0, by0 = max(bx0, 0), max(by0, 0)
        bx1, by1 = min(bx1, W), min(by1, H)
        if bx1 <= bx0 or by1 <= by0:
            continue

        local_dst = [(x - bx0, y - by0) for x, y in pts2]
        src = [(0, 0), (tw, 0), (tw, th), (0, th)]
        try:
            coeffs = _perspective_coeffs(local_dst, src)
        except np.linalg.LinAlgError:
            continue

        patch = tex.transform((bx1 - bx0, by1 - by0), Image.PERSPECTIVE,
                              coeffs, Image.NEAREST)
        # Fill, then re-trace the edge, so neighbouring faces of a box overlap
        # by a pixel instead of leaving a seam the backdrop shows through.
        mask = Image.new("L", (bx1 - bx0, by1 - by0), 0)
        md = ImageDraw.Draw(mask)
        md.polygon(local_dst, fill=255)
        md.line(local_dst + [local_dst[0]], fill=255, width=2 * ss, joint="curve")
        canvas.paste(patch, (bx0, by0), mask)

    canvas = _seal(canvas)

    if ss > 1:
        canvas = canvas.resize((W // ss, H // ss), Image.LANCZOS)

    if outline > 0:
        a = canvas.split()[3].point(lambda p: 255 if p > 128 else 0)
        grown = a.filter(ImageFilter.MaxFilter(outline * 2 + 1))
        # Outer ring only, so the joint seams can never read as white piping.
        ring_alpha = ImageChops.subtract(grown, a)
        ring = Image.new("RGBA", canvas.size, outline_color)
        ring.putalpha(ring_alpha)
        canvas = Image.alpha_composite(ring, canvas)

    bbox = canvas.split()[3].getbbox()
    return canvas.crop(bbox) if bbox else canvas


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("skin")
    ap.add_argument("out")
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--yaw", type=float, default=-26.0)
    ap.add_argument("--pitch", type=float, default=6.0)
    ap.add_argument("--outline", type=int, default=0)
    args = ap.parse_args()
    img = render(args.skin, height=args.height, yaw=args.yaw,
                 pitch=args.pitch, outline=args.outline)
    img.save(args.out)
    print(f"wrote {args.out} {img.size[0]}x{img.size[1]}")


if __name__ == "__main__":
    main()
