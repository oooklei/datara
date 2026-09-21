# Datara 后端公共镜像：五模块（api/master/worker/alert/logger）共用同一镜像，
# docker-compose 内以不同 command 启动（见根 docker-compose.yml）
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# curl 供容器 healthcheck 使用（compose 内 curl http://localhost:xxxx/health）
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tzdata \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖再拷代码，充分利用构建缓存
COPY requirements.txt ./
# pip 源用 aliyun HTTPS（清华源在 1.9 容器内被 DNS 解析为纯 IPv6 且容器无 IPv6 连通，秒败 versions: none）
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

COPY . .

EXPOSE 8000

# 默认启动 api 模块；master/worker/alert/logger 由 compose 覆盖 command
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
