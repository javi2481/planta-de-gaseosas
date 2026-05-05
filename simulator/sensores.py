import os
import time
import random
import math
import paho.mqtt.client as mqtt

BROKER  = os.environ.get("MQTT_BROKER", "mosquitto")
PORT    = int(os.environ.get("MQTT_PORT", "1883"))
ROOT    = os.environ.get("MQTT_TOPIC_PREFIX", "planta1")

# UNS — Unified Naming System: mapeo sensor → área de la planta.
# Topic resultante: planta1/<area>/sensor/<nombre>
AREA_MAP = {
    "temperatura_pasteurizador": "pasteurizador",
    "presion_llenadora":         "llenadora",
    "vibracion_llenadora":       "llenadora",
    "nivel_jarabe":              "mezcla",
    "caudal_agua":               "mezcla",
    "temperatura_camara_co2":    "almacenamiento",
    "temperatura_camara_fria":   "almacenamiento",
    "velocidad_cinta":           "transporte",
    "conteo_botellas":           "transporte",
    "conteo_rechazos":           "transporte",
    "nivel_tapas":               "insumos",
}

SENSORS = {
    "temperatura_pasteurizador": {"baseline": 75.0, "noise": 1.5, "spike": 92.0,  "kind": "gauge"},
    "presion_llenadora":         {"baseline": 3.2,  "noise": 0.1, "spike": 4.5,   "kind": "gauge"},
    "nivel_jarabe":              {"baseline": 65.0, "noise": 5.0, "spike": 12.0,  "kind": "gauge"},
    "caudal_agua":               {"baseline": 120.0,"noise": 8.0, "spike": 30.0,  "kind": "gauge"},
    "vibracion_llenadora":       {"baseline": 2.5,  "noise": 0.5, "spike": 12.0,  "kind": "gauge"},
    "temperatura_camara_co2":    {"baseline": 4.0,  "noise": 0.3, "spike": 9.0,   "kind": "gauge"},
    "velocidad_cinta":           {"baseline": 250.0,"noise": 10.0,"spike": 80.0,  "kind": "gauge"},
    "temperatura_camara_fria":   {"baseline": 4.0,  "noise": 0.2,                 "kind": "gauge"},
    "nivel_tapas":               {"baseline": 75.0, "noise": 1.0,                 "kind": "gauge"},
    "conteo_botellas":           {"baseline": 0,    "rate": 1.0,                  "kind": "counter"},
    "conteo_rechazos":           {"baseline": 0,    "rate": 0.02,                 "kind": "counter"},
}

client = mqtt.Client(client_id="simulator", protocol=mqtt.MQTTv5)
client.connect(BROKER, PORT, keepalive=30)
client.loop_start()  # I/O en background thread

# Estado para counters
counters = {"conteo_botellas": 0, "conteo_rechazos": 0}
t = 0
try:
    while True:
        spike_window = (t % 300) < 45  # 45 segundos de spike cada 5 minutos

        for name, cfg in SENSORS.items():
            if cfg["kind"] == "gauge":
                if spike_window and "spike" in cfg:
                    value = cfg["spike"]
                else:
                    value = cfg["baseline"] + random.gauss(0, cfg["noise"])
            else:  # counter
                if name == "conteo_botellas":
                    counters[name] += 1
                else:  # conteo_rechazos
                    if random.random() < cfg["rate"]:
                        counters[name] += 1
                value = counters[name]

            area = AREA_MAP.get(name, "general")
            client.publish(f"{ROOT}/{area}/sensor/{name}", payload=f"{value:.4f}", qos=0)

        t += 1
        time.sleep(1.0)
finally:
    client.loop_stop()
    client.disconnect()
