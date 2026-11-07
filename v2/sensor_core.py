"""
sensor_core.py — ImpactOS Monitor v2.0
Raspberry Pi 4 + MPU-6050 + GPS NEO-6M + Buzzer

Substitui o firmware MicroPython do Pico.
Roda em Python 3 no Raspberry Pi OS (Linux).

Dependências:
    pip install smbus2 pyserial RPi.GPIO
"""

import math
import time
import threading
import smbus2
import serial
import RPi.GPIO as GPIO
from datetime import datetime

# ─── CONFIGURAÇÕES ────────────────────────────────────────────────────────────

# Limite de impacto padrão (G) — pode ser alterado pelo display
LIMITE_IMPACTO   = 2.5
COOLDOWN_IMPACTO = 3.0    # segundos entre detecções
INTERVALO_LEITURA = 0.1   # segundos entre amostras (10 Hz)

# MPU-6050
MPU_ADDR   = 0x69             # AD0 ligado ao 3V3 (com AD0 no GND seria 0x68)
I2C_BUS    = 1             # /dev/i2c-1 no Pi 4

# GPS NEO-6M
GPS_PORTA  = '/dev/ttyS0'  # UART0 no Pi 4 (GP14/GP15)
GPS_BAUD   = 9600

# Buzzer
BUZZER_PIN = 17            # BCM 17 = pino físico 11
                           # ajuste conforme sua soldagem

# ─── ESTADO GLOBAL ────────────────────────────────────────────────────────────
# Compartilhado entre threads — leitura segura via lock

_lock = threading.Lock()

estado = {
    # Acelerômetro
    "g_total": 0.0,
    "ax": 0.0,
    "ay": 0.0,
    "az": 0.0,
    # GPS
    "lat":     None,
    "lng":     None,
    "alt":     0.0,
    "sat":     0,
    "gps_ok":  False,
    # Sistema
    "limite":         LIMITE_IMPACTO,
    "modo_silencioso": False,
    "calibracao_offset": 0.0,   # G subtraídos da leitura bruta
    "ultimo_impacto": 0.0,      # timestamp do último impacto
    "impactos_sessao": 0,
    "pico_sessao":    0.0,
    "amostras":       0,
    "inicio_sessao":  datetime.now(),
    "rodando":        True,
}

# Callbacks registrados por outras camadas
_callbacks_impacto = []

def registrar_callback_impacto(fn):
    """Registra função a ser chamada a cada impacto detectado."""
    _callbacks_impacto.append(fn)

def ler_estado():
    """Retorna cópia segura do estado atual."""
    with _lock:
        return estado.copy()

def atualizar_config(chave, valor):
    """Atualiza uma configuração em tempo de execução."""
    with _lock:
        estado[chave] = valor

# ─── MPU-6050 ─────────────────────────────────────────────────────────────────

bus = None

def iniciar_mpu():
    global bus
    try:
        bus = smbus2.SMBus(I2C_BUS)
        # Sai do modo sleep
        bus.write_byte_data(MPU_ADDR, 0x6B, 0x00)
        time.sleep(0.1)
        # Range ±8G → 0x10 no registrador ACCEL_CONFIG (0x1C)
        # Sensibilidade: 4096 LSB/G
        bus.write_byte_data(MPU_ADDR, 0x1C, 0x10)
        print("[MPU] Iniciado — range ±8G")
        return True
    except Exception as e:
        print(f"[MPU] ERRO: {e}")
        return False

def ler_mpu():
    """Retorna (g_total, ax, ay, az) ou zeros em caso de erro."""
    if not bus:
        return 0.0, 0.0, 0.0, 0.0
    try:
        dados = bus.read_i2c_block_data(MPU_ADDR, 0x3B, 6)

        def conv(hi, lo):
            v = (hi << 8) | lo
            return -(65536 - v) / 4096.0 if v >= 0x8000 else v / 4096.0

        ax = conv(dados[0], dados[1])
        ay = conv(dados[2], dados[3])
        az = conv(dados[4], dados[5])

        # Aplica offset de calibração
        g = math.sqrt(ax**2 + ay**2 + az**2) - estado["calibracao_offset"]
        return max(0.0, g), ax, ay, az
    except Exception:
        return 0.0, 0.0, 0.0, 0.0

def calibrar_sensor():
    """
    Captura 20 leituras em repouso e calcula o offset.
    O valor ideal em repouso é 1.0G (gravidade).
    """
    print("[MPU] Calibrando...")
    amostras = []
    for _ in range(20):
        g, _, _, _ = ler_mpu()
        amostras.append(g)
        time.sleep(0.05)
    media = sum(amostras) / len(amostras)
    offset = media - 1.0   # diferença em relação ao 1G esperado
    atualizar_config("calibracao_offset", offset)
    print(f"[MPU] Calibração concluída — offset: {offset:.4f}G")
    return offset

# ─── GPS NEO-6M ───────────────────────────────────────────────────────────────

gps_serial = None

def iniciar_gps():
    global gps_serial
    try:
        gps_serial = serial.Serial(GPS_PORTA, GPS_BAUD, timeout=1)
        print(f"[GPS] Iniciado em {GPS_PORTA}")
        return True
    except Exception as e:
        print(f"[GPS] ERRO: {e}")
        return False

def nmea_para_decimal(valor, direcao):
    """Converte NMEA DDDMM.MMMM para graus decimais."""
    if not valor:
        return None
    try:
        p = valor.index('.')
        graus = int(valor[:p - 2])
        minutos = float(valor[p - 2:])
        dec = graus + minutos / 60.0
        return -dec if direcao in ('S', 'W') else dec
    except Exception:
        return None

def processar_gps():
    """Lê e processa sentenças NMEA disponíveis no buffer."""
    if not gps_serial or not gps_serial.in_waiting:
        return
    try:
        linhas = []
        while gps_serial.in_waiting:
            linha = gps_serial.readline().decode('utf-8', errors='ignore').strip()
            if linha:
                linhas.append(linha)

        for texto in linhas:
            partes = texto.split(',')

            # GPRMC — posição + validade
            if texto.startswith('$GPRMC') or texto.startswith('$GNRMC'):
                if len(partes) > 6 and partes[2] == 'A':
                    lat = nmea_para_decimal(partes[3], partes[4])
                    lng = nmea_para_decimal(partes[5], partes[6])
                    if lat and lng:
                        with _lock:
                            estado["lat"]    = lat
                            estado["lng"]    = lng
                            estado["gps_ok"] = True
                else:
                    with _lock:
                        estado["gps_ok"] = False

            # GPGGA — altitude + satélites
            elif texto.startswith('$GPGGA') or texto.startswith('$GNGGA'):
                if len(partes) > 9:
                    with _lock:
                        try:
                            estado["sat"] = int(partes[7]) if partes[7] else 0
                            estado["alt"] = float(partes[9]) if partes[9] else 0.0
                        except Exception:
                            pass
    except Exception:
        pass

# ─── BUZZER ───────────────────────────────────────────────────────────────────

_buzzer_pwm = None

def iniciar_buzzer():
    global _buzzer_pwm
    # setmode deve ser chamado uma vez antes de qualquer operação GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUZZER_PIN, GPIO.OUT)
    # Cria instância PWM — frequência inicial 1000 Hz, duty cycle 0 (desligado)
    # Equivalente ao machine.PWM do MicroPython (slide 23 do material EEN251)
    _buzzer_pwm = GPIO.PWM(BUZZER_PIN, 1000)
    _buzzer_pwm.start(0)   # duty cycle 0 = desligado
    print(f"[BUZZER] Iniciado com PWM no pino BCM {BUZZER_PIN}")

def bipe(frequencia=1000, duracao=0.15, repeticoes=3, intervalo=0.1):
    """
    Aciona o buzzer N vezes via PWM.
    Equivalente ao buzzer.freq() + buzzer.duty_u16() do MicroPython.
    Ignora se modo silencioso ativo.
    """
    if estado["modo_silencioso"] or not _buzzer_pwm:
        return
    def _bipe():
        _buzzer_pwm.ChangeFrequency(frequencia)   # equivalente a buzzer.freq()
        for _ in range(repeticoes):
            _buzzer_pwm.ChangeDutyCycle(50)        # 50% = ligado (equivale a duty_u16(32768))
            time.sleep(duracao)
            _buzzer_pwm.ChangeDutyCycle(0)         # 0% = desligado
            time.sleep(intervalo)
    threading.Thread(target=_bipe, daemon=True).start()

# ─── LOOP PRINCIPAL ───────────────────────────────────────────────────────────

def _loop_sensores():
    """Thread principal de leitura — roda a ~10Hz."""
    while estado["rodando"]:
        agora = time.time()

        # 1. GPS em background
        processar_gps()

        # 2. Acelerômetro
        g, ax, ay, az = ler_mpu()

        # 3. Atualiza estado
        with _lock:
            estado["g_total"] = g
            estado["ax"]      = ax
            estado["ay"]      = ay
            estado["az"]      = az
            estado["amostras"] += 1
            if g > estado["pico_sessao"]:
                estado["pico_sessao"] = g

        # 4. Detecção de impacto com cooldown
        cooldown_ok = (agora - estado["ultimo_impacto"]) >= COOLDOWN_IMPACTO
        if g >= estado["limite"] and cooldown_ok:
            with _lock:
                estado["ultimo_impacto"]   = agora
                estado["impactos_sessao"] += 1

            # Severidade
            limite = estado["limite"]
            if g > limite * 2:
                sev = "high"
            elif g > limite * 1.3:
                sev = "medium"
            else:
                sev = "low"

            snapshot = {
                "timestamp": datetime.now(),
                "g_pico":    g,
                "ax": ax, "ay": ay, "az": az,
                "lat":  estado["lat"],
                "lng":  estado["lng"],
                "alt":  estado["alt"],
                "severidade": sev,
            }

            # Buzzer
            bipe(duracao=0.15, repeticoes=3, intervalo=0.1)

            # Notifica todas as camadas registradas
            for fn in _callbacks_impacto:
                try:
                    fn(snapshot)
                except Exception as e:
                    print(f"[CORE] Erro em callback: {e}")

        time.sleep(INTERVALO_LEITURA)

def iniciar():
    """Inicializa todos os periféricos e inicia a thread de leitura."""
    ok_mpu    = iniciar_mpu()
    ok_gps    = iniciar_gps()
    iniciar_buzzer()

    if not ok_mpu:
        print("[CORE] AVISO: MPU-6050 não encontrado.")
    if not ok_gps:
        print("[CORE] AVISO: GPS não encontrado.")

    t = threading.Thread(target=_loop_sensores, daemon=True)
    t.start()
    print("[CORE] Loop de sensores iniciado.")
    return t

def encerrar():
    """Para o loop e libera recursos."""
    with _lock:
        estado["rodando"] = False
    # Para o PWM antes do cleanup — conforme boas práticas do material EEN251
    if _buzzer_pwm:
        _buzzer_pwm.stop()
    GPIO.cleanup()   # restaura todos os pinos ao estado anterior
    if gps_serial:
        gps_serial.close()
    print("[CORE] Encerrado.")
