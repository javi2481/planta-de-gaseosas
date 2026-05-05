# Mapa de Archivos — Planta de Gaseosas

Listado completo de archivos del proyecto. Para cada archivo: qué hace, de qué depende, y quién lo usa.

---

## Capa: Infraestructura (Docker Compose)

### `docker-compose.yml`
- **Lenguaje:** YAML
- **Propósito:** Orquestación de los 7 servicios del stack. Define imágenes, puertos, volúmenes, redes, healthchecks y dependencias. Es el punto de entrada principal — un solo `docker-compose up -d` levanta todo.
- **Depende de:** `.env` (variables de entorno), `mosquitto/config/mosquitto.conf` (montado como volumen), `telegraf/telegraf.conf` (montado), `grafana/provisioning/` (montado), `grafana/dashboards/` (montado), `simulator/Dockerfile` (build context).
- **Usado por:** Docker Engine. No hay otro archivo que lo importe.

### `.env.example`
- **Lenguaje:** Shell env vars
- **Propósito:** Template de variables de entorno. Contiene todas las variables que `docker-compose.yml` y los configs referencian. El usuario debe copiarlo a `.env` antes de arrancar.
- **Depende de:** Nada.
- **Usado por:** El usuario (como referencia) y por `docker-compose.yml` (indirectamente, cuando se copia a `.env`).

### `.env`
- **Lenguaje:** Shell env vars
- **Propósito:** Variables de entorno reales con valores activos. **NO commitear.**
- **Depende de:** `.env.example` (se crea copiándolo).
- **Usado por:** `docker-compose.yml` (automáticamente, Docker Compose lo lee).

### `.gitignore`
- **Lenguaje:** Git ignore patterns
- **Propósito:** Excluir `.env` y otros archivos sensibles del versionado.
- **Depende de:** Nada.
- **Usado por:** Git.

### ` .gga `
- **Lenguaje:** Shell (formato propio del agente IA Gentleman)
- **Proposito:** Configuracion del agente de revision de codigo. Define que tipos de archivo revisar (`FILE_PATTERNS="*.py"`) para que el agente solo analice codigo Python y no archivos de config, JSON ni Markdown.
- **Depende de:** Nada.
- **Usado por:** El agente Gentleman cuando hace revisiones de codigo del proyecto.

---

## Capa: Simulación (Sensor Simulator)

### `simulator/sensores.py`
- **Lenguaje:** Python 3
- **Propósito:** Simulador de 11 sensores industriales. Publica MQTT cada segundo con valores baseline + ruido + spikes periódicos. Usa UNS (Unified Naming System) para organizar topics por área de planta. Es el "generador de datos" de todo el stack.
- **Depende de:** `simulator/requirements.txt` (paho-mqtt), Mosquitto (runtime, via MQTT), `AREA_MAP` interno (mapeo sensor→área).
- **Usado por:** Telegraf (consume los mensajes MQTT). El Dockerfile lo copia al container.

### `simulator/requirements.txt`
- **Lenguaje:** pip requirements
- **Propósito:** Dependencias Python del simulador. Solo `paho-mqtt==2.1.0`.
- **Depende de:** Nada.
- **Usado por:** `simulator/Dockerfile` (lo instala con pip).

### `simulator/Dockerfile`
- **Lenguaje:** Dockerfile
- **Propósito:** Construir la imagen del simulador basada en `python:3.11-slim`. Instala dependencias y copia el código.
- **Depende de:** `simulator/requirements.txt`, `simulator/sensores.py`.
- **Usado por:** `docker-compose.yml` (build context: `./simulator`).

---

## Capa: Broker MQTT

### `mosquitto/config/mosquitto.conf`
- **Lenguaje:** Mosquitto config
- **Propósito:** Configuración del broker MQTT. Define listener en puerto 1883, permite anonymous access, habilita persistencia y logging a stdout.
- **Depende de:** Nada.
- **Usado por:** `docker-compose.yml` (montado como volumen ro en el servicio `mosquitto`).

---

## Capa: Ingestión (Telegraf)

### `telegraf/telegraf.conf`
- **Lenguaje:** TOML
- **Propósito:** Configuración del agente Telegraf. Tres secciones:
  1. **Input** (`mqtt_consumer`): suscribe a `planta1/+/sensor/+`, parsea topic→measurement, data_type=float.
  2. **Processor** (`regex`): extrae tag `area` del topic para evitar colisiones de measurements.
  3. **Output** (`influxdb_v2`): escribe en InfluxDB 3 Core via API v2, bucket `sensores`, org vacía.
- **Depende de:** Mosquitto (runtime, lee de MQTT), InfluxDB (runtime, escribe via HTTP).
- **Usado por:** `docker-compose.yml` (montado como volumen ro en el servicio `telegraf`).

---

## Capa: Almacenamiento (InfluxDB + MinIO)

No hay archivos de configuración de InfluxDB en el repo — toda la config va en `docker-compose.yml` como flags y environment variables.

No hay archivos de configuración de MinIO en el repo — la config va en `docker-compose.yml` y el bucket se crea via `createbuckets`.

---

## Capa: Visualización (Grafana)

### `grafana/provisioning/datasources/influxdb.yaml`
- **Lenguaje:** YAML
- **Propósito:** Define el datasource InfluxDB3 en Grafana. Tipo `influxdb`, access `proxy`, URL `http://influxdb:8181`, base de datos `sensores`, httpMode `GET`.
- **Depende de:** InfluxDB (debe estar corriendo en 8181).
- **Usado por:** `docker-compose.yml` (montado en `/etc/grafana/provisioning/datasources/`). Grafana lo lee al iniciar.

### `grafana/provisioning/dashboards/default.yaml`
- **Lenguaje:** YAML
- **Propósito:** Dashboard provider de Grafana. Le dice a Grafana dónde buscar archivos JSON de dashboards (`/var/lib/grafana/dashboards`), en qué carpeta (`Planta de Gaseosas`), y con qué frecuencia actualizar (30s).
- **Depende de:** `grafana/dashboards/linea-envasado.json` (los dashboards que provisiona).
- **Usado por:** `docker-compose.yml` (montado en `/etc/grafana/provisioning/dashboards/`). Grafana lo lee al iniciar.

### `grafana/provisioning/alerting/contactpoints.yaml`
- **Lenguaje:** YAML
- **Propósito:** Define el punto de contacto para alertas. En desarrollo usa un webhook dummy (`http://localhost:9999/noop`) — las alertas se ven en la UI de Grafana pero no notifican a ningún canal externo.
- **Depende de:** Nada (el webhook apunta a un endpoint inexistente intencionalmente).
- **Usado por:** `docker-compose.yml` (montado en `/etc/grafana/provisioning/alerting/`). Grafana lo lee al iniciar.

### `grafana/provisioning/alerting/rules.yaml`
- **Lenguaje:** YAML
- **Propósito:** 2 reglas de alerta de Grafana:
  1. **Temperatura pasteurizador alta:** `mean("value") FROM temperatura_pasteurizador > 85`, severity: critical.
  2. **Vibracion llenadora alta:** `mean("value") FROM vibracion_llenadora > 8`, severity: warning. [TODO] El spec original dice que ambas deberían ser `critical`.
- **Depende de:** `grafana/provisioning/datasources/influxdb.yaml` (referencia `datasourceUid: InfluxDB3`).
- **Usado por:** `docker-compose.yml` (montado en `/etc/grafana/provisioning/alerting/`). Grafana lo lee al iniciar.

### `grafana/dashboards/linea-envasado.json`
- **Lenguaje:** JSON
- **Propósito:** Dashboard de Grafana con 11 paneles: 8 time-series para sensores gauge, 1 time-series para conteo de botellas (con `non_negative_derivative`), 1 stat panel para OEE, y 1 panel extra. [TODO] verificar distribución exacta de los 11 paneles. Refresh 5s, schemaVersion 39.
- **Depende de:** Datasource `InfluxDB3` (referenciado en cada panel).
- **Usado por:** `grafana/provisioning/dashboards/default.yaml` (lo carga automáticamente).

---

## Capa: Documentación

### `README.md`
- **Lenguaje:** Markdown
- **Propósito:** Guía rápida para levantar el stack. Incluye arquitectura simplificada, tabla de servicios, URLs de acceso, comandos de verificación, y nota de seguridad.
- **Depende de:** Nada (documentación).
- **Usado por:** Usuarios del proyecto.

### `docs/ARCHITECTURE.md`
- **Lenguaje:** Markdown (con diagramas Mermaid)
- **Propósito:** Documentación técnica completa de la arquitectura: diagramas de flujo y dependencias, tabla de servicios, justificación de cada elección tecnológica, y decisiones de arquitectura.
- **Depende de:** Nada (documentación).
- **Usado por:** Desarrolladores que necesitan entender el stack en profundidad.

### `docs/DATA-FLOW.md`
- **Lenguaje:** Markdown
- **Propósito:** Recorrido paso a paso de un dato desde el simulador hasta Grafana. Incluye ejemplo concreto con `temperatura_camara_fria` y caso de spike con `temperatura_pasteurizador`.
- **Depende de:** Nada (documentación).
- **Usado por:** Desarrolladores que necesitan entender cómo viaja la información.

### `docs/FILE-MAP.md`
- **Lenguaje:** Markdown
- **Propósito:** Este archivo. Mapa completo de todos los archivos del proyecto organizados por capa.
- **Depende de:** Nada (documentación).
- **Usado por:** Desarrolladores que necesitan navegar el proyecto.

### `docs/COMPONENTS.md`
- **Lenguaje:** Markdown
- **Propósito:** Documentación detallada de cada componente del stack: qué hace, cómo se configura, cómo se comunica, qué pasa si falla, cómo debuggearlo.
- **Depende de:** Nada (documentación).
- **Usado por:** Desarrolladores y operadores.

### `docs/GLOSSARY.md`
- **Lenguaje:** Markdown
- **Propósito:** Glosario de términos técnicos usados en el proyecto. Cada término tiene definición y ejemplo concreto del stack.
- **Depende de:** Nada (documentación).
- **Usado por:** Cualquiera que necesite entender la terminología.

### `docs/prd fabrica de gaseosas.md`
- **Lenguaje:** Markdown
- **Propósito:** [TODO] Documento PRD (Product Requirements Document) original de la fábrica de gaseosas. Contiene los requisitos de negocio que dieron origen al stack.
- **Depende de:** Nada (documento de entrada).
- **Usado por:** Referencia para entender el contexto de negocio.

---

## Capa: OpenSpec (SDD Artifacts)

### `openspec/specs/docker-compose-stack/spec.md`
- **Lenguaje:** Markdown
- **Propósito:** Spec maestra sincronizada del change `docker-compose-stack`. Es la fuente de verdad de los requisitos funcionales y no funcionales del stack. Contiene 4 FR + 4 NFR + 11 criterios de aceptación.
- **Depende de:** N/A (se genera desde el archive del change).
- **Usado por:** Sub-agentes de SDD para futuras verificaciones.

### `openspec/changes/archive/2026-05-05-docker-compose-stack/`
- **Lenguaje:** Varios (Markdown, YAML)
- **Propósito:** Directorio con todos los artefactos del change archivado: `proposal.md`, `spec.md`, `design.md`, `tasks.md`, `verify-report.md`, `explore.md`, `state.yaml`.
- **Depende de:** N/A.
- **Usado por:** Referencia histórica. No afecta al runtime.

---

## Resumen Visual de Dependencias entre Archivos

```
docker-compose.yml
  ├── .env (runtime, desde .env.example)
  ├── mosquitto/config/mosquitto.conf (volumen)
  ├── telegraf/telegraf.conf (volumen)
  │     └── Mosquitto (input) → InfluxDB (output)
  ├── grafana/provisioning/datasources/influxdb.yaml (volumen)
  │     └── Referencia a datasource InfluxDB3
  ├── grafana/provisioning/dashboards/default.yaml (volumen)
  │     └── grafana/dashboards/linea-envasado.json (volumen)
  ├── grafana/provisioning/alerting/contactpoints.yaml (volumen)
  ├── grafana/provisioning/alerting/rules.yaml (volumen)
  │     └── Referencia a datasource InfluxDB3
  └── simulator/ (build context)
        ├── Dockerfile
        │     ├── requirements.txt
        │     └── sensores.py
        └── sensores.py → publica a Mosquitto
```
