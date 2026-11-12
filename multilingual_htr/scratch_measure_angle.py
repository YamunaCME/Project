import cv2
import numpy as np
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from documents.services.easyocr_engine import EasyOCREngine

reader = EasyOCREngine.get_reader('en')
img_path = 'media/uploads/2026/11/02/2nd.jpeg'
img = cv2.imread(img_path)
raw_boxes = reader.readtext(img, detail=1)

def get_geom(item):
    xs = [p[0] for p in item[0]]
    ys = [p[1] for p in item[0]]
    return min(xs), max(xs), min(ys), max(ys)

angles = []
for it in raw_boxes:
    bbox = it[0]
    # bbox is [[x0,y0], [x1,y1], [x2,y2], [x3,y3]]
    # top edge is p0 to p1
    dx = bbox[1][0] - bbox[0][0]
    dy = bbox[1][1] - bbox[0][1]
    if dx > 30: # only for words of reasonable length
        angle_deg = np.degrees(np.arctan2(dy, dx))
        angles.append(angle_deg)

angles = np.array(angles)
print(f"Total word angles analyzed: {len(angles)}")
print(f"Mean angle: {np.mean(angles):.2f} degrees")
print(f"Median angle: {np.median(angles):.2f} degrees")
print(f"25th percentile: {np.percentile(angles, 25):.2f}, 75th percentile: {np.percentile(angles, 75):.2f}")
