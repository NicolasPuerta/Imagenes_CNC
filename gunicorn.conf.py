import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"

workers = 2
threads = 2
timeout = 120
graceful_timeout = 120
max_requests = 500
max_requests_jitter = 50