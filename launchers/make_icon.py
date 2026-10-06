"""Regenerates the launcher icon art: launchers/normalize-tabular-data.ico
(Windows shortcut icon) and launchers/normalize-tabular-data.icns (macOS app
bundle icon), plus a .png preview for quick inspection.

Run: uv run --with pillow python launchers/make_icon.py
"""

from PIL import Image, ImageDraw

MASTER = 1024
PURPLE = (91, 45, 144, 255)
WHITE = (255, 255, 255, 255)
WHITE_SOFT = (255, 255, 255, 130)
AMBER = (255, 200, 74, 255)

img = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# squircle background, macOS-ish corner radius
draw.rounded_rectangle((64, 64, 960, 960), radius=232, fill=PURPLE)

# data-table glyph: solid header row over a faint grid
left, top, right, bottom = 170, 170, 854, 840
header_h = 150
draw.rounded_rectangle(
    (left, top, right, top + header_h), radius=26, fill=WHITE
)
row_h = (bottom - top - header_h) / 2
for row in (1, 2):
    y = top + header_h + row * row_h
    draw.line((left, y, right, y), fill=WHITE_SOFT, width=18)
for col in (1, 2):
    x = left + col * (right - left) / 3
    draw.line((x, top + header_h, x, bottom), fill=WHITE_SOFT, width=18)

# check mark, overlapping the lower grid
draw.line(
    [(255, 615), (455, 835), (790, 425)],
    fill=AMBER,
    width=95,
    joint="curve",
)
for x, y in ((255, 615), (790, 425)):
    r = 47
    draw.ellipse((x - r, y - r, x + r, y + r), fill=AMBER)

img.save("launchers/icon_256.png", sizes=[(256, 256)])
img.save("launchers/normalize-tabular-data.ico", sizes=[
    (16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)
])
img.save("launchers/normalize-tabular-data.icns", sizes=[
    (16, 16), (32, 32), (64, 64), (128, 128), (256, 256)
])
