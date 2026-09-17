release: python manage.py collectstatic --noinput && python manage.py migrate --noinput
web: gunicorn dashboard.wsgi --workers ${WEB_CONCURRENCY:-5} --timeout ${WEB_TIMEOUT:-60} --max-requests 1000 --max-requests-jitter 100 --log-file -
