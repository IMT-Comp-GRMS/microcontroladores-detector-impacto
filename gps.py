import machine
import time

# Configura a UART 0 para o GPS (Pinos 0 e 1)
gps_serial = machine.UART(0, baudrate=9600, tx=machine.Pin(0), rx=machine.Pin(1))

print("--- DIAGNÓSTICO GPS NEO-6M ---")
print("Lendo dados brutos (NMEA)...")

while True:
    if gps_serial.any():
        dados = gps_serial.read()
        try:
            # Decodifica os bytes para texto
            linha = dados.decode('utf-8').strip()
            if linha.startswith('$GPRMC') or linha.startswith('$GPGGA'):
                print(linha)
        except:
            pass
    time.sleep(0.1)
