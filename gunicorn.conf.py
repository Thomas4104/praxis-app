# Gunicorn Konfiguration fuer OMNIA Praxissoftware
import multiprocessing

# Worker-Anzahl: CPU-Kerne * 2 + 1
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = 'sync'
timeout = 120
keepalive = 5
bind = '0.0.0.0:8000'
accesslog = '-'
errorlog = '-'
loglevel = 'info'
max_requests = 1000
max_requests_jitter = 50
graceful_timeout = 30
