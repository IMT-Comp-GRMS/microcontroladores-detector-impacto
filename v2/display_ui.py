"""
display_ui.py — ImpactOS Monitor v2.0
Interface touchscreen para o Raspberry Pi 7" Display (800x480)

Telas:
  - HOME: status em tempo real (G, GPS, IP, impactos)
  - CONFIG: limite de impacto, modo silencioso, calibração, cooldown
  - LOG: histórico de impactos da sessão

Dependências:
    pip install pillow
    tkinter já incluso no Raspberry Pi OS
"""

import tkinter as tk
from tkinter import font as tkfont
import threading
import time
import socket
from datetime import datetime

import sensor_core
import data_logger

# ─── CONFIGURAÇÕES VISUAIS ────────────────────────────────────────────────────

LARGURA  = 800
ALTURA   = 480

# Paleta de cores (mesmo tema do dashboard web)
COR = {
    "bg":        "#0a0c0f",
    "surface":   "#111318",
    "surface2":  "#181c23",
    "border":    "#1e2530",
    "accent":    "#f0a500",
    "ok":        "#00d68f",
    "danger":    "#ff2d2d",
    "text":      "#c8d6e8",
    "text_dim":  "#5a6880",
    "warn":      "#e05c00",
}

PRESETS = {
    "Frágil":     1.0,
    "Comum":      2.5,
    "Resistente": 5.0,
}

# ─── APLICAÇÃO PRINCIPAL ──────────────────────────────────────────────────────

class ImpactOSApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ImpactOS")
        self.geometry(f"{LARGURA}x{ALTURA}")
        self.configure(bg=COR["bg"])
        self.resizable(False, False)

        # Tela cheia no Pi
        self.attributes("-fullscreen", True)
        self.bind("<Escape>", lambda e: self.attributes("-fullscreen", False))

        # Fontes
        self.f_mono  = tkfont.Font(family="Courier", size=10)
        self.f_small = tkfont.Font(family="Courier", size=9)
        self.f_big   = tkfont.Font(family="Courier", size=48, weight="bold")
        self.f_med   = tkfont.Font(family="Courier", size=20, weight="bold")
        self.f_title = tkfont.Font(family="Courier", size=12, weight="bold")
        self.f_btn   = tkfont.Font(family="Courier", size=13, weight="bold")

        # Estado da UI
        self.tela_atual = "home"
        self.limite_temp = tk.DoubleVar(
            value=data_logger.carregar_config("limite_g", 2.5)
        )
        self.impactos_recentes = []  # cache para a tela de log

        # Container de telas
        self.container = tk.Frame(self, bg=COR["bg"])
        self.container.pack(fill="both", expand=True)

        self._construir_header()
        self._construir_telas()
        self._mostrar_tela("home")

        # Registra callback de impacto
        sensor_core.registrar_callback_impacto(self._on_impacto)

        # Inicia loop de atualização da UI
        self._atualizar_ui()

    # ── HEADER ────────────────────────────────────────────────────────────────

    def _construir_header(self):
        hdr = tk.Frame(self, bg=COR["surface"], height=48)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="ImpactOS", font=self.f_title,
                 bg=COR["surface"], fg=COR["accent"]).pack(side="left", padx=16)

        # Botões de navegação
        for nome, tela in [("HOME", "home"), ("CONFIG", "config"), ("LOG", "log")]:
            tk.Button(
                hdr, text=nome, font=self.f_small,
                bg=COR["surface"], fg=COR["text_dim"],
                activebackground=COR["accent"], activeforeground=COR["bg"],
                relief="flat", bd=0, padx=12, pady=4,
                command=lambda t=tela: self._mostrar_tela(t)
            ).pack(side="left", padx=4)

        # IP e relógio
        self.lbl_ip    = tk.Label(hdr, text="IP: ---", font=self.f_small,
                                   bg=COR["surface"], fg=COR["text_dim"])
        self.lbl_ip.pack(side="right", padx=16)

        self.lbl_clock = tk.Label(hdr, text="", font=self.f_small,
                                   bg=COR["surface"], fg=COR["text_dim"])
        self.lbl_clock.pack(side="right", padx=8)

    # ── TELAS ─────────────────────────────────────────────────────────────────

    def _construir_telas(self):
        self.telas = {}
        for nome in ("home", "config", "log"):
            f = tk.Frame(self.container, bg=COR["bg"])
            f.place(x=0, y=0, width=LARGURA, height=ALTURA - 48)
            self.telas[nome] = f

        self._construir_home()
        self._construir_config()
        self._construir_log()

    def _mostrar_tela(self, nome):
        self.tela_atual = nome
        for n, f in self.telas.items():
            f.lift() if n == nome else f.lower()
        if nome == "log":
            self._atualizar_log()

    # ── TELA HOME ─────────────────────────────────────────────────────────────

    def _construir_home(self):
        f = self.telas["home"]

        # G-meter — coluna esquerda
        col_g = tk.Frame(f, bg=COR["surface"], width=280)
        col_g.pack(side="left", fill="y", padx=(8,4), pady=8)
        col_g.pack_propagate(False)

        tk.Label(col_g, text="G TOTAL", font=self.f_small,
                 bg=COR["surface"], fg=COR["text_dim"]).pack(pady=(16,0))

        self.lbl_g = tk.Label(col_g, text="0.00", font=self.f_big,
                               bg=COR["surface"], fg=COR["ok"])
        self.lbl_g.pack()

        tk.Label(col_g, text="G", font=self.f_mono,
                 bg=COR["surface"], fg=COR["text_dim"]).pack()

        # Barra de progresso G
        self.canvas_bar = tk.Canvas(col_g, width=240, height=10,
                                     bg=COR["surface2"], highlightthickness=0)
        self.canvas_bar.pack(pady=8)
        self.bar_rect = self.canvas_bar.create_rectangle(0,0,0,10, fill=COR["ok"])

        # Eixos
        eixos = tk.Frame(col_g, bg=COR["surface"])
        eixos.pack(fill="x", padx=8)
        self.lbl_ax = self._eixo(eixos, "X")
        self.lbl_ay = self._eixo(eixos, "Y")
        self.lbl_az = self._eixo(eixos, "Z")

        # Limite
        self.lbl_limite_home = tk.Label(
            col_g, text="LIMITE: 2.5G", font=self.f_small,
            bg=COR["surface2"], fg=COR["accent"], pady=6
        )
        self.lbl_limite_home.pack(fill="x", padx=8, pady=(12,0))

        # Coluna direita — status
        col_info = tk.Frame(f, bg=COR["bg"])
        col_info.pack(side="left", fill="both", expand=True, padx=(4,8), pady=8)

        # GPS
        gps_frame = tk.Frame(col_info, bg=COR["surface"])
        gps_frame.pack(fill="x", pady=(0,6))
        tk.Label(gps_frame, text="// GPS", font=self.f_small,
                 bg=COR["surface"], fg=COR["text_dim"]).pack(anchor="w", padx=10, pady=(8,2))
        self.lbl_lat  = self._info_row(gps_frame, "LAT")
        self.lbl_lng  = self._info_row(gps_frame, "LNG")
        self.lbl_alt  = self._info_row(gps_frame, "ALT")
        self.lbl_sat  = self._info_row(gps_frame, "SAT")

        # Sessão
        ses_frame = tk.Frame(col_info, bg=COR["surface"])
        ses_frame.pack(fill="x", pady=(0,6))
        tk.Label(ses_frame, text="// SESSÃO", font=self.f_small,
                 bg=COR["surface"], fg=COR["text_dim"]).pack(anchor="w", padx=10, pady=(8,2))
        self.lbl_impactos = self._info_row(ses_frame, "IMPACTOS", COR["danger"])
        self.lbl_pico     = self._info_row(ses_frame, "PICO G",   COR["accent"])
        self.lbl_uptime   = self._info_row(ses_frame, "UPTIME")
        self.lbl_amostras = self._info_row(ses_frame, "AMOSTRAS")

        # Status silencioso
        self.lbl_silencioso = tk.Label(col_info, text="", font=self.f_small,
                                        bg=COR["bg"], fg=COR["warn"])
        self.lbl_silencioso.pack(anchor="w", padx=4)

    def _eixo(self, parent, label):
        f = tk.Frame(parent, bg=COR["surface2"], bd=0)
        f.pack(side="left", expand=True, padx=2, pady=4)
        tk.Label(f, text=label, font=self.f_small, bg=COR["surface2"],
                 fg=COR["text_dim"], width=3).pack()
        lbl = tk.Label(f, text="0.00", font=self.f_mono, bg=COR["surface2"],
                       fg=COR["text"], width=5)
        lbl.pack()
        return lbl

    def _info_row(self, parent, label, cor=None):
        f = tk.Frame(parent, bg=COR["surface"])
        f.pack(fill="x", padx=10, pady=1)
        tk.Label(f, text=label, font=self.f_small, width=10, anchor="w",
                 bg=COR["surface"], fg=COR["text_dim"]).pack(side="left")
        lbl = tk.Label(f, text="---", font=self.f_mono, anchor="w",
                       bg=COR["surface"], fg=cor or COR["text"])
        lbl.pack(side="left")
        return lbl

    # ── TELA CONFIG ───────────────────────────────────────────────────────────

    def _construir_config(self):
        f = self.telas["config"]

        tk.Label(f, text="// CONFIGURAÇÕES", font=self.f_title,
                 bg=COR["bg"], fg=COR["text_dim"]).pack(anchor="w", padx=16, pady=(12,4))

        # ── LIMITE DE IMPACTO ──
        sec_limite = tk.Frame(f, bg=COR["surface"])
        sec_limite.pack(fill="x", padx=16, pady=4)

        tk.Label(sec_limite, text="LIMITE DE IMPACTO",
                 font=self.f_title, bg=COR["surface"], fg=COR["accent"]
                 ).pack(anchor="w", padx=12, pady=(8,4))

        # Botões preset
        btn_frame = tk.Frame(sec_limite, bg=COR["surface"])
        btn_frame.pack(fill="x", padx=12, pady=4)

        for nome, valor in PRESETS.items():
            tk.Button(
                btn_frame, text=f"{nome}\n{valor}G",
                font=self.f_small, width=10, height=2,
                bg=COR["surface2"], fg=COR["text"],
                activebackground=COR["accent"], activeforeground=COR["bg"],
                relief="flat", bd=1,
                command=lambda v=valor: self._aplicar_limite(v)
            ).pack(side="left", padx=4)

        # Personalizado
        custom_frame = tk.Frame(sec_limite, bg=COR["surface"])
        custom_frame.pack(fill="x", padx=12, pady=(4,8))

        tk.Label(custom_frame, text="PERSONALIZADO:",
                 font=self.f_small, bg=COR["surface"], fg=COR["text_dim"]
                 ).pack(side="left")

        tk.Button(custom_frame, text="  −  ", font=self.f_btn,
                  bg=COR["surface2"], fg=COR["text"], relief="flat",
                  command=lambda: self._ajustar_limite(-0.5)
                  ).pack(side="left", padx=6)

        self.lbl_limite_config = tk.Label(
            custom_frame, textvariable=self.limite_temp,
            font=self.f_med, bg=COR["surface"], fg=COR["accent"], width=5
        )
        self.lbl_limite_config.pack(side="left")

        tk.Label(custom_frame, text="G", font=self.f_mono,
                 bg=COR["surface"], fg=COR["text_dim"]).pack(side="left")

        tk.Button(custom_frame, text="  +  ", font=self.f_btn,
                  bg=COR["surface2"], fg=COR["text"], relief="flat",
                  command=lambda: self._ajustar_limite(+0.5)
                  ).pack(side="left", padx=6)

        tk.Button(custom_frame, text="✓ CONFIRMAR", font=self.f_btn,
                  bg=COR["accent"], fg=COR["bg"], relief="flat", padx=8,
                  command=lambda: self._aplicar_limite(self.limite_temp.get())
                  ).pack(side="left", padx=12)

        # ── OUTRAS CONFIGURAÇÕES ──
        sec_outros = tk.Frame(f, bg=COR["surface"])
        sec_outros.pack(fill="x", padx=16, pady=4)

        tk.Label(sec_outros, text="OUTRAS CONFIGURAÇÕES",
                 font=self.f_title, bg=COR["surface"], fg=COR["accent"]
                 ).pack(anchor="w", padx=12, pady=(8,4))

        linha_outros = tk.Frame(sec_outros, bg=COR["surface"])
        linha_outros.pack(fill="x", padx=12, pady=(4,8))

        # Modo silencioso
        self.btn_silencioso = tk.Button(
            linha_outros, text="🔇 MODO SILENCIOSO: OFF",
            font=self.f_small, bg=COR["surface2"], fg=COR["text"],
            relief="flat", bd=1, padx=10, pady=8,
            command=self._toggle_silencioso
        )
        self.btn_silencioso.pack(side="left", padx=4)

        # Calibrar sensor
        self.btn_calibrar = tk.Button(
            linha_outros, text="⚖ CALIBRAR SENSOR",
            font=self.f_small, bg=COR["surface2"], fg=COR["text"],
            relief="flat", bd=1, padx=10, pady=8,
            command=self._calibrar
        )
        self.btn_calibrar.pack(side="left", padx=4)

        # Feedback de calibração
        self.lbl_calib_status = tk.Label(
            sec_outros, text="", font=self.f_small,
            bg=COR["surface"], fg=COR["ok"]
        )
        self.lbl_calib_status.pack(anchor="w", padx=12, pady=(0,8))

    def _ajustar_limite(self, delta):
        novo = round(self.limite_temp.get() + delta, 1)
        novo = max(0.5, min(20.0, novo))
        self.limite_temp.set(novo)

    def _aplicar_limite(self, valor):
        valor = round(float(valor), 1)
        self.limite_temp.set(valor)
        sensor_core.atualizar_config("limite", valor)
        data_logger.salvar_config("limite_g", valor)
        self.lbl_limite_home.config(text=f"LIMITE: {valor}G")
        print(f"[UI] Limite atualizado: {valor}G")

    def _toggle_silencioso(self):
        atual = sensor_core.estado["modo_silencioso"]
        novo = not atual
        sensor_core.atualizar_config("modo_silencioso", novo)
        data_logger.salvar_config("modo_silencioso", int(novo))
        texto = "🔇 MODO SILENCIOSO: ON" if novo else "🔇 MODO SILENCIOSO: OFF"
        cor   = COR["warn"] if novo else COR["text"]
        self.btn_silencioso.config(text=texto, fg=cor)

    def _calibrar(self):
        self.lbl_calib_status.config(text="Calibrando... mantenha o sensor em repouso.",
                                      fg=COR["accent"])
        self.btn_calibrar.config(state="disabled")

        def _exec():
            offset = sensor_core.calibrar_sensor()
            data_logger.salvar_config("calibracao_offset", offset)
            self.lbl_calib_status.config(
                text=f"Calibrado! Offset: {offset:+.4f}G",
                fg=COR["ok"]
            )
            self.btn_calibrar.config(state="normal")

        threading.Thread(target=_exec, daemon=True).start()

    # ── TELA LOG ──────────────────────────────────────────────────────────────

    def _construir_log(self):
        f = self.telas["log"]

        hdr = tk.Frame(f, bg=COR["bg"])
        hdr.pack(fill="x", padx=16, pady=(12,4))
        tk.Label(hdr, text="// HISTÓRICO DE IMPACTOS", font=self.f_title,
                 bg=COR["bg"], fg=COR["text_dim"]).pack(side="left")
        tk.Button(hdr, text="↻ ATUALIZAR", font=self.f_small,
                  bg=COR["surface2"], fg=COR["text_dim"], relief="flat",
                  command=self._atualizar_log).pack(side="right")

        # Cabeçalho da tabela
        cols = [("#", 4), ("HORÁRIO", 14), ("G PICO", 8),
                ("X/Y/Z", 18), ("COORDENADAS", 22), ("SEV", 8)]
        cab = tk.Frame(f, bg=COR["border"])
        cab.pack(fill="x", padx=16)
        for texto, w in cols:
            tk.Label(cab, text=texto, font=self.f_small, width=w, anchor="w",
                     bg=COR["border"], fg=COR["text_dim"], pady=4
                     ).pack(side="left", padx=2)

        # Área scrollável
        self.frame_log = tk.Frame(f, bg=COR["bg"])
        self.frame_log.pack(fill="both", expand=True, padx=16, pady=(0,8))

    def _atualizar_log(self):
        for w in self.frame_log.winfo_children():
            w.destroy()

        impactos = data_logger.carregar_impactos(limite=20)
        if not impactos:
            tk.Label(self.frame_log, text="[ NENHUM IMPACTO REGISTRADO ]",
                     font=self.f_mono, bg=COR["bg"], fg=COR["text_dim"]
                     ).pack(pady=20)
            return

        cores_sev = {"low": COR["accent"], "medium": COR["warn"], "high": COR["danger"]}

        for i, row in enumerate(impactos):
            bg = COR["surface"] if i % 2 == 0 else COR["surface2"]
            linha = tk.Frame(self.frame_log, bg=bg)
            linha.pack(fill="x", pady=1)

            sev = row.get("severidade", "low")
            cor_sev = cores_sev.get(sev, COR["text"])

            dados = [
                (f"#{i+1}", 4, COR["text_dim"]),
                (row.get("timestamp","")[-8:], 14, COR["text"]),
                (f"{float(row.get('g_pico',0)):.2f}G", 8, COR["accent"]),
                (f"{float(row.get('ax',0)):.1f}/{float(row.get('ay',0)):.1f}/{float(row.get('az',0)):.1f}", 18, COR["text"]),
                (f"{row.get('lat','')} {row.get('lng','')}", 22, COR["text_dim"]),
                (sev.upper(), 8, cor_sev),
            ]
            for texto, w, cor in dados:
                tk.Label(linha, text=texto, font=self.f_small, width=w,
                         anchor="w", bg=bg, fg=cor, pady=5
                         ).pack(side="left", padx=2)

    # ── ATUALIZAÇÃO PERIÓDICA DA UI ───────────────────────────────────────────

    def _atualizar_ui(self):
        try:
            e = sensor_core.ler_estado()

            # G-meter
            g = e["g_total"]
            limite = e["limite"]
            cor_g = COR["danger"] if g > limite else COR["warn"] if g > limite * 0.75 else COR["ok"]
            self.lbl_g.config(text=f"{g:.2f}", fg=cor_g)
            self.lbl_ax.config(text=f"{e['ax']:.2f}")
            self.lbl_ay.config(text=f"{e['ay']:.2f}")
            self.lbl_az.config(text=f"{e['az']:.2f}")

            # Barra
            pct = min(g / max(limite * 1.5, 5), 1.0)
            self.canvas_bar.coords(self.bar_rect, 0, 0, int(240 * pct), 10)
            self.canvas_bar.itemconfig(self.bar_rect, fill=cor_g)

            # GPS
            self.lbl_lat.config(text=f"{e['lat']:.6f}" if e["lat"] else "---")
            self.lbl_lng.config(text=f"{e['lng']:.6f}" if e["lng"] else "---")
            self.lbl_alt.config(text=f"{e['alt']:.0f} m")
            self.lbl_sat.config(
                text=str(e["sat"]),
                fg=COR["ok"] if e["gps_ok"] else COR["text_dim"]
            )

            # Sessão
            self.lbl_impactos.config(text=str(e["impactos_sessao"]))
            self.lbl_pico.config(text=f"{e['pico_sessao']:.2f}G")
            s = int((datetime.now() - e["inicio_sessao"]).total_seconds())
            self.lbl_uptime.config(text=f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}")
            self.lbl_amostras.config(text=str(e["amostras"]))

            # Silencioso
            self.lbl_silencioso.config(
                text="🔇 MODO SILENCIOSO ATIVO" if e["modo_silencioso"] else ""
            )

            # Limite na home
            self.lbl_limite_home.config(text=f"LIMITE: {limite:.1f}G")

            # IP e relógio
            self.lbl_clock.config(text=datetime.now().strftime("%H:%M:%S"))
            try:
                ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                ip = "---"
            self.lbl_ip.config(text=f"IP: {ip}")

            # Salva leitura no CSV
            data_logger.salvar_leitura(e)

        except Exception as ex:
            print(f"[UI] Erro na atualização: {ex}")

        self.after(200, self._atualizar_ui)   # atualiza a cada 200ms

    def _on_impacto(self, snapshot):
        """Chamado pela thread de sensores quando impacto é detectado."""
        data_logger.salvar_impacto(snapshot)
        # Flash visual na tela home
        self.after(0, lambda: self._flash_impacto(snapshot["g_pico"]))

    def _flash_impacto(self, g):
        self.lbl_g.config(fg=COR["danger"])
        self.after(300, lambda: self.lbl_g.config(
            fg=COR["danger"] if g > sensor_core.estado["limite"] else COR["ok"]
        ))

# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

def iniciar():
    # Carrega configs salvas antes de iniciar os sensores
    limite  = data_logger.carregar_config("limite_g", 2.5)
    offset  = data_logger.carregar_config("calibracao_offset", 0.0)
    silence = bool(data_logger.carregar_config("modo_silencioso", 0))
    cooldown = data_logger.carregar_config("cooldown", 3.0)

    sensor_core.atualizar_config("limite",             limite)
    sensor_core.atualizar_config("calibracao_offset",  offset)
    sensor_core.atualizar_config("modo_silencioso",    silence)
    sensor_core.COOLDOWN_IMPACTO = cooldown

    app = ImpactOSApp()
    app.mainloop()
