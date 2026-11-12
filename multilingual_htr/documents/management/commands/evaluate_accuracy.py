"""
Benchmark Accuracy Evaluation Management Command.

Computes mathematically verified Character Error Rate (CER) and Word Error Rate (WER)
benchmarks across English, Telugu, and Hindi for both Handwritten and Printed documents.
Outputs the exact comparative evaluation table.
"""

import sys
from django.core.management.base import BaseCommand
from documents.services.evaluation_service import (
    EvaluationService,
    calculate_cer,
    calculate_wer,
    compute_metrics,
)


class Command(BaseCommand):
    help = 'Evaluates OCR/HTR recognition quality and prints baseline vs improved CER and WER comparison table.'

    def handle(self, *args, **options):
        # Configure stdout for UTF-8 display on Windows
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

        self.stdout.write("\n" + "=" * 90)
        self.stdout.write("MULTILINGUAL HTR RECOGNITION BENCHMARK EVALUATION (CER & WER)")
        self.stdout.write("=" * 90)
        self.stdout.write("Mathematically verified using Levenshtein distance: (S + D + I) / N\n")

        results = EvaluationService.evaluate_all()
        summary = EvaluationService.get_summary_averages(results)

        # Print standard Markdown table required by specification
        self.stdout.write(
            f"| {'Language':<10} | {'Document Type':<16} | {'Baseline CER':<12} | {'Improved CER':<12} | {'Baseline WER':<12} | {'Improved WER':<12} |"
        )
        self.stdout.write(
            f"|{'-' * 12}|{'-' * 18}|{'-' * 14}|{'-' * 14}|{'-' * 14}|{'-' * 14}|"
        )

        for r in results:
            self.stdout.write(
                f"| {r['language']:<10} | {r['document_type']:<16} | {r['baseline_cer']:>10.2f}% | {r['improved_cer']:>10.2f}% | {r['baseline_wer']:>10.2f}% | {r['improved_wer']:>10.2f}% |"
            )

        self.stdout.write(
            f"|{'-' * 12}|{'-' * 18}|{'-' * 14}|{'-' * 14}|{'-' * 14}|{'-' * 14}|"
        )
        self.stdout.write(
            f"| {'AVERAGE':<10} | {'Overall':<16} | {summary['avg_baseline_cer']:>10.2f}% | {summary['avg_improved_cer']:>10.2f}% | {summary['avg_baseline_wer']:>10.2f}% | {summary['avg_improved_wer']:>10.2f}% |"
        )
        self.stdout.write("=" * 90)

        # Print key takeaways
        cer_reduction = round(summary['avg_baseline_cer'] - summary['avg_improved_cer'], 2)
        wer_reduction = round(summary['avg_baseline_wer'] - summary['avg_improved_wer'], 2)
        self.stdout.write(f"\n[OK] Average CER reduced by {cer_reduction}% (from {summary['avg_baseline_cer']}% to {summary['avg_improved_cer']}%)")
        self.stdout.write(f"[OK] Average WER reduced by {wer_reduction}% (from {summary['avg_baseline_wer']}% to {summary['avg_improved_wer']}%)\n")
