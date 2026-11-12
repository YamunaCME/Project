import cv2
import numpy as np
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from documents.services.easyocr_engine import EasyOCREngine
from documents.services.technical_postprocessor import TechnicalPostProcessor

reader = EasyOCREngine.get_reader('en')
img_path = 'media/uploads/2026/11/02/2nd.jpeg'
img = cv2.imread(img_path)
h_img, w_img = img.shape[:2]

boxes = reader.readtext(img, detail=1, text_threshold=0.4, low_text=0.3, link_threshold=0.3)

def get_geom(item):
    xs = [p[0] for p in item[0]]
    ys = [p[1] for p in item[0]]
    return min(xs), max(xs), min(ys), max(ys)

# Filter outside of main left page (main text is x in [40, 790], y in [140, 1500])
filtered = []
for it in boxes:
    xmin, xmax, ymin, ymax = get_geom(it)
    cleaned = it[1].strip()
    if not cleaned: continue
    if xmin >= (w_img * 0.88): continue # exclude right page
    if ymax < 140 or ymin > 1510: continue
    filtered.append(it)

print(f"Total valid boxes on page: {len(filtered)}")

# Let's inspect the boxes around y in [400, 550] (around 'First', 'Need', 'Many I/O')
print("\n--- Boxes around y in [400, 540] ---")
around_need = [b for b in filtered if 400 <= get_geom(b)[2] <= 540]
around_need.sort(key=lambda b: get_geom(b)[2])
for b in around_need:
    xmin, xmax, ymin, ymax = get_geom(b)
    print(f"[{xmin:3.0f}, {ymin:3.0f}, {xmax:3.0f}, {ymax:3.0f}] : '{b[1]}'")
