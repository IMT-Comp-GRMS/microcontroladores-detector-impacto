"""
main.py — ImpactOS Monitor v2.0
Ponto de entrada — inicia todos os módulos na ordem correta.

Executar no Raspberry Pi 4:
    python3 main.py

Para iniciar automaticamente ao ligar, criar serviço systemd:
    sudo nano /etc/systemd/system/impactos.service
"""

import threading
import signal
import sys

import data_logger
import sensor_core
import mqtt_publisher
import display_ui

def main():
    print("=" * 50)
    print("  ImpactOS Monitor v2.0")
    print("  Raspberry Pi 4 + MPU-6050 + GPS NEO-6M")
    print("  Conectividade: MQTT via Wi-Fi")
    print("=" * 50)

    # 1. Logger — cria CSVs e carrega configurações salvas
    data_logger.iniciar()

    # 2. Carrega configs salvas e aplica no sensor_core
    limite   = data_logger.carregar_config("limite_g", 2.5)
    offset   = data_logger.carregar_config("calibracao_offset", 0.0)
    silence  = bool(data_logger.carregar_config("modo_silencioso", 0))
    sensor_core.atualizar_config("limite",            limite)
    sensor_core.atualizar_config("calibracao_offset", offset)
    sensor_core.atualizar_config("modo_silencioso",   silence)

    # 3. Sensores — inicia thread de leitura contínua
    sensor_core.iniciar()

    # 4. MQTT — conecta ao Mosquitto e inicia publicação
    mqtt_publisher.iniciar()

    # 5. Tratamento de encerramento (Ctrl+C)
    def encerrar(sig, frame):
        print("\n[MAIN] Encerrando...")
        mqtt_publisher.encerrar()
        sensor_core.encerrar()
        sys.exit(0)

    signal.signal(signal.SIGINT,  encerrar)
    signal.signal(signal.SIGTERM, encerrar)

    # 6. Display touchscreen — bloqueia até fechar a janela
    display_ui.iniciar()

if __name__ == "__main__":
    main()
