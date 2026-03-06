{{- define "observatory-backend.otelEnv" -}}
{{- if .Values.otel.enabled -}}
- name: HOST_IP
  valueFrom:
    fieldRef:
      fieldPath: status.hostIP
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: "http://$(HOST_IP):4318"
- name: OTEL_EXPORTER_OTLP_PROTOCOL
  value: "http/protobuf"
- name: OTEL_RESOURCE_ATTRIBUTES
  value: "deployment.environment={{ required "otel.env is required" .Values.otel.env }},service.version={{ .Values.image.tag }}"
{{- end }}
{{- end }}
