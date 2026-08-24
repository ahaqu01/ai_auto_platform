FROM nginx:1.27-alpine
COPY deploy/demo/nginx.conf /etc/nginx/conf.d/default.conf
COPY apps/web/dist /usr/share/nginx/html
