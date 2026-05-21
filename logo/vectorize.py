"""
JPEG logo → SVG vectorizer (v4 - clean).
Downsamples first for smooth curves, then traces.
"""
import numpy as np
from PIL import Image
from scipy import ndimage
import sys, os

JPEG_PATH = sys.argv[1] if len(sys.argv) > 1 else \
    "/mnt/c/Users/angelo/Documents/alemai/inmueblebot/logo/mock_logov1.jpeg"
OUTPUT_PATH = sys.argv[2] if len(sys.argv) > 2 else \
    JPEG_PATH.rsplit('.', 1)[0] + '.svg'

# ── 1. Load and downsample ──────────────────────────────────────
SCALE = 4  # 1024 → 256
img = Image.open(JPEG_PATH).convert('RGB')
orig_w, orig_h = img.size
img_small = img.resize((orig_w // SCALE, orig_h // SCALE), Image.LANCZOS)
arr = np.array(img_small)
sh, sw, _ = arr.shape
print(f"Source: {orig_w}x{orig_h} → working at {sw}x{sh}")

# ── 2. Binary mask ──────────────────────────────────────────────
is_blue = ~((arr[:,:,0] > 200) & (arr[:,:,1] > 200) & (arr[:,:,2] > 200))
mask = ndimage.binary_closing(is_blue, structure=np.ones((3,3)), iterations=2)
mask = ndimage.binary_opening(mask, structure=np.ones((2,2)), iterations=1)

avg_color = arr[mask].mean(axis=0).astype(int)
cr, cg, cb = avg_color
print(f"Color: #{cr:02x}{cg:02x}{cb:02x} ({mask.sum()} px at {sw}x{sh})")

# ── 3. Row-span rectangles ──────────────────────────────────────
rects = []
for y in range(sh):
    row = mask[y, :]
    in_run = False
    run_start = 0
    for x in range(sw):
        if row[x] and not in_run:
            run_start = x
            in_run = True
        elif not row[x] and in_run:
            rects.append((run_start, y, x - run_start, 1))
            in_run = False
    if in_run:
        rects.append((run_start, y, sw - run_start, 1))

# Vertical merge
groups = {}
for x, y, rw, _ in rects:
    groups.setdefault((x, rw), []).append(y)

merged = []
for (x, rw), ys in groups.items():
    ys = sorted(ys)
    start_y = ys[0]
    prev_y = ys[0]
    for y in ys[1:]:
        if y == prev_y + 1:
            prev_y = y
        else:
            merged.append((x, start_y, rw, prev_y - start_y + 1))
            start_y = y
            prev_y = y
    merged.append((x, start_y, rw, prev_y - start_y + 1))

print(f"Rectangles: {len(merged)}")

# ── 4. Write SVG with proper scaling ────────────────────────────
# Scale coordinates back up so the SVG matches original dimensions
scale_factor = SCALE
svg_line = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {orig_w} {orig_h}">'
print(f"Scaling: {scale_factor}x (SVG viewBox: {orig_w}x{orig_h})")

with open(OUTPUT_PATH, 'w') as f:
    f.write(svg_line + '\n')
    f.write(f'  <rect width="{orig_w}" height="{orig_h}" fill="white"/>\n')
    for x, y, rw, rh in merged:
        # Scale coordinates
        sx = x * scale_factor
        sy = y * scale_factor
        sw2 = rw * scale_factor
        sh2 = rh * scale_factor
        f.write(f'  <rect x="{sx}" y="{sy}" width="{sw2}" height="{sh2}" fill="#{cr:02x}{cg:02x}{cb:02x}"/>\n')
    f.write('</svg>\n')

orig_size = os.path.getsize(JPEG_PATH)
svg_size = os.path.getsize(OUTPUT_PATH)
print(f"\n✅ {OUTPUT_PATH}")
print(f"   JPEG: {orig_size/1024:.1f} KB → SVG: {svg_size/1024:.1f} KB ({100-svg_size/orig_size*100:.0f}% reduction)")
