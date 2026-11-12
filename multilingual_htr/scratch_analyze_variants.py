import cv2
import numpy as np
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from documents.services.easyocr_engine import EasyOCREngine
from documents.services.preprocessing import PreprocessingPipeline
from documents.services.technical_postprocessor import TechnicalPostProcessor
from documents.management.commands.evaluate_accuracy import calculate_cer, calculate_wer

reader = EasyOCREngine.get_reader('en')
img_path = 'media/uploads/2026/11/02/2nd.jpeg'
orig_bgr = cv2.imread(img_path)

with open('media/samples/ground_truth_handwritten_technical_notes.txt', 'r', encoding='utf-8') as f:
    old_gt = f.read().strip()

verbatim_gt = """Efficient for block data transfer
Improves overall system performance
Priority Interrupt: polling and daisychaining
A priority interrupt is an interrupt system in which multiple interrupt requests are assign different priority levels and the CPU services the highest priority first
Need:
Many I/O devices may request CPU services simultaneously
Some devices are more critical
So, priority ensures important devices are serviced first
So, simultaneously interrupts can be serviced
The priority is established either by S/W method or H/W method
The S/W method which gives priority to simultaneous interrupts is called "polling"
The H/W method which gives priority to simultaneous interrupts is called "daisychaining"
Software method: (polling)
polling is a S/W based interrupt handling method in which the CPU checks the status of each devices one by one to find which device has requested first
Priority is not decided by the hardware.
The first device found request in service is treated as highest priority and Remaining devices will be in waiting state
CPU uses to program for S/W polling routines to test the devices the structure with look of following
if (device[0]_flag)
    device[0].service();
else if (device[1].flag)""".strip()

def get_geom(item):
    xs = [p[0] for p in item[0]]
    ys = [p[1] for p in item[0]]
    return min(xs), max(xs), min(ys), max(ys)

def process_and_group(boxes, img_w):
    # Filter right margin bleed (opposite page: x >= 800)
    filtered = []
    for it in boxes:
        xmin, xmax, ymin, ymax = get_geom(it)
        cleaned = it[1].strip()
        if not cleaned:
            continue
        # Opposite page of notebook begins past x >= 795
        if xmin >= (img_w * 0.88):
            continue
        # Extreme top or bottom background noise
        if ymax < 140 or ymin > 1520:
            continue
        filtered.append(it)

    # Collision-aware line clustering
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

            if has_h_collision:
                continue

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

    lines_text = [" ".join(it[1].strip() for it in l if it[1].strip()) for l in lines]
    raw_text = "\n".join(lines_text)
    cleaned_text = TechnicalPostProcessor.post_process(raw_text)

    # Compute confidence
    all_confs = [it[2] for it in filtered]
    avg_conf = (sum(all_confs) / len(all_confs)) * 100.0 if all_confs else 0.0

    return raw_text, cleaned_text, avg_conf, len(lines)

# Test 1: Original BGR
boxes_orig = reader.readtext(orig_bgr, detail=1, text_threshold=0.4, low_text=0.3, link_threshold=0.3)
raw_t, clean_t, conf, n_lines = process_and_group(boxes_orig, orig_bgr.shape[1])

print(f"=== ORIGINAL VARIANT ===")
print(f"Confidence: {conf:.2f}%, Lines: {n_lines}")
print(f"Against Old GT - Raw CER: {calculate_cer(old_gt, raw_t)*100:.2f}%, WER: {calculate_wer(old_gt, raw_t)*100:.2f}%")
print(f"Against Old GT - Clean CER: {calculate_cer(old_gt, clean_t)*100:.2f}%, WER: {calculate_wer(old_gt, clean_t)*100:.2f}%")
print(f"Against Verbatim GT - Clean CER: {calculate_cer(verbatim_gt, clean_t)*100:.2f}%, WER: {calculate_wer(verbatim_gt, clean_t)*100:.2f}%")
