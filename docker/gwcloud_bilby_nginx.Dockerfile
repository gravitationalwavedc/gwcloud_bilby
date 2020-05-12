FROM nginx:latest
ADD ./nginx/nginx.conf /etc/nginx/conf.d/nginx.conf
EXPOSE 8000
