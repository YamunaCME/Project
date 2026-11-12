import cv2
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from documents.services.easyocr_engine import EasyOCREngine
from documents.services.technical_postprocessor import TechnicalPostProcessor

reader = EasyOCREngine.get_reader('en')
img_path = 'media/uploads/2026/11/02/2nd.jpeg'
orig_bgr = cv2.imread(img_path)
h_img, w_img = orig_bgr.shape[:2]

boxes_orig = reader.readtext(orig_bgr, detail=1, text_threshold=0.4, low_text=0.3, link_threshold=0.3)

def get_geom(item):
    xs = [p[0] for p in item[0]]
    ys = [p[1] for p in item[0]]
    return min(xs), max(xs), min(ys), max(ys)

filtered = []
for it in boxes_orig:
    xmin, xmax, ymin, ymax = get_geom(it)
    cleaned = it[1].strip()
    if not cleaned: continue
    if xmin >= (w_img * 0.88): continue
    if ymax < 140 or ymin > 1520: continue
    filtered.append(it)

sorted_boxes = sorted(filtered, key=lambda it: get_geom(it)[2])
lines = []
for it in sorted_boxes:
    xmin, xmax, ytop, ybot = get_geom(it)
    ymid = (ytop + ybot) / 2.0
    h = max(1.0, ybot - ytop)
    w = max(1.0, xmax - xmin)

    matched_line = None
    min_v_dist = 9999.0
    for line in lines:
        has_h_collision = False
        for member in line:
            m_xmin, m_xmax, _, _ = get_geom(member)
            m_w = max(1.0, m_xmax - m_xmin)
            h_overlap = max(0.0, min(xmax, m_xmax) - max(xmin, m_xmin))
            if h_overlap > (0.25 * min(w, m_w)):
                has_h_collision = True
                break
        if has_h_collision: continue

        line_ymids = [(get_geom(x)[2] + get_geom(x)[3]) / 2.0 for x in line]
        line_heights = [get_geom(x)[3] - get_geom(x)[2] for x in line]
        avg_line_y = sum(line_ymids) / len(line_ymids)
        avg_line_h = sum(line_heights) / len(line_heights)

        v_dist = abs(ymid - avg_line_y)
        if v_dist < (max(h, avg_line_h) * 0.75) and v_dist < min_v_dist:
            min_v_dist = v_dist
            matched_line = line

    if matched_line is not None:
        matched_line.append(it)
    else:
        lines.append([it])

lines.sort(key=lambda l: sum((get_geom(x)[2] + get_geom(x)[3]) / 2.0 for x in l) / len(l))
for l in lines:
    l.sort(key=lambda it: get_geom(it)[0])

print(f"Total lines: {len(lines)}")
for idx, l in enumerate(lines):
    raw_l = " ".join(it[1].strip() for it in l)
    clean_l = TechnicalPostProcessor.post_process(raw_l)
    print(f"L{idx+1:02d}: {clean_l}")
