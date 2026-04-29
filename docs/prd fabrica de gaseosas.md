Proyecto 1 — Fábrica de gaseosas 
Vertical: Alimenticia / packaging  •  Complejidad: ★☆☆☆☆  •  Estimación: 3-4 fines de semana 
1. Resumen ejecutivo 
Sistema docker-compose que simula una línea de envasado de gaseosas con 8 sensores publicando 
datos por MQTT. Telegraf hace ingesta a InfluxDB 3 Core, Grafana muestra dashboards en tiempo 
real con alertas, y MinIO actúa como object storage. Establece el stack base que se reusará en 
proyectos posteriores. 
2. Objetivo de negocio 
Demostrar dominio práctico de la cadena de datos industrial moderna. Pasar de "entiendo MQTT en 
teoría" a "lo configuré y lo hago funcionar" en una vertical universalmente reconocible (todos vimos 
una línea de gaseosas). 
3. Por qué esta vertical 
La industria alimenticia es uno de los sectores más relevantes en Argentina y LATAM. Una línea de 
envasado tiene sensores variados, ritmo predecible, y casos de uso obvios (calidad, OEE, 
mantenimiento). Es la mejor vertical para arrancar porque cualquier persona sin background técnico 
entiende qué se está midiendo. 
4. User stories 
Story 1.1 — Como desarrollador, quiero levantar todo el stack con un solo comando 
• docker-compose up -d levanta Mosquitto, Telegraf, InfluxDB 3 Core, Grafana, MinIO en 
estado healthy. 
• Cada servicio tiene healthcheck definido. 
• Tiempo total de arranque menor a 60 segundos. 
Story 1.2 — Como sistema, quiero recibir datos de 8 sensores simulados 
Sensores que representan una línea de envasado real: 
• Caudal de jarabe (litros/min) 
• Presión de carbonatación (bar) 
• Velocidad de cinta (botellas/min) 
• Temperatura de pasteurizador (°C) 
• Conteo de botellas envasadas (acumulado) 
• Nivel de tapas en tolva (%) 
• Vibración de llenadora (mm/s) 
• Temperatura de cámara fría (°C) 
• Criterio de aceptación: cada sensor publica cada 1 segundo a topics MQTT estructurados 
(planta/linea1/sensor/<nombre>). 
• Criterio de aceptación: valores con baseline realista, ruido gaussiano, spike anómalo cada ~5 
minutos. 
Story 1.3 — Como operador, quiero ver dashboards en tiempo real con alertas 
• Dashboard Grafana con 8 paneles time-series (uno por sensor). 
• Panel adicional con OEE simplificado (productos buenos / productos totales). 
• Al menos 2 alertas configuradas (ej: temperatura pasteurizador fuera de rango, vibración 
alta). 
• Latencia desde sensor hasta dashboard menor a 3 segundos. 
Story 1.4 — Como sistema, quiero retener datos en object storage 
• InfluxDB 3 Core configurado con MinIO como backend de almacenamiento. 
• Archivos Parquet visibles en MinIO Console (puerto 9001). 
5. Stack técnico 
Componente 
Función 
Eclipse Mosquitto 2.0+ 
Broker MQTT que recibe los datos de los sensores 
Licencia 
Telegraf 1.30+ 
EPL/EDL 
Agente de ingesta MQTT → InfluxDB 3 
InfluxDB 3 Core 3.8+ 
MIT 
Time-series DB con motor Rust + Apache Arrow + 
Parquet 
Grafana 11+ 
Dashboards y alertas 
MIT/Apache 2 
MinIO 
AGPLv3 
Object storage S3-compatible para histórico 
Python 3.11 
AGPLv3 
Simulador de sensores con paho-mqtt 
PSF 
6. Recursos oficiales y URLs 
Documentación 
• InfluxDB 3 Core docs: https://docs.influxdata.com/influxdb3/core/ 
• Telegraf docs: https://docs.influxdata.com/telegraf/v1/ 
• Mosquitto docs: https://mosquitto.org/documentation/ 
• Grafana docs: https://grafana.com/docs/grafana/latest/ 
• MinIO docs: https://min.io/docs/minio/linux/index.html 
Repos oficiales en GitHub 
• influxdata/influxdb (rama 3.x): https://github.com/influxdata/influxdb 
• influxdata/telegraf: https://github.com/influxdata/telegraf 
• eclipse-mosquitto/mosquitto: https://github.com/eclipse-mosquitto/mosquitto 
• grafana/grafana: https://github.com/grafana/grafana 
• minio/minio: https://github.com/minio/minio 
• eclipse-paho/paho.mqtt.python: https://github.com/eclipse-paho/paho.mqtt.python 
Recursos de aprendizaje 
• InfluxDB University (cursos gratis): https://www.influxdata.com/university/ 
• Telegraf MQTT consumer plugin: 
https://github.com/influxdata/telegraf/tree/master/plugins/inputs/mqtt_consumer 
• Telegraf influxdb_v2 output (compatible v3): 
https://github.com/influxdata/telegraf/tree/master/plugins/outputs/influxdb_v2 
7. Estructura sugerida del repo 
fabrica-gaseosas/ 
├── docker-compose.yml 
├── README.md  (en español) 
├── .env.example 
├── mosquitto/ 
│   └── config/mosquitto.conf 
├── telegraf/ 
│   └── telegraf.conf 
├── influxdb/ 
│   └── config.toml 
├── grafana/ 
│   ├── dashboards/linea-envasado.json 
│   └── provisioning/ 
├── simulator/ 
│   ├── sensores.py 
│   ├── requirements.txt 
│   └── Dockerfile 
└── docs/ 
├── arquitectura.md 
└── capturas/ 
8. Scope explícito 
Qué SÍ entra: 
• Docker-compose completo del stack. 
• Simulador Python con 8 sensores. 
• Dashboard Grafana funcional. 
• MinIO conectado como backend. 
• README en español. 
Qué NO entra: 
• Protocolos industriales reales (OPC-UA, Modbus) — todo MQTT simulado. 
• Hardware real — todo software. 
• Plugins del Processing Engine — eso es proyecto 2. 
• Forecasting o anomaly detection — eso es proyectos posteriores. 
9. Definition of Done 
• docker-compose up -d arranca todo limpio. 
• Dashboard Grafana muestra los 8 sensores con datos en vivo. 
• Alertas se disparan al inyectar valor anómalo. 
• Archivos Parquet visibles en MinIO. 
• Repo público con licencia MIT. 
• Post LinkedIn con video de 60 segundos del dashboard. 
10. Hook para LinkedIn 
"Cómo monitoreás una línea de envasado de gaseosas con software 100% opensource. Stack 
moderno (InfluxDB 3 + MinIO + Grafana) en docker-compose. El video muestra una pipeline real 
funcionando en mi laptop." 