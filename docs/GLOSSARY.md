# Glosario — Planta de Gaseosas

Términos técnicos usados en el proyecto. Cada uno tiene definición clara y ejemplo concreto de este stack.

---

## A

### Area (Área de planta)
**Definición:** Zona funcional de la planta de gaseosas donde se ubica un sensor. En el UNS, cada sensor pertenece a un área.

**Ejemplo en este proyecto:** `pasteurizador`, `llenadora`, `mezcla`, `almacenamiento`, `transporte`, `insumos`.

**Dónde se usa:** Tag de InfluxDB (`area=almacenamiento`), segmento del topic MQTT (`planta1/almacenamiento/sensor/...`).

### AsyncIO
**Definición:** Modelo de programación asíncrona en Python. Permite concurrencia sin threads.

**Ejemplo en este proyecto:** **No se usa.** El simulador es single-threaded con `loop_start()` de paho-mqtt para I/O no bloqueante. Se eligió no usar asyncio porque 11 mensajes/seg no justifican la complejidad.

---

## B

### Baseline
**Definición:** Valor "normal" o esperado de un sensor. El simulador genera valores alrededor del baseline sumando ruido gaussiano.

**Ejemplo en este proyecto:** `temperatura_pasteurizador` tiene baseline de 75.0°C. Los valores típicos oscilan entre ~70 y ~80.

### Broker
**Definición:** Servidor intermediario en el protocolo MQTT. Recibe mensajes de los publishers y los distribuye a los suscriptores según los topics.

**Ejemplo en este proyecto:** **Mosquitto** (eclipse-mosquitto:2.0) es el broker. Corre en el contenedor `planta-mosquitto`, puerto 1883.

### Bucket
**Definición:** Contenedor de nivel superior en un object store S3. Equivale a una "carpeta raíz" donde se guardan objetos.

**Ejemplo en este proyecto:**
- Bucket `influxdb3` en MinIO: donde InfluxDB guarda los Parquet files.
- Bucket `sensores` en InfluxDB: base de datos logical donde Telegraf escribe los datos.

---

## C

### Counter (Contador)
**Definición:** Tipo de métrica que solo incrementa (monótonamente creciente). No decrece excepto cuando se reinicia el proceso.

**Ejemplo en este proyecto:** `conteo_botellas` y `conteo_rechazos` son counters. Incrementan cada segundo. En Grafana se grafican con `non_negative_derivative` para mostrar la tasa de cambio.

---

## D

### Docker Compose
**Definición:** Herramienta de Docker para definir y ejecutar aplicaciones multi-contenedor. Usa un archivo YAML para declarar servicios, redes, volúmenes y dependencias.

**Ejemplo en este proyecto:** `docker-compose.yml` declara 7 servicios conectados en la red `planta_net`.

---

## F

### Field
**Definición:** En InfluxDB, es el dato que se mide (el valor numérico). A diferencia de los tags, los fields **no son indexados**.

**Ejemplo en este proyecto:** `value=4.0738` es el field. Contiene la lectura del sensor.

### Flush
**Definición:** Envío en lote de datos acumulados. En lugar de enviar cada métrica individualmente, Telegraf las junta y las envía todas juntas en intervalos regulares.

**Ejemplo en este proyecto:** `flush_interval = "1s"` en Telegraf. Cada segundo envía un batch de ~11 métricas a InfluxDB.

---

## G

### Gauge
**Definición:** Tipo de métrica que representa un valor instantáneo que puede subir o bajar. A diferencia del counter, no es monótono.

**Ejemplo en este proyecto:** 9 de los 11 sensores son gauges: `temperatura_pasteurizador`, `presion_llenadora`, `vibracion_llenadora`, etc.

### Grafana Alert
**Definición:** Regla que evalúa una condición sobre datos de un datasource y cambia de estado (Normal → Alerting) cuando se cumple.

**Ejemplo en este proyecto:** 2 alertas:
- `Alta Temperatura Pasteurizador`: dispara cuando `temperatura_pasteurizador > 85°C`
- `Vibración Llenadora Alta`: dispara cuando `vibracion_llenadora > 8 mm/s`

---

## H

### Healthcheck
**Definición:** Comando que Docker ejecuta periódicamente dentro de un contenedor para verificar si el servicio está funcionando correctamente. Determina si el contenedor está `healthy` o `unhealthy`.

**Ejemplo en este proyecto:** Cada servicio tiene un healthcheck:
- Mosquitto: `mosquitto_sub -t '$SYS/broker/uptime' -W 3`
- InfluxDB: `curl -f http://localhost:8181/health`
- Grafana: `curl -f http://localhost:3000/api/health`
- Telegraf: `pgrep telegraf`
- Simulator: `pgrep -f sensores.py`

### HTTP 400 Bad Request
**Definición:** Código de error HTTP que indica que la petición está mal formada.

**Ejemplo en este proyecto:** Si el `organization` en telegraf.conf no está vacío (`""`), InfluxDB 3 Core responde 400. Es el error más común del stack.

---

## I

### InfluxDB
**Definición:** Base de datos optimizada para datos time-series (series temporales). Diseñada para alta velocidad de escritura y consultas por rango de tiempo.

**Ejemplo en este proyecto:** InfluxDB 3 Core (`influxdb:3-core`) corre en puerto 8181, sin auth (`--without-auth`), con object store apuntando a MinIO.

### InfluxQL
**Definición:** Lenguaje de consulta tipo SQL para InfluxDB. Similar a SQL pero con funciones específicas para time-series.

**Ejemplo en este proyecto:**
```sql
SELECT mean("value") FROM "temperatura_pasteurizador" WHERE time > now() - 1m
```

### I/O (Input/Output)
**Definición:** Operaciones de entrada/salida — lectura y escritura de datos (red, disco, etc.).

**Ejemplo en este proyecto:** `client.loop_start()` de paho-mqtt crea un thread de background para I/O MQTT no bloqueante, así el loop principal no se traba enviando datos.

---

## L

### Line Protocol
**Definición:** Formato de texto plano que InfluxDB usa para ingestión de datos. Estructura: `measurement,tags field timestamp`.

**Ejemplo en este proyecto:**
```
temperatura_camara_fria,area=almacenamiento,planta=gaseosas value=4.0738 1714939200
```

### Listener (MQTT)
**Definición:** Configuración en Mosquitto que define en qué puerto y con qué parámetros aceptar conexiones MQTT.

**Ejemplo en este proyecto:** `listener 1883 0.0.0.0` en mosquitto.conf — acepta conexiones MQTT en el puerto 1883 desde cualquier interfaz.

---

## M

### Measurement
**Definición:** En InfluxDB, es el equivalente a una "tabla" en una base de datos relacional. Agrupa datos del mismo tipo.

**Ejemplo en este proyecto:** Cada sensor tiene su propio measurement: `temperatura_pasteurizador`, `vibracion_llenadora`, etc. Telegraf extrae el nombre del último segmento del topic MQTT.

### Mosquitto
**Definición:** Broker MQTT open-source de Eclipse Foundation. Ligero y ampliamente usado en IoT.

**Ejemplo en este proyecto:** `eclipse-mosquitto:2.0` como contenedor Docker. Versión 2.0 requiere configuración explícita de listener y anonymous access.

### MQTT (Message Queuing Telemetry Transport)
**Definición:** Protocolo de mensajería ligero diseñado para dispositivos con recursos limitados y redes de bajo ancho de banda. Funciona sobre TCP/IP. Usa un modelo publish/subscribe con un broker intermediario.

**Ejemplo en este proyecto:** El simulador publica en topics MQTT, Mosquitto los distribuye, Telegraf se suscribe para ingerir los datos.

---

## O

### OEE (Overall Equipment Effectiveness)
**Definición:** Métrica industrial que mide la eficiencia de un equipo de producción. Se calcula como: `(unidades buenas / unidades totales) × 100`.

**Ejemplo en este proyecto:** En Grafana se calcula como:
```
OEE = (conteo_botellas - conteo_rechazos) / conteo_botellas × 100
```
Si se produjeron 120 botellas y 6 fueron rechazadas: OEE = (120-6)/120 × 100 = 95%.

### Object Store
**Definición:** Sistema de almacenamiento donde los datos se guardan como objetos (no como archivos en filesystem ni bloques). Cada objeto tiene datos, metadata y un identificador único. S3 de AWS es el estándar.

**Ejemplo en este proyecto:** MinIO actúa como object store para InfluxDB 3 Core. InfluxDB escribe Parquet files en MinIO como su backend de persistencia.

---

## P

### Parquet
**Definición:** Formato de archivo columnar optimizado para análisis. Almacena datos por columna (no por fila), lo que permite leer solo las columnas necesarias. Muy eficiente para time-series.

**Ejemplo en este proyecto:** InfluxDB 3 Core serializa los datos a Parquet y los guarda en MinIO. No se interactúa directamente con estos archivos — InfluxDB los gestiona internamente.

### Payload
**Definición:** El contenido real de un mensaje (sin headers ni metadata del protocolo).

**Ejemplo en este proyecto:** El payload de cada mensaje MQTT es un string ASCII con un float: `"75.4231"`. No es JSON — es el número directo como texto.

### Publisher
**Definición:** En MQTT, el cliente que envía (publica) mensajes a un topic en el broker.

**Ejemplo en este proyecto:** El **simulador Python** es el publisher. Publica 11 mensajes por segundo.

### QoS (Quality of Service)
**Definición:** Nivel de garantía de entrega en MQTT:
- **QoS 0:** Fire-and-forget. No hay confirmación. El mensaje puede perderse.
- **QoS 1:** Al menos una vez. El broker confirma recepción (puede llegar duplicado).
- **QoS 2:** Exactamente una vez. Garantía máxima pero más lento.

**Ejemplo en este proyecto:** `qos=0` en todas las publicaciones. Si un mensaje se pierde, no pasa nada — el siguiente segundo llega otro valor.

---

## R

### Retention (Retención)
**Definición:** Política que define cuánto tiempo se conservan los datos antes de ser eliminados automáticamente.

**Ejemplo en este proyecto:** **[TODO]** No hay retention policy configurada. Los datos se acumulan en MinIO indefinidamente. Para producción, configurar lifecycle rules en MinIO o retention policies en InfluxDB.

---

## S

### Spike
**Definición:** Valor artificialmente alto que el simulador genera periódicamente para probar alertas. Simula una anomalía del proceso real.

**Ejemplo en este proyecto:** Cada 5 minutos (`t % 300 < 45`), durante 45 segundos:
- `temperatura_pasteurizador` pasa de ~75°C a **92.0°C**
- `vibracion_llenadora` pasa de ~2.5 mm/s a **12.0 mm/s**

### Subscriber
**Definición:** En MQTT, el cliente que recibe mensajes de un topic del broker.

**Ejemplo en este proyecto:** **Telegraf** es el subscriber. Se suscribe a `planta1/+/sensor/+` y recibe todos los mensajes de sensores.

---

## T

### Tag
**Definición:** En InfluxDB, es metadata indexada que se puede usar para filtrar y agrupar datos. A diferencia de los fields, los tags son strings y están indexados.

**Ejemplo en este proyecto:** Cada punto en InfluxDB tiene estos tags:
- `area`: extraído del topic MQTT por el processor regex de Telegraf (ej. `"almacenamiento"`)
- `planta`: tag estático configurado en Telegraf (siempre `"gaseosas"`)
- `topic`: el topic MQTT completo (ej. `"planta1/almacenamiento/sensor/temperatura_camara_fria"`)

### Telegraf
**Definición:** Agente de recopilación de métricas de InfluxData. Tiene plugins de input (donde lee) y output (donde escribe).

**Ejemplo en este proyecto:** Telegraf 1.30 con input `mqtt_consumer`, processor `regex`, output `influxdb_v2`.

### Time-series (Serie Temporal)
**Definición:** Secuencia de datos ordenados por tiempo. Cada punto tiene un valor y un timestamp.

**Ejemplo en este proyecto:** Cada lectura de cada sensor es un punto en una time-series: `(temperatura_camara_fria, 4.0738, 2026-05-05T10:30:00Z)`.

### TLS (Transport Layer Security)
**Definición:** Protocolo de encriptación para comunicaciones de red. Sucesor de SSL.

**Ejemplo en este proyecto:** **[TODO]** No hay TLS. Todo el tráfico es plano (HTTP, MQTT sin encriptar). Para producción, habilitar TLS en Mosquitto, HTTPS en InfluxDB, y HTTPS en Grafana.

### Topic
**Definición:** En MQTT, es la "dirección" o canal al que se publica un mensaje. Tiene estructura jerárquica con segmentos separados por `/`.

**Ejemplo en este proyecto:**
- `planta1/pasteurizador/sensor/temperatura_pasteurizador` — topic de un sensor
- `planta1/+/sensor/+` — topic filter (wildcard `+` = un segmento cualquiera)
- `planta1/#` — wildcard `#` = cualquier cosa después de este punto

### Topic Filter
**Definición:** Patrón que un subscriber usa para suscribirse a múltiples topics. Usa wildcards:
- `+` coincide con exactamente un segmento
- `#` coincide con cero o más segmentos (debe ir al final)

**Ejemplo en este proyecto:** Telegraf usa `planta1/+/sensor/+` — coincide con cualquier área y cualquier sensor.

---

## U

### UNS (Unified Naming System)
**Definición:** Convención de nomenclatura que organiza los topics MQTT por área de planta. Estructura: `planta1/<area>/sensor/<nombre>`.

**Ejemplo en este proyecto:** Los 11 sensores se distribuyen en 6 áreas: pasteurizador, llenadora, mezcla, almacenamiento, transporte, insumos.

---

## V

### Volume (Volumen Docker)
**Definición:** Mecanismo de Docker para persistir datos más allá del ciclo de vida de un contenedor. Los datos viven fuera del container, en el host o en volúmenes gestionados.

**Ejemplo en este proyecto:**
- `minio_data:/data` — persiste Parquet files de InfluxDB
- `influxdb_data:/var/lib/influxdb3` — persiste metadata de InfluxDB
- `grafana_data:/var/lib/grafana` — persiste configuración de Grafana
- `mosquitto_data:/mosquitto/data` — persiste datos de Mosquitto

Con `docker-compose down` los volúmenes se preservan. Con `docker-compose down -v` se borran.

---

## W

### Webhook
**Definición:** Callback HTTP. Un servicio envía una petición HTTP a una URL cuando ocurre un evento.

**Ejemplo en este proyecto:** El contact point de alertas de Grafana apunta a `http://localhost:9999/noop` — un webhook dummy que no existe. Las alertas se ven en la UI pero no notifican a ningún canal externo.

### Wildcard (Comodín)
**Definición:** Carácter especial en un patrón que coincide con múltiples valores.

**Ejemplo en este proyecto:**
- `+` en `planta1/+/sensor/+` → cualquier área, cualquier sensor
- `#` en `planta1/#` → cualquier topic que empiece con `planta1/`
