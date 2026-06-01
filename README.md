# ImpactOS Monitor

Sistema embarcado de detecção e monitoramento de impactos em tempo real, desenvolvido com Raspberry Pi Pico e transmissão de dados via Bluetooth Low Energy (BLE).

---

## Sobre o Projeto

O ImpactOS é um sistema de monitoramento contínuo de aceleração que detecta impactos acima de um limite configurado, registra a localização GPS do evento e transmite os dados em tempo real para um dashboard web via Bluetooth. O projeto foi desenvolvido como um sistema embarcado compacto, projetado para ser instalado em uma caixa MDF com corte a laser.

Ao detectar um impacto, o sistema:
- Captura a força do impacto em G (múltiplos da gravidade) nos três eixos
- Registra as coordenadas GPS do momento do evento
- Transmite os dados via BLE para o dashboard web
- Aciona um alarme sonoro com o buzzer

---

## Hardware

| Componente | Modelo | Função |
|---|---|---|
| Microcontrolador | Raspberry Pi Pico (RP2040) | Processamento central |
| Acelerômetro | MPU-6050 (GY-521) | Leitura de aceleração ±8G |
| GPS | GY-NEO6MV2 (NEO-6M) | Localização com antena externa |
| Bluetooth | RC-HC08-17D1 (BLE 4.0) | Transmissão de dados |
| Buzzer | Buzzer ativo 5V | Alarme sonoro |
| Alimentação | Bateria 18650 + LDO AMS1117-3.3 | Fonte embarcada 3.3V |

### Pinagem

| Pino Pico | Pino Físico | Periférico | Função |
|---|---|---|---|
| GP0 | 1 | GPS NEO-6M | UART TX |
| GP1 | 2 | GPS NEO-6M | UART RX (TX do GPS) |
| GP2 | 4 | MPU-6050 | I2C SDA |
| GP3 | 5 | MPU-6050 | I2C SCL |
| GP4 | 6 | HC-08 | UART TX → BLE RX |
| GP5 | 7 | HC-08 | UART RX ← BLE TX |
| GP15 | 20 | Buzzer | Sinal PWM |
| 3V3 OUT | 36 | GPS, MPU, HC-08 | Alimentação 3.3V |
| VSYS | 39 | LDO AMS1117 | Entrada alimentação |
| GND | 3,8,13,18,23,28,33,38 | Todos | Terra |

---

## Software

### Firmware — MicroPython (`impact_monitor.py`)

Desenvolvido em MicroPython para o Raspberry Pi Pico. O loop principal opera a ~3.3 amostras por segundo com a seguinte cadência:

1. **Leitura GPS** — processamento não-bloqueante do buffer UART, parseando sentenças NMEA `$GPRMC` (posição + validade) e `$GPGGA` (altitude + satélites)
2. **Leitura do acelerômetro** — leitura dos 6 registradores do MPU-6050 via I2C, conversão de complemento de dois para float em G, cálculo da magnitude vetorial `√(X²+Y²+Z²)`
3. **Transmissão contínua** — envio de linha `MONITOR|...` pelo BLE a cada ciclo
4. **Detecção de impacto** — se magnitude > limite e cooldown expirado, dispara alarme sonoro e envia linha `IMPACT|...`

#### Protocolo de Dados

Mensagem de monitoramento contínuo:
```
MONITOR|G:1.02|AX:0.10|AY:-0.05|AZ:0.98|LAT:-23.550500|LNG:-46.633300|ALT:760.0|SAT:6|GPS:OK|THR:2.50
```

Mensagem de impacto detectado:
```
IMPACT|G:3.50|AX:1.20|AY:2.10|AZ:0.80|LAT:-23.550500|LNG:-46.633300|ALT:760.0
```

#### Configuração principal

```python
LIMITE_DE_IMPACTO = 2.5   # G — limite para disparo do alarme
COOLDOWN_IMPACTO  = 3.0   # segundos entre detecções
STATUS_INTERVALO  = 0.3   # segundos entre leituras
```

### Dashboard Web (`impact-dashboard.html`)

Interface web desenvolvida em HTML/CSS/JavaScript puro, sem dependências de servidor ou framework. Conecta ao HC-08 diretamente pelo navegador usando a **Web Bluetooth API**.

**Funcionalidades:**
- Conexão BLE direta sem pareamento prévio no sistema operacional
- G-meter em tempo real com indicação visual por cor (verde → laranja → vermelho)
- Gráfico de aceleração dos últimos ~12 segundos
- Indicação dos três eixos (X, Y, Z) individualmente
- Mapa interativo (OpenStreetMap) com marcação do último impacto
- Histórico de impactos com horário, força em G, coordenadas e severidade (LOW / MEDIUM / HIGH)
- Limite de impacto sincronizado automaticamente do firmware via campo `THR:`
- Modo simulação para testes sem hardware
- Layout responsivo para uso em dispositivos móveis e desktop

**Compatibilidade:** Chrome e Edge no desktop. No iOS, requer o app **Bluefy** ou **WebBLE** pois o Safari não suporta a Web Bluetooth API.

---

## Licença

Este projeto foi desenvolvido para fins acadêmicos.
