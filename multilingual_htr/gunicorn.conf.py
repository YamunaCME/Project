"""
Gunicorn Production Server Configuration.
"""

import multiprocessing

bind = "0.0.0.0:8000"
# For CPU-bound ML and OCR inference, limit workers to prevent out-of-memory errors
workers = min(4, multiprocessing.cpu_count())
threads = 2
timeout = 180  # allow time for large document OCR and model loads
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
accesslog = "-"
errorlog = "-"
loglevel = "info"
