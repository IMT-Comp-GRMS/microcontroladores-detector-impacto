import machine 
import math
import time

# --- CONFIGURAÇÃO DO BUZZER (Pino GP15) ---
buzzer = machine.PWM(machine.Pin(15)) # indica onde o buzzer esta localizado
buzzer.duty_u16(0) # Garante que comece mudo

def disparar_alarme():
    print("⚠️ ALARME: IMPACTO DETECTADO! ⚠️")
    buzzer.freq(1000)      # Frequência do apito
    buzzer.duty_u16(32768) # Volume em 50% (32768 é metade da capacidade de energia da placa)
    time.sleep(2)          # Apita por 2 segundos, garante que ele não ligue e desligue hiper rápido
    buzzer.duty_u16(0)     # Desliga o apito
    print("Sistema rearmado. Monitorando...")

# --- CONFIGURAÇÃO DO MPU 6050 (Pinos GP0 e GP1) ---
i2c = machine.I2C(0, sda=machine.Pin(0), scl=machine.Pin(1), freq=400000)
MPU_ADDR = 0x68

# Acorda o sensor
try:
    i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')
    print("MPU 6050 acordado e monitorando!")
except OSError:
    print("Erro: MPU 6050 não encontrado.")

def ler_magnitude():
    # Lê os dados brutos do sensor
    dados = i2c.readfrom_mem(MPU_ADDR, 0x3B, 6)
    
    def converte(high, low):
        val = (high << 8) + low
        if val >= 0x8000:
            val = -((65535 - val) + 1)
        return val
        
    x = converte(dados[0], dados[1]) / 16384.0
    y = converte(dados[2], dados[3]) / 16384.0
    z = converte(dados[4], dados[5]) / 16384.0
    
    # Aplica a fórmula da magnitude total
    magnitude = math.sqrt(x**2 + y**2 + z**2) # pitágoras
    return magnitude

# --- LOOP PRINCIPAL DO DISPOSITIVO ---
# Defina aqui a sua linha de corte (em força G)
LIMITE_DE_IMPACTO = 3.0  

print("Deixe o dispositivo parado. Pronto para teste de impacto!")

while True:
    try:
        # Lê a força G total naquele instante
        forca_total = ler_magnitude()
        
        # Se a força for maior que o nosso limite, dispara o alarme!
        if forca_total > LIMITE_DE_IMPACTO:
            print(f"Pico de força registrado: {forca_total:.2f}g")
            disparar_alarme()
            
        time.sleep(0.05) # Lê o sensor super rápido (20 vezes por segundo)
        
    except Exception as e:
        pass
