# Componentes — Planta de Gaseosas

Documentación detallada de cada componente del stack. Para cada uno: qué hace **en este proyecto**, cómo se configura, cómo se comunica, qué pasa si falla, y cómo debuggearlo.

---

## 1. Mosquitto (Broker MQTT)

### Qué hace en este proyecto

Es el **sistema nervioso central** del stack. Recibe los mensajes de los 11 sensores del simulador y los distribuye a Telegraf. Sin Mosquitto, los datos no viajan a ningún lado.

No almacena mensajes persistentes — funciona como un tubo: lo que entra, sale inmediatamente a los suscriptores.

### Archivos de configuración

| Archivo | Rol |
|---------|-----|
| `mosquitto/config/mosquitto.conf` | Configuración completa: listener 1883, anonymous, persistencia, logging |
| `docker-compose.yml` | Servicio `mosquitto`: imagen, puertos, volumes, healthcheck |

### Cómo se comunica

| Con quién | Protocolo | Dirección | Qué intercambia |
|-----------|-----------|-----------|-----------------|
| Simulador | MQTT (TCP 1883) | Recibe | PUBLISH de 11 sensores, 1 msg/s c/u |
| Telegraf | MQTT (TCP 1883) | Envía | Mensajes MQTT distribuidos a suscriptores |

**Flujo:** El simulador hace `PUBLISH` a un topic → Mosquitto lo recibe → Telegraf (suscrito a `planta1/+/sensor/+`) lo recibe como callback.

### Qué pasa si falla

| Escenario | Efecto | Recuperación |
|-----------|--------|-------------|
| Mosquitto se cae | El simulador pierde conexión. Telegraf pierde fuente de datos. **No se pierden datos en InfluxDB** (lo que ya está escrito sigue ahí). | Docker Engine reinicia el contenedor automáticamente (`restart: unless-stopped`). El simulador reconecta solo (paho-mqtt tiene auto-reconnect). |
| Mosquitto tarda en arrancar | Telegraf no arranca (depende de `mosquitto: condition: service_healthy`). Simulator no arranca. | El healthcheck de Mosquitto (`mosquitto_sub -t '$SYS/broker/uptime' -W 3`) debe pasar primero. Timeout maximo: ~70 segundos (10s start_period + 5s interval x 12 retries). |
| Puerto 1883 en uso | Mosquitto no arranca. Todo el stack falla. | Liberar el puerto: `lsof -i :1883` o `netstat -ano | findstr 1883`. |

### Cómo debuggearlo

```bash
# Ver logs en tiempo real
docker-compose logs -f mosquitto

# Verificar que el broker responde
docker-compose exec mosquitto mosquitto_sub -h localhost -t 'test' -W 3

# Suscribirse manualmente a todos los sensores (para ver datos en vivo)
docker-compose exec mosquitto mosquitto_sub -h localhost -t 'planta1/+/sensor/#' -v

# Verificar que está healthy
docker-compose ps mosquitto
# Debería mostrar "healthy" en la columna STATE

# Reiniciar forzadamente
docker-compose restart mosquitto

# Ver configuración activa
docker-compose exec mosquitto cat /mosquitto/config/mosquitto.conf
```

**Señales de que algo anda mal:**
- Logs con `Error: Address already in use` → puerto ocupado.
- Logs con `not authorised` → falta `allow_anonymous true` en mosquitto.conf.
- Healthcheck falla → Mosquitto está corriendo pero no acepta subscriptions.

---

## 2. Simulador Python

### Qué hace en este proyecto

Es la **fuente de datos**. Genera lecturas de 11 sensores industriales ficticios y las publica por MQTT. Sin él, el stack está vacío — Grafana no muestra nada.

Los sensores simulan una línea de envasado real: temperatura del pasteurizador, vibración de la llenadora, conteo de botellas, etc.

**Importante:** No es un sensor real. Es un programa que genera valores con ruido gaussiano alrededor de un baseline, con spikes artificiales cada 5 minutos para probar las alertas.

### Archivos de configuración

| Archivo | Rol |
|---------|-----|
| `simulator/sensores.py` | Código principal: defines sensores, loop de publicación, lógica de spikes |
| `simulator/Dockerfile` | Build de la imagen Python |
| `simulator/requirements.txt` | Dependencia: `paho-mqtt==2.1.0` |
| `docker-compose.yml` | Servicio `simulator`: env vars, build context, healthcheck |

### Cómo se comunica

| Con quién | Protocolo | Dirección | Qué intercambia |
|-----------|-----------|-----------|-----------------|
| Mosquitto | MQTT (TCP 1883) | Envía | 11 mensajes/seg, topics UNS, payload float ASCII |

No recibe datos de nadie. Es un productor puro.

### Qué pasa si falla

| Escenario | Efecto | Recuperación |
|-----------|--------|-------------|
| Simulador se cae | No llegan datos nuevos a Mosquitto → Telegraf no recibe nada → Grafana muestra datos viejos hasta que expiren. InfluxDB sigue funcionando. | Docker Engine reinicia (`restart: unless-stopped`). |
| No puede conectar a Mosquitto | paho-mqtt intenta reconectar indefinidamente. No crashea. | Cuando Mosquitto vuelve, se reconecta automáticamente. |
| Bug en sensores.py | El proceso Python termina con excepción. Docker reinicia el contenedor. | Revisar logs para ver el traceback. |

### Cómo debuggearlo

```bash
# Ver logs en tiempo real
docker-compose logs -f simulator

# Ver qué sensores está publicando
docker-compose logs simulator | tail -20
# [TODO] El simulador no loggea al stdout actualmente — solo publica MQTT.
# Para debuggear, agregar print() al loop o usar mosquitto_sub.

# Verificar que el proceso corre dentro del container
docker-compose exec simulator pgrep -f sensores.py

# Ejecutar localmente (sin Docker) para debuggear rápido
pip install paho-mqtt==2.1.0
MQTT_BROKER=localhost python simulator/sensores.py

# Suscribirse desde afuera para ver los datos
mosquitto_sub -h localhost -t 'planta1/+/sensor/#' -v
```

**Señales de que algo anda mal:**
- El container se reinicia constantemente → `docker-compose logs simulator` muestra el traceback.
- No se ven datos en Grafana pero Mosquitto está OK → probablemente el simulador no está publicando.

---

## 3. Telegraf

### Qué hace en este proyecto

Es el **traductor y transportador**. Lee mensajes MQTT, los transforma (extrae tags, parsea el measurement name), y los escribe en InfluxDB. Sin Telegraf, los datos se quedan en Mosquitto y nunca llegan a la base de datos.

Es un componente "tonto" pero esencial: no toma decisiones, solo mueve datos de A a B con transformaciones mínimas.

### Archivos de configuración

| Archivo | Rol |
|---------|-----|
| `telegraf/telegraf.conf` | Configuración completa: input MQTT, processor regex, output InfluxDB |
| `docker-compose.yml` | Servicio `telegraf`: volumen, depends_on, healthcheck |

### Cómo se comunica

| Con quién | Protocolo | Dirección | Qué intercambia |
|-----------|-----------|-----------|-----------------|
| Mosquitto | MQTT (TCP 1883) | Recibe | Mensajes MQTT de sensores |
| InfluxDB | HTTP (TCP 8181) | Envía | POST /api/v2/write con line protocol, gzip, batch de ~11 métricas/s |

### Qué pasa si falla

| Escenario | Efecto | Recuperación |
|-----------|--------|-------------|
| Telegraf se cae | Los mensajes MQTT del simulador se pierden (Mosquitto no los persiste). InfluxDB deja de recibir datos nuevos. | Docker reinicia automáticamente. |
| No puede conectar a Mosquitto | Logs con errores de conexión. No recibe datos. | Reconexión automática cuando Mosquitto vuelve. |
| No puede conectar a InfluxDB | Logs con errores HTTP. Los mensajes se buferan internamente hasta `metric_buffer_limit = 10000`. Si se llena, descarta los más viejos. | Reconexión automática. Datos en buffer se pierden si supera el límite. |
| `organization` no vacío | InfluxDB 3 Core responde HTTP 400. **Todos los writes fallan silenciosamente.** | Fix: `organization = ""` en telegraf.conf. Este es el error más común. |

### Cómo debuggearlo

```bash
# Ver logs en tiempo real
docker-compose logs -f telegraf

# Buscar writes exitosos (batch confirmations)
docker-compose logs telegraf | grep -i "wrote"
# [TODO] Telegraf en modo quiet no loggea writes exitosos.
# Para ver actividad, cambiar quiet = false en telegraf.conf y reiniciar.

# Buscar errores
docker-compose logs telegraf | grep -i "error"

# Verificar proceso dentro del container
docker-compose exec telegraf pgrep telegraf

# Ver la config activa
docker-compose exec telegraf cat /etc/telegraf/telegraf.conf

# Modo debug (temporal)
# Cambiar en telegraf.conf: debug = true, quiet = false
# Luego: docker-compose restart telegraf
```

**Señales de que algo anda mal:**
- `400 Bad Request` → el `organization` no está vacío.
- `connection refused` → Mosquitto o InfluxDB no están corriendo.
- Silencio total en logs → Telegraf puede estar healthy pero no recibiendo mensajes (verificar simulador y Mosquitto primero).

---

## 4. InfluxDB 3 Core

### Qué hace en este proyecto

Es la **base de datos time-series**. Recibe los datos de Telegraf, los almacena, y los expone para consulta via InfluxQL. Es el corazón del almacenamiento.

A diferencia de bases de datos tradicionales, InfluxDB 3 Core no escribe en disco local — serializa todo a **Parquet files** y los guarda en MinIO (S3-compatible). Esto significa que el almacenamiento es horizontalmente escalable y no depende del disco del container.

### Archivos de configuración

| Archivo | Rol |
|---------|-----|
| `docker-compose.yml` | Servicio `influxdb`: flags de comando, env vars, ports, volumes, depends_on |

**No hay archivo de configuración separado.** Toda la config va como flags de CLI y variables de entorno en `docker-compose.yml`.

### Cómo se comunica

| Con quién | Protocolo | Dirección | Qué intercambia |
|-----------|-----------|-----------|-----------------|
| Telegraf | HTTP (TCP 8181) | Recibe | POST /api/v2/write con line protocol |
| Grafana | HTTP (TCP 8181) | Recibe | GET /query con InfluxQL |
| MinIO | HTTP S3 (TCP 9000) | Envía | PUT de Parquet files al bucket `influxdb3` |

### Qué pasa si falla

| Escenario | Efecto | Recuperación |
|-----------|--------|-------------|
| InfluxDB se cae | Telegraf no puede escribir (buffer interno). Grafana no puede consultar (paneles vacíos). | Docker reinicia. Datos ya escritos en MinIO se preservan. |
| MinIO no está disponible | InfluxDB no puede escribir Parquet. Falla al iniciar o al escribir. | InfluxDB depende de `minio: condition: service_healthy`. No arranca sin MinIO. |
| `--without-auth` habilitado | Cualquiera que llegue al puerto 8181 puede leer/escribir. | Intencional para desarrollo. Para producción, quitar el flag y configurar tokens. |
| Bucket `influxdb3` no existe | InfluxDB falla al iniciar. | `createbuckets` debe correr exitosamente antes de InfluxDB. Si falla, `docker-compose down -v && docker-compose up -d`. |

### Cómo debuggearlo

```bash
# Ver logs en tiempo real
docker-compose logs -f influxdb

# Healthcheck manual
docker-compose exec influxdb curl -fsS http://localhost:8181/health

# Consultar datos directamente via InfluxQL
curl "http://localhost:8181/query?db=sensores&q=SELECT+last(value)+FROM+temperatura_pasteurizador"

# Ver todos los measurements
curl "http://localhost:8181/query?db=sensores&q=SHOW+MEASUREMENTS"

# Ver datos recientes de un sensor
curl "http://localhost:8181/query?db=sensores&q=SELECT+*+FROM+temperatura_camara_fria+WHERE+time+%3E+now()+-+5m"

# Ver flags de inicio
docker-compose exec influxdb ps aux

# Ver logs de escritura a MinIO
docker-compose logs influxdb | grep -i "s3\|parquet\|object"
```

**Señales de que algo anda mal:**
- `connection refused` en el healthcheck → InfluxDB no arrancó (probablemente bucket no existe o MinIO no está).
- `400 Bad Request` a Telegraf → ver telegraf.conf `organization = ""`.
- Sin datos en Grafana pero Telegraf OK → verificar con curl directo a InfluxDB.

---

## 5. MinIO

### Qué hace en este proyecto

Es el **disco duro de InfluxDB**. Almacena los Parquet files que InfluxDB genera. Sin MinIO, InfluxDB no tiene dónde guardar los datos.

Pensalo como un "AWS S3 local" — expone la misma API S3 pero corre en tu máquina.

### Archivos de configuración

| Archivo | Rol |
|---------|-----|
| `docker-compose.yml` | Servicio `minio`: imagen, command, env vars, ports |
| `docker-compose.yml` (servicio `createbuckets`) | Job one-shot que crea el bucket `influxdb3` |

**No hay archivo de configuración de MinIO.** Todo va via flags de CLI y env vars.

### Cómo se comunica

| Con quién | Protocolo | Dirección | Qué intercambia |
|-----------|-----------|-----------|-----------------|
| InfluxDB | HTTP S3 (TCP 9000) | Recibe | PUT de Parquet files |
| Usuario | HTTP API (9000) + Console web (9001) | Recibe | Navegación de buckets, inspección de archivos |

### Qué pasa si falla

| Escenario | Efecto | Recuperación |
|-----------|--------|-------------|
| MinIO se cae | InfluxDB no puede escribir nuevos datos. Los datos ya persistidos en Parquet se pierden si el volumen se corrompe. | Docker reinicia. El volumen `minio_data:/data` persiste entre reinicios. |
| Bucket `influxdb3` no existe | InfluxDB falla al iniciar. | createbuckets lo crea automáticamente. Si falla, reiniciar el stack. |
| Puerto 9000 o 9001 en uso | MinIO no arranca. | Liberar puerto o cambiar el mapeo en docker-compose.yml. |

### Cómo debuggearlo

```bash
# Ver logs
docker-compose logs -f minio

# Acceder a la consola web
# Abrir http://localhost:9001
# Login: MINIO_ROOT_USER / MINIO_ROOT_PASSWORD (del .env)

# Ver buckets con CLI
docker-compose exec minio mc alias set local http://localhost:9000 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD
docker-compose exec minio mc ls local/

# Ver contenido del bucket influxdb3
docker-compose exec minio mc ls local/influxdb3/

# Healthcheck manual
docker-compose exec minio curl -fsS http://localhost:9000/minio/health/live

# Verificar que createbuckets corrió OK
docker-compose logs createbuckets
# Debería mostrar: "bucket ready: influxdb3"
```

---

## 6. createbuckets

### Qué hace en este proyecto

Es un **trabajo de bootstrapping**. Crea el bucket `influxdb3` en MinIO antes de que InfluxDB intente usarlo. Es un contenedor que corre una vez, crea el bucket, y muere.

Sin este servicio, InfluxDB arrancaría antes que el bucket exista y fallaría al intentar escribir.

### Archivos de configuración

| Archivo | Rol |
|---------|-----|
| `docker-compose.yml` | Servicio `createbuckets`: entrypoint inline con comandos mc |

**No hay archivo separado.** Todo el script está inline en el entrypoint del compose.

### Cómo se comunica

| Con quién | Protocolo | Dirección | Qué intercambia |
|-----------|-----------|-----------|-----------------|
| MinIO | HTTP S3 (TCP 9000) | Envía | mc alias set, mc mb (crear bucket), mc anonymous set |

### Qué pasa si falla

| Escenario | Efecto | Recuperación |
|-----------|--------|-------------|
| createbuckets falla | InfluxDB no arranca (depende de `condition: service_completed_successfully`). | Docker reinicia createbuckets automáticamente (`restart: on-failure`). |
| MinIO no está listo | createbuckets falla porque no puede conectar. | createbuckets reintenta automáticamente hasta que MinIO esté healthy.

### Cómo debuggearlo

```bash
# Ver si corrió exitosamente
docker-compose ps createbuckets
# Debería mostrar "exited (0)"

# Ver logs
docker-compose logs createbuckets

# Si falló, eliminar y recrear
docker-compose rm -f createbuckets
docker-compose up -d createbuckets
```

---

## 7. Grafana

### Qué hace en este proyecto

Es la **cara visible** del stack. Muestra dashboards en tiempo real, gestiona alertas, y permite consultar datos de InfluxDB via InfluxQL. Es donde el operador interactúa con el sistema.

Todo el provisioning es as code — no hay que configurar nada manualmente en la UI de Grafana. Al arrancar, ya tiene el datasource, el dashboard y las alertas listas.

### Archivos de configuración

| Archivo | Rol |
|---------|-----|
| `grafana/provisioning/datasources/influxdb.yaml` | Datasource InfluxDB3 |
| `grafana/provisioning/dashboards/default.yaml` | Dashboard provider (dónde buscar JSONs) |
| `grafana/dashboards/linea-envasado.json` | Dashboard con 11 paneles |
| `grafana/provisioning/alerting/contactpoints.yaml` | Contact point para alertas (webhook dummy) |
| `grafana/provisioning/alerting/rules.yaml` | 2 reglas de alerta |
| `docker-compose.yml` | Servicio `grafana`: imagen, env vars, ports, volumes |

### Cómo se comunica

| Con quién | Protocolo | Dirección | Qué intercambia |
|-----------|-----------|-----------|-----------------|
| InfluxDB | HTTP InfluxQL (TCP 8181) | Envía queries | GET /query con queries InfluxQL, recibe time-series data |
| Usuario | HTTP web (TCP 3000) | Recibe | Navegación web, interacción con dashboards |
| Contact point | HTTP webhook (TCP 9999) | Envía | NOTIFICATION de alertas (a endpoint dummy) |

### Qué pasa si falla

| Escenario | Efecto | Recuperación |
|-----------|--------|-------------|
| Grafana se cae | No se puede ver el dashboard ni las alertas. **Los datos siguen fluyendo** (simulador → Mosquitto → Telegraf → InfluxDB funciona igual). | Docker reinicia automáticamente. |
| Datasource no se provisiona | Paneles vacíos, "No data". | Verificar logs: `docker-compose logs grafana | grep -i datasource`. |
| Alertas no aparecen | Posible problema con el provisioning YAML. | Verificar: `docker-compose exec grafana cat /etc/grafana/provisioning/alerting/rules.yaml` |

### Cómo debuggearlo

```bash
# Ver logs
docker-compose logs -f grafana

# Verificar health
docker-compose exec grafana curl -fsS http://localhost:3000/api/health

# Ver datasource provisionado
docker-compose exec grafana cat /etc/grafana/provisioning/datasources/influxdb.yaml

# Ver alertas provisionadas
docker-compose exec grafana cat /etc/grafana/provisioning/alerting/rules.yaml

# Ver dashboard JSON montado
docker-compose exec grafana cat /var/lib/grafana/dashboards/linea-envasado.json

# Acceder a la UI
# http://localhost:3000 (admin/admin)

# Ver logs de provisioning
docker-compose logs grafana | grep -i "provision"

# Ver estado de alertas
# En la UI: Alerting → Alert Rules
```

---

## Resumen: Orden de Dependencias y Fallback

```
Si falla este componente → afecta a estos otros:

mosquitto     → simulator (no puede publicar), telegraf (no puede leer)
simulator     → todo el stack (no hay datos nuevos)
telegraf      → influxdb (no recibe writes), grafana (no hay datos nuevos)
influxdb      → grafana (paneles vacíos), telegraf (buffer se llena)
minio         → influxdb (no puede persistir)
createbuckets → influxdb (no arranca sin bucket)
grafana       → nadie (solo la UI se pierde, el pipeline sigue)
```

**Componente más crítico:** El simulador. Si se cae, no hay datos. Si Mosquitto se cae, el simulador no puede publicar. Son los dos eslabones iniciales de la cadena.

**Componente menos crítico:** Grafana. Si se cae, todo el pipeline de datos sigue funcionando. Solo perdés la visualización temporalmente.
