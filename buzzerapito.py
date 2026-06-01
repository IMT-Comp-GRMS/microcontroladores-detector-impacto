from machine import Pin
import time

# Configura o pino GP15 como uma porta de saída de energia (OUT)
buzzer = Pin(15, Pin.OUT)

def disparar_alarme():
    print("Alarme ativado! Apitando...")
    buzzer.value(1)  # Manda energia (Liga o buzzer)
    time.sleep(1)    # Mantém o som por 1 segundo
    
    print("Alarme desativado.")
    buzzer.value(0)  # Corta a energia (Desliga o buzzer)

# Chama a função para testar
disparar_alarme()
