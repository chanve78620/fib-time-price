FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py index.html classic.html ./
ENV PORT=8765
EXPOSE 8765
CMD gunicorn server:app --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 120
