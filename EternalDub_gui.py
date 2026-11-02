# SPDX-License-Identifier: MIT
# EternalDub - Copyright (C) 2026 Moguel0818 e colaboradores / and contributors
# -*- coding: utf-8 -*-
"""
EternalDub - interface grafica (inspirada no Subtitle Edit).

Janela:
  * esquerda ...... lista das dublagens (nome, origem, atraso, padrao) + editor da selecionada
  * direita ....... faixas do filme (o que entra no arquivo final) / emendas / registro (log)
  * embaixo ....... ondas sonoras: filme (verde) e dublagem (laranja) na mesma linha do tempo.
                    Roda do mouse = zoom; arraste a faixa laranja = muda o atraso; as emendas (linhas
                    vermelhas) se arrastam; clique na regua e aperte F8 para OUVIR dali.

O filme e montado SEM recodificar (copia dos fluxos).  Veja EternalDub_core.py.
Edicao das emendas: EternalDub_emendas.py. Previa de audio: EternalDub_audio.py.
Idiomas da interface: um arquivo .json por idioma na pasta idiomas/. Veja EternalDub_i18n.py.
Requisitos: Python 3.9+, numpy, PySide6, FFmpeg.
"""
import copy
import math
import os
import queue
import shutil
import sys
import threading
import time
import traceback
from pathlib import Path

try:
    from PySide6.QtCore import (Qt, QObject, QPoint, QThread, QTimer, Signal, QSettings, QUrl, QLocale, QTranslator,
                                QLibraryInfo)
    from PySide6.QtGui import (QAction, QActionGroup, QColor, QIcon, QPainter, QPalette, QPolygon, QDesktopServices,
                               QKeySequence)
    from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
                                   QDialogButtonBox, QDoubleSpinBox, QFileDialog, QGridLayout, QGroupBox,
                                   QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
                                   QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
                                   QProgressBar, QPushButton, QSlider, QSpinBox, QSplitter, QStyle,
                                   QTabWidget, QTableWidget, QTableWidgetItem, QToolBar,
                                   QVBoxLayout, QWidget)
except ImportError:
    print("Falta o PySide6 / PySide6 is missing:   python -m pip install PySide6 numpy")
    sys.exit(1)

try:                                    # tocar a previa (se este Qt nao tiver audio, o resto do programa funciona)
    from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QMediaDevices
    TEM_AUDIO = True
except Exception:
    TEM_AUDIO = False

import numpy as np

try:
    import EternalDub_i18n as i18n
    from EternalDub_i18n import tr, rot_conf, rot_metodo, rot_tipo
except ImportError:                     # sem o arquivo de idiomas: avisa (em portugues) em vez de quebrar
    i18n = None

    def tr(texto):
        return texto
    rot_conf = rot_metodo = rot_tipo = tr

# Os arquivos .py do EternalDub precisam ser da MESMA versao. Se a pasta tiver arquivos misturados
# (ex.: "EternalDub_core (1).py" baixado ao lado do antigo), o programa avisa logo ao abrir.
VERSAO_ARQUIVOS = "1.3"
ARQUIVOS = ("EternalDub_gui.py", "EternalDub_core.py", "EternalDub_emendas.py", "EternalDub_audio.py",
            "EternalDub_i18n.py", "detectar_atraso.py")
core = emendas = previa_audio = None
try:
    if i18n is None:
        raise ModuleNotFoundError("EternalDub_i18n", name="EternalDub_i18n")
    if getattr(i18n, "VERSAO_IDIOMAS", None) != VERSAO_ARQUIVOS:
        raise ImportError("EternalDub_i18n.py (%s) / EternalDub_gui.py (%s): %s" % (
            getattr(i18n, "VERSAO_IDIOMAS", "?"), VERSAO_ARQUIVOS, getattr(i18n, "__file__", "?")))
    import EternalDub_core as core
    import EternalDub_emendas as emendas
    import EternalDub_audio as previa_audio
    ERRO_ARQUIVOS = None
    for _mod, _attr in ((core, "VERSAO_NUCLEO"), (emendas, "VERSAO_EMENDAS"), (previa_audio, "VERSAO_AUDIO")):
        if getattr(_mod, _attr, None) != VERSAO_ARQUIVOS:
            ERRO_ARQUIVOS = "%s (%s) / EternalDub_gui.py (%s): %s" % (
                os.path.basename(getattr(_mod, "__file__", "?")), getattr(_mod, _attr, "?"), VERSAO_ARQUIVOS,
                getattr(_mod, "__file__", "?"))
            break
except ModuleNotFoundError as _e:
    core = None
    ERRO_ARQUIVOS = ("falta o arquivo %s.py nesta pasta / missing file %s.py" % (_e.name, _e.name)
                     if _e.name in ("EternalDub_core", "EternalDub_emendas", "EternalDub_audio", "detectar_atraso",
                                    "EternalDub_i18n") else str(_e))
except Exception as _e:
    core = None
    ERRO_ARQUIVOS = str(_e)

NOME_APP = "EternalDub"
VERSAO = VERSAO_ARQUIVOS
URL_PROJETO = "https://github.com/Moguel0818/EternalDub"
AUTOR = "Moguel0818"
LICENCA = "MIT"


def fmt_tempo(t):
    sinal = "-" if t < 0 else ""
    t = abs(t)
    m, s = divmod(t, 60)
    return "%s%d:%05.2f" % (sinal, int(m), s) if t < 10 else "%s%d:%02d" % (sinal, int(m), int(s))


def fmt_falta(seg):
    return tr("%d min") % math.ceil(seg / 60) if seg >= 60 else tr("%d s") % max(1, seg)


def fmt_tempo_ms(t):
    """h:mm:ss.mmm (ou m:ss.mmm abaixo de uma hora): as emendas precisam de precisao de milissegundo."""
    sinal = "-" if t < 0 else ""
    ms = int(round(abs(t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    sec, ms = divmod(ms, 1000)
    return "%s%d:%02d:%02d.%03d" % (sinal, h, m, sec, ms) if h else "%s%d:%02d.%03d" % (sinal, m, sec, ms)


def fmt_quantia(q):
    """+2500 ms / -1200 ms (quantia de uma emenda, em segundos)."""
    return "%+d ms" % int(round(q * 1000))


# ============================================================ tarefas em segundo plano
class Tarefa(QThread):
    ok = Signal(object)
    erro = Signal(str)
    msg = Signal(str)
    prog = Signal(int)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.cancelar = threading.Event()

    def run(self):
        try:
            self.ok.emit(self.fn(self.msg.emit, self.prog.emit, self.cancelar))
        except core.Cancelado:
            self.erro.emit("__cancelado__")
        except Exception:
            self.erro.emit(traceback.format_exc())


class CarregadorOnda(QObject):
    """
    Le o audio COMPLETO das faixas (so para desenhar a onda) em SEGUNDO PLANO, um arquivo por vez.
      * varias faixas do mesmo arquivo saem numa leitura so;
      * PAUSA sozinho enquanto outra tarefa (detectar, gerar...) usa o disco, e depois CONTINUA de
        onde parou (um HD fica muito lento atendendo duas leituras ao mesmo tempo);
      * pedidos urgentes (a dublagem selecionada) passam na frente: o filme pausa e continua depois.
    """
    progresso = Signal(str, float, float)     # caminho, fracao 0..1, segundos ja lidos do arquivo
    parcial = Signal(str, int, object)        # caminho, faixa, onda ate agora
    pronto = Signal(str, int, object)         # caminho, faixa, onda completa
    falhou = Signal(str, str)                 # caminho, erro
    ocioso = Signal()

    def __init__(self):
        super().__init__()
        self._cond = threading.Condition()
        self._fila = []
        self._atual = None
        self._thread = None
        self._pausado = False
        self._encerrar = False

    # ---- consultas
    def ocupado(self):
        with self._cond:
            return self._atual is not None or bool(self._fila)

    def pausado(self):
        with self._cond:
            return self._pausado and (self._atual is not None or bool(self._fila))

    def lendo(self):
        with self._cond:
            return self._atual["caminho"] if self._atual else None

    # ---- pedidos
    def pedir(self, caminho, posicoes, codecs, duracao, urgente=False):
        posicoes = {int(p) for p in posicoes}
        with self._cond:
            if self._encerrar:
                return
            atual = self._atual
            if atual and atual["caminho"] == caminho:
                posicoes -= set(atual["leitura"].posicoes)
            for j in self._fila:                 # ja pedido? junta (se ainda nao comecou)
                if j["caminho"] == caminho:
                    novas = posicoes - set(j["leitura"].posicoes)
                    if novas and j["leitura"].amostras == 0:
                        j["leitura"] = core.LeituraCompleta(caminho, set(j["leitura"].posicoes) | novas,
                                                            codecs, duracao)
                        j["envs"].update({p: core.EnvelopeIncremental() for p in novas})
                        novas = set()
                    posicoes = novas
                    if urgente:
                        self._fila.remove(j)
                        self._fila.insert(0, j)
                    break
            if posicoes:
                j = {"caminho": caminho, "leitura": core.LeituraCompleta(caminho, posicoes, codecs, duracao),
                     "envs": {p: core.EnvelopeIncremental() for p in posicoes}}
                self._fila.insert(0, j) if urgente else self._fila.append(j)
            if urgente and atual and atual["caminho"] != caminho and self._fila and \
                    self._fila[0]["caminho"] == caminho:
                atual["ceder"] = True            # o que esta lendo pausa e volta logo depois
                atual["parar"].set()
            self._iniciar()

    def _iniciar(self):
        if self._thread is None and self._fila and not self._encerrar:
            self._thread = threading.Thread(target=self._trabalhar, daemon=True)
            self._thread.start()

    # ---- controle
    def pausar(self):
        """Outra tarefa vai usar o disco: para de ler (guardando o que ja leu)."""
        with self._cond:
            self._pausado = True
            if self._atual:
                self._atual["parar"].set()

    def retomar(self):
        with self._cond:
            self._pausado = False
            self._cond.notify_all()
            self._iniciar()

    def _remover(self, filtro):
        with self._cond:
            fica = []
            for j in self._fila:
                if filtro(j):
                    j["leitura"].descartar()
                else:
                    fica.append(j)
            self._fila = fica
            if self._atual and filtro(self._atual):
                self._atual["descartar"] = True
                self._atual["parar"].set()

    def cancelar_arquivo(self, caminho):
        self._remover(lambda j: j["caminho"] == caminho)

    def cancelar_tudo(self):
        self._remover(lambda j: True)

    def encerrar(self, espera=5.0):
        with self._cond:
            self._encerrar = True
            self._cond.notify_all()
            t = self._thread
        self.cancelar_tudo()
        if t is not None:
            t.join(espera)

    # ---- trabalho (linha de execucao propria)
    def _trabalhar(self):
        while True:
            with self._cond:
                while self._pausado and self._fila and not self._encerrar:
                    self._cond.wait(0.5)
                if not self._fila or self._encerrar:
                    self._thread = None
                    self._atual = None
                    break
                job = self._fila.pop(0)
                job["parar"] = threading.Event()
                job["ceder"] = False
                job["descartar"] = False
                self._atual = job
            caminho, envs = job["caminho"], job["envs"]

            def parcial(p, amostras, envs=envs, caminho=caminho):
                envs[p].adicionar(amostras)
                self.parcial.emit(caminho, p, envs[p].valor())

            def cortar(n, envs=envs, caminho=caminho):
                for p, e in envs.items():
                    e.truncar(n)
                    self.parcial.emit(caminho, p, e.valor())
            try:
                job["leitura"].rodar(job["parar"],
                                     ao_progresso=lambda f, seg, caminho=caminho: self.progresso.emit(caminho, f, seg),
                                     ao_parcial=parcial, ao_cortar=cortar)
                for p in job["leitura"].posicoes:
                    self.pronto.emit(caminho, p, core.envelope_do_cache(caminho, p))
            except core.Cancelado:
                with self._cond:
                    if job["descartar"] or self._encerrar:
                        job["leitura"].descartar()
                    else:                        # pausa ou cedeu a vez: volta para a fila e continua depois
                        self._fila.insert(1 if job["ceder"] and self._fila else 0, job)
            except Exception:
                job["leitura"].descartar()
                self.falhou.emit(caminho, traceback.format_exc())
            with self._cond:
                self._atual = None
        self.ocioso.emit()


# ============================================================ onda sonora
class OndaWidget(QWidget):
    """
    Ondas do filme (verde, em cima) e da dublagem (laranja, embaixo) na mesma linha do tempo.
      * arrastar a faixa laranja ........ muda o atraso (Ctrl+arrastar: so o trecho sob o mouse;
                                           Ctrl+Shift+arrastar: este trecho e os seguintes);
      * arrastar o resto ................. move a visao; roda do mouse: zoom;
      * linhas vermelhas ................ emendas da sincronia por trechos: clique para escolher, arraste para
                                           mover; setas movem 10 ms (Shift: 100 ms; Ctrl: 1 ms);
      * clique na regua ................. posiciona o ponto de onde se ouve (linha azul);
      * botao direito ................... menu (ouvir daqui, adicionar ou remover emenda...).
    """
    atraso_arrastado = Signal(int)              # novo atraso em ms enquanto arrasta a faixa laranja
    arraste_comecou = Signal()                  # (para o "desfazer": um passo por arraste)
    arraste_terminou = Signal(str)              # 'dub', 'emenda', 'segmento', 'cabeca' ou 'pan'
    emenda_selecionada = Signal(int)            # indice da emenda escolhida
    emenda_arrastada = Signal(int, float)       # indice, novo tempo (s) do filme
    emenda_empurrada = Signal(int, float)       # indice, deslocamento (s) pelas setas do teclado
    segmento_arrastado = Signal(float, float, bool)   # tempo do filme (s) do clique, deslocamento (s), so_este
    cabeca_movida = Signal(float)               # tempo (s) escolhido na regua
    tocar_pedido = Signal()                     # tecla Espaco na onda
    menu_pedido = Signal(float, int, object)    # tempo (s), emenda mais perto (-1 = nenhuma), posicao na tela
    TOPO = 20
    MARGEM_CLIQUE = 6                           # px

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.ref = None
        self.dub = None
        self.escala_ref = 1.0
        self.escala_dub = 1.0
        self.atraso = 0.0           # segundos
        self.atempo = 1.0
        self.trechos = None         # [[ini_filme, fim_filme, ini_dub], ...] (sincronia por trechos)
        self.emendas = []           # [{"t", "silencio", "remocao", "som"}] ja com o ajuste fino somado
        self.emenda_sel = -1
        self.cabeca = None          # ponto de onde se ouve (s do filme)
        self.t0 = -2.0              # tempo (s) na borda esquerda
        self.pps = 12.0             # pixels por segundo
        self.rot_ref = tr("Filme (referência)")
        self.rot_dub = tr("Dublagem")
        self._arraste = None
        self._mouse_x = None

    # ---- dados
    @staticmethod
    def _preparar(env):
        if env is None or len(env) == 0:
            return None, None, 1.0
        p = float(np.percentile(np.abs(env), 99.5))
        escala = 0.95 / p if p > 0 else 1.0
        return (np.append(env[:, 0], env[-1, 0]).astype(np.float32),
                np.append(env[:, 1], env[-1, 1]).astype(np.float32), min(escala, 40.0))

    def set_ref(self, env, rotulo=None):
        vmin, vmax, esc = self._preparar(env)
        self.ref = None if vmin is None else (vmin, vmax, len(env))
        self.escala_ref = esc
        self.rot_ref = rotulo or tr("Filme (referência)")
        self.update()

    def set_dub(self, env, rotulo=None):
        vmin, vmax, esc = self._preparar(env)
        self.dub = None if vmin is None else (vmin, vmax, len(env))
        self.escala_dub = esc
        self.rot_dub = rotulo or tr("Dublagem")
        self.update()

    def set_atraso(self, ms, atempo=1.0, trechos=None):
        self.atraso = ms / 1000.0
        self.atempo = atempo
        if trechos:
            t = np.asarray(trechos, dtype=np.float64)
            self.trechos = (t[:, 0], t[:, 1], t[:, 2])
        else:
            self.trechos = None
        self.update()

    def set_emendas(self, lista, selecionada=None):
        self.emendas = list(lista)
        if selecionada is not None:
            self.emenda_sel = selecionada
        if self.emenda_sel >= len(self.emendas):
            self.emenda_sel = -1
        self.update()

    def set_cabeca(self, t, seguir=False):
        self.cabeca = None if t is None else max(0.0, float(t))
        if seguir and self.cabeca is not None:
            x = self._x_de(self.cabeca)
            if x < 0 or x > self.width() * 0.92:        # a leitura saiu da tela: a visao acompanha
                self.t0 = self.cabeca - 0.08 * self.width() / self.pps
        self.update()

    def centralizar(self, t):
        self.t0 = t - 0.5 * self.width() / self.pps
        self.update()

    def ver_inicio(self):
        self.pps = max(self.width(), 200) / 60.0
        self.t0 = -2.0
        self.update()

    def _x_de(self, t):
        return (t - self.t0) * self.pps

    def _t_de(self, x):
        return self.t0 + x / self.pps

    def _altura_faixa(self):
        return max(20, (self.height() - self.TOPO) // 2)

    # ---- desenho
    def _extremos(self, vmin, vmax, n, atraso, atempo, w, trechos=None):
        xs = np.arange(w + 1, dtype=np.float64)
        tt = self.t0 + xs / self.pps
        dentro = np.ones(w + 1, bool)
        if trechos is not None:                     # sincronia por trechos: cada pedaco tem seu atraso
            fi, ff, di = trechos
            tt = tt - atraso                        # atraso = ajuste fino somado ao mapa
            k = np.clip(np.searchsorted(fi, tt, side="right") - 1, 0, len(fi) - 1)
            dentro = (tt >= fi[k]) & (tt < ff[k])
            s = (di[k] + (tt - fi[k]) * atempo) * core.ENV_RATE
        else:
            s = (tt - atraso) * atempo * core.ENV_RATE
        idx = np.floor(s).astype(np.int64)
        a = idx[:-1]
        b = np.maximum(idx[1:], a + 1)
        ok = (b > 0) & (a < n) & dentro[:-1] & dentro[1:]
        a = np.clip(a, 0, n - 1)
        b = np.clip(b, 1, n)
        b = np.maximum(b, a + 1)
        inter = np.empty(2 * w, np.int64)
        inter[0::2] = a
        inter[1::2] = b
        mn = np.minimum.reduceat(vmin, inter)[0::2]
        mx = np.maximum.reduceat(vmax, inter)[0::2]
        return mn, mx, ok

    def _faixa(self, p, dados, escala, atraso, atempo, y0, h, cor, rotulo, trechos=None):
        w = self.width()
        p.fillRect(0, y0, w, h, QColor(22, 22, 22))
        p.setPen(QColor(50, 50, 50))
        p.drawLine(0, y0, w, y0)
        meio = y0 + h / 2.0
        amp = h / 2.0 - 4
        if dados is None:
            p.setPen(QColor(120, 120, 120))
            p.drawText(10, int(meio), tr("(sem onda - %s)") % rotulo)
            return
        vmin, vmax, n = dados
        mn, mx, ok = self._extremos(vmin, vmax, n, atraso, atempo, w, trechos)
        p.setPen(cor)
        for x in range(w):
            if not ok[x]:
                continue
            ya = int(meio - float(mx[x]) * escala * amp)
            yb = int(meio - float(mn[x]) * escala * amp)
            p.drawLine(x, ya, x, max(yb, ya + 1))
        p.setPen(QColor(220, 220, 220))
        p.drawText(8, y0 + 14, rotulo)

    def _regua(self, p, w):
        p.fillRect(0, 0, w, self.TOPO, QColor(36, 36, 36))
        passos = [0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600]
        alvo = 90.0 / self.pps
        passo = next((x for x in passos if x >= alvo), passos[-1])
        t = math.floor(self.t0 / passo) * passo
        fim = self.t0 + w / self.pps + passo
        while t <= fim:
            x = int((t - self.t0) * self.pps)
            p.setPen(QColor(110, 110, 110))
            p.drawLine(x, self.TOPO - 6, x, self.TOPO)
            p.setPen(QColor(200, 200, 200))
            p.drawText(x + 3, self.TOPO - 7, fmt_tempo(t))
            t += passo

    def _desenhar_emendas(self, p, w, fh):
        y0 = self.TOPO + fh                                    # faixa da dublagem
        for i, e in enumerate(self.emendas):
            x1, x2 = self._x_de(e["t"]), self._x_de(e["t"] + e["silencio"])
            if x2 < -40 or x1 > w + 40:
                continue
            sel = i == self.emenda_sel
            alto = e.get("som") == "alto"
            if x2 - x1 >= 1:                                   # o silencio inserido aparece como uma faixa
                p.fillRect(int(x1), y0, max(1, int(x2 - x1)), fh, QColor(230, 70, 70, 60))
            cor = QColor(255, 215, 60) if sel else (QColor(255, 130, 40) if alto else QColor(230, 70, 70))
            p.setPen(cor)
            for x in {int(x1), int(x2)}:
                p.drawLine(x, y0 + 2, x, y0 + fh - 2)
                if sel:
                    p.drawLine(x + 1, y0 + 2, x + 1, y0 + fh - 2)
            quantia = e["silencio"] - e["remocao"]
            texto = ("! " if alto else "") + fmt_quantia(quantia)
            p.drawText(int(x1) + 4, y0 + fh - 8, texto)
            if sel:                                            # alca no topo para mostrar que se pode arrastar
                p.fillRect(int(x1) - 3, y0 + 2, 7, 5, cor)

    def _desenhar_cabeca(self, p, w, h):
        if self.cabeca is None:
            return
        x = int(self._x_de(self.cabeca))
        if not -10 <= x <= w + 10:
            return
        p.setPen(QColor(0, 200, 255))
        p.drawLine(x, 0, x, h)
        p.setBrush(QColor(0, 200, 255))
        p.drawPolygon(QPolygon([QPoint(x - 5, 0), QPoint(x + 5, 0), QPoint(x, 8)]))
        p.setBrush(Qt.BrushStyle.NoBrush)

    def paintEvent(self, ev):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(18, 18, 18))
        fh = self._altura_faixa()
        self._faixa(p, self.ref, self.escala_ref, 0.0, 1.0, self.TOPO, fh, QColor(70, 190, 110), self.rot_ref)
        if self.trechos is not None:
            rot = tr("%s   (sincronia por trechos: %d trechos, ajuste %+d ms)") % (
                self.rot_dub, len(self.trechos[0]), int(round(self.atraso * 1000)))
        else:
            rot = tr("%s   (atraso %+d ms)") % (self.rot_dub, int(round(self.atraso * 1000)))
        self._faixa(p, self.dub, self.escala_dub, self.atraso, self.atempo, self.TOPO + fh, fh,
                    QColor(240, 160, 60), rot, self.trechos)
        self._regua(p, w)
        x0 = int((0 - self.t0) * self.pps)         # marca do tempo zero
        if 0 <= x0 < w:
            p.setPen(QColor(90, 90, 160))
            p.drawLine(x0, self.TOPO, x0, h)
        self._desenhar_emendas(p, w, fh)
        if self._mouse_x is not None:
            p.setPen(QColor(255, 255, 255))
            x = int(self._mouse_x)
            p.drawLine(x, self.TOPO, x, h)
            p.drawText(min(x + 6, w - 70), h - 6, fmt_tempo(self.t0 + self._mouse_x / self.pps))
        self._desenhar_cabeca(p, w, h)
        p.end()

    # ---- mouse
    def _emenda_em(self, x):
        """Indice da emenda cuja linha esta a poucos pixels de x (-1 = nenhuma)."""
        melhor, dist = -1, self.MARGEM_CLIQUE + 1.0
        for i, e in enumerate(self.emendas):
            for t in (e["t"], e["t"] + e["silencio"]):
                d = abs(self._x_de(t) - x)
                if d < dist:
                    melhor, dist = i, d
        return melhor

    def _posicionar_cabeca(self, x):
        self.cabeca = max(0.0, self._t_de(x))
        self.cabeca_movida.emit(self.cabeca)

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        x, y = ev.position().x(), ev.position().y()
        if y <= self.TOPO:                                    # regua: de onde se ouve
            self._arraste = {"modo": "cabeca"}
            self._posicionar_cabeca(x)
            self.update()
            return
        i = self._emenda_em(x)
        if i >= 0:
            self.emenda_sel = i
            self.emenda_selecionada.emit(i)
            self._arraste = {"modo": "emenda", "i": i, "dt": self._t_de(x) - self.emendas[i]["t"]}
            self.arraste_comecou.emit()
            self.update()
            return
        em_dub = self.dub is not None and y > self.TOPO + self._altura_faixa()
        mods = ev.modifiers()
        if em_dub and self.emendas and mods & Qt.KeyboardModifier.ControlModifier:
            self._arraste = {"modo": "segmento", "x0": x, "t_clique": self._t_de(x),
                             "so_este": not mods & Qt.KeyboardModifier.ShiftModifier}
            self.arraste_comecou.emit()
        elif em_dub:
            self._arraste = {"modo": "dub", "x0": x, "t0": self.t0, "atraso0": self.atraso}
            self.arraste_comecou.emit()
        else:
            self._arraste = {"modo": "pan", "x0": x, "t0": self.t0, "atraso0": self.atraso}

    def mouseMoveEvent(self, ev):
        x, y = ev.position().x(), ev.position().y()
        self._mouse_x = x
        a = self._arraste
        if a:
            modo, dx = a["modo"], (x - a.get("x0", x)) / self.pps
            if modo == "pan":
                self.t0 = a["t0"] - dx
            elif modo == "dub":
                self.atraso_arrastado.emit(int(round((a["atraso0"] + dx) * 1000)))
            elif modo == "emenda":
                self.emenda_arrastada.emit(a["i"], self._t_de(x) - a["dt"])
            elif modo == "segmento":
                self.segmento_arrastado.emit(a["t_clique"], dx, a["so_este"])
            elif modo == "cabeca":
                self._posicionar_cabeca(x)
        else:
            i = self._emenda_em(x) if y > self.TOPO else -1
            self.setCursor(Qt.CursorShape.SplitHCursor if i >= 0 else Qt.CursorShape.ArrowCursor)
            if i >= 0:
                e = self.emendas[i]
                self.setToolTip(tr("Emenda %d em %s: %s") % (i + 1, fmt_tempo_ms(e["t"]),
                                                             fmt_quantia(e["silencio"] - e["remocao"])))
            else:
                self.setToolTip("")
        self.update()

    def mouseReleaseEvent(self, ev):
        a, self._arraste = self._arraste, None
        if a:
            self.arraste_terminou.emit(a["modo"])

    def leaveEvent(self, ev):
        self._mouse_x = None
        self.update()

    def wheelEvent(self, ev):
        x = ev.position().x()
        f = 1.25 if ev.angleDelta().y() > 0 else 0.8
        tx = self.t0 + x / self.pps
        self.pps = min(800.0, max(0.02, self.pps * f))
        self.t0 = tx - x / self.pps
        self.update()

    def keyPressEvent(self, ev):
        mods = ev.modifiers()
        if ev.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self.emenda_sel >= 0:
            passo = 0.1 if mods & Qt.KeyboardModifier.ShiftModifier else \
                (0.001 if mods & Qt.KeyboardModifier.ControlModifier else 0.01)
            self.emenda_empurrada.emit(self.emenda_sel, passo if ev.key() == Qt.Key.Key_Right else -passo)
            ev.accept()
            return
        if ev.key() == Qt.Key.Key_Space:
            self.tocar_pedido.emit()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def contextMenuEvent(self, ev):
        x = ev.pos().x()
        self.menu_pedido.emit(self._t_de(x), self._emenda_em(x), ev.globalPos())


# ============================================================ ouvir a previa
class ReprodutorAudio(QObject):
    """
    Toca a previa (EternalDub_audio.Previa) na placa de som, em tempo real.

    Uma linha de execucao propria gera o audio (FFmpeg + montador) e o poe numa fila; um temporizador da
    interface passa os blocos para a placa de som (QAudioSink) conforme ela tem espaco. A posicao que se
    mostra na onda e o que a placa de som JA TOCOU, nao o que foi gerado.

    `fabrica_saida` existe para os testes (uma saida falsa, sem placa de som).
    """
    posicao = Signal(float)         # tempo do filme (s) que esta tocando agora
    terminou = Signal()             # chegou ao fim sozinho
    falhou = Signal(str)
    mudou = Signal(bool)            # True: comecou a tocar; False: parou

    TAXA = 48000
    BYTES_POR_SEGUNDO = TAXA * 2 * 2          # 16 bits, estereo

    def __init__(self, fabrica_saida=None, parent=None):
        super().__init__(parent)
        self._fabrica = fabrica_saida or self._saida_qt
        self._volume = 1.0
        self._saida = self._io = self._thread = self._cancelar = self._fila = None
        self._t_ini = 0.0
        self._gravados = 0
        self._pendente = b""
        self._fim = False
        self._timer = QTimer(self)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._bombear)

    def _saida_qt(self):
        if not TEM_AUDIO:
            raise RuntimeError(tr("Esta instalação do Qt não tem suporte a áudio (QtMultimedia)."))
        dispositivo = QMediaDevices.defaultAudioOutput()
        if dispositivo.isNull():
            raise RuntimeError(tr("Não encontrei nenhuma saída de áudio."))
        formato = QAudioFormat()
        formato.setSampleRate(self.TAXA)
        formato.setChannelCount(2)
        formato.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not dispositivo.isFormatSupported(formato):
            raise RuntimeError(tr("A saída de áudio não aceita 48 kHz estéreo de 16 bits."))
        saida = QAudioSink(dispositivo, formato)
        saida.setBufferSize(self.BYTES_POR_SEGUNDO // 2)          # 0,5 s: pouca demora ao parar ou mudar o ponto
        return saida

    def tocando(self):
        return self._saida is not None

    def tempo_atual(self):
        """Tempo do filme (s) que esta tocando (o ponto de partida, se nao estiver tocando)."""
        if self._saida is None:
            return self._t_ini
        return self._t_ini + self._saida.processedUSecs() / 1e6

    def definir_volume(self, v):
        self._volume = max(0.0, min(1.0, float(v)))
        if self._saida is not None:
            self._saida.setVolume(self._volume)

    def tocar(self, fabrica_previa, t_ini):
        """fabrica_previa(cancelar) -> previa_audio.Previa. Comeca do tempo t_ini do filme."""
        self.parar(silencioso=True)
        self._t_ini, self._gravados, self._pendente, self._fim = float(t_ini), 0, b"", False
        try:
            self._saida = self._fabrica()
            self._saida.setVolume(self._volume)
            self._io = self._saida.start()
        except Exception as e:
            self._saida = self._io = None
            self.falhou.emit(str(e))
            return False
        cancelar, fila = threading.Event(), queue.Queue(maxsize=24)        # 24 x 0,25 s = 6 s de folga
        self._cancelar, self._fila = cancelar, fila

        def produzir():
            def colocar(item):
                while not cancelar.is_set():
                    try:
                        fila.put(item, timeout=0.1)
                        return
                    except queue.Full:
                        continue
            try:
                fabrica_previa(cancelar).executar(lambda x: colocar(("pcm", previa_audio.para_pcm16_estereo(x))))
                colocar(("fim", None))
            except core.Cancelado:
                pass
            except Exception:
                colocar(("erro", traceback.format_exc()))
        self._thread = threading.Thread(target=produzir, daemon=True)
        self._thread.start()
        self._timer.start()
        self.mudou.emit(True)
        return True

    def parar(self, silencioso=False):
        """Para e devolve o tempo do filme em que parou."""
        t = self.tempo_atual()
        self._timer.stop()
        if self._cancelar is not None:
            self._cancelar.set()
        if self._saida is not None:
            try:
                self._saida.stop()
            except Exception:
                pass
        estava = self._saida is not None
        self._saida = self._io = self._fila = self._cancelar = None
        self._t_ini = t
        if estava and not silencioso:
            self.mudou.emit(False)
        return t

    def _bombear(self):
        if self._saida is None:
            return
        while True:                                               # fila -> placa de som, enquanto couber
            if not self._pendente:
                try:
                    tipo, dado = self._fila.get_nowait()
                except queue.Empty:
                    break
                if tipo == "erro":
                    self.parar()
                    linhas = dado.strip().splitlines()
                    self.falhou.emit(linhas[-1] if linhas else tr("Erro ao tocar."))
                    return
                if tipo == "fim":
                    self._fim = True
                    break
                self._pendente = dado
            livre = int(self._saida.bytesFree())
            livre -= livre % 4                     # so quadros inteiros (16 bits x 2 canais = 4 bytes)
            if livre <= 0:
                break
            n = self._io.write(self._pendente[:livre])
            n = int(n) if n and n > 0 else 0
            self._gravados += n
            self._pendente = self._pendente[n:]
            if n == 0:
                break
        processado = self._saida.processedUSecs() / 1e6
        self.posicao.emit(self._t_ini + processado)
        if self._fim and not self._pendente and self._fila.empty():
            tocado_tudo = processado >= self._gravados / self.BYTES_POR_SEGUNDO - 0.02
            if tocado_tudo or self._saida.state() == QAudio.State.IdleState:
                self.parar(silencioso=True)
                self.mudou.emit(False)
                self.terminou.emit()


# ============================================================ desfazer / refazer
class Historico:
    """Pilha de estados de sincronia (atraso, velocidade e trechos) de uma dublagem, para Desfazer e Refazer."""
    LIMITE = 100

    def __init__(self):
        self.passado, self.futuro = [], []

    @staticmethod
    def estado(d):
        return (d.atraso_ms, d.atempo, copy.deepcopy(d.trechos), d.status)

    @staticmethod
    def aplicar(d, e):
        d.atraso_ms, d.atempo, d.trechos, d.status = e[0], e[1], copy.deepcopy(e[2]), e[3]

    def guardar(self, d):
        self.passado.append(self.estado(d))
        del self.passado[:-self.LIMITE]
        self.futuro.clear()

    def desfazer(self, d):
        if not self.passado:
            return False
        self.futuro.append(self.estado(d))
        self.aplicar(d, self.passado.pop())
        return True

    def refazer(self, d):
        if not self.futuro:
            return False
        self.passado.append(self.estado(d))
        self.aplicar(d, self.futuro.pop())
        return True


# ============================================================ escolher quais faixas adicionar
class EscolherFaixas(QDialog):
    """Lista as faixas de audio (dublagens) ou de legenda de um arquivo para a pessoa marcar quais quer."""

    def __init__(self, arquivo, idiomas_filme=(), parent=None, tipo="audio"):
        super().__init__(parent)
        legenda = tipo == "subtitle"
        self.setWindowTitle(tr("Quais legendas deste arquivo você quer adicionar?") if legenda else
                            tr("Quais faixas deste arquivo são dublagens?"))
        self.resize(560, 300)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(os.path.basename(arquivo.caminho) + "\n" +
                             (tr("Marque as legendas que você quer adicionar:") if legenda else
                              tr("Marque as faixas de áudio que você quer adicionar:"))))
        self.lista = QListWidget()
        faixas = arquivo.legendas if legenda else arquivo.audios
        if legenda:     # pre-marca as legendas PT-BR
            marcar = {f.pos for f in faixas if core.eh_ptbr(f.idioma, f.titulo)} or {0}
        else:           # pre-marca os idiomas que o filme ainda nao tem (ex.: as faixas em portugues da fonte antiga)
            marcar = {f.pos for f in faixas if f.idioma and f.idioma not in idiomas_filme} or {0}
        for f in faixas:
            texto = tr("faixa %d:  %s") % (f.pos, f.rotulo())
            if legenda and f.forcada():
                texto += "  [" + tr("forçada") + "]"
            it = QListWidgetItem(texto)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if f.pos in marcar else Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, f.pos)
            self.lista.addItem(it)
        lay.addWidget(self.lista)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def escolhidas(self):
        return [self.lista.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lista.count())
                if self.lista.item(i).checkState() == Qt.CheckState.Checked]


# ============================================================ editar uma legenda externa
class EditarLegenda(QDialog):
    """Nome, idioma, atraso e 'forcada' de uma legenda externa (o arquivo da legenda nunca e alterado)."""

    def __init__(self, leg, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Legenda"))
        self.resize(520, 0)
        lay = QVBoxLayout(self)
        origem = os.path.basename(leg.arquivo) + ("  (" + tr("faixa %d") % leg.faixa + ")" if leg.faixa else "")
        info = QLabel(origem + ("\n" + leg.detalhe if leg.detalhe else ""))
        info.setWordWrap(True)
        lay.addWidget(info)
        g = QGridLayout()
        self.nome = QLineEdit(leg.nome)
        self.nome.setPlaceholderText(tr("ex.: Português (Brasil)"))
        self.idioma = QLineEdit(leg.idioma)
        self.idioma.setMaxLength(3)
        self.idioma.setFixedWidth(60)
        self.idioma.setToolTip(tr("Código de 3 letras: por, eng, spa..."))
        self.atraso = QSpinBox()
        self.atraso.setRange(-3600000, 3600000)
        self.atraso.setSingleStep(10)
        self.atraso.setSuffix(" ms")
        self.atraso.setValue(int(leg.atraso_ms))
        self.atraso.setToolTip(tr("Positivo: a legenda aparece mais tarde. Negativo: aparece mais cedo."))
        self.forcada = QCheckBox(tr("Forçada (só as falas em outro idioma; aparece mesmo com a legenda desligada)"))
        self.forcada.setChecked(bool(leg.forcada))
        g.addWidget(QLabel(tr("Nome:")), 0, 0)
        g.addWidget(self.nome, 0, 1, 1, 3)
        g.addWidget(QLabel(tr("Idioma:")), 1, 0)
        g.addWidget(self.idioma, 1, 1)
        g.addWidget(QLabel(tr("Atraso:")), 2, 0)
        g.addWidget(self.atraso, 2, 1)
        g.setColumnStretch(3, 1)
        lay.addLayout(g)
        lay.addWidget(self.forcada)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def aplicar(self, leg):
        leg.nome = self.nome.text().strip()
        idioma = self.idioma.text().strip().lower()
        leg.idioma = idioma if len(idioma) == 3 else (leg.idioma or "und")
        leg.atraso_ms = int(self.atraso.value())
        leg.forcada = self.forcada.isChecked()


# ============================================================ janela principal
class Janela(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("%s %s" % (NOME_APP, VERSAO))
        self.resize(1360, 820)
        self.setAcceptDrops(True)
        self.cfg = QSettings("EternalDub", "EternalDub")
        if not self.cfg.value("migrado"):           # aproveita as opcoes salvas no nome antigo do projeto
            antigo = QSettings("Dubsync", "Dubsync")
            for k in ("pasta", "ffmpeg", "ffprobe"):
                v = antigo.value(k, "")
                if v and not self.cfg.value(k, ""):
                    self.cfg.setValue(k, v)
            self.cfg.setValue("migrado", "1")
        self.ferr = core.achar_ferramentas({k: self.cfg.value(k, "") for k in ("ffmpeg", "ffprobe")})
        self.manter = None                  # faixas do filme que vao para o arquivo final (indices)
        self.legendas = []                  # core.LegendaExterna adicionadas
        self.ordem = []                     # chaves das faixas do arquivo final, em ordem (veja core.Organizacao)
        self.padrao_audio = None            # chave do audio que toca sozinho (None = o primeiro)
        self.padrao_legenda = None          # chave da legenda que aparece sozinha (None = nenhuma)
        self._org_manual = False            # a pessoa organizou a mao: o padrao automatico nao e reaplicado
        self._idioma_original = ""          # "" = descobrir sozinho
        self._linhas_saida = []             # chave de cada linha da tabela do arquivo final (None = sempre vai)
        self._preenchendo_filme = False
        self.film = None
        self.dubs = []
        self._envs = {}                 # (caminho, faixa) -> onda (parcial ou completa)
        self._completas = set()         # chaves cuja onda ja esta completa
        self._arquivos = {}             # caminho -> core.Arquivo (faixas, duracao, codecs)
        self._onda_ini = {}             # caminho -> instante em que a leitura comecou (p/ tempo restante)
        self._ref_mostrada = False
        self.carregador = CarregadorOnda()
        self.carregador.progresso.connect(self._onda_progresso)
        self.carregador.parcial.connect(self._onda_parcial)
        self.carregador.pronto.connect(self._onda_pronta)
        self.carregador.falhou.connect(self._onda_falhou)
        self.carregador.ocioso.connect(self._onda_ociosa)
        self._fila = []
        self._atual = None
        self._carregando = False
        self._projeto = ""
        self._hist = {}                 # id(dublagem) -> Historico (desfazer / refazer)
        self._ult_edicao = None         # (id da dublagem, tipo, instante): junta ajustes seguidos num passo so
        self._arraste_base = None       # estado da dublagem quando um arraste comecou
        self._amp_cache = {}            # chave da onda -> (amplitude, referencia) para medir o som nas emendas
        self._atualizando_emendas = False   # True enquanto a aba Emendas e refeita (os controles nao reagem)
        self._quantia_ant = 1
        self._t_fim_audio = None
        modo = self.cfg.value("modo_audio", "dub")
        self._modo_audio = modo if modo in previa_audio.MODOS else "dub"
        self.player = ReprodutorAudio(parent=self)
        try:
            self.player.definir_volume(float(self.cfg.value("volume", 0.8)))
        except (TypeError, ValueError):
            self.player.definir_volume(0.8)
        self.player.posicao.connect(self._ao_posicao_audio)
        self.player.terminou.connect(self._ao_fim_audio)
        self.player.falhou.connect(self._ao_falha_audio)
        self.player.mudou.connect(self._ao_mudar_reproducao)
        self._criar_acoes()
        self._criar_menus()
        self._criar_toolbar()
        self._criar_central()
        self._criar_status()
        self._atualizar_estado()
        self.log(tr("EternalDub pronto. Arraste o filme para a janela (ou use Arquivo > Abrir filme)."))
        if not core.ffmpeg_ok(self.ferr):
            self.log(tr("ATENÇÃO: FFmpeg não encontrado. Instale o FFmpeg ou use Opções > Localizar FFmpeg."))
        self.log(tr("FFmpeg: %s") % core.versoes(self.ferr))

    # ------------------------------------------------ construcao
    def _acao(self, texto, slot, atalho=None, icone=None, dica=None):
        a = QAction(texto, self)
        if icone is not None:
            a.setIcon(self.style().standardIcon(icone))
        if atalho:
            a.setShortcut(QKeySequence(atalho))
        if dica:
            a.setToolTip(dica)
        a.triggered.connect(slot)
        return a

    def _criar_acoes(self):
        S = QStyle.StandardPixmap
        self.a_abrir = self._acao(tr("Abrir filme..."), self.acao_abrir_filme, "Ctrl+O", S.SP_DirOpenIcon,
                                  tr("Escolha o filme de alta qualidade (.mkv)"))
        self.a_add = self._acao(tr("Adicionar dublagem..."), self.acao_adicionar, "Ctrl+D", S.SP_FileDialogNewFolder,
                                tr("Adicione arquivos com dublagens (várias faixas de uma vez)"))
        self.a_rem = self._acao(tr("Remover"), self.acao_remover, "Del", S.SP_TrashIcon)
        self.a_add_leg = self._acao(tr("Adicionar legenda..."), self.acao_add_legenda, "Ctrl+L",
                                    S.SP_FileDialogContentsView,
                                    tr("Legenda externa (.srt, .ass, .sup...) ou uma faixa de legenda de outro arquivo"))
        self.a_sobe = self._acao(tr("Mover para cima"), lambda *_: self.acao_mover(-1), "Ctrl+Up")
        self.a_desce = self._acao(tr("Mover para baixo"), lambda *_: self.acao_mover(1), "Ctrl+Down")
        self.a_det = self._acao(tr("Detectar atraso"), self.acao_detectar, "F5", S.SP_BrowserReload,
                                tr("Compara música e efeitos da dublagem com o áudio do filme"))
        self.a_det_arq = self._acao(tr("Detectar usando outra faixa do arquivo..."), self.acao_detectar_faixa_arquivo,
                                    "Ctrl+F5", None,
                                    tr("Ex.: usar a faixa em inglês da mesma fonte e aplicar a todas as dublagens dela"))
        self.a_det_vid = self._acao(tr("Detectar pelo vídeo (lento)..."), self.acao_detectar_video, None, None,
                                    tr("Compara os cortes de cena dos vídeos"))
        self.a_mapa = self._acao(tr("Sincronizar trecho por trecho..."), self.acao_mapear, "Ctrl+M", None,
                                 tr("Para versões com cortes diferentes: mede o atraso a cada segundo e monta a "
                                    "dublagem pedaço por pedaço"))
        self.a_zero = self._acao(tr("Zerar atraso, velocidade e trechos"), self.acao_zerar)
        self.a_teste = self._acao(tr("Gerar teste (5 min)"), lambda *_: self.acao_gerar(True), "F6", S.SP_DialogApplyButton,
                                  tr("Gera só os 5 primeiros minutos para conferir a sincronia"))
        self.a_final = self._acao(tr("Gerar arquivo final"), lambda *_: self.acao_gerar(False), "F7",
                                  S.SP_DialogSaveButton, tr("Gera o MKV completo (sem recodificar)"))
        self.a_cancel = self._acao(tr("Cancelar tarefa"), self.acao_cancelar, "Esc", S.SP_BrowserStop)
        self.a_verif = self._acao(tr("Verificar integridade (hash)..."), self.acao_verificar, None, None,
                                  tr("Confere se vídeo, áudios e legendas originais continuam idênticos"))
        self.a_cache = self._acao(tr("Limpar cache de áudio"), self.acao_limpar_cache)
        self.a_abrirproj = self._acao(tr("Abrir projeto..."), self.acao_abrir_projeto, "Ctrl+Shift+O")
        self.a_salvarproj = self._acao(tr("Salvar projeto..."), self.acao_salvar_projeto, "Ctrl+S")
        self.a_sair = self._acao(tr("Sair"), self.close, "Ctrl+Q")
        self.a_ff = self._acao(tr("Localizar FFmpeg..."), lambda *_: self.acao_localizar("ffmpeg"))
        self.a_sobre = self._acao(tr("Sobre o EternalDub / créditos"), self.acao_sobre)
        self.a_site = self._acao(tr("Página do projeto (GitHub)"), self.acao_site)
        self.a_bug = self._acao(tr("Relatar um problema..."), self.acao_relatar)
        self.a_zoom = self._acao(tr("Ver o início na onda"), lambda *_: self.onda.ver_inicio(), "Home")
        self.a_ondas = self._acao(tr("Carregar as ondas (filme e dublagens)"),
                                  lambda *_: self._garantir_ondas(todas=True), None, None,
                                  tr("Lê o áudio completo em segundo plano só para desenhar a onda"))
        self.a_parar_ondas = self._acao(tr("Parar a leitura das ondas"), self.acao_parar_ondas)
        self.a_det_completo = self._acao(tr("Detectar lendo os arquivos inteiros (lento)..."),
                                         self.acao_detectar_completo, None, None,
                                         tr("Para quando a análise rápida não acha a dublagem"))
        # ---- ouvir
        self.a_tocar = self._acao(tr("Ouvir / parar"), self.acao_tocar, "F8", S.SP_MediaPlay,
                                  tr("Toca a partir da linha azul (clique na régua da onda para escolher o ponto)"))
        self.a_ouvir_emenda = self._acao(tr("Ouvir a emenda selecionada"), self.acao_ouvir_emenda, "F9", None,
                                         tr("Toca 3 s antes e 3 s depois da emenda"))
        self.a_inicio_audio = self._acao(tr("Voltar a linha azul ao início"), self.acao_inicio_audio, "Shift+F8")
        self.a_modos = {}
        grupo_modos = QActionGroup(self)
        grupo_modos.setExclusive(True)
        for modo, rotulo in (("dub", tr("Ouvir a dublagem (já sincronizada)")),
                             ("filme", tr("Ouvir o filme (referência)")),
                             ("mix", tr("Ouvir os dois juntos (se combinam, está sincronizado)"))):
            a_ = QAction(rotulo, self, checkable=True)
            a_.setChecked(modo == self._modo_audio)
            a_.triggered.connect(lambda *_, m=modo: self.acao_modo_audio(m))
            grupo_modos.addAction(a_)
            self.a_modos[modo] = a_
        # ---- emendas e desfazer
        self.a_add_emenda = self._acao(tr("Adicionar emenda na linha azul..."), self.acao_add_emenda, "Ctrl+E", None,
                                       tr("Cria uma emenda: silêncio inserido ou um pedaço que sai da dublagem"))
        self.a_rem_emenda = self._acao(tr("Remover emenda selecionada"), self.acao_remover_emenda, "Ctrl+Del")
        self.a_pausa = self._acao(tr("Procurar uma pausa perto da emenda"), self.acao_pausa, "Ctrl+P", None,
                                  tr("Move a emenda para o ponto mais silencioso da dublagem em volta"))
        self.a_desfazer = self._acao(tr("Desfazer"), self.acao_desfazer, "Ctrl+Z")
        self.a_refazer = self._acao(tr("Refazer"), self.acao_refazer, "Ctrl+Y")

    def _criar_menus(self):
        mb = self.menuBar()
        m = mb.addMenu(tr("Arquivo"))
        for a in (self.a_abrir, self.a_abrirproj, self.a_salvarproj):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_sair)
        m = mb.addMenu(tr("Dublagens"))
        for a in (self.a_add, self.a_rem, self.a_sobe, self.a_desce):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_add_leg)
        m = mb.addMenu(tr("Sincronização"))
        for a in (self.a_det, self.a_det_arq, self.a_det_completo, self.a_det_vid, self.a_mapa):
            m.addAction(a)
        m.addSeparator()
        for a in (self.a_desfazer, self.a_refazer, self.a_zero):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_zoom)
        m.addAction(self.a_ondas)
        m.addAction(self.a_parar_ondas)
        m = mb.addMenu(tr("Emendas"))
        for a in (self.a_add_emenda, self.a_rem_emenda, self.a_pausa, self.a_ouvir_emenda):
            m.addAction(a)
        m = mb.addMenu(tr("Reprodução"))
        for a in (self.a_tocar, self.a_inicio_audio):
            m.addAction(a)
        m.addSeparator()
        for a in self.a_modos.values():
            m.addAction(a)
        m = mb.addMenu(tr("Montar"))
        for a in (self.a_teste, self.a_final, self.a_cancel):
            m.addAction(a)
        m = mb.addMenu(tr("Ferramentas"))
        for a in (self.a_verif, self.a_cache):
            m.addAction(a)
        m = mb.addMenu(tr("Opções"))
        m.addAction(self.a_ff)
        sub = m.addMenu("Idioma / Language")           # sempre nos dois idiomas, para quem nao le o atual
        grupo_idioma = QActionGroup(self)
        grupo_idioma.setExclusive(True)
        self.acoes_idioma = {}
        for codigo, nome in i18n.IDIOMAS:
            a = QAction(nome, self, checkable=True)
            a.setChecked(codigo == i18n.atual())
            a.triggered.connect(lambda *_, c=codigo: self.acao_idioma(c))
            grupo_idioma.addAction(a)
            sub.addAction(a)
            self.acoes_idioma[codigo] = a
        m = mb.addMenu(tr("Ajuda"))
        for a in (self.a_sobre, self.a_site, self.a_bug):
            m.addAction(a)

    def _criar_toolbar(self):
        tb = QToolBar(tr("Principal"))
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        for a in (self.a_abrir, self.a_add, self.a_add_leg, self.a_rem):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(self.a_det)
        tb.addSeparator()
        for a in (self.a_teste, self.a_final, self.a_cancel):
            tb.addAction(a)
        self.addToolBar(tb)
        # ---- ouvir: botao, o que ouvir e volume
        tb2 = QToolBar(tr("Ouvir"))
        tb2.setMovable(False)
        tb2.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tb2.addAction(self.a_tocar)
        self.cmb_modo = QComboBox()
        self.cmb_modo.setToolTip(tr("O que tocar"))
        for modo, rotulo in (("dub", tr("Dublagem")), ("filme", tr("Filme")), ("mix", tr("Filme + dublagem"))):
            self.cmb_modo.addItem(rotulo, modo)
        self.cmb_modo.setCurrentIndex(max(0, self.cmb_modo.findData(self._modo_audio)))
        self.cmb_modo.currentIndexChanged.connect(lambda *_: self.acao_modo_audio(self.cmb_modo.currentData()))
        tb2.addWidget(self.cmb_modo)
        self.lbl_cabeca = QLabel("  0:00.000  ")
        self.lbl_cabeca.setStyleSheet("color: #00c8ff; font-family: monospace;")
        self.lbl_cabeca.setToolTip(tr("Ponto de onde se ouve (linha azul)"))
        tb2.addWidget(self.lbl_cabeca)
        self.sld_volume = QSlider(Qt.Orientation.Horizontal)
        self.sld_volume.setRange(0, 100)
        self.sld_volume.setFixedWidth(90)
        self.sld_volume.setValue(int(round(self.player._volume * 100)))
        self.sld_volume.setToolTip(tr("Volume"))
        self.sld_volume.valueChanged.connect(self._ao_mudar_volume)
        tb2.addWidget(QLabel(tr("Volume") + " "))
        tb2.addWidget(self.sld_volume)
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb2)

    def _criar_central(self):
        # ---- lista de dublagens
        self.tab = QTableWidget(0, 6)
        self.tab.setHorizontalHeaderLabels(["#", tr("Nome"), tr("Origem"), tr("Atraso (ms)"), tr("Padrão"),
                                            tr("Status")])
        self.tab.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tab.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tab.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tab.setAlternatingRowColors(True)
        self.tab.verticalHeader().setVisible(False)
        h = self.tab.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.tab.itemSelectionChanged.connect(self._ao_selecionar)

        # ---- editor da dublagem selecionada (estilo "Show / Duration / Text" do Subtitle Edit)
        box = QGroupBox(tr("Dublagem selecionada"))
        g = QGridLayout(box)
        self.ed_nome = QLineEdit()
        self.ed_nome.textEdited.connect(self._ed_nome)
        self.ed_idioma = QLineEdit()
        self.ed_idioma.setMaxLength(3)
        self.ed_idioma.setFixedWidth(60)
        self.ed_idioma.setToolTip(tr("Código de 3 letras: por, eng, spa..."))
        self.ed_idioma.textEdited.connect(self._ed_idioma)
        self.sp_atraso = QSpinBox()
        self.sp_atraso.setRange(-3600000, 3600000)
        self.sp_atraso.setSingleStep(10)
        self.sp_atraso.setSuffix(" ms")
        self.sp_atraso.valueChanged.connect(self._ed_atraso)
        self.chk_padrao = QCheckBox(tr("Faixa padrão (toca sozinha)"))
        self.chk_padrao.toggled.connect(self._ed_padrao)
        self.lbl_origem = QLabel("-")
        self.lbl_origem.setWordWrap(True)
        self.lbl_vel = QLabel("-")
        self.lbl_vel.setWordWrap(True)
        g.addWidget(QLabel(tr("Nome")), 0, 0)
        g.addWidget(self.ed_nome, 0, 1, 1, 5)
        g.addWidget(QLabel(tr("Idioma")), 0, 6)
        g.addWidget(self.ed_idioma, 0, 7)
        g.addWidget(QLabel(tr("Atraso")), 1, 0)
        g.addWidget(self.sp_atraso, 1, 1)
        self.botoes_nudge = []
        for i, delta in enumerate((-1000, -100, -10, 10, 100, 1000)):
            b = QPushButton("%+d" % delta)
            b.setFixedWidth(52)
            b.clicked.connect(lambda *_, d=delta: self._nudge(d))
            g.addWidget(b, 1, 2 + i)
            self.botoes_nudge.append(b)
        g.addWidget(self.chk_padrao, 2, 0, 1, 4)
        g.addWidget(QLabel(tr("Velocidade")), 3, 0)
        g.addWidget(self.lbl_vel, 3, 1, 1, 7)
        g.addWidget(QLabel(tr("Origem")), 4, 0)
        g.addWidget(self.lbl_origem, 4, 1, 1, 7)
        linha = QHBoxLayout()
        self.b_det = QPushButton(tr("Detectar atraso (F5)"))
        self.b_det.clicked.connect(self.acao_detectar)
        self.b_det2 = QPushButton(tr("Detectar usando outra faixa do arquivo..."))
        self.b_det2.clicked.connect(self.acao_detectar_faixa_arquivo)
        self.b_mapa = QPushButton(tr("Sincronizar trecho por trecho..."))
        self.b_mapa.setToolTip(tr("Para versões com cortes diferentes: mede o atraso a cada segundo e monta a "
                                  "dublagem pedaço por pedaço"))
        self.b_mapa.clicked.connect(self.acao_mapear)
        linha.addWidget(self.b_det)
        linha.addWidget(self.b_det2)
        linha.addWidget(self.b_mapa)
        linha.addStretch(1)
        g.addLayout(linha, 5, 0, 1, 8)
        self.editor = box

        esq = QWidget()
        le = QVBoxLayout(esq)
        le.setContentsMargins(0, 0, 0, 0)
        le.addWidget(self.tab, 1)
        le.addWidget(box)

        # ---- direita: arquivo final / emendas / registro
        pf = self._criar_painel_saida()
        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.abas = QTabWidget()
        self.abas.addTab(pf, tr("Arquivo final"))
        self.abas.addTab(self._criar_painel_emendas(), tr("Emendas"))
        self.abas.addTab(self.txt_log, tr("Registro"))

        topo = QSplitter(Qt.Orientation.Horizontal)
        topo.addWidget(esq)
        topo.addWidget(self.abas)
        topo.setStretchFactor(0, 1)
        topo.setStretchFactor(1, 1)

        # ---- onda
        self.onda = OndaWidget()
        self.onda.atraso_arrastado.connect(self._onda_arrastou)
        self.onda.arraste_comecou.connect(self._ao_comecar_arraste)
        self.onda.arraste_terminou.connect(self._ao_terminar_arraste)
        self.onda.emenda_selecionada.connect(self._ao_escolher_emenda_na_onda)
        self.onda.emenda_arrastada.connect(self._ao_arrastar_emenda)
        self.onda.emenda_empurrada.connect(self._ao_empurrar_emenda)
        self.onda.segmento_arrastado.connect(self._ao_arrastar_segmento)
        self.onda.cabeca_movida.connect(self._ao_mover_cabeca)
        self.onda.tocar_pedido.connect(self.acao_tocar)
        self.onda.menu_pedido.connect(self._menu_da_onda)
        baixo = QWidget()
        lb = QVBoxLayout(baixo)
        lb.setContentsMargins(0, 0, 0, 0)
        lb.addWidget(self.onda, 1)
        dica = QLabel(tr("Roda do mouse = zoom  |  arraste a faixa LARANJA = atraso (Ctrl = só o trecho)  |  "
                         "arraste uma linha VERMELHA = move a emenda  |  clique na régua + F8 = ouvir daí  |  "
                         "botão direito = mais opções  |  Home = início"))
        dica.setStyleSheet("color: #999; padding: 2px 6px;")
        dica.setWordWrap(True)
        lb.addWidget(dica)

        div = QSplitter(Qt.Orientation.Vertical)
        div.addWidget(topo)
        div.addWidget(baixo)
        div.setStretchFactor(0, 3)
        div.setStretchFactor(1, 2)
        self.setCentralWidget(div)

    # colunas da tabela do arquivo final
    COL_MANTER, COL_NUM, COL_TIPO, COL_IDIOMA, COL_TITULO, COL_PADRAO, COL_MARCAS, COL_CODEC, COL_ORIGEM = range(9)

    def _criar_painel_saida(self):
        """
        Aba 'Arquivo final': TODAS as faixas que podem ir para o MKV (as do filme, as dublagens e as legendas
        externas) na ordem em que vao ficar: videos, audios, legendas. Marca o que entra, muda a ordem, escolhe a
        faixa padrao. O padrao BDRemux PT-BR (dublagem PT-BR, idioma original, legenda PT-BR) e aplicado sozinho.
        """
        pf = QWidget()
        lf = QVBoxLayout(pf)
        self.lbl_filme = QLabel(tr("Nenhum filme aberto. Arraste o .mkv para a janela."))
        self.lbl_filme.setWordWrap(True)
        self.lbl_manter = QLabel("")
        self.lbl_manter.setWordWrap(True)
        lf.addWidget(self.lbl_filme)
        lf.addWidget(self.lbl_manter)
        linha = QHBoxLayout()
        self.b_marcar = QPushButton(tr("Marcar tudo"))
        self.b_marcar.setToolTip(tr("Põe no arquivo final todas as faixas do filme"))
        self.b_marcar.clicked.connect(lambda *_: self._marcar_saida(True))
        self.b_desmarcar = QPushButton(tr("Desmarcar tudo"))
        self.b_desmarcar.setToolTip(tr("Tira do arquivo final todos os áudios e legendas do filme (o vídeo "
                                       "continua; dublagens e legendas adicionadas também)"))
        self.b_desmarcar.clicked.connect(lambda *_: self._marcar_saida(False))
        self.b_saida_sobe = QPushButton("▲ " + tr("Subir"))
        self.b_saida_sobe.setToolTip(tr("Sobe a faixa escolhida (entre as do mesmo tipo)"))
        self.b_saida_sobe.clicked.connect(lambda *_: self._mover_saida(-1))
        self.b_saida_desce = QPushButton("▼ " + tr("Descer"))
        self.b_saida_desce.setToolTip(tr("Desce a faixa escolhida (entre as do mesmo tipo)"))
        self.b_saida_desce.clicked.connect(lambda *_: self._mover_saida(1))
        for b in (self.b_marcar, self.b_desmarcar, self.b_saida_sobe, self.b_saida_desce):
            linha.addWidget(b)
        linha.addStretch(1)
        lf.addLayout(linha)
        self.tab_filme = QTableWidget(0, 9)
        self.tab_filme.setHorizontalHeaderLabels([tr("Manter"), "#", tr("Tipo"), tr("Idioma"), tr("Título"),
                                                  tr("Padrão"), tr("Marcas"), tr("Codec"), tr("Origem")])
        self.tab_filme.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tab_filme.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tab_filme.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tab_filme.verticalHeader().setVisible(False)
        self.tab_filme.verticalHeader().setDefaultSectionSize(24)
        self.tab_filme.horizontalHeader().setStretchLastSection(True)
        self.tab_filme.setToolTip(tr("Marque o que entra no arquivo final; Subir/Descer mudam a ordem; 'Padrão' é a "
                                     "faixa que toca (ou aparece) sozinha. Clique duas vezes numa legenda "
                                     "adicionada para editar."))
        self.tab_filme.itemChanged.connect(self._ao_mudar_item_saida)
        self.tab_filme.itemSelectionChanged.connect(self._atualizar_estado)
        self.tab_filme.itemDoubleClicked.connect(self._ao_duplo_clique_saida)
        lf.addWidget(self.tab_filme, 1)
        linha = QHBoxLayout()
        self.b_leg_add = QPushButton(tr("Adicionar legenda..."))
        self.b_leg_add.setToolTip(tr("Legenda externa (.srt, .ass, .sup...) ou uma faixa de legenda de outro arquivo"))
        self.b_leg_add.clicked.connect(self.acao_add_legenda)
        self.b_leg_editar = QPushButton(tr("Editar legenda..."))
        self.b_leg_editar.clicked.connect(self.acao_editar_legenda)
        self.b_leg_rem = QPushButton(tr("Remover legenda"))
        self.b_leg_rem.clicked.connect(self.acao_remover_legenda)
        for b in (self.b_leg_add, self.b_leg_editar, self.b_leg_rem):
            linha.addWidget(b)
        linha.addStretch(1)
        lf.addLayout(linha)
        g = QGridLayout()
        g.addWidget(QLabel(tr("Idioma original:")), 0, 0)
        self.cmb_original = QComboBox()
        self.cmb_original.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.cmb_original.setToolTip(tr("Idioma em que o filme foi feito; a faixa principal dele fica logo depois "
                                        "do áudio PT-BR"))
        self.cmb_original.currentIndexChanged.connect(self._ao_mudar_idioma_original)
        linha = QHBoxLayout()
        linha.addWidget(self.cmb_original)
        self.b_padrao_saida = QPushButton(tr("Aplicar o padrão BDRemux PT-BR"))
        self.b_padrao_saida.setToolTip(tr("1) áudio PT-BR  2) áudio no idioma original  3) legenda PT-BR (externa ou "
                                          "do filme). O resto do filme fica desmarcado."))
        self.b_padrao_saida.clicked.connect(self.acao_padrao_saida)
        linha.addWidget(self.b_padrao_saida)
        linha.addStretch(1)
        g.addLayout(linha, 0, 1)
        g.addWidget(QLabel(tr("Faixa de referência:")), 1, 0)
        self.cmb_ref = QComboBox()
        self.cmb_ref.setToolTip(tr("Faixa de referência (áudio ORIGINAL do filme, usada para comparar):"))
        self.cmb_ref.currentIndexChanged.connect(self._ao_mudar_ref)
        g.addWidget(self.cmb_ref, 1, 1)
        g.setColumnStretch(1, 1)
        lf.addLayout(g)
        self.chk_org_auto = QCheckBox(tr("Organizar sozinho no padrão BDRemux PT-BR"))
        self.chk_org_auto.setToolTip(tr("Ao abrir o filme e ao adicionar dublagens ou legendas, o arquivo final é "
                                        "organizado sozinho (até você mudar algo à mão)."))
        # ligado por padrao na interface em portugues (o padrao e o de BDRemux PT-BR)
        padrao_auto = "true" if i18n.atual() == "pt" else "false"
        self.chk_org_auto.setChecked(str(self.cfg.value("organizar_auto", padrao_auto)).lower() != "false")
        self.chk_org_auto.toggled.connect(self._ao_mudar_org_auto)
        lf.addWidget(self.chk_org_auto)
        return pf

    def _criar_painel_emendas(self):
        """Aba 'Emendas': lista das emendas da dublagem selecionada e os controles para ajusta-las."""
        pw = QWidget()
        lay = QVBoxLayout(pw)
        self.lbl_emendas = QLabel("")
        self.lbl_emendas.setWordWrap(True)
        lay.addWidget(self.lbl_emendas)
        self.tab_em = QTableWidget(0, 5)
        self.tab_em.setHorizontalHeaderLabels(["#", tr("Tempo no filme"), tr("Quantia"), tr("Som na emenda"),
                                               tr("O que acontece")])
        self.tab_em.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tab_em.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tab_em.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tab_em.verticalHeader().setVisible(False)
        cab = self.tab_em.horizontalHeader()
        for c, modo in enumerate((QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.ResizeToContents,
                                  QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.ResizeToContents,
                                  QHeaderView.ResizeMode.Stretch)):
            cab.setSectionResizeMode(c, modo)
        self.tab_em.itemSelectionChanged.connect(self._ao_escolher_emenda_na_tabela)
        self.tab_em.itemDoubleClicked.connect(lambda *_: self.acao_ir_para_emenda())
        lay.addWidget(self.tab_em, 1)

        box = QGroupBox(tr("Emenda selecionada"))
        g = QGridLayout(box)
        self.sp_em_tempo = QDoubleSpinBox()
        self.sp_em_tempo.setDecimals(3)
        self.sp_em_tempo.setRange(0.0, 360000.0)
        self.sp_em_tempo.setSingleStep(0.01)
        self.sp_em_tempo.setSuffix(" s")
        self.sp_em_tempo.setToolTip(tr("Em que ponto do filme a dublagem passa de um alinhamento para o outro"))
        self.sp_em_tempo.setKeyboardTracking(False)
        self.sp_em_tempo.valueChanged.connect(self._ed_emenda_tempo)
        self.sp_em_quantia = QSpinBox()
        self.sp_em_quantia.setRange(-600000, 600000)
        self.sp_em_quantia.setSingleStep(10)
        self.sp_em_quantia.setSuffix(" ms")
        self.sp_em_quantia.setToolTip(tr("Positivo: entra silêncio e o resto da dublagem fica mais tarde. "
                                         "Negativo: sai um pedaço da dublagem e o resto fica mais cedo."))
        self.sp_em_quantia.setKeyboardTracking(False)
        self.sp_em_quantia.valueChanged.connect(self._ed_emenda_quantia)
        g.addWidget(QLabel(tr("Tempo")), 0, 0)
        g.addWidget(self.sp_em_tempo, 0, 1)
        self.botoes_emenda = []
        for i, delta in enumerate((-100, -10, 10, 100)):
            b = QPushButton("%+d" % delta)
            b.setFixedWidth(52)
            b.setToolTip(tr("Move a emenda %+d ms (Shift+setas na onda: 100 ms; setas: 10 ms; Ctrl+setas: 1 ms)") % delta)
            b.clicked.connect(lambda *_, d=delta: self._empurrar_emenda_selecionada(d / 1000.0))
            g.addWidget(b, 0, 2 + i)
            self.botoes_emenda.append(b)
        g.addWidget(QLabel(tr("Quantia")), 1, 0)
        g.addWidget(self.sp_em_quantia, 1, 1)
        self.chk_ima = QCheckBox(tr("Ao arrastar, encaixar numa pausa da dublagem"))
        self.chk_ima.setChecked(str(self.cfg.value("ima_pausas", "true")).lower() != "false")
        self.chk_ima.setToolTip(tr("Procura o ponto mais silencioso perto de onde você soltou, para não cortar "
                                   "uma fala"))
        self.chk_ima.toggled.connect(lambda v: self.cfg.setValue("ima_pausas", "true" if v else "false"))
        g.addWidget(self.chk_ima, 2, 0, 1, 6)
        linha = QHBoxLayout()
        self.b_em_add = QPushButton(tr("Adicionar na linha azul..."))
        self.b_em_add.clicked.connect(self.acao_add_emenda)
        self.b_em_rem = QPushButton(tr("Remover"))
        self.b_em_rem.clicked.connect(self.acao_remover_emenda)
        self.b_em_pausa = QPushButton(tr("Achar pausa"))
        self.b_em_pausa.clicked.connect(self.acao_pausa)
        self.b_em_ouvir = QPushButton(tr("Ouvir (F9)"))
        self.b_em_ouvir.clicked.connect(self.acao_ouvir_emenda)
        self.b_em_ir = QPushButton(tr("Ir até ela"))
        self.b_em_ir.clicked.connect(self.acao_ir_para_emenda)
        for b in (self.b_em_add, self.b_em_rem, self.b_em_pausa, self.b_em_ouvir, self.b_em_ir):
            linha.addWidget(b)
        linha.addStretch(1)
        g.addLayout(linha, 3, 0, 1, 6)
        self.box_emenda = box
        lay.addWidget(box)
        return pw

    def _criar_status(self):
        self.lbl_status = QLabel("")
        self.barra = QProgressBar()
        self.barra.setFixedWidth(240)
        self.barra.setRange(0, 100)
        self.barra.setValue(0)
        self.lbl_onda = QLabel("")
        self.lbl_onda.setStyleSheet("color: #8fd19e; padding: 0 8px;")
        self.barra_onda = QProgressBar()
        self.barra_onda.setFixedWidth(130)
        self.barra_onda.setRange(0, 100)
        self.barra_onda.setTextVisible(False)
        self.barra_onda.setVisible(False)
        self.statusBar().addWidget(self.lbl_status, 1)
        self.statusBar().addPermanentWidget(self.lbl_onda)
        self.statusBar().addPermanentWidget(self.barra_onda)
        self.statusBar().addPermanentWidget(self.barra)

    # ------------------------------------------------ utilidades
    def log(self, texto):
        self.txt_log.appendPlainText(time.strftime("[%H:%M:%S] ") + texto)
        self.lbl_status.setText(texto.splitlines()[0] if texto else "")

    def erro(self, titulo, detalhe):
        self.log(titulo + ": " + detalhe.strip().splitlines()[-1] if detalhe.strip() else titulo)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(NOME_APP)
        box.setText(titulo)
        box.setInformativeText(detalhe.strip().splitlines()[-1] if detalhe.strip() else "")
        box.setDetailedText(detalhe)
        box.exec()

    def aviso(self, texto):
        QMessageBox.information(self, NOME_APP, texto)

    def _ocupado(self):
        return self._atual is not None

    def _atualizar_estado(self):
        tem_film = self.film is not None
        tem_dub = self._dub_atual() is not None
        ocupado = self._ocupado()
        self.a_add.setEnabled(tem_film and not ocupado)
        self.a_det.setEnabled(tem_film and tem_dub and not ocupado)
        self.a_det_arq.setEnabled(tem_film and tem_dub and not ocupado)
        self.a_det_vid.setEnabled(tem_film and tem_dub and not ocupado)
        self.a_det_completo.setEnabled(tem_film and tem_dub and not ocupado)
        self.a_mapa.setEnabled(tem_film and tem_dub and not ocupado)
        self.b_det.setEnabled(tem_film and tem_dub and not ocupado)
        self.b_det2.setEnabled(tem_film and tem_dub and not ocupado)
        self.b_mapa.setEnabled(tem_film and tem_dub and not ocupado)
        self.a_rem.setEnabled(tem_dub and not ocupado)
        # sem dublagem tambem da para gerar: so reorganiza o filme (ex.: deixar so o audio PT-BR que ele ja tem)
        self.a_teste.setEnabled(tem_film and not ocupado)
        self.a_final.setEnabled(tem_film and not ocupado)
        k = self._chave_escolhida_saida() if tem_film else None
        mesmas = [x for x in self.ordem if self._tipo_chave(x) == self._tipo_chave(k)] if k is not None else []
        self.a_add_leg.setEnabled(tem_film and not ocupado)
        self.b_leg_add.setEnabled(tem_film and not ocupado)
        self.b_leg_editar.setEnabled(k is not None and k[0] == "leg" and not ocupado)
        self.b_leg_rem.setEnabled(k is not None and k[0] == "leg" and not ocupado)
        self.b_saida_sobe.setEnabled(bool(mesmas) and k in mesmas and mesmas.index(k) > 0 and not ocupado)
        self.b_saida_desce.setEnabled(bool(mesmas) and k in mesmas and mesmas.index(k) < len(mesmas) - 1 and
                                      not ocupado)
        for w in (self.b_marcar, self.b_desmarcar, self.b_padrao_saida, self.cmb_original, self.chk_org_auto,
                  self.tab_filme):
            w.setEnabled(tem_film and not ocupado)
        self.a_verif.setEnabled(tem_film and not ocupado)
        self.a_cancel.setEnabled(ocupado)
        self.a_parar_ondas.setEnabled(self.carregador.ocupado())
        self.a_abrir.setEnabled(not ocupado)
        self.editor.setEnabled(tem_dub)
        tem_em = tem_dub and 0 <= self.onda.emenda_sel < len(self.onda.emendas)
        self.a_tocar.setEnabled(tem_dub or tem_film)
        self.a_inicio_audio.setEnabled(tem_dub or tem_film)
        self.a_add_emenda.setEnabled(tem_dub and not ocupado)
        self.a_rem_emenda.setEnabled(tem_em and not ocupado)
        self.a_pausa.setEnabled(tem_em and not ocupado)
        self.a_ouvir_emenda.setEnabled(tem_em)
        self.a_desfazer.setEnabled(tem_dub and bool(self._hist.get(id(self._dub_atual()), Historico()).passado))
        self.a_refazer.setEnabled(tem_dub and bool(self._hist.get(id(self._dub_atual()), Historico()).futuro))
        self.box_emenda.setEnabled(tem_dub and not ocupado)
        for w in (self.sp_em_tempo, self.sp_em_quantia, self.b_em_rem, self.b_em_pausa, self.b_em_ouvir,
                  self.b_em_ir, *self.botoes_emenda):
            w.setEnabled(tem_em and not ocupado)
        self.b_em_add.setEnabled(tem_dub and not ocupado)

    # ------------------------------------------------ fila de tarefas
    def _submeter(self, titulo, fn, ao_terminar=None, ao_falhar=None):
        self._fila.append((titulo, fn, ao_terminar, ao_falhar))
        if not self._ocupado():
            self._proxima()

    def _proxima(self):
        self._fase = None
        self.barra.setFormat("%p%")
        if not self._fila:
            self.barra.setRange(0, 100)
            self.barra.setValue(0)
            self.carregador.retomar()           # disco livre: a onda continua de onde parou
            self._atualizar_estado()
            return
        titulo, fn, ok, falha = self._fila.pop(0)
        t = Tarefa(fn)
        t.msg.connect(self._t_msg)
        t.prog.connect(self._t_prog)
        t.ok.connect(self._t_ok)
        t.erro.connect(self._t_erro)
        t.finished.connect(self._t_fim)
        self._atual = (t, titulo, ok, falha)
        self._t_inicio = time.monotonic()
        if self.carregador.ocupado():
            self.carregador.pausar()            # a tarefa usa o disco sozinha (muito mais rapido num HD)
            self.lbl_onda.setText(tr("Onda: pausada enquanto a tarefa roda (continua depois)"))
        self.log(titulo + "...")
        self.barra.setRange(0, 0)
        self._atualizar_estado()
        t.start()

    def _t_msg(self, m):
        self.log(m)

    def _t_prog(self, v):
        self.barra.setRange(0, 100)
        self.barra.setValue(v)
        agora = time.monotonic()                 # tempo restante da etapa atual
        fase = getattr(self, "_fase", None)
        if fase is None or v < fase[1]:
            fase = self._fase = (agora, v)
        if v - fase[1] >= 2 and agora - fase[0] > 10 and v < 100:
            seg = (agora - fase[0]) / (v - fase[1]) * (100 - v)
            self.barra.setFormat("%p%  - " + tr("faltam ~%s") % fmt_falta(seg))
        else:
            self.barra.setFormat("%p%")

    def _t_ok(self, res):
        _, titulo, ok, _ = self._atual
        try:
            if ok:
                ok(res)
        except Exception:
            self.erro(tr("Erro ao concluir: %s") % titulo, traceback.format_exc())

    def _t_erro(self, tb):
        _, titulo, _, falha = self._atual
        if tb == "__cancelado__":
            self.log(tr("Cancelado."))
            return
        if falha:
            falha(tb)
        else:
            self.erro(tr("Falhou: %s") % titulo, tb)

    def _t_fim(self):
        if self._atual:
            self.log(tr("(levou %s)") % fmt_tempo(time.monotonic() - getattr(self, "_t_inicio", time.monotonic())))
        if self._atual:
            self._atual[0].wait()
        self._atual = None
        self._proxima()

    def acao_cancelar(self, *_):
        """Cancela so a TAREFA (detectar, gerar...). A leitura das ondas continua."""
        self._fila.clear()
        if self._atual:
            self._atual[0].cancelar.set()
            self.log(tr("Cancelando..."))

    def acao_parar_ondas(self, *_):
        if self.carregador.ocupado():
            self.carregador.cancelar_tudo()
            self.log(tr("Leitura das ondas interrompida (Sincronização > Carregar as ondas para continuar)."))

    # ------------------------------------------------ ondas em segundo plano
    def _chave_ref(self):
        return (self.film.caminho, self._ref_pos()) if self.film else None

    def _codecs(self, caminho):
        arq = self._arquivos.get(caminho)
        return {f.pos: f.codec for f in arq.audios} if arq else {}

    def _duracao(self, caminho):
        arq = self._arquivos.get(caminho)
        return arq.duracao if arq else 0.0

    def _garantir_ondas(self, todas=False):
        """
        Pede ao carregador as ondas que faltam. A dublagem SELECIONADA vem primeiro (o arquivo dela
        costuma ser bem menor que o UHD, entao aparece rapido); o filme continua depois.
        """
        if not self.film:
            return
        ref = self._chave_ref()
        if ref not in self._completas:
            self.carregador.pedir(ref[0], [ref[1]], self._codecs(ref[0]), self._duracao(ref[0]))
        alvos = self.dubs if todas else ([self._dub_atual()] if self._dub_atual() else [])
        por_arquivo = {}
        for d in alvos:
            if (d.arquivo, d.faixa) not in self._completas:
                por_arquivo.setdefault(d.arquivo, set()).add(d.faixa)
        if not todas:                       # leva junto as outras faixas do mesmo arquivo (mesma leitura)
            for d in self.dubs:
                if d.arquivo in por_arquivo and (d.arquivo, d.faixa) not in self._completas:
                    por_arquivo[d.arquivo].add(d.faixa)
        sel = self._dub_atual()
        for caminho, posicoes in por_arquivo.items():
            urgente = bool(sel and sel.arquivo == caminho and (sel.arquivo, sel.faixa) not in self._completas)
            self.carregador.pedir(caminho, posicoes, self._codecs(caminho), self._duracao(caminho), urgente=urgente)
        self._atualizar_estado()

    def _nome_curto(self, caminho):
        if self.film and caminho == self.film.caminho:
            return tr("filme")
        n = os.path.basename(caminho)
        return n if len(n) <= 28 else n[:25] + "..."

    def _onda_progresso(self, caminho, fracao, segundos):
        agora = time.monotonic()
        ini = self._onda_ini.get(caminho)
        if ini is None or fracao < ini[1] or agora - ini[2] > 5:     # (re)comeco ou volta de uma pausa
            ini = self._onda_ini[caminho] = [agora, fracao, agora]
        ini[2] = agora
        extra = ""
        if fracao - ini[1] > 0.01 and agora - ini[0] > 3:
            vel = (fracao - ini[1]) / (agora - ini[0])               # fracao do arquivo por segundo
            seg = (1.0 - fracao) / vel
            try:
                extra += " - %.0f MB/s" % (vel * os.path.getsize(caminho) / 1e6)
            except OSError:
                pass
            extra += " - " + tr("faltam ~%s") % fmt_falta(seg)
        self.lbl_onda.setText(tr("Onda (%s): %d%%%s") % (self._nome_curto(caminho), int(fracao * 100), extra))
        self.barra_onda.setVisible(True)
        self.barra_onda.setValue(int(fracao * 100))

    def _mostrar_onda(self, chave, env, completa):
        sufixo = "" if completa else "   " + tr("(carregando...)")
        if chave == self._chave_ref():
            self.onda.set_ref(env, tr("Filme - faixa %d") % chave[1] + sufixo)
            if not self._ref_mostrada:
                self._ref_mostrada = True
                self.onda.ver_inicio()
        d = self._dub_atual()
        if d and (d.arquivo, d.faixa) == chave:
            self.onda.set_dub(env, d.nome + sufixo)

    def _onda_parcial(self, caminho, pos, env):
        chave = (caminho, pos)
        if chave not in self._completas:
            self._envs[chave] = env
            self._mostrar_onda(chave, env, False)

    def _onda_pronta(self, caminho, pos, env):
        chave = (caminho, pos)
        self._envs[chave] = env
        self._completas.add(chave)
        self._mostrar_onda(chave, env, True)
        self._onda_ini.pop(caminho, None)
        d = self._dub_atual()
        if d and (d.arquivo, d.faixa) == chave and d.trechos:      # agora da para medir o som em cada emenda
            self._atualizar_painel_emendas()

    def _onda_falhou(self, caminho, tb):
        self._onda_ini.pop(caminho, None)
        self.log(tr("Não consegui ler a onda de %s: %s") % (os.path.basename(caminho), tb.strip().splitlines()[-1]))

    def _onda_ociosa(self):
        self.lbl_onda.setText("")
        self.barra_onda.setVisible(False)
        self._atualizar_estado()

    # ------------------------------------------------ filme
    def acao_abrir_filme(self, *_):
        pasta = self.cfg.value("pasta", "")
        caminho, _ = QFileDialog.getOpenFileName(
            self, tr("Abrir filme"), pasta, tr("Vídeos (*.mkv *.mp4 *.m2ts *.ts *.avi *.mov);;Todos os arquivos (*)"))
        if caminho:
            self._carregar_filme(os.path.normpath(caminho))

    def _carregar_filme(self, caminho):
        try:
            arq = core.sondar_arquivo(caminho)
        except Exception as e:
            self.erro(tr("Não consegui abrir o filme"), str(e))
            return
        if not arq.audios:
            self.aviso(tr("Esse arquivo não tem nenhuma faixa de áudio."))
            return
        if self.film and self.film.caminho != caminho:
            self.carregador.cancelar_arquivo(self.film.caminho)
        self.film = arq
        self._arquivos[caminho] = arq
        self._ref_mostrada = False
        self.onda.set_ref(None)
        self.cfg.setValue("pasta", os.path.dirname(caminho))
        self.lbl_filme.setText(caminho)
        self._novo_filme_na_saida()
        self.cmb_ref.blockSignals(True)
        self.cmb_ref.clear()
        for f in arq.audios:
            self.cmb_ref.addItem(tr("faixa %d: %s") % (f.pos, f.rotulo()), f.pos)
        self.cmb_ref.setCurrentIndex(core.faixa_ingles(arq))
        self.cmb_ref.blockSignals(False)
        self.log(tr("Filme aberto: %s (%d faixas de áudio). A onda carrega em segundo plano; "
                    "você já pode adicionar dublagens e detectar o atraso.") % (os.path.basename(caminho),
                                                                                 len(arq.audios)))
        self._carregar_onda_ref()
        self._atualizar_estado()

    # ------------------------------------------------ arquivo final (ordem, o que entra, faixa padrao)
    def _novo_filme_na_saida(self):
        """Filme novo: tudo marcado na ordem do arquivo, ou o padrao BDRemux PT-BR se estiver ligado."""
        self.manter = set(f.idx for f in self.film.faixas if f.tipo in core.TIPOS_ESCOLHIVEIS)
        self.ordem, self.padrao_audio, self.padrao_legenda = [], None, None
        self._org_manual = False
        self._idioma_original = ""
        self.cmb_original.blockSignals(True)
        self.cmb_original.clear()
        self.cmb_original.addItem(tr("automático (%s)") % (core.idioma_original_auto(self.film) or "?"), "")
        for idioma in sorted({f.idioma for f in self.film.audios if f.idioma}):
            self.cmb_original.addItem(idioma, idioma)
        self.cmb_original.blockSignals(False)
        self._organizar_auto()
        self._preencher_saida()

    def _organizacao(self):
        return core.Organizacao(ordem=list(self.ordem), manter=self._manter_param(), padrao_audio=self.padrao_audio,
                                padrao_legenda=self.padrao_legenda)

    def _organizar_auto(self):
        """
        Reaplica o padrao BDRemux PT-BR (ordem e o que entra) se a opcao estiver ligada e a pessoa nao tiver
        organizado a mao. A faixa padrao escolhida pela pessoa continua (sem escolha: o primeiro audio).
        """
        if self.film and self.chk_org_auto.isChecked() and not self._org_manual:
            org = core.organizar_padrao(self.film, self.dubs, self.legendas, self._idioma_original or None)
            self.ordem, self.manter = org.ordem, set(org.manter)
            return True
        return False

    def acao_padrao_saida(self, *_):
        if not self.film:
            return
        org = core.organizar_padrao(self.film, self.dubs, self.legendas, self._idioma_original or None)
        self.ordem, self.manter = org.ordem, set(org.manter)
        self.padrao_audio = self.padrao_legenda = None
        self._org_manual = False
        self.log(tr("Arquivo final no padrão BDRemux PT-BR: áudio PT-BR, áudio original, legenda PT-BR."))
        self._depois_de_mudar_saida()

    def _ao_mudar_org_auto(self, ligado):
        self.cfg.setValue("organizar_auto", "true" if ligado else "false")
        if ligado and self._organizar_auto():
            self._depois_de_mudar_saida()

    def _ao_mudar_idioma_original(self, *_):
        self._idioma_original = self.cmb_original.currentData() or ""
        if self._organizar_auto():
            self._depois_de_mudar_saida()

    def _mudou_a_lista(self):
        """Dublagens ou legendas entraram/sairam ou mudaram: reorganiza (se for automatico) e refaz a tabela."""
        self._organizar_auto()
        self._preencher_saida()
        for i, d in enumerate(self.dubs):      # coluna 'Padrao' da lista de dublagens
            it = self.tab.item(i, 4) if i < self.tab.rowCount() else None
            if it is not None:
                it.setText(tr("Sim") if self._eh_padrao(d) else "")

    def _organizou_a_mao(self):
        if not self._org_manual:
            self._org_manual = True
            self.log(tr("Organização feita à mão: o padrão automático não será reaplicado (use \"Aplicar o padrão "
                        "BDRemux PT-BR\" para voltar a ele)."))

    def _depois_de_mudar_saida(self):
        self._refresh_tabela()          # refaz tambem a tabela do arquivo final (veja _refresh_tabela)

    def _tipo_chave(self, k):
        return core.tipo_da_chave(self.film, k) if self.film else None

    def _efetivo(self):
        """(itens do arquivo final por tipo, audio padrao, legenda padrao)."""
        org = self._organizacao()
        itens = core.itens_saida(self.film, self.dubs, self.legendas, org)
        return (itens,) + core.padroes_efetivos(itens, org)

    def _eh_padrao(self, d):
        if not self.film:
            return d.padrao
        _, pa, _ = self._efetivo()
        return pa == ("dub", d)

    def _preencher_saida(self, selecionar=None):
        """Refaz a tabela do arquivo final: cada tipo na ordem em que vai ficar; o que nao entra fica cinza."""
        if selecionar is None:
            linhas = self.tab_filme.selectionModel().selectedRows() if self.tab_filme.selectionModel() else []
            if linhas and linhas[0].row() < len(self._linhas_saida):
                selecionar = self._linhas_saida[linhas[0].row()]
        self._preenchendo_filme = True
        try:
            if not self.film:
                self.tab_filme.setRowCount(0)
                self._linhas_saida = []
                self.lbl_manter.setText("")
                return
            self.ordem = core.completar_ordem(self.film, self.dubs, self.legendas, self.ordem)
            itens, pa, pl = self._efetivo()
            numero, n = {}, 1
            for t in core.TIPOS_ESCOLHIVEIS:
                for k in itens[t]:
                    numero[k] = n
                    n += 1
            fx = {f.idx: f for f in self.film.faixas}
            linhas = [k for t in core.TIPOS_ESCOLHIVEIS for k in self.ordem if self._tipo_chave(k) == t]
            extras = [f for f in self.film.faixas if f.tipo not in core.TIPOS_ESCOLHIVEIS]
            self._linhas_saida = linhas + [None] * len(extras)
            self.tab_filme.setRowCount(len(self._linhas_saida))
            cinza = QColor(130, 130, 130)
            for r, k in enumerate(linhas):
                tipo, entra = self._tipo_chave(k), k in numero
                manter = QTableWidgetItem("")
                if k[0] == "filme":
                    f = fx[k[1]]
                    manter.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled |
                                    Qt.ItemFlag.ItemIsSelectable)
                    origem = tr("filme #%d") % f.idx
                    codec = f.codec + (" %dch" % f.canais if f.canais else "") + \
                        (" → SRT" if f.codec in core.LEGENDAS_PARA_SRT else "")
                    idioma, titulo = f.idioma, f.titulo
                    marcas = [self._nome_marca(m) for m in ("forced", "comment", "hearing_impaired",
                                                            "visual_impaired") if f.disposicao.get(m)]
                elif k[0] == "dub":
                    d = k[1]
                    manter.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
                    manter.setToolTip(tr("Dublagens e legendas adicionadas sempre entram (para tirar, remova da lista)"))
                    origem = tr("dublagem: %s") % os.path.basename(d.arquivo)
                    codec = "FLAC" if (d.trechos or abs(d.atempo - 1.0) > 1e-9) else (d.detalhe.split(" | ")[0])
                    idioma, titulo, marcas = d.idioma, d.nome, []
                else:
                    x = k[1]
                    manter.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
                    manter.setToolTip(tr("Dublagens e legendas adicionadas sempre entram (para tirar, remova da lista)"))
                    origem = tr("legenda: %s") % os.path.basename(x.arquivo)
                    codec = x.codec + (" → SRT" if x.codec in core.LEGENDAS_PARA_SRT else "")
                    idioma, titulo = x.idioma, x.nome
                    marcas = ([tr("forçada")] if x.forcada else []) + \
                        ([tr("atraso %+d ms") % x.atraso_ms] if x.atraso_ms else [])
                manter.setCheckState(Qt.CheckState.Checked if entra else Qt.CheckState.Unchecked)
                self.tab_filme.setItem(r, self.COL_MANTER, manter)
                valores = {self.COL_NUM: str(numero[k]) if entra else "-", self.COL_TIPO: rot_tipo(tipo),
                           self.COL_IDIOMA: idioma, self.COL_TITULO: titulo, self.COL_MARCAS: ", ".join(marcas),
                           self.COL_CODEC: codec, self.COL_ORIGEM: origem}
                for c, v in valores.items():
                    it = QTableWidgetItem(v)
                    if not entra:
                        it.setForeground(cinza)
                    self.tab_filme.setItem(r, c, it)
                padrao = QTableWidgetItem("")
                if tipo in ("audio", "subtitle"):
                    padrao.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled |
                                    Qt.ItemFlag.ItemIsSelectable)
                    padrao.setCheckState(Qt.CheckState.Checked if entra and k in (pa, pl) else Qt.CheckState.Unchecked)
                    padrao.setToolTip(tr("Toca sozinha ao abrir o arquivo") if tipo == "audio" else
                                      tr("Aparece sozinha ao abrir o arquivo (normalmente deixe desmarcado)"))
                self.tab_filme.setItem(r, self.COL_PADRAO, padrao)
            for i, f in enumerate(extras, len(linhas)):
                valores = {self.COL_MANTER: tr("sempre"), self.COL_TIPO: rot_tipo(f.tipo), self.COL_IDIOMA: f.idioma,
                           self.COL_TITULO: f.titulo, self.COL_CODEC: f.codec, self.COL_ORIGEM: tr("filme #%d") % f.idx}
                for c in range(self.tab_filme.columnCount()):
                    self.tab_filme.setItem(i, c, QTableWidgetItem(valores.get(c, "")))
            self.tab_filme.resizeColumnsToContents()
            if selecionar is not None and selecionar in self._linhas_saida:
                self.tab_filme.selectRow(self._linhas_saida.index(selecionar))
            self.lbl_manter.setText(tr("Arquivo final: %d vídeo, %d áudio(s), %d legenda(s), nesta ordem.")
                                    % (len(itens["video"]), len(itens["audio"]), len(itens["subtitle"])))
        finally:
            self._preenchendo_filme = False
        self._atualizar_estado()

    def _chave_escolhida_saida(self):
        linhas = self.tab_filme.selectionModel().selectedRows() if self.tab_filme.selectionModel() else []
        r = linhas[0].row() if linhas else -1
        return self._linhas_saida[r] if 0 <= r < len(self._linhas_saida) else None

    def _ao_mudar_item_saida(self, item):
        """Clique numa caixinha da tabela do arquivo final: 'Manter' (faixas do filme) ou 'Padrão'."""
        if self._preenchendo_filme or not self.film or item.row() >= len(self._linhas_saida):
            return
        k = self._linhas_saida[item.row()]
        if k is None or item.column() not in (self.COL_MANTER, self.COL_PADRAO):
            return
        marcado = item.checkState() == Qt.CheckState.Checked
        tipo = self._tipo_chave(k)
        if item.column() == self.COL_MANTER:
            if k[0] != "filme":
                return
            if not marcado and tipo == "video" and not any(
                    f.idx != k[1] and f.idx in self.manter for f in self.film.videos):
                self.log(tr("O arquivo final precisa de um vídeo: essa faixa continua."))
            else:
                (self.manter.add if marcado else self.manter.discard)(k[1])
                self._organizou_a_mao()
        else:
            _, pa, pl = self._efetivo()
            if marcado and k[0] == "filme" and k[1] not in self.manter:
                self.manter.add(k[1])            # escolher como padrao uma faixa desmarcada: ela passa a entrar
                self._organizou_a_mao()
            if tipo == "audio":
                if marcado:
                    self.padrao_audio = k
                elif self.padrao_audio == k:
                    self.padrao_audio = None     # volta a ser o primeiro audio
                if not marcado and k == pa and self.padrao_audio is None and k == self._efetivo()[0]["audio"][0]:
                    self.log(tr("Um áudio sempre é o padrão (o primeiro, se nenhum for escolhido). Para trocar, "
                                "marque outro."))
            elif tipo == "subtitle":
                if marcado:
                    self.padrao_legenda = k
                elif pl == k:
                    self.padrao_legenda = None
            for d in self.dubs:                  # (projetos antigos guardavam isto na dublagem)
                d.padrao = self.padrao_audio == ("dub", d)
        self._depois_de_mudar_saida()

    def _marcar_saida(self, tudo):
        if not self.film:
            return
        self.manter = set(f.idx for f in self.film.faixas
                          if f.tipo in core.TIPOS_ESCOLHIVEIS and (tudo or f.tipo == "video"))
        self._organizou_a_mao()
        self._depois_de_mudar_saida()

    def _mover_saida(self, delta):
        """Sobe ou desce a faixa escolhida entre as do mesmo tipo (videos, audios e legendas nao se misturam)."""
        k = self._chave_escolhida_saida()
        if k is None:
            return
        tipo = self._tipo_chave(k)
        mesmas = [x for x in self.ordem if self._tipo_chave(x) == tipo]
        i = mesmas.index(k)
        j = i + delta
        if not 0 <= j < len(mesmas):
            return
        a, b = self.ordem.index(mesmas[i]), self.ordem.index(mesmas[j])
        self.ordem[a], self.ordem[b] = self.ordem[b], self.ordem[a]
        self._organizou_a_mao()
        self._refresh_tabela()
        self._preencher_saida(selecionar=k)

    def _ao_duplo_clique_saida(self, item):
        k = self._linhas_saida[item.row()] if item.row() < len(self._linhas_saida) else None
        if k is None:
            return
        if k[0] == "leg":
            self.acao_editar_legenda()
        elif k[0] == "dub" and k[1] in self.dubs:
            self.tab.selectRow(self.dubs.index(k[1]))

    def _manter_param(self):
        """None = todas as faixas do filme (mais simples para o FFmpeg)."""
        if not self.film or self.manter is None:
            return None
        todas = set(f.idx for f in self.film.faixas if f.tipo in core.TIPOS_ESCOLHIVEIS)
        return None if self.manter >= todas else set(self.manter)

    # ------------------------------------------------ legendas externas
    def acao_add_legenda(self, *_):
        pasta = self.cfg.value("pasta", "")
        caminhos, _ = QFileDialog.getOpenFileNames(
            self, tr("Adicionar legenda(s)"), pasta,
            tr("Legendas (*.srt *.ass *.ssa *.vtt *.sup *.idx *.sub *.mks *.mkv *.mp4);;Todos os arquivos (*)"))
        if caminhos:
            self._adicionar_legendas([os.path.normpath(c) for c in caminhos])

    @staticmethod
    def _idioma_pelo_nome(caminho):
        """'Filme.pt-BR.srt' / 'Filme.por.srt' / 'Filme.eng.forced.srt' -> codigo de 3 letras (ou '')."""
        partes = [p.lower() for p in os.path.basename(caminho).split(".")[1:-1]]
        tabela = {"pt-br": "por", "ptbr": "por", "pt": "por", "por": "por", "pob": "por", "br": "por",
                  "en": "eng", "eng": "eng", "es": "spa", "spa": "spa", "fr": "fre", "fre": "fre", "fra": "fre",
                  "it": "ita", "ita": "ita", "de": "ger", "ger": "ger", "deu": "ger", "ja": "jpn", "jpn": "jpn"}
        return next((tabela[p] for p in reversed(partes) if p in tabela), "")

    def _adicionar_legendas(self, caminhos):
        if not self.film:
            self.aviso(tr("Abra primeiro o filme de alta qualidade."))
            return
        novas = []
        vistos = []
        for c in caminhos:
            raiz, ext = os.path.splitext(c)
            if ext.lower() == ".sub" and os.path.isfile(raiz + ".idx"):
                c = raiz + ".idx"                     # VobSub: o .idx descreve o .sub
            if c in vistos:
                continue
            vistos.append(c)
            try:
                arq = core.sondar_arquivo(c)
            except Exception as e:
                self.erro(tr("Não consegui abrir a legenda"), str(e))
                continue
            if not arq.legendas:
                self.aviso(tr("Sem faixa de legenda em:\n%s") % c)
                continue
            self.cfg.setValue("pasta", os.path.dirname(c))
            if len(arq.legendas) == 1:
                escolhidas = [0]
            else:
                dlg = EscolherFaixas(arq, (), self, tipo="subtitle")
                if not dlg.exec():
                    continue
                escolhidas = dlg.escolhidas()
            nome_arq = os.path.basename(c).lower()
            for pos in escolhidas:
                f = arq.legendas[pos]
                if any(x.chave() == (os.path.abspath(c), pos) for x in self.legendas):
                    continue
                idioma = f.idioma if len(f.idioma) == 3 and f.idioma != "und" else (self._idioma_pelo_nome(c) or "por")
                forcada = f.forcada() or any(p in nome_arq for p in ("forced", "forcad", "forçad"))
                nome = f.titulo
                if not nome and core.eh_portugues(idioma):
                    nome = tr("Português (Brasil) - Forçada") if forcada else tr("Português (Brasil)")
                x = core.LegendaExterna(arquivo=c, faixa=pos, nome=nome, idioma=idioma, forcada=forcada,
                                        codec=f.codec, detalhe=f.rotulo())
                for d in self.dubs:                       # legenda do mesmo arquivo de uma dublagem: mesmo atraso
                    if os.path.normcase(os.path.abspath(d.arquivo)) == os.path.normcase(os.path.abspath(c)):
                        if d.trechos:
                            self.log(tr("Atenção: %s vem do mesmo arquivo de uma dublagem sincronizada por trechos; "
                                        "a legenda entra com um atraso só (ajuste em Editar legenda).")
                                     % os.path.basename(c))
                        else:
                            x.atraso_ms = d.atraso_ms
                            if abs(d.atempo - 1.0) > 1e-9:
                                self.log(tr("Atenção: a dublagem de %s teve a velocidade corrigida; a legenda não "
                                            "acompanha essa correção.") % os.path.basename(c))
                        break
                novas.append(x)
        if novas:
            self.legendas.extend(novas)
            self.log(tr("%d legenda(s) adicionada(s).") % len(novas))
            self._mudou_a_lista()
            self.abas.setCurrentIndex(0)

    def _legenda_escolhida(self):
        k = self._chave_escolhida_saida()
        return k[1] if k is not None and k[0] == "leg" else None

    def acao_editar_legenda(self, *_):
        x = self._legenda_escolhida()
        if x is None:
            return
        dlg = EditarLegenda(x, self)
        if dlg.exec():
            dlg.aplicar(x)
            self._mudou_a_lista()

    def acao_remover_legenda(self, *_):
        x = self._legenda_escolhida()
        if x is None:
            return
        self.legendas = [y for y in self.legendas if y is not x]
        if self.padrao_legenda == ("leg", x):
            self.padrao_legenda = None
        self._mudou_a_lista()

    def _ref_pos(self):
        d = self.cmb_ref.currentData()
        return int(d) if d is not None else 0

    def _ao_mudar_ref(self, _):
        self._ref_mostrada = False
        self._carregar_onda_ref()

    def _carregar_onda_ref(self):
        if not self.film:
            return
        chave = self._chave_ref()
        if chave in self._envs:
            self._mostrar_onda(chave, self._envs[chave], chave in self._completas)
        else:
            self.onda.set_ref(None, tr("Filme - faixa %d") % chave[1] + "   " + tr("(carregando...)"))
        self._garantir_ondas()

    # ------------------------------------------------ dublagens
    def acao_adicionar(self, *_):
        pasta = self.cfg.value("pasta", "")
        caminhos, _ = QFileDialog.getOpenFileNames(
            self, tr("Adicionar dublagem(ns)"), pasta,
            tr("Áudio/vídeo (*.mkv *.mka *.mp4 *.m4a *.mp3 *.ac3 *.eac3 *.dts *.flac *.wav *.aac *.ogg *.m2ts)"
               ";;Todos os arquivos (*)"))
        if caminhos:
            self._adicionar_arquivos([os.path.normpath(c) for c in caminhos])

    def _adicionar_arquivos(self, caminhos):
        if not self.film:
            self.aviso(tr("Abra primeiro o filme de alta qualidade."))
            return
        idiomas_filme = {f.idioma for f in self.film.audios if f.idioma}
        novas = []
        for c in caminhos:
            try:
                arq = core.sondar_arquivo(c)
            except Exception as e:
                self.erro(tr("Não consegui abrir a dublagem"), str(e))
                continue
            if not arq.audios:
                self.aviso(tr("Sem faixa de áudio em:\n%s") % c)
                continue
            self.cfg.setValue("pasta", os.path.dirname(c))
            self._arquivos[c] = arq
            if len(arq.audios) == 1:
                escolhidas = [0]
            else:
                dlg = EscolherFaixas(arq, idiomas_filme, self)
                if not dlg.exec():
                    continue
                escolhidas = dlg.escolhidas()
            for pos in escolhidas:
                f = arq.audios[pos]
                if any(d.chave() == (os.path.abspath(c), pos) for d in self.dubs):
                    continue
                idioma = f.idioma if len(f.idioma) == 3 else ("por" if i18n.atual() == "pt" else "und")
                novas.append(core.Dublagem(arquivo=c, faixa=pos, nome=core.nome_sugerido(f.titulo, tr("Dublagem PT-BR")),
                                           idioma=idioma, detalhe=f.rotulo()))
        if novas:
            self.dubs.extend(novas)
            self.log(tr("%d dublagem(ns) adicionada(s).") % len(novas))
            self._organizar_auto()
            self._refresh_tabela(len(self.dubs) - len(novas))

    def _dub_atual(self):
        r = self.tab.currentRow() if hasattr(self, "tab") else -1
        return self.dubs[r] if 0 <= r < len(self.dubs) else None

    def _refresh_tabela(self, selecionar=None):
        self._preencher_saida()
        if selecionar is None:
            selecionar = self.tab.currentRow()
        self.tab.blockSignals(True)
        self.tab.setRowCount(len(self.dubs))
        for i, d in enumerate(self.dubs):
            vals = [str(i + 1), d.nome, tr("%s : faixa %d") % (os.path.basename(d.arquivo), d.faixa),
                    self._texto_atraso(d), tr("Sim") if self._eh_padrao(d) else "", d.status]
            for c, v in enumerate(vals):
                self.tab.setItem(i, c, QTableWidgetItem(v))
        self.tab.blockSignals(False)
        if self.dubs:
            self.tab.selectRow(max(0, min(selecionar, len(self.dubs) - 1)))
        self._ao_selecionar()

    @staticmethod
    def _texto_atraso(d):
        vel = "  (x%.4f)" % (1.0 / d.atempo) if abs(d.atempo - 1.0) > 1e-9 else ""
        if d.trechos:
            aj = ("  %+d" % d.atraso_ms) if d.atraso_ms else ""
            return tr("%d trechos") % len(d.trechos) + aj + vel
        return "%+d%s" % (d.atraso_ms, vel)

    def _ao_selecionar(self):
        d = self._dub_atual()
        self._carregando = True
        if d:
            self.ed_nome.setText(d.nome)
            self.ed_idioma.setText(d.idioma)
            self.sp_atraso.setValue(d.atraso_ms)
            self.chk_padrao.setChecked(self._eh_padrao(d))
            self.lbl_origem.setText(tr("%s  -  faixa %d  (%s)") % (d.arquivo, d.faixa, d.detalhe))
            txt = tr("normal") if abs(d.atempo - 1.0) < 1e-9 else \
                tr("corrigida (atempo=%.6f; só esta dublagem será convertida para FLAC)") % d.atempo
            if d.trechos:
                txt += "   |   " + tr("sincronia por trechos: %d trechos (o Atraso acima é um ajuste fino somado a "
                                       "todos; só esta dublagem vira FLAC)") % len(d.trechos)
            self.lbl_vel.setText(txt)
        else:
            self.ed_nome.clear()
            self.ed_idioma.clear()
            self.lbl_origem.setText("-")
            self.lbl_vel.setText("-")
        self._carregando = False
        if id(d) != getattr(self, "_dub_do_painel", None):
            self.onda.emenda_sel = -1                         # outra dublagem: a emenda escolhida deixa de valer
            self._dub_do_painel = id(d)
        self._atualizar_estado()
        if d:
            self.onda.set_atraso(d.atraso_ms, d.atempo, d.trechos)
            self._carregar_onda_dub(d)
        else:
            self.onda.set_dub(None)
        self._atualizar_painel_emendas()

    def _carregar_onda_dub(self, d):
        chave = (d.arquivo, d.faixa)
        if d.arquivo not in self._arquivos:
            try:
                self._arquivos[d.arquivo] = core.sondar_arquivo(d.arquivo)
            except Exception:
                pass
        if chave in self._envs:
            self._mostrar_onda(chave, self._envs[chave], chave in self._completas)
        else:
            self.onda.set_dub(None, d.nome + "   " + tr("(carregando...)"))
        self._garantir_ondas()

    def acao_remover(self, *_):
        if self.onda.hasFocus() and self.onda.emenda_sel >= 0:      # Del na onda com uma emenda escolhida: e a emenda
            self.acao_remover_emenda()
            return
        r = self.tab.currentRow()
        if 0 <= r < len(self.dubs):
            d = self.dubs[r]
            self._hist.pop(id(d), None)
            del self.dubs[r]
            if self.padrao_audio == ("dub", d):
                self.padrao_audio = None
            self._organizar_auto()
            self._refresh_tabela(r)

    def acao_mover(self, delta):
        """Muda a ordem das dublagens na lista E no arquivo final (as duas trocam de lugar entre si)."""
        r = self.tab.currentRow()
        n = r + delta
        if 0 <= r < len(self.dubs) and 0 <= n < len(self.dubs):
            a, b = ("dub", self.dubs[r]), ("dub", self.dubs[n])
            self.dubs[r], self.dubs[n] = self.dubs[n], self.dubs[r]
            if self.film:
                self.ordem = core.completar_ordem(self.film, self.dubs, self.legendas, self.ordem)
                i, j = self.ordem.index(a), self.ordem.index(b)
                self.ordem[i], self.ordem[j] = self.ordem[j], self.ordem[i]
            self._refresh_tabela(n)

    def acao_zerar(self, *_):
        d = self._dub_atual()
        if d:
            self._guardar_historico(d, "zerar", forcar=True)
            d.atraso_ms, d.atempo, d.status, d.trechos = 0, 1.0, "", None
            self._refresh_tabela()

    # ------------------------------------------------ editor
    def _ed_nome(self, texto):
        d = self._dub_atual()
        if d and not self._carregando:
            d.nome = texto
            self.tab.item(self.tab.currentRow(), 1).setText(texto)
            self._mudou_a_lista()

    def _ed_idioma(self, texto):
        d = self._dub_atual()
        if d and not self._carregando:
            d.idioma = texto.strip().lower()
            self._mudou_a_lista()

    def _ed_atraso(self, valor):
        d = self._dub_atual()
        if d and not self._carregando:
            self._guardar_historico(d, "atraso")
            d.atraso_ms = int(valor)
            self.tab.item(self.tab.currentRow(), 3).setText(self._texto_atraso(d))
            self.onda.set_atraso(d.atraso_ms, d.atempo, d.trechos)
            if d.trechos:                                   # o ajuste fino desloca todas as emendas
                self._atualizar_painel_emendas()

    def _ed_padrao(self, marcado):
        """Faixa padrao = a que toca sozinha ao abrir o arquivo. Desmarcar volta para o primeiro audio."""
        d = self._dub_atual()
        if d and not self._carregando:
            if marcado:
                self.padrao_audio = ("dub", d)
            elif self.padrao_audio == ("dub", d):
                self.padrao_audio = None
            for o in self.dubs:
                o.padrao = self.padrao_audio == ("dub", o)
            if not marcado and self._eh_padrao(d):
                self.log(tr("Um áudio sempre é o padrão (o primeiro, se nenhum for escolhido). Para trocar, "
                            "marque outro."))
            self._refresh_tabela()

    def _nudge(self, delta):
        if self._dub_atual():
            self.sp_atraso.setValue(self.sp_atraso.value() + delta)

    def _onda_arrastou(self, ms):
        if self._dub_atual():
            self.sp_atraso.setValue(max(-3600000, min(3600000, ms)))

    # ------------------------------------------------ deteccao
    def acao_detectar(self, *_):
        d = self._dub_atual()
        if not (self.film and d) or self._ocupado():
            return
        caminho, ref = self.film.caminho, self._ref_pos()

        def job(msg, prog, cancelar):
            return core.detectar(caminho, ref, d.arquivo, d.faixa, cancelar, msg, prog)
        self._submeter(tr("Detectando o atraso (análise rápida: lê só trechos do filme)"), job,
                       lambda r: self._aplicar_resultado([d], r, (d.arquivo, d.faixa)))

    def acao_detectar_faixa_arquivo(self, *_):
        d = self._dub_atual()
        if not (self.film and d) or self._ocupado():
            return
        try:
            arq = core.sondar_arquivo(d.arquivo)
        except Exception as e:
            self.erro(tr("Não consegui abrir o arquivo"), str(e))
            return
        itens = ["%d: %s" % (f.pos, f.rotulo()) for f in arq.audios]
        item, ok = QInputDialog.getItem(
            self, tr("Faixa usada na medição"),
            tr("Medir o atraso usando qual faixa deste arquivo?\n"
               "(o resultado vale para TODAS as dublagens que vieram deste arquivo)"),
            itens, core.faixa_ingles(arq), False)
        if not ok:
            return
        pos = int(item.split(":")[0])
        alvos = [x for x in self.dubs if os.path.abspath(x.arquivo) == os.path.abspath(d.arquivo)]
        caminho, ref, origem = self.film.caminho, self._ref_pos(), d.arquivo

        def job(msg, prog, cancelar):
            return core.detectar(caminho, ref, origem, pos, cancelar, msg, prog)
        self._submeter(tr("Detectando o atraso (faixa %d do arquivo)") % pos, job,
                       lambda r: self._aplicar_resultado(alvos, r, (origem, pos)))

    def acao_detectar_completo(self, *_):
        d = self._dub_atual()
        if not (self.film and d) or self._ocupado():
            return
        try:
            gb = os.path.getsize(self.film.caminho) / 1e9
        except OSError:
            gb = 0
        r = QMessageBox.question(
            self, NOME_APP,
            tr("A análise completa lê o filme INTEIRO (%.0f GB) e a dublagem inteira.\nNum HD isso leva vários "
               "minutos (a onda do filme aproveita a mesma leitura). Continuar?") % gb,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        caminho, ref = self.film.caminho, self._ref_pos()

        def job(msg, prog, cancelar):
            return core.detectar(caminho, ref, d.arquivo, d.faixa, cancelar, msg, prog, completo=True)
        self._submeter(tr("Detectando o atraso (análise completa)"), job,
                       lambda res: self._aplicar_resultado([d], res, (d.arquivo, d.faixa)))

    def acao_detectar_video(self, *_):
        d = self._dub_atual()
        if not (self.film and d) or self._ocupado():
            return
        r = QMessageBox.question(self, NOME_APP,
                                 tr("Comparar os cortes de cena dos vídeos pode levar MUITO tempo com um UHD 4K "
                                    "(de vários minutos a mais de uma hora).\n\nA dublagem precisa estar num arquivo "
                                    "com vídeo.  Continuar?"),
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        film = self.film.caminho

        def job(msg, prog, cancelar):
            return core.detectar_video(film, d.arquivo, msg, cancelar)
        self._submeter(tr("Detectando o atraso pelo vídeo"), job,
                       lambda res: self._aplicar_resultado([d], res, (d.arquivo, d.faixa)))

    def _aplicar_resultado(self, alvos, r, medida=None):
        """medida = (arquivo, faixa) usados na medicao (a sincronia por trechos mede com a mesma faixa)."""
        st, conf = r["status"], r["confianca"]
        self.log(tr("Resultado (%s): %s, confiança %s, atraso %+d ms, velocidade x%.5f") %
                 (rot_metodo(r["metodo"]), i18n.rot_status(st), rot_conf(conf), r["atraso_ms"], 1.0 / r["atempo"]))
        if r.get("modo") == "rapido" and r.get("lido_filme_s"):
            self.log(tr("Análise rápida: leu só %s do filme e %s da dublagem (trechos espalhados).")
                     % (fmt_tempo(r["lido_filme_s"]), fmt_tempo(r["lido_dub_s"] or 0)))
        if r.get("falhas"):
            self.log(tr("Obs.: não achei a dublagem perto de %s do filme (cena sem música/efeitos, ou diferente?).")
                     % ", ".join(fmt_tempo(t) for t in r["falhas"]))
        if st == "BAIXA_CONFIANCA" or conf == "BAIXA":
            for a in alvos:
                a.status = tr("sem correspondência confiável")
            self._refresh_tabela()
            if r.get("motivo"):
                self.log(tr("Análise rápida: %s") % r["motivo"])
            self.aviso(tr("Não encontrei uma correspondência confiável entre a dublagem e o filme.\n\n"
                          "Opções (menu Sincronização):\n"
                          " - 'Detectar usando outra faixa do arquivo' (ex.: a faixa em inglês da mesma fonte);\n"
                          " - 'Detectar lendo os arquivos inteiros (lento)';\n"
                          " - 'Detectar pelo vídeo';\n"
                          " - ou arraste a faixa laranja na onda para alinhar na mão."))
            return
        if st == "OK":
            for a in alvos:
                self._guardar_historico(a, "deteccao", forcar=True)
                a.atraso_ms, a.atempo, a.trechos = r["atraso_ms"], 1.0, None
                a.status = tr("detectado: %s, confiança %s") % (rot_metodo(r["metodo"]), rot_conf(conf))
        elif st in ("VELOCIDADE", "DERIVA"):
            if st == "VELOCIDADE":
                motivo = tr(r["descricao_velocidade"])
            else:
                motivo = tr("o atraso muda %.2f s por hora (velocidades um pouco diferentes)") % \
                    abs(r["deriva_s_por_hora"])
            resp = QMessageBox.question(
                self, NOME_APP,
                tr("A dublagem e o filme têm VELOCIDADES diferentes:\n%s.\n\nCorrigir a velocidade? Ao gerar o "
                   "arquivo, SOMENTE a dublagem será convertida para FLAC (o vídeo não é tocado).\n\n"
                   "Atraso depois da correção: %+d ms") % (motivo, r["atraso_ms"]),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            sim = resp == QMessageBox.StandardButton.Yes
            for a in alvos:
                self._guardar_historico(a, "deteccao", forcar=True)
                a.atraso_ms, a.trechos = r["atraso_ms"], None
                a.atempo = r["atempo"] if sim else 1.0
                a.status = (tr("velocidade corrigida (x%.4f), confiança %s") % (1 / r["atempo"], rot_conf(conf)) if sim
                            else tr("velocidade DIFERENTE, confiança %s") % rot_conf(conf))
        else:                                       # CORTES
            linhas = [tr("de %s a %s: %+d ms") % (fmt_tempo(g["ini"]), fmt_tempo(g["fim"]), g["atraso_ms"])
                      for g in r["grupos"]]
            cab = (tr("As versões têm CORTES diferentes: o atraso muda ao longo do filme (tempos do filme).")
                   if r.get("tempo_grupos") == "filme" else
                   tr("As versões têm CORTES diferentes: o atraso muda ao longo do filme."))
            self.log(tr("Trechos com atrasos diferentes: %s") % "; ".join(linhas))
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle(NOME_APP)
            box.setText(cab + "\n\n" + "\n".join(linhas[:12]))
            box.setInformativeText(
                tr("Um único atraso deixa parte das falas fora do lugar.\n\n"
                   "Sincronizar trecho por trecho (recomendado): o EternalDub mede o atraso a cada segundo e monta a "
                   "dublagem pedaço por pedaço. Onde a dublagem não tem um pedaço do filme entra silêncio; onde ela "
                   "tem algo que não existe no filme, esse pedaço sai (de preferência numa pausa). Só a dublagem "
                   "vira FLAC (sem perdas); o filme não é tocado."))
            b_mapa = box.addButton(tr("Sincronizar trecho por trecho"), QMessageBox.ButtonRole.AcceptRole)
            b_um = box.addButton(tr("Usar um atraso só (%+d ms)") % r["atraso_ms"], QMessageBox.ButtonRole.ActionRole)
            box.addButton(tr("Cancelar"), QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(b_mapa)
            box.exec()
            for a in alvos:
                a.status = tr("CORTES diferentes - ver registro")
            if box.clickedButton() is b_um:
                for a in alvos:
                    self._guardar_historico(a, "deteccao", forcar=True)
                    a.atraso_ms, a.atempo, a.trechos = r["atraso_ms"], 1.0, None
            elif box.clickedButton() is b_mapa:
                arq, faixa = medida or (alvos[0].arquivo, alvos[0].faixa)
                self._iniciar_mapa(alvos, arq, faixa, r.get("atempo", 1.0), r["atraso_ms"],
                                   [g["atraso_ms"] for g in r["grupos"]])
        self._refresh_tabela()

    # ------------------------------------------------ sincronia por trechos
    def acao_mapear(self, *_):
        d = self._dub_atual()
        if not (self.film and d) or self._ocupado():
            return
        try:
            arq = core.sondar_arquivo(d.arquivo)
        except Exception as e:
            self.erro(tr("Não consegui abrir o arquivo"), str(e))
            return
        pos = d.faixa
        if len(arq.audios) > 1:
            itens = ["%d: %s" % (f.pos, f.rotulo()) for f in arq.audios]
            item, ok = QInputDialog.getItem(
                self, tr("Faixa usada na medição"),
                tr("Medir trecho por trecho usando qual faixa deste arquivo?\n"
                   "(a própria dublagem funciona; uma faixa no idioma original da mesma fonte costuma ser ainda "
                   "melhor, e aí o resultado vale para TODAS as dublagens deste arquivo)"),
                itens, d.faixa, False)
            if not ok:
                return
            pos = int(item.split(":")[0])
        alvos = [d] if pos == d.faixa else \
            [x for x in self.dubs if os.path.abspath(x.arquivo) == os.path.abspath(d.arquivo)]
        centro = None if (d.trechos or (d.atraso_ms == 0 and abs(d.atempo - 1.0) < 1e-9)) else d.atraso_ms
        self._iniciar_mapa(alvos, d.arquivo, pos, d.atempo if centro is not None else 1.0, centro, None)

    def _iniciar_mapa(self, alvos, arquivo, faixa, atempo, centro_ms, grupos_ms):
        caminho, ref = self.film.caminho, self._ref_pos()
        try:
            gb = os.path.getsize(caminho) / 1e9
        except OSError:
            gb = 0
        if not core.em_cache(caminho, ref):
            r = QMessageBox.question(
                self, NOME_APP,
                tr("A sincronia por trechos precisa do áudio INTEIRO do filme (%.0f GB) e da dublagem. A onda do "
                   "filme ainda não foi lida por completo, então o filme será lido agora (num HD pode levar vários "
                   "minutos; fica guardado para as próximas vezes). Continuar?") % gb,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes:
                return

        def job(msg, prog, cancelar):
            return core.mapear(caminho, ref, arquivo, faixa, atempo, centro_ms, grupos_ms, cancelar, msg, prog)
        self._submeter(tr("Sincronizando trecho por trecho"), job, lambda m: self._aplicar_mapa(alvos, m))

    def _aplicar_mapa(self, alvos, m):
        n = len(m["pedacos"])
        self.log(tr("Sincronia por trechos: %d trechos, %d emendas; o mapa concorda com %.0f%% dos pontos medidos "
                    "com segurança.") % (len(m["trechos"]), len(m["cortes"]), m["concordancia"]))
        for t in m["trechos"]:
            self.log(tr("   %s a %s: atraso %+d ms") % (fmt_tempo(max(0.0, t["ini"])), fmt_tempo(t["fim"]),
                                                       round(t["atraso"] * 1000)))
        for c in m["cortes"]:
            if c["delta"] > 0:
                self.log(tr("   emenda em %s: %d ms de silêncio (a dublagem não tem esse pedaço)")
                         % (fmt_tempo(c["t"]), round(c["delta"] * 1000)))
            else:
                self.log(tr("   emenda em %s: saem %d ms da dublagem (pedaço que não existe no filme)")
                         % (fmt_tempo(c["t"]), round(-c["delta"] * 1000)))
        resumo = [tr("Trechos: %d   (emendas: %d)") % (len(m["trechos"]), len(m["cortes"])),
                  tr("Concorda com %.0f%% dos pontos medidos com segurança") % m["concordancia"],
                  tr("Silêncio inserido no total: %.1f s") % m["silencio_s"],
                  tr("Dublagem removida no total: %.1f s") % m["removido_s"]]
        if m["inicio_fora_s"] > 0.5:
            resumo.append(tr("Começo da dublagem que fica antes do filme (não entra): %.1f s") % m["inicio_fora_s"])
        if m["fim_fora_s"] > 0.5:
            resumo.append(tr("Fim da dublagem que passa do filme (não entra): %.1f s") % m["fim_fora_s"])
        for linha in resumo:
            self.log(linha)
        if len(m["trechos"]) <= 1 and abs(m["atempo"] - 1.0) < 1e-9:
            atr = int(round(m["trechos"][0]["atraso"] * 1000)) if m["trechos"] else 0
            for a in alvos:                     # um trecho so: atraso simples, montado por copia exata
                self._guardar_historico(a, "mapa", forcar=True)
                a.atraso_ms, a.atempo, a.trechos = atr, 1.0, None
                a.status = tr("um atraso só serve (%+d ms)") % atr
            self._refresh_tabela()
            self.aviso(tr("O mapa achou um único trecho: um atraso só (%+d ms) serve para o filme inteiro.") % atr)
            return
        for a in alvos:
            self._guardar_historico(a, "mapa", forcar=True)
            a.trechos = [list(x) for x in m["pedacos"]]
            a.atempo, a.atraso_ms = m["atempo"], 0
            a.status = tr("sincronia por trechos: %d trechos") % n
        self._refresh_tabela()
        self.aviso(tr("Sincronia por trechos pronta.\n\n%s\n\nA onda mostra a dublagem já no lugar (as emendas "
                      "ficam marcadas em vermelho). A lista completa das emendas está no Registro e na aba Emendas, onde "
                      "você pode ajustar cada uma à mão e ouvir o resultado (F8).\n\n"
                      "Confira com Gerar teste (5 min) e, no arquivo final, ouça alguns pontos das emendas.")
                   % "\n".join(resumo))

    # ------------------------------------------------ desfazer / refazer
    def _guardar_historico(self, d, tipo, estado=None, forcar=False):
        """
        Guarda o estado atual de `d` para o Desfazer. Ajustes seguidos do mesmo tipo (arrastar, repetir uma
        seta, girar o botao do atraso) viram UM passo so, a nao ser que `forcar`.
        """
        agora = time.monotonic()
        ult = self._ult_edicao
        junta = (not forcar) and ult is not None and ult[0] == id(d) and ult[1] == tipo and agora - ult[2] < 1.5
        self._ult_edicao = (id(d), tipo, agora)
        if junta:
            return
        h = self._hist.setdefault(id(d), Historico())
        if estado is None:
            h.guardar(d)
        else:
            h.passado.append(estado)
            del h.passado[:-h.LIMITE]
            h.futuro.clear()

    def _depois_de_historico(self, d):
        self._ult_edicao = None
        self._refresh_tabela()

    def acao_desfazer(self, *_):
        d = self._dub_atual()
        h = self._hist.get(id(d)) if d else None
        if h and h.desfazer(d):
            self._depois_de_historico(d)
            self._reiniciar_audio()
        else:
            self.log(tr("Nada para desfazer."))

    def acao_refazer(self, *_):
        d = self._dub_atual()
        h = self._hist.get(id(d)) if d else None
        if h and h.refazer(d):
            self._depois_de_historico(d)
            self._reiniciar_audio()
        else:
            self.log(tr("Nada para refazer."))

    # ------------------------------------------------ emendas: o modelo ligado a dublagem selecionada
    def _duracoes(self, d):
        """(fim do audio do filme, fim do audio da dublagem) em segundos; 0 = nao se sabe."""
        dur_f = dur_d = 0.0
        if self.film:
            try:
                dur_f = self.film.fim_audio(self._ref_pos())
            except IndexError:
                dur_f = self.film.duracao
        arq = self._arquivos.get(d.arquivo)
        if arq:
            try:
                dur_d = arq.fim_audio(d.faixa)
            except IndexError:
                dur_d = arq.duracao
        return dur_f, dur_d

    def _modelo_de(self, d, estado=None):
        """Modelo editavel da sincronia de `d` (ou do `estado` guardado: atraso_ms, atempo, trechos, status)."""
        atraso_ms, atempo, trechos = (d.atraso_ms, d.atempo, d.trechos) if estado is None else estado[:3]
        dur_f, dur_d = self._duracoes(d)
        if trechos:
            return emendas.MapaEditavel.de_trechos(trechos, atempo, dur_f, dur_d)
        return emendas.MapaEditavel.de_atraso(atraso_ms / 1000.0, atempo, dur_f, dur_d)

    @staticmethod
    def _ajuste_fino(d, estado=None):
        """Segundos que o atraso (ms) soma a TODOS os tempos do mapa (so existe quando ha sincronia por trechos)."""
        atraso_ms, trechos = (d.atraso_ms, d.trechos) if estado is None else (estado[0], estado[2])
        return atraso_ms / 1000.0 if trechos else 0.0

    def _gravar_modelo(self, d, m, aj):
        """Passa o modelo editado para a dublagem (aj = ajuste fino que ja estava somado ao mapa)."""
        if m.tem_emendas():
            d.trechos = m.para_trechos()
            d.atraso_ms = int(round(aj * 1000))
            d.status = tr("sincronia por trechos: %d trechos") % len(d.trechos)
        else:                                               # sem emendas: volta a um atraso so (copia exata)
            d.trechos = None
            d.atraso_ms = int(round((m.atraso_unico() + aj) * 1000))
            d.status = tr("um atraso só serve (%+d ms)") % d.atraso_ms

    def _amplitude(self, d):
        """(amplitude 10 ms, volume de referencia) da onda da dublagem para medir o som nas emendas, ou (None, 0)."""
        chave = (d.arquivo, d.faixa)
        env = self._envs.get(chave)
        if env is None or len(env) == 0:
            return None, 0.0
        c = self._amp_cache.get(chave)
        if c is None or c[0] is not env:
            amp = emendas.amplitude_do_envelope(env)
            c = self._amp_cache[chave] = (env, amp, emendas.referencia_de_nivel(amp))
        return c[1], c[2]

    def _emendas_da_onda(self, d, m=None):
        """Emendas de `d` para a onda e a tabela: tempos do filme (ja com o ajuste fino) e o som em cada uma."""
        m = m or self._modelo_de(d)
        aj = self._ajuste_fino(d)
        amp, ref = self._amplitude(d)
        saida = []
        for i, e in enumerate(m.emendas):
            nivel = emendas.nivel_da_emenda(m, i, amp, ref) if amp is not None else None
            saida.append({"t": e.t + aj, "silencio": e.silencio, "remocao": e.remocao, "nivel": nivel,
                          "som": emendas.classificar_nivel(nivel)})
        return saida

    def _atualizar_painel_emendas(self, selecionar=None):
        """Refaz a aba Emendas e as marcas da onda a partir da dublagem selecionada."""
        d = self._dub_atual()
        lista = self._emendas_da_onda(d) if d is not None else []
        self._atualizando_emendas = True
        try:
            self.onda.set_emendas(lista, selecionar)
            sel = self.onda.emenda_sel
            self.tab_em.setRowCount(len(lista))
            for i, e in enumerate(lista):
                quantia = e["silencio"] - e["remocao"]
                som = {"pausa": tr("pausa"), "baixo": tr("som baixo"), "alto": tr("SOM ALTO (pode cortar fala)")}.get(
                    e["som"], "-")
                texto = tr("entra silêncio (a dublagem não tem esse pedaço)") if quantia > 0 else \
                    tr("sai um pedaço da dublagem (não existe no filme)")
                for c, v in enumerate((str(i + 1), fmt_tempo_ms(e["t"]), fmt_quantia(quantia), som, texto)):
                    it = QTableWidgetItem(v)
                    it.setToolTip(v)
                    if c == 3 and e["som"] == "alto":
                        it.setForeground(QColor(255, 140, 60))
                    self.tab_em.setItem(i, c, it)
            if 0 <= sel < len(lista):
                self.tab_em.selectRow(sel)
            else:
                self.tab_em.clearSelection()
            if d is None:
                self.lbl_emendas.setText("")
            elif not lista:
                self.lbl_emendas.setText(tr("Esta dublagem não tem emendas (um atraso só). Para criar uma, clique com "
                                            "o botão direito na onda ou use \"Adicionar na linha azul\": ela diz "
                                            "quanto silêncio entra (ou sai da dublagem) a partir daquele ponto."))
            else:
                total_sil = sum(e["silencio"] for e in lista)
                total_rem = sum(e["remocao"] for e in lista)
                self.lbl_emendas.setText(tr("Emendas: %d. Silêncio inserido: %.2f s. Removido da dublagem: %.2f s. "
                                            "Arraste as linhas vermelhas na onda, ou escolha uma na lista.")
                                         % (len(lista), total_sil, total_rem))
            self._sincronizar_controles_emenda(lista)
        finally:
            self._atualizando_emendas = False
        self._atualizar_estado()

    def _sincronizar_controles_emenda(self, lista=None):
        i = self.onda.emenda_sel
        d = self._dub_atual()
        lista = lista if lista is not None else (self._emendas_da_onda(d) if d else [])
        ok = d is not None and 0 <= i < len(lista)
        for w in (self.sp_em_tempo, self.sp_em_quantia):
            w.blockSignals(True)
        if ok:
            e = lista[i]
            self.sp_em_tempo.setValue(e["t"])
            self.sp_em_quantia.setValue(int(round((e["silencio"] - e["remocao"]) * 1000)))
            self._quantia_ant = self.sp_em_quantia.value()
        for w in (self.sp_em_tempo, self.sp_em_quantia):
            w.blockSignals(False)

    # ---- editar
    def _editar_emendas(self, operacao, tipo, forcar=False):
        """
        Aplica operacao(modelo, ajuste_fino) a sincronia da dublagem selecionada. A operacao devolve None quando
        nao fez nada (nesse caso nada muda e nada vai para o Desfazer). Devolve o que ela devolveu.
        """
        d = self._dub_atual()
        if d is None or self._ocupado():
            return None
        antes = Historico.estado(d)
        m, aj = self._modelo_de(d), self._ajuste_fino(d)
        r = operacao(m, aj)
        if r is None:
            return None
        self._guardar_historico(d, tipo, antes, forcar)
        self._gravar_modelo(d, m, aj)
        self._mostrar_edicao(d)
        return r

    def _mostrar_edicao(self, d, selecionar=None):
        """Atualiza tabela, onda e painel depois de uma edicao da sincronia de `d`."""
        if d in self.dubs:
            r = self.dubs.index(d)
            for c, v in ((3, self._texto_atraso(d)), (5, d.status)):
                if self.tab.item(r, c):
                    self.tab.item(r, c).setText(v)
        self._carregando = True
        self.sp_atraso.setValue(d.atraso_ms)
        self._carregando = False
        self.onda.set_atraso(d.atraso_ms, d.atempo, d.trechos)
        self._atualizar_painel_emendas(selecionar)

    def _emenda_escolhida(self):
        """(dublagem, indice da emenda escolhida) ou (None, -1)."""
        d, i = self._dub_atual(), self.onda.emenda_sel
        return (d, i) if d is not None and i >= 0 else (None, -1)

    def _ao_escolher_emenda_na_onda(self, i):
        self._atualizar_painel_emendas(i)
        if self.abas.currentIndex() == 0:               # estava na aba Arquivo final: mostra a aba Emendas
            self.abas.setCurrentIndex(1)

    def _ao_escolher_emenda_na_tabela(self):
        if self._atualizando_emendas:
            return
        linhas = self.tab_em.selectionModel().selectedRows()
        i = linhas[0].row() if linhas else -1
        self.onda.emenda_sel = i
        self.onda.update()
        self._sincronizar_controles_emenda()
        self._atualizar_estado()

    def _ao_comecar_arraste(self):
        d = self._dub_atual()
        if d is None:
            return
        self._arraste_base = Historico.estado(d)
        self._guardar_historico(d, "arraste", self._arraste_base, forcar=True)
        self._ult_edicao = (id(d), "atraso", time.monotonic())     # os ajustes deste arraste nao empilham de novo

    def _ao_terminar_arraste(self, modo):
        self._arraste_base = None
        if modo in ("emenda", "segmento", "dub"):
            self._atualizar_painel_emendas()
        if modo in ("emenda", "segmento", "dub", "cabeca"):
            self._reiniciar_audio()

    def _ao_arrastar_emenda(self, i, t_filme):
        """A pessoa esta arrastando a linha da emenda i ate t_filme (o mapa e refeito a partir de ANTES do arraste)."""
        d, base = self._dub_atual(), self._arraste_base
        if d is None or base is None:
            return
        m, aj = self._modelo_de(d, base), self._ajuste_fino(d, base)
        if not 0 <= i < len(m.emendas):
            return
        t = t_filme - aj
        if self.chk_ima.isChecked():
            amp, ref = self._amplitude(d)
            if amp is not None:
                t = emendas.encaixar_em_pausa(m, i, t, amp, ref)
        m.mover_emenda(i, t)
        self._gravar_modelo(d, m, aj)
        self._mostrar_edicao(d, i)

    def _ao_arrastar_segmento(self, t_clique, dx, so_este):
        d, base = self._dub_atual(), self._arraste_base
        if d is None or base is None:
            return
        m, aj = self._modelo_de(d, base), self._ajuste_fino(d, base)
        k = sum(1 for e in m.emendas if e.t + aj <= t_clique)         # trecho sob o clique
        m.deslocar_trecho(k, dx, so_este)
        self._gravar_modelo(d, m, aj)
        self._mostrar_edicao(d)

    def _ao_empurrar_emenda(self, i, dt):
        """Setas do teclado na onda: move a emenda i por dt segundos."""
        self._editar_emendas(lambda m, aj: m.mover_emenda(i, m.emendas[i].t + dt), "emenda_mover")
        self.onda.emenda_sel = i
        self._atualizar_painel_emendas(i)
        self._reiniciar_audio()

    def _empurrar_emenda_selecionada(self, dt):
        d, i = self._emenda_escolhida()
        if d is not None:
            self._ao_empurrar_emenda(i, dt)

    def _ed_emenda_tempo(self, valor):
        d, i = self._emenda_escolhida()
        if d is None or self._atualizando_emendas:
            return
        self._editar_emendas(lambda m, aj: m.mover_emenda(i, valor - aj), "emenda_mover")
        self._atualizar_painel_emendas(i)
        self._reiniciar_audio()

    def _ed_emenda_quantia(self, valor):
        d, i = self._emenda_escolhida()
        if d is None or self._atualizando_emendas:
            return
        if valor == 0:                      # quantia zero nao existe (a emenda seria inutil): pula para o lado oposto
            self.sp_em_quantia.setValue(1 if getattr(self, "_quantia_ant", 1) < 0 else -1)
            return
        self._quantia_ant = valor
        self._editar_emendas(lambda m, aj: m.definir_quantia(i, valor / 1000.0), "emenda_quantia")
        self._atualizar_painel_emendas(i)
        self._reiniciar_audio()

    def acao_add_emenda(self, *_, t=None):
        d = self._dub_atual()
        if d is None or self._ocupado():
            return
        if t is None:
            t = self.onda.cabeca if self.onda.cabeca is not None else max(0.0, self.onda.t0)
        q, ok = QInputDialog.getInt(
            self, tr("Adicionar emenda"),
            tr("Emenda em %s.\n\nQuantos milissegundos?\n  + (positivo): entra silêncio e o resto da dublagem fica "
               "mais tarde;\n  - (negativo): sai um pedaço da dublagem e o resto fica mais cedo.") % fmt_tempo_ms(t),
            200, -600000, 600000, 10)
        if not ok or q == 0:
            return
        i = self._editar_emendas(lambda m, aj: m.inserir_emenda(t - aj, q / 1000.0), "emenda_nova", forcar=True)
        if i is None:
            self.aviso(tr("Não coube uma emenda nesse ponto: precisa haver pelo menos 50 ms de dublagem de cada "
                          "lado (e a emenda não pode ficar antes de a dublagem começar)."))
            return
        self.onda.emenda_sel = i
        self._atualizar_painel_emendas(i)
        self.abas.setCurrentIndex(1)
        self._reiniciar_audio()

    def acao_remover_emenda(self, *_):
        d, i = self._emenda_escolhida()
        if d is None or self._ocupado():
            return
        if self._editar_emendas(lambda m, aj: m.remover_emenda(i) and True, "emenda_rem", forcar=True):
            self.onda.emenda_sel = min(i, len(d.trechos or []) - 2) if d.trechos else -1
            self._atualizar_painel_emendas(self.onda.emenda_sel)
            self._reiniciar_audio()

    def acao_pausa(self, *_):
        d, i = self._emenda_escolhida()
        if d is None or self._ocupado():
            return
        amp, ref = self._amplitude(d)
        if amp is None:
            self.aviso(tr("A onda da dublagem ainda não carregou: sem ela não dá para saber onde há pausas."))
            return
        def mover(m, aj):
            m.mover_emenda(i, emendas.melhor_posicao(m, i, amp, ref))
            return True
        self._editar_emendas(mover, "emenda_mover", forcar=True)
        self._atualizar_painel_emendas(i)
        self._reiniciar_audio()

    def acao_ir_para_emenda(self, *_):
        d, i = self._emenda_escolhida()
        if d is None:
            return
        t = self._emendas_da_onda(d)[i]["t"]
        self.onda.centralizar(t)
        self.onda.set_cabeca(max(0.0, t - 2.0))

    def acao_ouvir_emenda(self, *_):
        d, i = self._emenda_escolhida()
        if d is None:
            return
        t = self._emendas_da_onda(d)[i]["t"]
        self.onda.set_cabeca(max(0.0, t - 3.0))
        self._iniciar_audio(max(0.0, t - 3.0), t + 3.0)

    def _menu_da_onda(self, t, i, pos):
        m = QMenu(self)
        m.addAction(tr("Ouvir a partir daqui")).triggered.connect(lambda *_: self._ouvir_daqui(t))
        if self._dub_atual() is not None and not self._ocupado():
            m.addAction(tr("Adicionar emenda aqui...")).triggered.connect(lambda *_: self.acao_add_emenda(t=t))
            if i >= 0:
                self.onda.emenda_sel = i
                self._atualizar_painel_emendas(i)
                m.addSeparator()
                m.addAction(tr("Ouvir a emenda %d") % (i + 1)).triggered.connect(self.acao_ouvir_emenda)
                m.addAction(tr("Procurar uma pausa perto da emenda %d") % (i + 1)).triggered.connect(self.acao_pausa)
                m.addAction(tr("Remover a emenda %d") % (i + 1)).triggered.connect(self.acao_remover_emenda)
        m.exec(pos)

    # ------------------------------------------------ ouvir
    def _ouvir_daqui(self, t):
        self.onda.set_cabeca(t)
        self._iniciar_audio(t)

    def _ao_mover_cabeca(self, t):
        self.lbl_cabeca.setText("  " + fmt_tempo_ms(t) + "  ")

    def _ao_mudar_volume(self, v):
        self.player.definir_volume(v / 100.0)
        self.cfg.setValue("volume", v / 100.0)

    def acao_modo_audio(self, modo):
        if modo not in previa_audio.MODOS:
            return
        self._modo_audio = modo
        self.cfg.setValue("modo_audio", modo)
        self.cmb_modo.blockSignals(True)
        self.cmb_modo.setCurrentIndex(max(0, self.cmb_modo.findData(modo)))
        self.cmb_modo.blockSignals(False)
        self.a_modos[modo].setChecked(True)
        self._reiniciar_audio()

    def acao_inicio_audio(self, *_):
        self.player.parar()
        self.onda.set_cabeca(0.0)
        self._ao_mover_cabeca(0.0)
        self.onda.ver_inicio()

    def acao_tocar(self, *_):
        if self.player.tocando():
            t = self.player.parar()
            self.onda.set_cabeca(t)
            return
        t = self.onda.cabeca if self.onda.cabeca is not None else max(0.0, self.onda.t0)
        self._iniciar_audio(t)

    def _iniciar_audio(self, t_ini, t_fim=None):
        modo = self._modo_audio
        d = self._dub_atual()
        if modo in ("dub", "mix") and d is None:
            self.aviso(tr("Selecione uma dublagem na lista para ouvir."))
            return
        if modo in ("filme", "mix") and not self.film:
            self.aviso(tr("Abra o filme primeiro."))
            return
        ref = self._ref_pos()
        filme = None
        if self.film and modo in ("filme", "mix"):
            filme = (self.film.caminho, ref, self.film.audios[ref].codec)
        dub = copy.deepcopy(d) if d is not None and modo in ("dub", "mix") else None
        if t_fim is None:
            t_fim = self.film.duracao if self.film and self.film.duracao else 1e5
        if t_ini >= t_fim - 0.2:
            t_ini = 0.0
        self._t_fim_audio = t_fim
        ferr = self.ferr
        self.onda.set_cabeca(t_ini)
        self.player.tocar(lambda cancelar: previa_audio.Previa(ferr, modo, t_ini, t_fim, filme=filme, dub=dub,
                                                                 cancelar=cancelar), t_ini)

    def _reiniciar_audio(self):
        """Depois de uma edicao: se estava tocando, recomeca do ponto atual com o novo mapa."""
        if self.player.tocando():
            self._iniciar_audio(self.player.tempo_atual(), getattr(self, "_t_fim_audio", None))

    def _ao_posicao_audio(self, t):
        self.onda.set_cabeca(t, seguir=True)
        self._ao_mover_cabeca(t)

    def _ao_fim_audio(self):
        self.onda.set_cabeca(self.player.tempo_atual())

    def _ao_falha_audio(self, texto):
        self.log(tr("Não consegui tocar: %s") % texto)
        self.aviso(tr("Não consegui tocar o áudio:\n%s") % texto)

    def _ao_mudar_reproducao(self, tocando):
        S = QStyle.StandardPixmap
        self.a_tocar.setIcon(self.style().standardIcon(S.SP_MediaStop if tocando else S.SP_MediaPlay))
        if tocando:
            if self.carregador.ocupado():
                self.carregador.pausar()               # um disco so: a previa tem prioridade sobre a leitura das ondas
        elif not self._ocupado():
            self.carregador.retomar()
        self._atualizar_estado()

    # ------------------------------------------------ montagem
    def _descrever_saida(self, film, dubs, legs, org):
        """Linhas para o Registro: cada faixa do arquivo final, na ordem, com as marcas que vai ter."""
        itens = core.itens_saida(film, dubs, legs, org)
        pa, pl = core.padroes_efetivos(itens, org)
        fx = {f.idx: f for f in film.faixas}
        linhas, n = [], 1
        for t in core.TIPOS_ESCOLHIVEIS:
            for k in itens[t]:
                if k[0] == "filme":
                    f = fx[k[1]]
                    desc = tr("do filme: %s") % f.rotulo()
                elif k[0] == "dub":
                    desc = tr("dublagem: %s (%s)") % (k[1].nome, k[1].idioma or "und")
                else:
                    desc = tr("externa: %s (%s)") % (k[1].nome or os.path.basename(k[1].arquivo), k[1].idioma or "und")
                marcas = core.disposicao(film, k, k in (pa, pl), fx)
                nomes = [self._nome_marca(m) for m in marcas.split("+")] if marcas != "0" else []
                linhas.append("  %d. %s - %s%s" % (n, rot_tipo(t), desc, "  [%s]" % ", ".join(nomes) if nomes else ""))
                n += 1
        return linhas

    @staticmethod
    def _nome_marca(m):
        """Nome de uma marca (disposition) do MKV para mostrar."""
        return {"default": tr("padrão"), "forced": tr("forçada"), "comment": tr("comentário"),
                "hearing_impaired": tr("para surdos"), "visual_impaired": tr("audiodescrição")}.get(m, m)

    def acao_gerar(self, teste):
        if self._ocupado() or not self.film:
            return
        try:
            core.validar(self.film, self.dubs, self.legendas)
        except Exception as e:
            self.aviso(str(e))
            return
        base = Path(self.film.caminho)
        if self.dubs:
            sufixo = tr("_dublado_TESTE") if teste else tr("_dublado")
        else:                                       # sem dublagem: so reorganiza as faixas do filme
            sufixo = tr("_remux_TESTE") if teste else tr("_remux")
        sugestao = str(base.with_name(base.stem + sufixo + ".mkv"))
        caminho, _ = QFileDialog.getSaveFileName(self, tr("Salvar como"), sugestao, "Matroska (*.mkv)")
        if not caminho:
            return
        caminho = os.path.normpath(caminho)
        if not caminho.lower().endswith(".mkv"):
            caminho += ".mkv"
        if os.path.abspath(caminho) == os.path.abspath(self.film.caminho):
            self.aviso(tr("O arquivo de saída não pode ser o próprio filme."))
            return
        if not teste:
            try:
                livre = shutil.disk_usage(os.path.dirname(caminho) or ".").free
                precisa = os.path.getsize(self.film.caminho) * 1.02
                if livre < precisa:
                    r = QMessageBox.question(
                        self, NOME_APP,
                        tr("Espaço livre no destino: %.1f GB. O filme tem %.1f GB.\nContinuar mesmo assim?")
                        % (livre / 1e9, precisa / 1.02e9),
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    if r != QMessageBox.StandardButton.Yes:
                        return
            except OSError:
                pass
        # copias: a pessoa pode continuar mexendo na lista enquanto o arquivo e gerado
        film, ferr = self.film, self.ferr
        dubs = [core.Dublagem(**vars(d)) for d in self.dubs]
        legs = [core.LegendaExterna(**vars(x)) for x in self.legendas]
        troca = {id(a): b for a, b in zip(self.dubs + self.legendas, dubs + legs)}

        def copia(k):
            if k is None or k[0] == "filme":
                return k
            novo = troca.get(id(k[1]))
            return (k[0], novo) if novo is not None else None
        org = core.Organizacao(
            ordem=[copia(k) for k in core.completar_ordem(film, self.dubs, self.legendas, self.ordem)],
            manter=self._manter_param(), padrao_audio=copia(self.padrao_audio),
            padrao_legenda=copia(self.padrao_legenda))
        try:
            core.validar_manter(film, org.manter)
        except Exception as e:
            self.aviso(str(e))
            return
        posicoes, nomes, ref_saida = core.posicoes_para_conferencia(film, dubs, legs, org, self._ref_pos())
        self.log(tr("Faixas do arquivo final, nesta ordem:"))
        for linha in self._descrever_saida(film, dubs, legs, org):
            self.log(linha)

        def job(msg, prog, cancelar):
            saida = core.montar(film, dubs, caminho, teste, ferr, msg, prog, cancelar, org=org, legendas=legs)
            msg(tr("ARQUIVO PRONTO: %s") % saida)
            if not posicoes:
                return saida, []
            msg(tr("Conferindo se cada dublagem tem som e está sincronizada (lê só 3 trechos curtos; o arquivo já "
                   "está pronto, mesmo que você cancele esta conferência)..."))
            conf = core.conferir_dublagens(saida, posicoes, ref_saida, nomes, ferr, teste, cancelar, msg, prog)
            return saida, conf

        def pronto(res):
            saida, conf = res
            self.log(tr("Pronto (%s): %s") % ("ffmpeg", saida))
            linhas, mudas, fora = [], [], []
            for c in conf:
                buracos = c.get("sem_audio_em") or []
                if c["com_som"] is None:
                    txt = tr("não deu para conferir (os trechos não puderam ser lidos a tempo)")
                elif not c["com_som"]:
                    txt = tr("MUDA (sem som)")
                    mudas.append(c["nome"])
                elif c["sobra_ms"] is None:
                    txt = tr("com som (sincronia não conferida: sem trecho parecido com a faixa de referência)")
                elif abs(c["sobra_ms"]) > 40:
                    txt = tr("com som, mas FORA de sincronia em %+d ms") % c["sobra_ms"]
                    fora.append(c["nome"])
                else:
                    txt = tr("com som e sincronizada (diferença %+d ms)") % c["sobra_ms"]
                if buracos:
                    txt += "; " + tr("SEM ÁUDIO por volta de %s (a dublagem acaba antes ou tem um buraco ali?)") % \
                        ", ".join(fmt_tempo(t) for t in buracos)
                if c.get("entrelacamento_s") is not None:
                    if c["entrelacamento_s"] > 2.0:
                        txt += "; " + tr("ATENÇÃO: o áudio ficou gravado até %.0f s longe do vídeo dentro do arquivo "
                                         "(alguns players ficam mudos nesses pontos)") % c["entrelacamento_s"]
                    else:
                        txt += "; " + tr("áudio bem entrelaçado com o vídeo")
                linhas.append("%s: %s" % (c["nome"], txt))
                self.log(tr("Conferência - %s") % linhas[-1])
            resumo = "\n".join(linhas) or tr("nenhuma dublagem adicionada (só a organização das faixas mudou)")
            if mudas:
                self.erro(tr("Dublagem muda no arquivo gerado"),
                          tr("Estas dublagens saíram SEM SOM no arquivo gerado:\n%s\n\nGere o arquivo de novo. Se "
                             "continuar, relate o problema (Ajuda > Relatar um problema) com o conteúdo do "
                             "Registro.\n\n%s") % ("\n".join(mudas), resumo))
                return
            if teste:
                r = QMessageBox.question(self, NOME_APP,
                                         tr("Teste gerado:\n%s\n\nConferência automática:\n%s\n\nAbrir no player "
                                            "padrão para ouvir?") % (saida, resumo),
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if r == QMessageBox.StandardButton.Yes:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(saida))
            else:
                QMessageBox.information(
                    self, NOME_APP,
                    tr("Arquivo final gerado (sem recodificar):\n%s\n\nConferência automática:\n%s\n\nPara conferir "
                       "que vídeo, áudios e legendas originais continuam IDÊNTICOS, use Ferramentas > Verificar "
                       "integridade.\n\nDica: para assistir, espere a leitura das ondas terminar (canto inferior "
                       "direito) ou use Sincronização > Parar a leitura das ondas. Num HD lento, duas leituras ao "
                       "mesmo tempo fazem o vídeo travar.") % (saida, resumo))
        self._submeter(tr("Gerando o teste de 5 minutos") if teste else tr("Gerando o arquivo final"), job, pronto)

    def acao_verificar(self, *_):
        if self._ocupado() or not self.film:
            return
        caminho, _ = QFileDialog.getOpenFileName(self, tr("Arquivo final a verificar"), self.cfg.value("pasta", ""),
                                                 "Matroska (*.mkv)")
        if not caminho:
            return
        film, ferr, manter = self.film, self.ferr, self._manter_param()

        def job(msg, prog, cancelar):
            return core.verificar_integridade(film, os.path.normpath(caminho), ferr, msg, prog, cancelar, manter)

        def pronto(res):
            ruins = [n for n, ok in res if not ok]
            for n, ok in res:
                self.log((tr("IDÊNTICO") if ok else tr("DIFERENTE")) + "  " + n)
            if ruins:
                self.aviso(tr("ATENÇÃO: estes fluxos do filme original estão DIFERENTES no arquivo final:\n\n%s\n\n"
                              "Gere o arquivo de novo e confira outra vez. Se continuar diferente, relate o problema "
                              "(Ajuda > Relatar um problema).") % "\n".join(ruins))
            else:
                self.aviso(tr("Todos os %d fluxos originais (vídeo, áudio, legendas) estão IDÊNTICOS no arquivo "
                              "final.") % len(res))
        self._submeter(tr("Verificando a integridade (lê os dois arquivos inteiros)"), job, pronto)

    # ------------------------------------------------ projeto / opcoes
    def acao_salvar_projeto(self, *_):
        if not self.film:
            self.aviso(tr("Abra um filme primeiro."))
            return
        caminho, _ = QFileDialog.getSaveFileName(self, tr("Salvar projeto"), self._projeto or
                                                 str(Path(self.film.caminho).with_suffix(".eternaldub")),
                                                 tr("Projeto EternalDub (*.eternaldub)"))
        if caminho:
            core.salvar_projeto(caminho, self.film.caminho, self._ref_pos(), self.dubs, self._manter_param(),
                                self.legendas, self._organizacao(), self._idioma_original, self._org_manual)
            self._projeto = caminho
            self.log(tr("Projeto salvo: %s") % caminho)

    def acao_abrir_projeto(self, *_):
        caminho, _ = QFileDialog.getOpenFileName(self, tr("Abrir projeto"), self.cfg.value("pasta", ""),
                                                 tr("Projeto EternalDub (*.eternaldub *.dubsync)"))
        if not caminho:
            return
        try:
            p = core.abrir_projeto(caminho)
        except Exception as e:
            self.erro(tr("Não consegui abrir o projeto"), str(e))
            return
        if p["filme"] and os.path.isfile(p["filme"]):
            self._carregar_filme(p["filme"])
            if 0 <= p["ref"] < self.cmb_ref.count():
                self.cmb_ref.setCurrentIndex(p["ref"])
        elif p["filme"]:
            self.aviso(tr("O filme do projeto não foi encontrado:\n%s") % p["filme"])
        dubs = [d for d in p["dublagens"] if os.path.isfile(d.arquivo)]
        legs = [x for x in p["legendas"] if os.path.isfile(x.arquivo)]
        if len(dubs) != len(p["dublagens"]):
            self.aviso(tr("Alguns arquivos de dublagem do projeto não foram encontrados e foram ignorados."))
        if len(legs) != len(p["legendas"]):
            self.aviso(tr("Alguns arquivos de legenda do projeto não foram encontrados e foram ignorados."))
        self.dubs, self.legendas = dubs, legs
        self._projeto = caminho
        self._hist.clear()
        if self.film:
            todas = set(f.idx for f in self.film.faixas if f.tipo in core.TIPOS_ESCOLHIVEIS)
            self._escolher_idioma_original(p["idioma_original"])
            self.padrao_audio, self.padrao_legenda = p["padrao_audio"], p["padrao_legenda"]
            if p["ordem"] is not None:                   # projeto 1.3: a organizacao exatamente como estava
                self.ordem = p["ordem"]
                self.manter = (set(p["manter"]) & todas) if p["manter"] is not None else set(todas)
                self._org_manual = p["organizacao_manual"]
            elif p["manter"] is not None:                # projeto antigo com faixas escolhidas a mao
                self.ordem, self.manter = [], set(p["manter"]) & todas
                self._org_manual = True
            else:                                        # projeto antigo com o filme inteiro
                self.ordem, self.manter = [], set(todas)
                self._org_manual = False
            self._organizar_auto()
        self._refresh_tabela(0)

    def _escolher_idioma_original(self, codigo):
        """Poe o idioma original na caixinha (sem reorganizar nada)."""
        self._idioma_original = codigo or ""
        self.cmb_original.blockSignals(True)
        i = self.cmb_original.findData(self._idioma_original)
        if i < 0:
            self.cmb_original.addItem(self._idioma_original, self._idioma_original)
            i = self.cmb_original.count() - 1
        self.cmb_original.setCurrentIndex(i)
        self.cmb_original.blockSignals(False)

    def acao_idioma(self, codigo):
        if codigo == i18n.atual():
            return
        self.cfg.setValue("idioma", codigo)
        # mensagem nos DOIS idiomas: quem escolheu pode nao ler o atual
        QMessageBox.information(self, NOME_APP,
                                "O idioma será aplicado ao reabrir o EternalDub.\n\n"
                                "The new language will be applied when you restart EternalDub.")

    def acao_localizar(self, nome):
        caminho, _ = QFileDialog.getOpenFileName(self, tr("Localizar %s") % nome, "",
                                                 tr("Programas (*.exe);;Todos os arquivos (*)"))
        if caminho:
            self.cfg.setValue(nome, os.path.normpath(caminho))
            if nome == "ffmpeg":                      # o ffprobe costuma ficar na mesma pasta
                probe = os.path.join(os.path.dirname(caminho), "ffprobe" + os.path.splitext(caminho)[1])
                if os.path.isfile(probe):
                    self.cfg.setValue("ffprobe", probe)
            self.ferr = core.achar_ferramentas({k: self.cfg.value(k, "") for k in ("ffmpeg", "ffprobe")})
            self.log("%s: %s" % (nome, caminho))

    def acao_limpar_cache(self, *_):
        self.carregador.cancelar_tudo()
        self._envs.clear()
        self._completas.clear()
        self.onda.set_ref(None)
        self.onda.set_dub(None)
        n = core.limpar_cache()
        self.aviso(tr("%d arquivo(s) de cache removido(s).") % n)

    def acao_site(self, *_):
        QDesktopServices.openUrl(QUrl(URL_PROJETO))

    def acao_relatar(self, *_):
        r = QMessageBox.question(
            self, NOME_APP,
            tr("Para relatar um problema, abra um \"Issue\" na página do projeto e cole o conteúdo da aba Registro "
               "(e, se houver, o arquivo %s).\n\nAbrir a página agora?") % str(Path.home() / ".eternaldub" / "erro.log"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl(URL_PROJETO + "/issues"))

    def acao_sobre(self, *_):
        traducao = i18n.tradutores() if i18n.atual() != "pt" else []
        QMessageBox.about(
            self, tr("Sobre o EternalDub"),
            "<b>%s %s</b><br><br>" % (NOME_APP, VERSAO) +
            tr("Adiciona dublagens a releases de alta qualidade (BDRemux, WEB-DL...) <b>sem recodificar</b> o vídeo.") +
            "<br><br>" +
            tr("1) Abra o filme  2) adicione as dublagens  3) <i>Detectar atraso</i> (ou arraste a faixa laranja na "
               "onda)  4) <i>Gerar teste</i> e confira  5) <i>Gerar arquivo final</i>.") +
            "<br><br>" +
            tr("Se a dublagem tiver velocidade diferente (ex.: PAL), o programa avisa e corrige só a dublagem. "
               "Se as versões tiverem cortes diferentes, ele sincroniza a dublagem trecho por trecho, e você pode "
               "ajustar cada emenda à mão e ouvir o resultado (F8) sem gerar nada.") +
            "<br><br><b>" + tr("Créditos") + "</b><br>" +
            tr("Criação, testes e direção do projeto: %s") % AUTOR + "<br>" +
            tr("Código escrito com auxílio de IA (Claude, da Anthropic).") + "<br>" +
            tr("Usa: FFmpeg, Qt for Python (PySide6) e NumPy.") + "<br>" +
            (tr("Tradução (%s): %s") % (dict(i18n.IDIOMAS).get(i18n.atual(), ""), ", ".join(traducao)) + "<br>"
             if traducao else "") +
            tr("Colaboradores: veja CREDITS.md e a página do projeto.") + "<br><br>" +
            tr("Software livre e de código aberto (licença %s).") % LICENCA + "<br>" +
            '<a href="%s">%s</a>' % (URL_PROJETO, URL_PROJETO))

    # ------------------------------------------------ arrastar e soltar
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        caminhos = [os.path.normpath(u.toLocalFile()) for u in ev.mimeData().urls() if u.isLocalFile()]
        if not caminhos or self._ocupado():
            return
        legendas = [c for c in caminhos if os.path.splitext(c)[1].lower() in core.EXT_LEGENDA + (".sub",)]
        outros = [c for c in caminhos if c not in legendas]
        if self.film is None and outros:
            self._carregar_filme(outros.pop(0))
        if outros:
            self._adicionar_arquivos(outros)
        if legendas:
            self._adicionar_legendas(legendas)

    def closeEvent(self, ev):
        if self._ocupado():
            r = QMessageBox.question(self, NOME_APP, tr("Há uma tarefa em andamento. Cancelar e sair?"),
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes:
                ev.ignore()
                return
            self._fila.clear()
            if self._atual:
                self._atual[0].cancelar.set()
                self._atual[0].wait(5000)
        self.player.parar(silencioso=True)
        self.carregador.encerrar()        # a leitura das ondas para sem perguntar (recomeca depois)
        ev.accept()


# ============================================================ inicio
def tema_escuro(app):
    app.setStyle("Fusion")
    p = QPalette()
    R = QPalette.ColorRole
    p.setColor(R.Window, QColor(37, 37, 38))
    p.setColor(R.WindowText, QColor(225, 225, 225))
    p.setColor(R.Base, QColor(28, 28, 28))
    p.setColor(R.AlternateBase, QColor(36, 36, 38))
    p.setColor(R.ToolTipBase, QColor(50, 50, 50))
    p.setColor(R.ToolTipText, QColor(230, 230, 230))
    p.setColor(R.Text, QColor(225, 225, 225))
    p.setColor(R.Button, QColor(52, 52, 54))
    p.setColor(R.ButtonText, QColor(230, 230, 230))
    p.setColor(R.Highlight, QColor(0, 102, 180))
    p.setColor(R.HighlightedText, QColor(255, 255, 255))
    p.setColor(R.PlaceholderText, QColor(130, 130, 130))
    p.setColor(R.Link, QColor(110, 170, 255))
    app.setPalette(p)


def escolher_idioma():
    """Idioma salvo nas opcoes; senao, o do sistema (se houver traducao dele) ou o ingles."""
    salvo = QSettings("EternalDub", "EternalDub").value("idioma", "")
    if salvo and (salvo == "pt" or salvo in i18n.disponiveis()):
        return salvo
    try:
        return i18n.para_codigo(QLocale.system().name())
    except Exception:
        return i18n.do_sistema() if i18n else "pt"


def traduzir_qt(app, codigo):
    """Botoes padrao do Qt (Sim/Nao, OK/Cancelar, Mostrar detalhes) no idioma escolhido, se o Qt tiver traducao."""
    if codigo == "en":
        return
    try:
        pasta = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        t = QTranslator(app)
        nomes = ["qtbase_pt_BR", "qtbase_pt"] if codigo == "pt" else ["qtbase_" + codigo]
        if any(t.load(n, pasta) for n in nomes):
            app.installTranslator(t)
            app._tradutor_qt = t
    except Exception:
        pass


def pasta_de_recursos():
    """Onde ficam icone.png e idiomas/: ao lado dos .py, ou dentro do programa empacotado (.exe)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def problema_arquivos():
    """Texto explicando a mistura de versoes, ou None se os arquivos combinam."""
    if not ERRO_ARQUIVOS:
        return None
    pasta = os.path.dirname(os.path.abspath(__file__))
    return (tr("Os arquivos do EternalDub nesta pasta não combinam:\n%s\n\nPasta: %s\n\nComo resolver: extraia o "
               "EternalDub numa pasta NOVA e vazia, ou apague os arquivos antigos desta pasta (inclusive cópias com "
               "(1), (2) no nome, e os antigos dubsync_*.py).\nTodos estes precisam ser da versão %s: %s.")
            % (ERRO_ARQUIVOS, pasta, VERSAO_ARQUIVOS, ", ".join(ARQUIVOS)))


def autoteste(destino=None):
    """
    Confere se o programa abre e se as pecas principais funcionam, sem usar a tela nem arquivos de midia. Serve para
    testar o programa empacotado (.exe): `EternalDub.exe --autoteste resultado.txt`. Devolve 0 se tudo estiver bem.
    """
    linhas, ok = [], [True]

    def passo(nome, fn):
        try:
            linhas.append("OK      %s %s" % (nome, fn() or ""))
        except Exception:
            ok[0] = False
            linhas.append("FALHOU  %s\n%s" % (nome, traceback.format_exc()))

    def idiomas():
        assert "en" in i18n.disponiveis(), "a pasta idiomas/ nao foi encontrada"
        i18n.definir("en")
        assert i18n.tr("Abrir filme...") == "Open movie..."
        i18n.definir("pt")
        return ",".join(i18n.disponiveis())

    def modelo():
        m = emendas.MapaEditavel.de_trechos([[1.0, 50.0, 0.0], [52.0, 90.0, 49.0]], 1.0)
        assert m.para_trechos() == [[1.0, 50.0, 0.0], [52.0, 90.0, 49.0]]
        assert m.inserir_emenda(70.0, -0.5) == 1 and len(m.para_trechos()) == 3

    def janela():
        j = Janela()
        j.show()
        QApplication.processEvents()
        j.close()
        QApplication.processEvents()

    def ferramentas():
        f = core.achar_ferramentas()
        return core.versoes(f) if core.ffmpeg_ok(f) else "(FFmpeg nao encontrado: normal neste teste)"

    passo("versao", lambda: VERSAO)
    passo("idiomas", idiomas)
    passo("emendas", modelo)
    passo("audio-qt", lambda: "QtMultimedia " + ("ok" if TEM_AUDIO else "AUSENTE"))
    passo("janela", janela)
    passo("ffmpeg", ferramentas)
    texto = "\n".join(linhas) + "\n" + ("AUTOTESTE OK" if ok[0] else "AUTOTESTE FALHOU") + "\n"
    if destino:
        try:
            Path(destino).write_text(texto, encoding="utf-8")
        except OSError:
            pass
    try:
        if sys.stdout:
            print(texto)
    except Exception:
        pass
    return 0 if ok[0] else 1


def principal():
    app = QApplication(sys.argv)
    app.setApplicationName(NOME_APP)
    app.setApplicationVersion(VERSAO)
    icone = pasta_de_recursos() / "icone.png"
    if icone.is_file():
        app.setWindowIcon(QIcon(str(icone)))
    codigo = escolher_idioma() if i18n else "pt"
    if i18n:
        i18n.definir(codigo)
    traduzir_qt(app, codigo)
    tema_escuro(app)
    texto = problema_arquivos()
    if texto:
        try:
            if sys.stderr:
                print(texto, file=sys.stderr)
        except Exception:
            pass
        QMessageBox.critical(None, NOME_APP + " - " + tr("arquivos de versões diferentes"), texto)
        sys.exit(2)
    if "--autoteste" in sys.argv:
        resto = sys.argv[sys.argv.index("--autoteste") + 1:]
        sys.exit(autoteste(resto[0] if resto and not resto[0].startswith("-") else None))

    def gancho(tipo, valor, tb):
        texto = "".join(traceback.format_exception(tipo, valor, tb))
        try:
            pasta = Path.home() / ".eternaldub"
            pasta.mkdir(exist_ok=True)
            (pasta / "erro.log").write_text(texto, encoding="utf-8")
        except OSError:
            pass
        try:
            if sys.stderr:
                print(texto, file=sys.stderr)
        except Exception:
            pass
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setText(tr("Ocorreu um erro inesperado."))
        box.setInformativeText(tr("Copie o texto dos detalhes e relate o problema na página do projeto:\n%s")
                               % (URL_PROJETO + "/issues"))
        box.setDetailedText(texto)
        box.exec()
    sys.excepthook = gancho
    j = Janela()
    j.show()
    if i18n and not i18n.PASTA_OK:
        QMessageBox.warning(j, NOME_APP, "A pasta 'idiomas' não foi encontrada ao lado do programa: a interface "
                                         "fica só em português.\nThe 'idiomas' folder was not found next to the "
                                         "program: the interface is available in Portuguese only.")
    for a in sys.argv[1:]:                       # arquivos passados na linha de comando
        if os.path.isfile(a) and j.film is None:
            j._carregar_filme(os.path.normpath(a))
    sys.exit(app.exec())


if __name__ == "__main__":
    principal()
