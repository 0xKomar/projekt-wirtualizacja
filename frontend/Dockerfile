FROM nginx:1.30-alpine

# The official image fills in ${BACKEND_URL} when the container starts.
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY public/ /usr/share/nginx/html/
