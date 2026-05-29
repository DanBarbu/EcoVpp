FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY hydrobattery_atlas.py .
EXPOSE 8004
CMD ["uvicorn", "hydrobattery_atlas:app", "--host", "0.0.0.0", "--port", "8004"]
