import cv2
import os
import django
import numpy as np

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from documents.services.easyocr_engine import EasyOCREngine
from documents.management.commands.evaluate_accuracy import calculate_cer, calculate_wer

reader = EasyOCREngine.get_reader('en')
img_path = 'media/uploads/2026/11/02/2nd.jpeg'
img = cv2.imread(img_path)
h_img, w_img = img.shape[:2]
print(f"Image dimensions: width={w_img}, height={h_img}")

raw_boxes = reader.readtext(img, detail=1)

def get_geom(item):
    xs = [p[0] for p in item[0]]
    ys = [p[1] for p in item[0]]
    return min(xs), max(xs), min(ys), max(ys)

print("\n--- ALL BOXES WITH X > 650 (RIGHT SIDE / OPPOSITE PAGE) ---")
for it in raw_boxes:
    xmin, xmax, ymin, ymax = get_geom(it)
    if xmin > 650:
        print(f"[{xmin:4.0f}, {ymin:4.0f}, {xmax:4.0f}, {ymax:4.0f}] conf={it[2]*100:4.1f}% : '{it[1]}'")
