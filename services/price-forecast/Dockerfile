FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY metoc_nowcast.py weather.py model.py price_forecast.py opcom.py calibration.py validate.py ./
EXPOSE 8003
CMD ["uvicorn", "price_forecast:app", "--host", "0.0.0.0", "--port", "8003"]
