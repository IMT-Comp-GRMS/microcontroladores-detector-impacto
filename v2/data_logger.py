"""
data_logger.py — ImpactOS Monitor v2.0
Salva leituras e impactos em arquivos CSV.

No 4º bimestre: substitua as funções _salvar_* por chamadas
à API do Google Sheets ou upload para servidor remoto.
"""

import csv
import os
import threading
from datetime import datetime
from pathlib import Path

# ─── CONFIGURAÇÃO ─────────────────────────────────────────────────────────────

PASTA_DADOS  = Path.home() / "impactos_data"
ARQ_IMPACTOS = PASTA_DADOS / "impactos.csv"
ARQ_LEITURAS = PASTA_DADOS / "leituras.csv"
ARQ_CONFIG   = PASTA_DADOS / "configuracoes.csv"

# Salva leitura contínua a cada N amostras (evita CSV gigante)
# 1 = toda amostra, 10 = a cada ~1s (com INTERVALO=0.1s)
LEITURAS_INTERVALO = 10

_lock = threading.Lock()
_contador_leituras = 0

# ─── CABEÇALHOS ───────────────────────────────────────────────────────────────

CABECALHO_IMPACTOS = [
    "timestamp", "g_pico", "ax", "ay", "az",
    "lat", "lng", "alt", "severidade"
]

CABECALHO_LEITURAS = [
    "timestamp", "g_total", "ax", "ay", "az",
    "lat", "lng", "alt", "sat", "gps_ok"
]

CABECALHO_CONFIG = ["chave", "valor"]

# ─── INICIALIZAÇÃO ────────────────────────────────────────────────────────────

def iniciar():
    """Cria a pasta e os arquivos CSV se não existirem."""
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    _criar_csv_se_nao_existe(ARQ_IMPACTOS, CABECALHO_IMPACTOS)
    _criar_csv_se_nao_existe(ARQ_LEITURAS, CABECALHO_LEITURAS)
    _criar_csv_se_nao_existe(ARQ_CONFIG,   CABECALHO_CONFIG)
    print(f"[LOGGER] Dados em: {PASTA_DADOS}")

def _criar_csv_se_nao_existe(caminho, cabecalho):
    if not caminho.exists():
        with open(caminho, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(cabecalho)

# ─── SALVAR IMPACTO ───────────────────────────────────────────────────────────

def salvar_impacto(snapshot: dict):
    """
    Chamado pelo sensor_core via callback a cada impacto.
    snapshot contém: timestamp, g_pico, ax, ay, az,
                     lat, lng, alt, severidade
    """
    linha = [
        snapshot["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
        f"{snapshot['g_pico']:.4f}",
        f"{snapshot['ax']:.4f}",
        f"{snapshot['ay']:.4f}",
        f"{snapshot['az']:.4f}",
        f"{snapshot['lat']:.6f}" if snapshot["lat"] else "",
        f"{snapshot['lng']:.6f}" if snapshot["lng"] else "",
        f"{snapshot['alt']:.1f}",
        snapshot["severidade"],
    ]
    _append_csv(ARQ_IMPACTOS, linha)
    print(f"[LOGGER] Impacto salvo — {snapshot['g_pico']:.2f}G ({snapshot['severidade']})")

# ─── SALVAR LEITURA CONTÍNUA ──────────────────────────────────────────────────

def salvar_leitura(estado: dict):
    """
    Chamado periodicamente com o estado atual dos sensores.
    Salva apenas a cada LEITURAS_INTERVALO amostras.
    """
    global _contador_leituras
    with _lock:
        _contador_leituras += 1
        if _contador_leituras % LEITURAS_INTERVALO != 0:
            return

    linha = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        f"{estado['g_total']:.4f}",
        f"{estado['ax']:.4f}",
        f"{estado['ay']:.4f}",
        f"{estado['az']:.4f}",
        f"{estado['lat']:.6f}"  if estado["lat"]  else "",
        f"{estado['lng']:.6f}"  if estado["lng"]  else "",
        f"{estado['alt']:.1f}",
        estado["sat"],
        1 if estado["gps_ok"] else 0,
    ]
    _append_csv(ARQ_LEITURAS, linha)

# ─── CONFIGURAÇÕES PERSISTENTES ───────────────────────────────────────────────

def salvar_config(chave: str, valor):
    """Salva ou atualiza uma configuração no CSV."""
    configs = carregar_todas_configs()
    configs[chave] = str(valor)

    with open(ARQ_CONFIG, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(CABECALHO_CONFIG)
        for k, v in configs.items():
            w.writerow([k, v])

def carregar_config(chave: str, padrao=None):
    """Lê uma configuração salva. Retorna padrao se não encontrar."""
    configs = carregar_todas_configs()
    val = configs.get(chave)
    if val is None:
        return padrao
    # Tenta converter para número
    try:
        return float(val) if '.' in val else int(val)
    except ValueError:
        return val

def carregar_todas_configs() -> dict:
    """Retorna dicionário com todas as configs salvas."""
    if not ARQ_CONFIG.exists():
        return {}
    configs = {}
    with open(ARQ_CONFIG, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            configs[row["chave"]] = row["valor"]
    return configs

# ─── LEITURA DO HISTÓRICO ─────────────────────────────────────────────────────

def carregar_impactos(limite=50) -> list:
    """
    Retorna os últimos N impactos como lista de dicionários.
    Usado pelo display local e pela API Flask.
    """
    if not ARQ_IMPACTOS.exists():
        return []
    with open(ARQ_IMPACTOS, 'r', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    return rows[-limite:][::-1]   # mais recentes primeiro

def total_impactos() -> int:
    """Retorna total de impactos registrados no CSV."""
    if not ARQ_IMPACTOS.exists():
        return 0
    with open(ARQ_IMPACTOS, 'r', encoding='utf-8') as f:
        return sum(1 for _ in csv.DictReader(f))

def caminho_impactos() -> str:
    """Retorna o caminho absoluto do CSV de impactos (para exportação)."""
    return str(ARQ_IMPACTOS)

def caminho_leituras() -> str:
    """Retorna o caminho absoluto do CSV de leituras."""
    return str(ARQ_LEITURAS)

# ─── UTILITÁRIO ───────────────────────────────────────────────────────────────

def _append_csv(caminho, linha):
    with _lock:
        with open(caminho, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(linha)
