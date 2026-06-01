import machine
import math
import time

# --- 1. CONFIGURAÇÃO DO BLUETOOTH (HM10) ---
# Configura a comunicação nos pinos GP4 (TX) e GP5 (RX) com a velocidade padrão do módulo
# bluetooth = machine.UART(1, baudrate=38400, tx=machine.Pin(4), rx=machine.Pin(5))
bluetooth = machine.UART(1, baudrate=9600, tx=machine.Pin(4), rx=machine.Pin(5))

# --- 2. CONFIGURAÇÃO DO BUZZER ---
buzzer = machine.PWM(machine.Pin(15))
buzzer.duty_u16(0)

# Atualizamos a função para receber a força e enviar pelo Bluetooth
def disparar_alarme(forca_do_impacto):
    print("⚠️ ALARME: IMPACTO DETECTADO! ⚠️")
    
    # 1º Passo: Dispara o aviso para o celular pelo ar
   # Adicionamos o \r\n (Enter) para forçar o app a mostrar a tela
    mensagem = f"ALERTA! Queda de {forca_do_impacto:.2f}G detectada!\r\n"
    
    # O .encode('utf-8') transforma o texto em bytes para a placa conseguir enviar
    bluetooth.write(mensagem.encode('utf-8'))
    
    # 2º Passo: Apita o buzzer no local
    buzzer.freq(1000)
    buzzer.duty_u16(32768)
    time.sleep(2)
    buzzer.duty_u16(0)
    print("Sistema rearmado. Monitorando...")

# --- 3. CONFIGURAÇÃO DO MPU 6050 ---
i2c = machine.I2C(1, sda=machine.Pin(2), scl=machine.Pin(3), freq=400000)
MPU_ADDR = 0x68

try:
    i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')
except OSError:
    print("Erro: MPU 6050 não encontrado.")

def ler_magnitude():
    dados = i2c.readfrom_mem(MPU_ADDR, 0x3B, 6)
    def converte(high, low):
        val = (high << 8) + low
        if val >= 0x8000:
            val = -((65535 - val) + 1)
        return val
    x = converte(dados[0], dados[1]) / 16384.0
    y = converte(dados[2], dados[3]) / 16384.0
    z = converte(dados[4], dados[5]) / 16384.0
    return math.sqrt(x**2 + y**2 + z**2)

# --- 4. LOOP PRINCIPAL ---
LIMITE_DE_IMPACTO = 2.0

print("Sistema completo rodando! Aguardando impactos...")

while True:
    try:
        forca_total = ler_magnitude()
        print(f"Monitorando... Força: {forca_total:.2f}g")
        bluetooth.write(f"Monitorando... Força: {forca_total:.2f}g\r\n".encode('utf-8'))
        
        # Se passar do limite, chama a função passando a força exata do impacto!
        if forca_total > LIMITE_DE_IMPACTO:
            disparar_alarme(forca_total)
            
        time.sleep(0.3) 
        
    except Exception as e:
        print("⚠️ Erro na leitura do sensor:", e)
        time.sleep(1)
        
