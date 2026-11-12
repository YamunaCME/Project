import sys
import os

sys.path.insert(0, '.')
from documents.management.commands.evaluate_accuracy import calculate_cer, calculate_wer

with open('media/samples/ground_truth_handwritten_technical_notes.txt', 'r', encoding='utf-8') as f:
    old_gt = f.read().strip()

actual_verbatim = """Efficient for block data transfer
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

cer = calculate_cer(old_gt, actual_verbatim) * 100
wer = calculate_wer(old_gt, actual_verbatim) * 100
print("Old Ground Truth vs Verbatim Page Text:")
print(f"CER: {cer:.2f}%")
print(f"WER: {wer:.2f}%")
