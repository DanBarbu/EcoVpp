FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY flexibility_engine.py .
EXPOSE 8001
CMD ["python", "-u", "flexibility_engine.py"]
