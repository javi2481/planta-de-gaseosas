# Planta de Gaseosas — Stack de Monitoreo IoT

Stack Docker Compose para el monitoreo en tiempo real de una linea de envasado de gaseosas. Incluye simulacion de sensores, ingestion MQTT, almacenamiento en time-series sobre object storage (MinIO/InfluxDB 3 Core) y visualizacion en Grafana.

## Arquitectura

```
Simulador Python --> Mosquitto (MQTT) --> Telegraf --> InfluxDB 3 Core --> Grafana
  (11 sensores, UNS)    planta1/<area>/     + area tag             |
                          sensor/<nombre>                         MinIO (Parquet)
```

## Servicios

| Servicio       | Descripcion                              | Puerto host  |
|----------------|------------------------------------------|--------------|
| mosquitto      | Broker MQTT                              | 1883         |
| minio          | Object storage (backend de InfluxDB)     | 9000, 9001   |
| influxdb       | Time-series DB (InfluxDB 3 Core)         | 8181         |
| telegraf       | Agente de ingestion MQTT -> InfluxDB     | —            |
| grafana        | Visualizacion y alertas                  | 3000         |
| simulator      | Simulador de 11 sensores con UNS (Unified Naming System) | —            |
| createbuckets  | Job de inicio: crea el bucket en MinIO (se ejecuta una vez y termina) | —  |

## Requisitos

- Docker Engine 24+ con soporte para `healthcheck` y `depends_on: condition`
- Docker Compose v2 (`docker compose` o `docker compose`)
- Acceso a internet para pull de imagenes en el primer arranque

## Instalacion

### 1. Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd planta-de-gaseosas
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
```

Editar `.env` si se desean cambiar credenciales u otros parametros. Los valores por defecto del `.env.example` funcionan sin modificacion para desarrollo local.

### 3. Levantar el stack

```bash
docker compose up -d
```

El stack tarda hasta 70 segundos en que todos los servicios pasen a estado `healthy`. Se puede verificar con:

```bash
docker compose ps
```

Se esperan 6 servicios en estado `running/healthy` y 1 (`createbuckets`) en `exited (0)`.

## URLs de acceso

| Servicio         | URL                          | Credenciales         |
|------------------|------------------------------|----------------------|
| Grafana          | http://localhost:3000        | admin / admin        |
| MinIO Console    | http://localhost:9001        | minioadmin / minioadmin123 |
| InfluxDB API     | http://localhost:8181        | sin autenticacion    |
| MQTT Broker      | tcp://localhost:1883         | anonimo              |

El dashboard `Linea de Envasado` aparece automaticamente en Grafana bajo la carpeta `Planta de Gaseosas`, sin necesidad de importarlo manualmente.

## UNS — Unified Naming System

Los sensores se organizan por área de la planta de la planta. El topic MQTT sigue el formato:

```
planta1/<area>/sensor/<nombre>
```

| Área | Sensores |
|------|----------|
| pasteurizador | temperatura_pasteurizador |
| llenadora | presion_llenadora, vibracion_llenadora |
| mezcla | nivel_jarabe, caudal_agua |
| almacenamiento | temperatura_camara_co2, temperatura_camara_fria |
| transporte | velocidad_cinta, conteo_botellas, conteo_rechazos |
| insumos | nivel_tapas |

Cada punto en InfluxDB lleva el tag `area` para distinguir mediciones con nombres genéricos entre áreas. Ejemplo de consulta:

```sql
SELECT mean("value") FROM "temperatura_pasteurizador" WHERE "area" = 'pasteurizador' AND $timeFilter
```

## Verificacion rapida

```bash
# Ver logs del simulador
docker compose logs -f simulator

# Ver logs de Telegraf (confirmar escrituras)
docker compose logs -f telegraf

# Consultar InfluxDB directamente
curl "http://localhost:8181/query?db=sensores&q=SELECT+last(value)+FROM+temperatura_pasteurizador"
```

## Bajar el stack

Detener y conservar datos en volumenes:

```bash
docker compose down
```

Detener y eliminar todos los volumenes (borrado completo):

```bash
docker compose down -v
```

## Nota de seguridad

ADVERTENCIA: Este stack esta configurado para desarrollo local exclusivamente. DEBE NOT usarse en produccion sin antes:

- Habilitar autenticacion en InfluxDB (`influxdb3 create token --admin`)
- Habilitar TLS en Mosquitto y Grafana
- Usar Docker secrets o un gestor de secretos en lugar de `.env` plano
- Cambiar todas las credenciales por defecto
- Restringir la exposicion de puertos al host
