# Production entry is published by the deployment stack on 18091; nginx listens on 80 inside the container.
FROM nginx:1.27-alpine
COPY dist /usr/share/nginx/html
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
