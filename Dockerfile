FROM python:3.13-alpine
WORKDIR /app
COPY main.py index.html .
COPY images/ images/
CMD ["python", "main.py"]
