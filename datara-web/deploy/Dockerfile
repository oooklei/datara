# Datara 前端镜像：dist 已在本地/CI 构建完成，远端仅需 nginx:alpine（内网拉取快）
FROM nginx:1.27-alpine

COPY dist /usr/share/nginx/html
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
