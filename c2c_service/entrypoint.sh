#!/bin/bash

python manage.py migrate
java -jar /tmp/tika-server.jar & python manage.py runserver 0.0.0.0:8000