# Datara 前端（datara-newweb）WSL Docker 部署镜像
# 构建上下文 = 本目录（dist 由构建脚本拷入，见 compose/README 注释）
FROM nginx:stable-alpine

COPY dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
