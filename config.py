import os
from dotenv import load_dotenv

load_dotenv()

CHUNK_SIZE =200
CHUNK_OVERLAP=30

# grag
BATCH_SIZE=5
MAX_CONCURRENCY=1

#agent
NGINX_PATH="C:\\Users\\admin\\Desktop\\lab\\nginx-1.30.4\\conf\\nginx.conf"
PROMETHEUS_URL="http://localhost:9090"