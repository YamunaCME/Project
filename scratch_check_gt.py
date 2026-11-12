import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

with open('media/samples/ground_truth_handwritten_technical_notes.txt', 'r', encoding='utf-8') as f:
    gt_lines = [l.strip() for l in f.readlines() if l.strip()]

print(f"Total GT lines: {len(gt_lines)}")
for i, l in enumerate(gt_lines):
    print(f"{i+1:2d}: {l}")
