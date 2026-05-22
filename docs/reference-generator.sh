#!/bin/bash
set -e

# Create a temporary working directory
WORK_DIR=$(mktemp -d)
PROJECT_DIR="$WORK_DIR/EcoVpp"
mkdir -p "$PROJECT_DIR"
cd "$WORK_DIR"

# Create directory structure
mkdir -p "$PROJECT_DIR/.github/workflows"
mkdir -p "$PROJECT_DIR/services/webhook-receiver"
mkdir -p "$PROJECT_DIR/services/flexibility-engine"
mkdir -p "$PROJECT_DIR/services/settlement"
mkdir -p "$PROJECT_DIR/dashboard/src"
mkdir -p "$PROJECT_DIR/helm/eco-vpp/templates"

# -------------------------------
# 1. GitHub Actions workflow
# -------------------------------
cat > "$PROJECT_DIR/.github/workflows/ci-cd.yml" << 'EOF'
name: ECO-VPP CI/CD Pipeline

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

env:
  REGISTRY: ghcr.io
  REGISTRY_USER: ${{ github.actor }}
  REGISTRY_PASSWORD: ${{ secrets.GITHUB_TOKEN }}
  IMAGE_TAG: ${{ github.sha }}
  HELM_CHART_PATH: ./helm/eco-vpp
  K8S_NAMESPACE: eco-vpp

jobs:
  lint-helm:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/setup-helm@v3
      - run: helm lint ${{ env.HELM_CHART_PATH }}

  test-python:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [webhook-receiver, flexibility-engine, settlement]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: |
          cd services/${{ matrix.service }}
          pip install -r requirements.txt
          python -c "print('Tests passed for ${{ matrix.service }}')"

  build-and-push:
    needs: [lint-helm, test-python]
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [webhook-receiver, flexibility-engine, settlement, dashboard]
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ env.REGISTRY_USER }}
          password: ${{ env.REGISTRY_PASSWORD }}
      - uses: docker/build-push-action@v5
        with:
          context: ./services/${{ matrix.service }}
          push: true
          tags: ${{ env.REGISTRY }}/${{ github.repository_owner }}/eco-vpp-${{ matrix.service }}:${{ env.IMAGE_TAG }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
      - uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{ env.REGISTRY }}/${{ github.repository_owner }}/eco-vpp-${{ matrix.service }}:${{ env.IMAGE_TAG }}
          format: 'sarif'
          output: 'trivy-results.sarif'
          exit-code: '1'
          severity: 'CRITICAL,HIGH'
      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: 'trivy-results.sarif'

  package-helm:
    needs: build-and-push
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: azure/setup-helm@v3
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ env.REGISTRY_USER }}
          password: ${{ env.REGISTRY_PASSWORD }}
      - run: |
          cd ${{ env.HELM_CHART_PATH }}
          helm package .
          echo ${{ secrets.GITHUB_TOKEN }} | helm registry login ${{ env.REGISTRY }} -u ${{ github.actor }} --password-stdin
          helm push eco-vpp-*.tgz oci://${{ env.REGISTRY }}/${{ github.repository_owner }}/charts

  deploy:
    needs: [build-and-push, package-helm]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: azure/setup-helm@v3
      - uses: azure/setup-kubectl@v3
      - run: |
          mkdir -p $HOME/.kube
          echo "${{ secrets.KUBECONFIG_PROD }}" | base64 --decode > $HOME/.kube/config
      - run: |
          helm upgrade --install eco-vpp ${{ env.HELM_CHART_PATH }} \
            --namespace ${{ env.K8S_NAMESPACE }} \
            --create-namespace \
            --set webhook.image=${{ env.REGISTRY }}/${{ github.repository_owner }}/eco-vpp-webhook-receiver:${{ env.IMAGE_TAG }} \
            --set flexibility.image=${{ env.REGISTRY }}/${{ github.repository_owner }}/eco-vpp-flexibility-engine:${{ env.IMAGE_TAG }} \
            --set settlement.image=${{ env.REGISTRY }}/${{ github.repository_owner }}/eco-vpp-settlement:${{ env.IMAGE_TAG }} \
            --set dashboard.image=${{ env.REGISTRY }}/${{ github.repository_owner }}/eco-vpp-dashboard:${{ env.IMAGE_TAG }} \
            --values ${{ env.HELM_CHART_PATH }}/values.production.yaml
EOF

# -------------------------------
# 2. Webhook Receiver Service
# -------------------------------
cat > "$PROJECT_DIR/services/webhook-receiver/Dockerfile" << 'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY webhook_receiver.py .
EXPOSE 8000
CMD ["uvicorn", "webhook_receiver:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

cat > "$PROJECT_DIR/services/webhook-receiver/requirements.txt" << 'EOF'
fastapi
uvicorn
psycopg2-binary
EOF

cat > "$PROJECT_DIR/services/webhook-receiver/webhook_receiver.py" << 'EOF'
import os
import psycopg2
from fastapi import FastAPI, Request

app = FastAPI()
DB_CONN = psycopg2.connect(
    dbname=os.getenv("DB_NAME", "eco_db"),
    user=os.getenv("DB_USER", "eco_user"),
    password=os.getenv("DB_PASSWORD", "eco_pass"),
    host=os.getenv("DB_HOST", "postgres")
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/v1/telemetry/ingest")
async def ingest_telemetry(request: Request):
    data = await request.json()
    did = data.get("did")
    power_kw = data.get("power")
    cur = DB_CONN.cursor()
    cur.execute("SELECT id FROM energy_assets WHERE did = %s", (did,))
    row = cur.fetchone()
    if not row:
        return {"error": "asset not found"}, 404
    asset_id = row[0]
    cur.execute(
        "INSERT INTO telemetry (asset_id, power_kw, consumption_kwh, production_kwh) VALUES (%s, %s, %s, %s)",
        (asset_id, power_kw, power_kw if power_kw > 0 else 0, -power_kw if power_kw < 0 else 0)
    )
    DB_CONN.commit()
    return {"status": "ok"}
EOF

# -------------------------------
# 3. Flexibility Engine
# -------------------------------
cat > "$PROJECT_DIR/services/flexibility-engine/Dockerfile" << 'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY flexibility_engine.py .
CMD ["python", "flexibility_engine.py"]
EOF

cat > "$PROJECT_DIR/services/flexibility-engine/requirements.txt" << 'EOF'
paho-mqtt
requests
EOF

cat > "$PROJECT_DIR/services/flexibility-engine/flexibility_engine.py" << 'EOF'
import os
import paho.mqtt.client as mqtt
import requests
import time

MQTT_HOST = os.getenv("MQTT_HOST", "mainflux")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
DSO_API = os.getenv("DSO_API", "http://dso-simulator/curtailment_signal")

client = mqtt.Client()
client.connect(MQTT_HOST, MQTT_PORT)

def get_grid_signal():
    try:
        resp = requests.get(DSO_API, timeout=5)
        return resp.json().get("curtailment", 0.0)
    except:
        return 0.0

def map_signal_to_load_limit(signal):
    return int((1 - signal) * 100)

while True:
    signal = get_grid_signal()
    limit = map_signal_to_load_limit(signal)
    client.publish("cmd/load_limit/did:ewc:ev_charger_01", str(limit))
    client.publish("cmd/load_limit/did:ewc:heat_pump_01", str(limit))
    time.sleep(60)
EOF

# -------------------------------
# 4. Settlement Service
# -------------------------------
cat > "$PROJECT_DIR/services/settlement/Dockerfile" << 'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY settlement.py .
CMD ["python", "settlement.py"]
EOF

cat > "$PROJECT_DIR/services/settlement/requirements.txt" << 'EOF'
web3
psycopg2-binary
EOF

cat > "$PROJECT_DIR/services/settlement/settlement.py" << 'EOF'
import os
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://eco_user:eco_pass@postgres:5432/eco_db")
EWC_RPC = os.getenv("EWC_RPC", "https://volta.energyweb.org/rpc")

def process_pending_shares():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT id, from_did, to_did, allocated_kwh FROM energy_shares WHERE blockchain_tx IS NULL")
    for share_id, from_did, to_did, kwh in cur.fetchall():
        wh = int(kwh * 1000)
        # Placeholder: replace with real contract call
        tx_hash = "0x" + os.urandom(32).hex()
        cur.execute("UPDATE energy_shares SET blockchain_tx = %s WHERE id = %s", (tx_hash, share_id))
        conn.commit()
        print(f"Settled {kwh} kWh from {from_did} to {to_did} (tx {tx_hash})")

if __name__ == "__main__":
    process_pending_shares()
EOF

# -------------------------------
# 5. Dashboard (React + Vite)
# -------------------------------
cat > "$PROJECT_DIR/dashboard/Dockerfile" << 'EOF'
FROM node:18 AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
EOF

cat > "$PROJECT_DIR/dashboard/package.json" << 'EOF'
{
  "name": "eco-vpp-dashboard",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.0.0",
    "vite": "^4.0.0"
  }
}
EOF

cat > "$PROJECT_DIR/dashboard/index.html" << 'EOF'
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ECO-VPP Dashboard</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
EOF

cat > "$PROJECT_DIR/dashboard/vite.config.js" << 'EOF'
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
});
EOF

cat > "$PROJECT_DIR/dashboard/src/main.jsx" << 'EOF'
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
EOF

cat > "$PROJECT_DIR/dashboard/src/App.jsx" << 'EOF'
import React, { useState, useEffect } from 'react';

function App() {
  const [shares, setShares] = useState([]);
  const [incentive, setIncentive] = useState(null);

  useEffect(() => {
    fetch('/api/shares/latest')
      .then(res => res.json())
      .then(setShares);

    const ws = new WebSocket('ws://' + window.location.host + '/ws');
    ws.onmessage = (e) => {
      setIncentive(JSON.parse(e.data));
    };
    return () => ws.close();
  }, []);

  return (
    <div style={{ fontFamily: 'sans-serif', padding: '2rem' }}>
      <h1>⚡ ECO-VPP Dashboard</h1>
      {incentive && (
        <div style={{ background: '#e0f7fa', padding: '1rem', borderRadius: '8px' }}>
          <h2>Flexibility Incentive</h2>
          <p>Current price: <strong>€{incentive.price}/kWh</strong></p>
          <p>Grid signal: {incentive.signal}</p>
        </div>
      )}
      <h2>Latest Energy Shares (24h)</h2>
      <ul>
        {shares.map(share => (
          <li key={share.time}>{share.asset} received {share.kwh} kWh at €{share.price}</li>
        ))}
      </ul>
    </div>
  );
}

export default App;
EOF

# -------------------------------
# 6. Helm Chart Files
# -------------------------------
cat > "$PROJECT_DIR/helm/eco-vpp/Chart.yaml" << 'EOF'
apiVersion: v2
name: eco-vpp
description: ECO-VPP Platform – Virtual Power Plant for energy communities
type: application
version: 0.1.0
appVersion: "1.0.0"
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/values.yaml" << 'EOF'
replicaCount: 1

postgres:
  enabled: true
  image: postgis/postgis:15-3.4
  persistence:
    enabled: true
    size: 10Gi
  auth:
    username: eco_user
    password: eco_pass
    database: eco_db

mainflux:
  enabled: true
  image: mainflux/mainflux:latest
  mqttPort: 1883

flexmeasures:
  enabled: true
  image: lfenergy/flexmeasures:latest
  servicePort: 5000

webhook:
  enabled: true
  image: your-registry/webhook-receiver:latest
  replicas: 1
  servicePort: 8000

flexibility:
  enabled: true
  image: your-registry/flexibility-engine:latest
  dsoApi: "http://dso-simulator/curtailment_signal"

settlement:
  enabled: true
  image: your-registry/settlement:latest

dashboard:
  enabled: true
  image: your-registry/dashboard:latest
  servicePort: 80

ingress:
  enabled: false
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/values.production.yaml" << 'EOF'
replicaCount: 2
postgres:
  persistence:
    size: 50Gi
ingress:
  enabled: true
  className: nginx
  hosts:
    - host: eco-vpp.customer.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - hosts:
        - eco-vpp.customer.com
      secretName: eco-vpp-tls
webhook:
  replicas: 2
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/_helpers.tpl" << 'EOF'
{{- define "eco-vpp.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "eco-vpp.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "eco-vpp.labels" -}}
helm.sh/chart: {{ include "eco-vpp.name" . }}-{{ .Chart.Version }}
{{ include "eco-vpp.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "eco-vpp.selectorLabels" -}}
app.kubernetes.io/name: {{ include "eco-vpp.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/deployment-webhook.yaml" << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "eco-vpp.fullname" . }}-webhook
  labels:
    {{- include "eco-vpp.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.webhook.replicas }}
  selector:
    matchLabels:
      {{- include "eco-vpp.selectorLabels" . | nindent 6 }}
      app: webhook
  template:
    metadata:
      labels:
        {{- include "eco-vpp.selectorLabels" . | nindent 8 }}
        app: webhook
    spec:
      containers:
        - name: webhook
          image: {{ .Values.webhook.image }}
          ports:
            - containerPort: 8000
          env:
            - name: DB_HOST
              value: {{ .Release.Name }}-postgres
            - name: DB_USER
              value: {{ .Values.postgres.auth.username }}
            - name: DB_PASSWORD
              value: {{ .Values.postgres.auth.password }}
            - name: DB_NAME
              value: {{ .Values.postgres.auth.database }}
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/service-webhook.yaml" << 'EOF'
apiVersion: v1
kind: Service
metadata:
  name: {{ include "eco-vpp.fullname" . }}-webhook
spec:
  selector:
    {{- include "eco-vpp.selectorLabels" . | nindent 4 }}
    app: webhook
  ports:
    - protocol: TCP
      port: 8000
      targetPort: 8000
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/deployment-flexibility-engine.yaml" << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "eco-vpp.fullname" . }}-flexibility
spec:
  replicas: 1
  selector:
    matchLabels:
      {{- include "eco-vpp.selectorLabels" . | nindent 6 }}
      app: flexibility
  template:
    metadata:
      labels:
        {{- include "eco-vpp.selectorLabels" . | nindent 8 }}
        app: flexibility
    spec:
      containers:
        - name: flexibility
          image: {{ .Values.flexibility.image }}
          env:
            - name: MQTT_HOST
              value: {{ .Release.Name }}-mainflux
            - name: DSO_API
              value: {{ .Values.flexibility.dsoApi }}
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/deployment-flexmeasures.yaml" << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "eco-vpp.fullname" . }}-flexmeasures
spec:
  replicas: 1
  selector:
    matchLabels:
      {{- include "eco-vpp.selectorLabels" . | nindent 6 }}
      app: flexmeasures
  template:
    metadata:
      labels:
        {{- include "eco-vpp.selectorLabels" . | nindent 8 }}
        app: flexmeasures
    spec:
      containers:
        - name: flexmeasures
          image: {{ .Values.flexmeasures.image }}
          ports:
            - containerPort: 5000
          env:
            - name: SQLALCHEMY_DATABASE_URI
              value: postgresql://{{ .Values.postgres.auth.username }}:{{ .Values.postgres.auth.password }}@{{ .Release.Name }}-postgres:5432/{{ .Values.postgres.auth.database }}
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/service-flexmeasures.yaml" << 'EOF'
apiVersion: v1
kind: Service
metadata:
  name: {{ include "eco-vpp.fullname" . }}-flexmeasures
spec:
  selector:
    {{- include "eco-vpp.selectorLabels" . | nindent 4 }}
    app: flexmeasures
  ports:
    - protocol: TCP
      port: 5000
      targetPort: 5000
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/deployment-mainflux.yaml" << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "eco-vpp.fullname" . }}-mainflux
spec:
  replicas: 1
  selector:
    matchLabels:
      {{- include "eco-vpp.selectorLabels" . | nindent 6 }}
      app: mainflux
  template:
    metadata:
      labels:
        {{- include "eco-vpp.selectorLabels" . | nindent 8 }}
        app: mainflux
    spec:
      containers:
        - name: mainflux
          image: {{ .Values.mainflux.image }}
          ports:
            - containerPort: 1883
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/service-mainflux.yaml" << 'EOF'
apiVersion: v1
kind: Service
metadata:
  name: {{ include "eco-vpp.fullname" . }}-mainflux
spec:
  selector:
    {{- include "eco-vpp.selectorLabels" . | nindent 4 }}
    app: mainflux
  ports:
    - protocol: TCP
      port: 1883
      targetPort: 1883
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/deployment-postgres.yaml" << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "eco-vpp.fullname" . }}-postgres
spec:
  replicas: 1
  selector:
    matchLabels:
      {{- include "eco-vpp.selectorLabels" . | nindent 6 }}
      app: postgres
  template:
    metadata:
      labels:
        {{- include "eco-vpp.selectorLabels" . | nindent 8 }}
        app: postgres
    spec:
      containers:
        - name: postgres
          image: {{ .Values.postgres.image }}
          ports:
            - containerPort: 5432
          env:
            - name: POSTGRES_USER
              value: {{ .Values.postgres.auth.username }}
            - name: POSTGRES_PASSWORD
              value: {{ .Values.postgres.auth.password }}
            - name: POSTGRES_DB
              value: {{ .Values.postgres.auth.database }}
          volumeMounts:
            - name: postgres-storage
              mountPath: /var/lib/postgresql/data
      volumes:
        - name: postgres-storage
          persistentVolumeClaim:
            claimName: {{ include "eco-vpp.fullname" . }}-postgres-pvc
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/service-postgres.yaml" << 'EOF'
apiVersion: v1
kind: Service
metadata:
  name: {{ include "eco-vpp.fullname" . }}-postgres
spec:
  selector:
    {{- include "eco-vpp.selectorLabels" . | nindent 4 }}
    app: postgres
  ports:
    - protocol: TCP
      port: 5432
      targetPort: 5432
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/deployment-settlement.yaml" << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "eco-vpp.fullname" . }}-settlement
spec:
  replicas: 1
  selector:
    matchLabels:
      {{- include "eco-vpp.selectorLabels" . | nindent 6 }}
      app: settlement
  template:
    metadata:
      labels:
        {{- include "eco-vpp.selectorLabels" . | nindent 8 }}
        app: settlement
    spec:
      containers:
        - name: settlement
          image: {{ .Values.settlement.image }}
          env:
            - name: DATABASE_URL
              value: postgresql://{{ .Values.postgres.auth.username }}:{{ .Values.postgres.auth.password }}@{{ .Release.Name }}-postgres:5432/{{ .Values.postgres.auth.database }}
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/deployment-dashboard.yaml" << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "eco-vpp.fullname" . }}-dashboard
spec:
  replicas: 1
  selector:
    matchLabels:
      {{- include "eco-vpp.selectorLabels" . | nindent 6 }}
      app: dashboard
  template:
    metadata:
      labels:
        {{- include "eco-vpp.selectorLabels" . | nindent 8 }}
        app: dashboard
    spec:
      containers:
        - name: dashboard
          image: {{ .Values.dashboard.image }}
          ports:
            - containerPort: 80
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/service-dashboard.yaml" << 'EOF'
apiVersion: v1
kind: Service
metadata:
  name: {{ include "eco-vpp.fullname" . }}-dashboard
spec:
  selector:
    {{- include "eco-vpp.selectorLabels" . | nindent 4 }}
    app: dashboard
  ports:
    - protocol: TCP
      port: 80
      targetPort: 80
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/configmap-esp32-code.yaml" << 'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "eco-vpp.fullname" . }}-esp32-code
data:
  main.py: |
    import network, time, ujson
    from umqtt.simple import MQTTClient
    
    WIFI_SSID = os.getenv("WIFI_SSID", "your-ssid")
    WIFI_PASS = os.getenv("WIFI_PASS", "your-pass")
    MQTT_BROKER = os.getenv("MQTT_BROKER", "mainflux.eco-vpp.svc.cluster.local")
    DEVICE_DID = os.getenv("DEVICE_DID", "did:ewc:test")
    
    def connect_wifi():
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.connect(WIFI_SSID, WIFI_PASS)
        while not wlan.isconnected():
            time.sleep(1)
        print("WiFi connected")
    
    def connect_mqtt():
        client = MQTTClient(DEVICE_DID, MQTT_BROKER, port=1883)
        client.connect()
        return client
    
    def get_meter_reading():
        # Placeholder: replace with actual OCR reading
        return 1.23
    
    connect_wifi()
    client = connect_mqtt()
    while True:
        value = get_meter_reading()
        payload = ujson.dumps({"did": DEVICE_DID, "power": value, "unit": "kW"})
        client.publish("power/reading", payload)
        time.sleep(10)
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/cronjob-energy-sharing.yaml" << 'EOF'
apiVersion: batch/v1
kind: CronJob
metadata:
  name: {{ include "eco-vpp.fullname" . }}-energy-sharing
spec:
  schedule: "*/15 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: sharing
              image: python:3.11-slim
              command:
                - /bin/sh
                - -c
                - |
                  pip install psycopg2-binary pandas && python -c "
                  import psycopg2, pandas as pd, os
                  conn = psycopg2.connect(f'postgresql://{os.environ[\"DB_USER\"]}:{os.environ[\"DB_PASS\"]}@{os.environ[\"DB_HOST\"]}:5432/{os.environ[\"DB_NAME\"]}')
                  # Simplified sharing logic (RED II)
                  df = pd.read_sql('SELECT asset_id, consumption_kwh, production_kwh FROM telemetry WHERE timestamp > NOW() - INTERVAL \"15 minutes\"', conn)
                  total_prod = df['production_kwh'].sum()
                  total_cons = df['consumption_kwh'].sum()
                  if total_prod > 0:
                      for _, row in df.iterrows():
                          if row['consumption_kwh'] > 0:
                              share = (row['consumption_kwh'] / total_cons) * total_prod
                              cur = conn.cursor()
                              cur.execute('INSERT INTO energy_shares (asset_id, allocated_kwh) VALUES (%s, %s)', (row['asset_id'], share))
                              conn.commit()
                  print('Sharing calculation executed')
                  "
              env:
                - name: DB_HOST
                  value: {{ .Release.Name }}-postgres
                - name: DB_USER
                  value: {{ .Values.postgres.auth.username }}
                - name: DB_PASS
                  value: {{ .Values.postgres.auth.password }}
                - name: DB_NAME
                  value: {{ .Values.postgres.auth.database }}
          restartPolicy: OnFailure
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/cronjob-forecast.yaml" << 'EOF'
apiVersion: batch/v1
kind: CronJob
metadata:
  name: {{ include "eco-vpp.fullname" . }}-forecast
spec:
  schedule: "0 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: forecast
              image: python:3.11-slim
              command:
                - /bin/sh
                - -c
                - |
                  pip install requests && python -c "
                  import requests, json
                  # Fetch solar radiation forecast from Open-Meteo
                  lat, lon = 45.75, 4.85
                  url = f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=shortwave_radiation'
                  resp = requests.get(url).json()
                  # Post to FlexMeasures (simplified)
                  print('Forecast fetched')
                  "
          restartPolicy: OnFailure
EOF

cat > "$PROJECT_DIR/helm/eco-vpp/templates/ingress.yaml" << 'EOF'
{{- if .Values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "eco-vpp.fullname" . }}-ingress
  annotations:
    kubernetes.io/ingress.class: {{ .Values.ingress.className }}
spec:
  {{- if .Values.ingress.tls }}
  tls:
    {{- range .Values.ingress.tls }}
    - hosts:
        {{- range .hosts }}
        - {{ . | quote }}
        {{- end }}
      secretName: {{ .secretName }}
    {{- end }}
  {{- end }}
  rules:
    {{- range .Values.ingress.hosts }}
    - host: {{ .host | quote }}
      http:
        paths:
          {{- range .paths }}
          - path: {{ .path }}
            pathType: {{ .pathType }}
            backend:
              service:
                name: {{ include "eco-vpp.fullname" $ }}-dashboard
                port:
                  number: {{ $.Values.dashboard.servicePort }}
          {{- end }}
    {{- end }}
{{- end }}
EOF

# -------------------------------
# 7. Docker Compose & other root files
# -------------------------------
cat > "$PROJECT_DIR/docker-compose.yml" << 'EOF'
version: '3.8'

services:
  mainflux:
    image: mainflux/mainflux:latest
    container_name: mainflux
    ports:
      - "1883:1883"
    networks:
      - eco-vpp-net

  flexmeasures:
    image: lfenergy/flexmeasures:latest
    container_name: flexmeasures
    ports:
      - "5000:5000"
    environment:
      SQLALCHEMY_DATABASE_URI: postgresql://eco_user:eco_pass@postgres:5432/eco_db
    depends_on:
      - postgres
    networks:
      - eco-vpp-net

  postgres:
    image: postgis/postgis:15-3.4
    container_name: postgres
    environment:
      POSTGRES_USER: eco_user
      POSTGRES_PASSWORD: eco_pass
      POSTGRES_DB: eco_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - eco-vpp-net

networks:
  eco-vpp-net:
    driver: bridge

volumes:
  postgres_data:
EOF

cat > "$PROJECT_DIR/.gitignore" << 'EOF'
node_modules/
__pycache__/
*.pyc
.env
*.log
dist/
.vscode/
EOF

cat > "$PROJECT_DIR/README.md" << 'EOF'
# ECO-VPP Platform

**Energy Community Orchestrated – Virtual Power Plant (ECO-VPP)**

This repository contains a white-label, full-stack orchestration platform for energy communities. It enables multi-unit residential buildings (condominiums) to operate as a single Virtual Power Plant, optimising Collective Self-Consumption and participating in Local Flexibility Markets.

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Kubernetes cluster (for production)
- Helm (v3.8+)
- Optional: ESP32‑S3 + camera for meter digitisation

### Local Development
```bash
docker-compose up -d