# Tasks: fix-alertas-y-robustez

## Phase 1: Fixes

- [x] 1.1 `simulator/sensores.py` L50: cambiar `(t % 300) < 2` por `(t % 300) < 45`
- [x] 1.2 `grafana/provisioning/alerting/rules.yaml` L66: verificar que `severity: critical` está presente (ya lo tiene, sin cambios)
- [x] 1.3 `docker-compose.yml` L72: cambiar `restart: "no"` por `restart: on-failure` en servicio createbuckets

## Phase 2: Verification

- [x] 2.1 Inspeccionar `sensores.py` para confirmar que la ventana de spike es 45s c/5min
- [x] 2.2 Inspeccionar `docker-compose.yml` para confirmar `restart: on-failure` en createbuckets
- [x] 2.3 Confirmar visualmente en `rules.yaml` que la alerta vibracion_llenadora tiene `severity: critical`

## Phase 3: Deploy

- [ ] 3.1 Ejecutar `docker compose up -d --force-recreate simulator createbuckets` para aplicar cambios
