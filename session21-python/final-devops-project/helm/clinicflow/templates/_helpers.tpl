{{/* Chart name */}}
{{- define "clinicflow.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Fully qualified app name: release name, or release-chart if they differ */}}
{{- define "clinicflow.fullname" -}}
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

{{- define "clinicflow.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Common labels */}}
{{- define "clinicflow.labels" -}}
helm.sh/chart: {{ include "clinicflow.chart" . }}
app.kubernetes.io/name: {{ include "clinicflow.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: clinicflow
{{- end }}

{{/* Selector labels; call with (dict "ctx" . "component" "backend") */}}
{{- define "clinicflow.selectorLabels" -}}
app.kubernetes.io/name: {{ include "clinicflow.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{- define "clinicflow.backendImage" -}}
{{ .Values.backend.image.repository }}:{{ .Values.backend.image.tag | default .Chart.AppVersion }}
{{- end }}
{{- define "clinicflow.frontendImage" -}}
{{ .Values.frontend.image.repository }}:{{ .Values.frontend.image.tag | default .Chart.AppVersion }}
{{- end }}

{{- define "clinicflow.postgresName" -}}
{{ include "clinicflow.fullname" . }}-postgres
{{- end }}

{{- define "clinicflow.dbHost" -}}
{{- if .Values.postgres.enabled }}{{ include "clinicflow.postgresName" . }}{{ else }}{{ required "postgres.host is required when postgres.enabled=false" .Values.postgres.host }}{{ end }}
{{- end }}

{{- define "clinicflow.secretName" -}}
{{- if .Values.postgres.auth.existingSecret }}{{ .Values.postgres.auth.existingSecret }}{{ else }}{{ include "clinicflow.fullname" . }}-db{{ end }}
{{- end }}
