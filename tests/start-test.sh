#!/bin/bash -ex
export DEVICE_MANAGER_URL="http://localhost:5000"
export FLASK_APP=apptests.py
( cd tests || exit
flask run &
cd ..
)
echo Starting dredd
dredd --hookfiles "./tests/dredd-hooks/*hook.py" \
 --server "gunicorn history.app:app \
          --bind 0.0.0.0:8000 \
          --reload -R \
          --access-logfile - \
          --log-file - \
          --env PYTHONUNBUFFERED=1 -k gevent" \
--language python docs/history.apib http://127.0.0.1:8000
fuser -k 5000/tcp
