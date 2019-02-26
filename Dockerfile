FROM alpine:3.9
RUN \
	apk update && \
	apk add python py-pip && \
	pip install Jinja2 redis Werkzeug
COPY src /app
WORKDIR /app
EXPOSE 5000
CMD ["python","shortly.py"]