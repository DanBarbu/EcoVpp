{{/* Common labels */}}
{{- define "eco-vpp.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "eco-vpp.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "eco-vpp.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "eco-vpp.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "eco-vpp.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "eco-vpp.image" -}}
{{- printf "%s/%s/%s:%s" .Values.image.registry .Values.image.repository .component (default .Values.image.tag .tag) -}}
{{- end -}}

{{- define "eco-vpp.dbUrl" -}}
postgresql://{{ .Values.postgres.user }}:{{ .Values.postgres.password }}@{{ include "eco-vpp.fullname" . }}-postgres:5432/{{ .Values.postgres.database }}
{{- end -}}
