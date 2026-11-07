"""
mqtt_publisher.py — ImpactOS Monitor v2.0
Publica dados dos sensores no broker MQTT (Mosquitto).

Tópicos:
  impactos/leitura  → leitura contínua a cada 200ms (JSON)
  impactos/impacto  → evento de impacto detectado (JSON)
  impactos/config   → configuração atual do limite (JSON)

O dashboard web assina esses tópicos via WebSocket.

Dependências:
  pip install paho-mqtt
"""

import json
import time
import threading
import paho.mqtt.client as mqtt

import sensor_core
import data_logger

# ─── CONFIGURAÇÃO ─────────────────────────────────────────────────────────────

BROKER_HOST  = "localhost"   # Mosquitto rodando no próprio Pi 4
BROKER_PORT  = 1883          # Porta MQTT padrão (Python → Broker)
BROKER_WS    = 9001          # Porta WebSocket (Browser → Broker)

TOPICO_LEITURA = "impactos/leitura"
TOPICO_IMPACTO = "impactos/impacto"
TOPICO_CONFIG  = "impactos/config"

INTERVALO_PUBLICACAO = 0.2   # segundos entre publicações contínuas (~5Hz)

# ─── CLIENTE MQTT ─────────────────────────────────────────────────────────────

client = mqtt.Client(client_id="impactos_pi4")

def _on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[MQTT] Conectado ao broker Mosquitto")
        # Publica config inicial assim que conecta
        _publicar_config()
    else:
        print(f"[MQTT] Erro de conexão — código {rc}")

def _on_disconnect(client, userdata, rc):
    print(f"[MQTT] Desconectado (rc={rc}) — tentando reconectar...")

client.on_connect    = _on_connect
client.on_disconnect = _on_disconnect

# ─── PUBLICAÇÕES ──────────────────────────────────────────────────────────────

def _publicar(topico: str, payload: dict, retain=False):
    """Serializa para JSON e publica no tópico."""
    try:
        client.publish(topico, json.dumps(payload), qos=0, retain=retain)
    except Exception as e:
        print(f"[MQTT] Erro ao publicar em {topico}: {e}")

def _publicar_config():
    """Publica o limite atual como mensagem retida (retained)."""
    e = sensor_core.ler_estado()
    _publicar(TOPICO_CONFIG, {
        "limite":          e["limite"],
        "modo_silencioso": e["modo_silencioso"],
    }, retain=True)  # retain=True → novos clientes recebem imediatamente ao conectar

def publicar_impacto(snapshot: dict):
    """
    Chamado pelo sensor_core via callback a cada impacto.
    Também salva no CSV.
    """
    data_logger.salvar_impacto(snapshot)

    payload = {
        "timestamp":  snapshot["timestamp"].strftime("%H:%M:%S"),
        "g_pico":     round(snapshot["g_pico"], 3),
        "ax":         round(snapshot["ax"], 3),
        "ay":         round(snapshot["ay"], 3),
        "az":         round(snapshot["az"], 3),
        "lat":        snapshot["lat"],
        "lng":        snapshot["lng"],
        "alt":        snapshot["alt"],
        "severidade": snapshot["severidade"],
    }
    _publicar(TOPICO_IMPACTO, payload)
    print(f"[MQTT] Impacto publicado — {snapshot['g_pico']:.2f}G ({snapshot['severidade']})")

# ─── LOOP DE PUBLICAÇÃO CONTÍNUA ──────────────────────────────────────────────

def _loop_publicacao():
    """Publica leitura contínua dos sensores a ~5Hz."""
    from datetime import datetime
    while True:
        try:
            e = sensor_core.ler_estado()
            s = int((datetime.now() - e["inicio_sessao"]).total_seconds())

            payload = {
                "g":          round(e["g_total"], 3),
                "ax":         round(e["ax"], 3),
                "ay":         round(e["ay"], 3),
                "az":         round(e["az"], 3),
                "lat":        e["lat"],
                "lng":        e["lng"],
                "alt":        e["alt"],
                "sat":        e["sat"],
                "gps_ok":     e["gps_ok"],
                "limite":     e["limite"],
                "impactos":   e["impactos_sessao"],
                "pico":       round(e["pico_sessao"], 3),
                "uptime":     s,
                "silencioso": e["modo_silencioso"],
            }
            _publicar(TOPICO_LEITURA, payload)

            # Salva no CSV a cada N publicações
            data_logger.salvar_leitura(e)

        except Exception as ex:
            print(f"[MQTT] Erro no loop de publicação: {ex}")

        time.sleep(INTERVALO_PUBLICACAO)

# ─── INICIALIZAÇÃO ────────────────────────────────────────────────────────────

def iniciar():
    """Conecta ao broker e inicia publicação contínua."""
    # Registra callback de impacto no sensor_core
    sensor_core.registrar_callback_impacto(publicar_impacto)

    # Conecta ao Mosquitto com reconexão automática
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    except Exception as e:
        print(f"[MQTT] Não foi possível conectar ao broker: {e}")
        print("[MQTT] Verifique se o Mosquitto está rodando: sudo systemctl status mosquitto")
        return

    # Loop de rede MQTT em thread separada (não bloqueante)
    client.loop_start()

    # Loop de publicação contínua em thread separada
    t = threading.Thread(target=_loop_publicacao, daemon=True)
    t.start()

    print(f"[MQTT] Publicando em {BROKER_HOST}:{BROKER_PORT}")
    print(f"[MQTT] Dashboard conecta via WebSocket na porta {BROKER_WS}")

def encerrar():
    """Desconecta do broker."""
    client.loop_stop()
    client.disconnect()
    print("[MQTT] Desconectado.")
