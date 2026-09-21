#!/bin/bash
docker cp /tmp/i8_diag11.py datara-worker:/tmp/i8_diag11.py
docker exec -e PYTHONPATH=/app datara-worker python /tmp/i8_diag11.py
