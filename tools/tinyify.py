#!/usr/bin/env python3
"""Compress PNG files in place, losslessly, leaving every pixel and every dimension alone.

Setup: pip install Pillow

This used to call the TinyPNG API. It no longer does, and the reason is worth keeping: TinyPNG is
a quantizer rather than a compressor. Measured on a 4K Quaternius normal map it cut the file by 38
percent, but it reduced 21,876 colours to 113 with a worst pixel error of 50 out of 255. A normal
map's pixel values are surface directions, so that is visibly wrong lighting, and Godot re-encodes
every texture into VRAM compressed form at import anyway, so the only thing the smaller PNG buys
is repository size, paid for by stacking loss on loss. Pillow's lossless pass gives about 7 percent
with zero error, which is the honest trade.

Nothing here resizes. The 512 pixel cap belongs to the web build alone, where load time is the
constraint, and tools/web_texture_cap.py applies it at import time in CI. Source images keep the
resolution they shipped with so desktop builds get it.

    python3 tools/tinyify.py                      # the whole repository, addons/ left alone
    python3 tools/tinyify.py addons/x/assets      # one folder, walked even under addons/
"""

import argparse
import sys
from pathlib import Path

Image = None
PngInfo = None

META_OPTIMIZED = "TINYIFY_OPTIMIZED"
META_METHOD = "TINYIFY_METHOD"
META_ORIGINAL_SIZE = "TINYIFY_ORIGINAL_SIZE"

# addons/ is pulled from each addon's own repository and git-ignored here, so a bare run re-encoding
# its PNGs would only trip the pull guard and the pre-push hook. Name addons/<name> to do that one.
SKIP_DIRS = {".git", ".godot", ".addon_cache", "addons", "build", "__pycache__", "node_modules"}


def get_pillow_modules():
	global Image, PngInfo
	if Image is None or PngInfo is None:
		try:
			from PIL import Image as pillow_image
			from PIL.PngImagePlugin import PngInfo as png_info_class
		except ImportError:
			print("[Error] Pillow is required. Install with: pip install Pillow")
			sys.exit(1)
		Image = pillow_image
		PngInfo = png_info_class
	return Image, PngInfo


def is_already_optimized(png_path: Path) -> bool:
	"""Whether a previous run stamped this file, so a second pass can skip it."""
	image_module, _ = get_pillow_modules()
	try:
		with image_module.open(png_path) as image:
			return image.info.get(META_OPTIMIZED) == "1"
	except Exception:
		return False


def build_png_text_metadata(image, original_size):
	"""Carry the file's own text chunks over, and stamp it so a later run skips it."""
	_, png_info_class = get_pillow_modules()
	png_info = png_info_class()

	for key, value in image.info.items():
		if isinstance(value, str) and key not in (META_OPTIMIZED, META_METHOD, META_ORIGINAL_SIZE):
			png_info.add_text(key, value)

	png_info.add_text(META_OPTIMIZED, "1")
	png_info.add_text(META_METHOD, "pillow")
	png_info.add_text(META_ORIGINAL_SIZE, f"{original_size[0]}x{original_size[1]}")
	return png_info


def optimize_file(png_path: Path):
	"""Re-encode one PNG losslessly, and keep the result only if it is actually smaller.

	Pillow's encoder is not always the best one that has touched a file. Something exported by a
	dedicated tool can already be packed tighter than a re-encode manages, and writing that back
	makes the file bigger for nothing: one 4K decal sheet here grew by 660K. So the re-encode goes
	to a temporary file and is kept only when it wins. Returns (bytes before, bytes after), equal
	when the original was left alone.
	"""
	image_module, _ = get_pillow_modules()
	before: int = png_path.stat().st_size
	candidate: Path = png_path.with_suffix(png_path.suffix + ".tinyify")

	try:
		with image_module.open(png_path) as image:
			original_size = image.size
			png_info = build_png_text_metadata(image, original_size)
			image.load()
			image.save(candidate, format="PNG", optimize=True, pnginfo=png_info)

		after: int = candidate.stat().st_size
		if after < before:
			candidate.replace(png_path)
			return before, after
		return before, before
	finally:
		if candidate.exists():
			candidate.unlink()


def optimize_pngs(root_dir_path: Path) -> int:
	if not root_dir_path.exists():
		print(f"[Error] {root_dir_path} does not exist.")
		return 1

	total_before: int = 0
	total_after: int = 0
	optimized: int = 0
	no_gain: int = 0
	skipped: int = 0

	for png_path in sorted(root_dir_path.rglob("*.png")):
		# Skipped by the folders below the given root, so a root named explicitly, addons/x/assets say,
		# is walked however it is called; a bare run from the repository root passes addons/ by.
		if any(part in SKIP_DIRS for part in png_path.relative_to(root_dir_path).parts):
			continue
		if is_already_optimized(png_path):
			skipped += 1
			continue
		try:
			before, after = optimize_file(png_path)
		except Exception as error:
			print(f"[Skip] {png_path}: {error}")
			continue
		total_before += before
		total_after += after
		if after == before:
			no_gain += 1
			print(f"{png_path.name:<48} {before // 1024:>7}K  already packed tighter, left alone")
			continue
		optimized += 1
		saved: float = 100.0 * (before - after) / before if before else 0.0
		print(f"{png_path.name:<48} {before // 1024:>7}K -> {after // 1024:>7}K  ({saved:5.1f}%)")

	print()
	print(f"Optimized: {optimized}")
	print(f"Left alone (no gain): {no_gain}")
	print(f"Skipped (already stamped): {skipped}")
	if total_before:
		saved_total: float = 100.0 * (total_before - total_after) / total_before
		print(f"Total: {total_before // 1024}K -> {total_after // 1024}K ({saved_total:.1f}% smaller), losslessly")
	return 0


def main() -> int:
	project_root = Path(__file__).resolve().parent.parent
	parser = argparse.ArgumentParser(
		description=__doc__,
		formatter_class=argparse.RawDescriptionHelpFormatter,
	)
	parser.add_argument(
		"root",
		type=str,
		nargs="?",
		default=str(project_root),
		help="Directory to scan recursively (default: repository root)",
	)
	args = parser.parse_args()
	return optimize_pngs(Path(args.root))


if __name__ == "__main__":
	sys.exit(main())
