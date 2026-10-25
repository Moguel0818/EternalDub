# SPDX-License-Identifier: MIT
# EternalDub - Copyright (C) 2026 Moguel0818 e colaboradores / and contributors
# -*- coding: utf-8 -*-
"""
EternalDub - interface grafica (inspirada no Subtitle Edit).

Janela:
  * esquerda ...... lista das dublagens (nome, origem, atraso, padrao) + editor da selecionada
  * direita ....... faixas do filme (o que entra no arquivo final) / registro (log)
  * embaixo ....... ondas sonoras: filme (verde) e dublagem (laranja) na mesma linha do tempo.
                    Arraste a faixa laranja para mudar o atraso; roda do mouse = zoom.

Tudo e montado SEM recodificar (copia dos fluxos).  Veja EternalDub_core.py.
Idiomas da interface: portugues (Brasil) e ingles. Veja EternalDub_i18n.py.
Requisitos: Python 3.9+, numpy, PySide6, FFmpeg  (mkvmerge recomendado).
"""
import math
import os
import shutil
import sys
import threading
import time
import traceback
from pathlib import Path

try:
    from PySide6.QtCore import Qt, QObject, QThread, Signal, QSettings, QUrl, QLocale, QTranslator, QLibraryInfo
    from PySide6.QtGui import (QAction, QActionGroup, QColor, QPainter, QPalette, QDesktopServices,
                               QKeySequence)
    from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
                                   QDialogButtonBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout,
                                   QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
                                   QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
                                   QProgressBar, QPushButton, QSpinBox, QSplitter, QStyle,
                                   QTabWidget, QTableWidget, QTableWidgetItem, QToolBar,
                                   QVBoxLayout, QWidget)
except ImportError:
    print("Falta o PySide6 / PySide6 is missing:   python -m pip install PySide6 numpy")
    sys.exit(1)

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
VERSAO_ARQUIVOS = "1.0"
ARQUIVOS = ("EternalDub_gui.py", "EternalDub_core.py", "EternalDub_i18n.py", "detectar_atraso.py")
try:
    if i18n is None:
        raise ModuleNotFoundError("EternalDub_i18n", name="EternalDub_i18n")
    if getattr(i18n, "VERSAO_IDIOMAS", None) != VERSAO_ARQUIVOS:
        raise ImportError("EternalDub_i18n.py (%s) / EternalDub_gui.py (%s): %s" % (
            getattr(i18n, "VERSAO_IDIOMAS", "?"), VERSAO_ARQUIVOS, getattr(i18n, "__file__", "?")))
    import EternalDub_core as core
    ERRO_ARQUIVOS = None
    if getattr(core, "VERSAO_NUCLEO", None) != VERSAO_ARQUIVOS:
        ERRO_ARQUIVOS = "EternalDub_core.py (%s) / EternalDub_gui.py (%s): %s" % (
            getattr(core, "VERSAO_NUCLEO", "?"), VERSAO_ARQUIVOS, getattr(core, "__file__", "?"))
except ModuleNotFoundError as _e:
    core = None
    ERRO_ARQUIVOS = ("falta o arquivo %s.py nesta pasta / missing file %s.py" % (_e.name, _e.name)
                     if _e.name in ("EternalDub_core", "detectar_atraso", "EternalDub_i18n") else str(_e))
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
    atraso_arrastado = Signal(int)          # novo atraso em ms enquanto arrasta a faixa laranja
    TOPO = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setMouseTracking(True)
        self.ref = None
        self.dub = None
        self.escala_ref = 1.0
        self.escala_dub = 1.0
        self.atraso = 0.0           # segundos
        self.atempo = 1.0
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

    def set_atraso(self, ms, atempo=1.0):
        self.atraso = ms / 1000.0
        self.atempo = atempo
        self.update()

    def ver_inicio(self):
        self.pps = max(self.width(), 200) / 60.0
        self.t0 = -2.0
        self.update()

    # ---- desenho
    def _extremos(self, vmin, vmax, n, atraso, atempo, w):
        xs = np.arange(w + 1, dtype=np.float64)
        s = ((self.t0 + xs / self.pps) - atraso) * atempo * core.ENV_RATE
        idx = np.floor(s).astype(np.int64)
        a = idx[:-1]
        b = np.maximum(idx[1:], a + 1)
        ok = (b > 0) & (a < n)
        a = np.clip(a, 0, n - 1)
        b = np.clip(b, 1, n)
        b = np.maximum(b, a + 1)
        inter = np.empty(2 * w, np.int64)
        inter[0::2] = a
        inter[1::2] = b
        mn = np.minimum.reduceat(vmin, inter)[0::2]
        mx = np.maximum.reduceat(vmax, inter)[0::2]
        return mn, mx, ok

    def _faixa(self, p, dados, escala, atraso, atempo, y0, h, cor, rotulo):
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
        mn, mx, ok = self._extremos(vmin, vmax, n, atraso, atempo, w)
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

    def paintEvent(self, ev):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(18, 18, 18))
        fh = max(20, (h - self.TOPO) // 2)
        self._faixa(p, self.ref, self.escala_ref, 0.0, 1.0, self.TOPO, fh, QColor(70, 190, 110), self.rot_ref)
        self._faixa(p, self.dub, self.escala_dub, self.atraso, self.atempo, self.TOPO + fh, fh,
                    QColor(240, 160, 60), tr("%s   (atraso %+d ms)") % (self.rot_dub, int(round(self.atraso * 1000))))
        self._regua(p, w)
        x0 = int((0 - self.t0) * self.pps)         # marca do tempo zero
        if 0 <= x0 < w:
            p.setPen(QColor(90, 90, 160))
            p.drawLine(x0, self.TOPO, x0, h)
        if self._mouse_x is not None:
            p.setPen(QColor(255, 255, 255))
            x = int(self._mouse_x)
            p.drawLine(x, self.TOPO, x, h)
            p.drawText(min(x + 6, w - 70), h - 6, fmt_tempo(self.t0 + self._mouse_x / self.pps))
        p.end()

    # ---- mouse
    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        x, y = ev.position().x(), ev.position().y()
        fh = max(20, (self.height() - self.TOPO) // 2)
        em_dub = self.dub is not None and y > self.TOPO + fh
        self._arraste = {"modo": "dub" if em_dub else "pan", "x0": x, "t0": self.t0, "atraso0": self.atraso}

    def mouseMoveEvent(self, ev):
        x = ev.position().x()
        self._mouse_x = x
        a = self._arraste
        if a:
            dx = (x - a["x0"]) / self.pps
            if a["modo"] == "pan":
                self.t0 = a["t0"] - dx
            else:
                self.atraso_arrastado.emit(int(round((a["atraso0"] + dx) * 1000)))
        self.update()

    def mouseReleaseEvent(self, ev):
        self._arraste = None

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


# ============================================================ escolher quais faixas adicionar
class EscolherFaixas(QDialog):
    def __init__(self, arquivo, idiomas_filme=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Quais faixas deste arquivo são dublagens?"))
        self.resize(560, 300)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(os.path.basename(arquivo.caminho) + "\n" +
                             tr("Marque as faixas de áudio que você quer adicionar:")))
        self.lista = QListWidget()
        # pre-marca os idiomas que o filme ainda nao tem (ex.: as faixas em portugues de uma fonte antiga)
        novas = {f.pos for f in arquivo.audios if f.idioma and f.idioma not in idiomas_filme}
        marcar = novas or {0}
        for f in arquivo.audios:
            it = QListWidgetItem(tr("faixa %d:  %s") % (f.pos, f.rotulo()))
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
            for k in ("pasta", "motor", "ffmpeg", "ffprobe", "mkvmerge"):
                v = antigo.value(k, "")
                if v and not self.cfg.value(k, ""):
                    self.cfg.setValue(k, v)
            self.cfg.setValue("migrado", "1")
        self.ferr = core.achar_ferramentas({k: self.cfg.value(k, "") for k in ("ffmpeg", "ffprobe", "mkvmerge")})
        salvo = self.cfg.value("motor_v06", "")
        if salvo in ("ffmpeg", "mkvmerge"):
            self.motor = salvo
        else:
            self.motor = "mkvmerge" if self.ferr.mkvmerge else "ffmpeg"
        if self.motor == "mkvmerge" and not self.ferr.mkvmerge:
            self.motor = "ffmpeg"
        self.manter = None                  # faixas do filme que vao para o arquivo final (indices)
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
        self._criar_acoes()
        self._criar_menus()
        self._criar_toolbar()
        self._criar_central()
        self._criar_status()
        self._atualizar_estado()
        self.log(tr("EternalDub pronto. Arraste o filme para a janela (ou use Arquivo > Abrir filme)."))
        if not core.ffmpeg_ok(self.ferr):
            self.log(tr("ATENÇÃO: FFmpeg não encontrado. Instale o FFmpeg ou use Opções > Localizar FFmpeg."))
        self.log(tr("Montagem: %s | %s") % (self.motor, core.versoes(self.ferr)))
        if not self.ferr.mkvmerge:
            self.log(tr("mkvmerge não encontrado: a montagem usa o FFmpeg. Instalar o MKVToolNix (só o programa; a "
                        "janela dele não precisa ser usada) deixa o EternalDub usar o mkvmerge, que é o recomendado."))

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
        self.a_sobe = self._acao(tr("Mover para cima"), lambda *_: self.acao_mover(-1), "Ctrl+Up")
        self.a_desce = self._acao(tr("Mover para baixo"), lambda *_: self.acao_mover(1), "Ctrl+Down")
        self.a_det = self._acao(tr("Detectar atraso"), self.acao_detectar, "F5", S.SP_BrowserReload,
                                tr("Compara música e efeitos da dublagem com o áudio do filme"))
        self.a_det_arq = self._acao(tr("Detectar usando outra faixa do arquivo..."), self.acao_detectar_faixa_arquivo,
                                    "Ctrl+F5", None,
                                    tr("Ex.: usar a faixa em inglês da mesma fonte e aplicar a todas as dublagens dela"))
        self.a_det_vid = self._acao(tr("Detectar pelo vídeo (lento)..."), self.acao_detectar_video, None, None,
                                    tr("Compara os cortes de cena dos vídeos"))
        self.a_zero = self._acao(tr("Zerar atraso e velocidade"), self.acao_zerar)
        self.a_teste = self._acao(tr("Gerar teste (5 min)"), lambda *_: self.acao_gerar(True), "F6", S.SP_MediaPlay,
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
        self.a_mk = self._acao(tr("Localizar mkvmerge..."), lambda *_: self.acao_localizar("mkvmerge"))
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
        m = mb.addMenu(tr("Sincronização"))
        for a in (self.a_det, self.a_det_arq, self.a_det_completo, self.a_det_vid):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_zero)
        m.addAction(self.a_zoom)
        m.addAction(self.a_ondas)
        m.addAction(self.a_parar_ondas)
        m = mb.addMenu(tr("Montar"))
        for a in (self.a_teste, self.a_final, self.a_cancel):
            m.addAction(a)
        m = mb.addMenu(tr("Ferramentas"))
        for a in (self.a_verif, self.a_cache):
            m.addAction(a)
        m = mb.addMenu(tr("Opções"))
        sub = m.addMenu(tr("Motor de montagem"))
        grupo = QActionGroup(self)
        grupo.setExclusive(True)
        self.a_m_ff = QAction(tr("FFmpeg (cópia sem recodificar)"), self, checkable=True)
        self.a_m_mk = QAction(tr("mkvmerge (cópia sem recodificar - recomendado)") if self.ferr.mkvmerge
                              else tr("mkvmerge (não encontrado)"), self, checkable=True)
        self.a_m_mk.setEnabled(bool(self.ferr.mkvmerge))
        for a, nome in ((self.a_m_ff, "ffmpeg"), (self.a_m_mk, "mkvmerge")):
            grupo.addAction(a)
            sub.addAction(a)
            a.triggered.connect(lambda *_, n=nome: self.acao_motor(n))
        (self.a_m_mk if self.motor == "mkvmerge" else self.a_m_ff).setChecked(True)
        m.addAction(self.a_ff)
        m.addAction(self.a_mk)
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
        for a in (self.a_abrir, self.a_add, self.a_rem):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(self.a_det)
        tb.addSeparator()
        for a in (self.a_teste, self.a_final, self.a_cancel):
            tb.addAction(a)
        self.addToolBar(tb)

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
        linha.addWidget(self.b_det)
        linha.addWidget(self.b_det2)
        linha.addStretch(1)
        g.addLayout(linha, 5, 0, 1, 8)
        self.editor = box

        esq = QWidget()
        le = QVBoxLayout(esq)
        le.setContentsMargins(0, 0, 0, 0)
        le.addWidget(self.tab, 1)
        le.addWidget(box)

        # ---- direita: filme / registro
        self.lbl_filme = QLabel(tr("Nenhum filme aberto. Arraste o .mkv para a janela."))
        self.lbl_filme.setWordWrap(True)
        self.tab_filme = QTableWidget(0, 6)
        self.tab_filme.setHorizontalHeaderLabels([tr("Manter"), "#", tr("Tipo"), tr("Codec"), tr("Idioma"),
                                                  tr("Título")])
        self.tab_filme.itemChanged.connect(self._ao_mudar_manter)
        self.lbl_manter = QLabel(tr("Marque as faixas do FILME que vão para o arquivo final "
                                    "(as dublagens da lista entram todas)."))
        self.lbl_manter.setWordWrap(True)
        self.tab_filme.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tab_filme.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tab_filme.verticalHeader().setVisible(False)
        self.tab_filme.horizontalHeader().setStretchLastSection(True)
        self.cmb_ref = QComboBox()
        self.cmb_ref.currentIndexChanged.connect(self._ao_mudar_ref)
        pf = QWidget()
        lf = QVBoxLayout(pf)
        lf.addWidget(self.lbl_filme)
        lf.addWidget(self.lbl_manter)
        lf.addWidget(self.tab_filme, 1)
        lf.addWidget(QLabel(tr("Faixa de referência (áudio ORIGINAL do filme, usada para comparar):")))
        lf.addWidget(self.cmb_ref)
        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.abas = QTabWidget()
        self.abas.addTab(pf, tr("Filme"))
        self.abas.addTab(self.txt_log, tr("Registro"))

        topo = QSplitter(Qt.Orientation.Horizontal)
        topo.addWidget(esq)
        topo.addWidget(self.abas)
        topo.setStretchFactor(0, 3)
        topo.setStretchFactor(1, 2)

        # ---- onda
        self.onda = OndaWidget()
        self.onda.atraso_arrastado.connect(self._onda_arrastou)
        baixo = QWidget()
        lb = QVBoxLayout(baixo)
        lb.setContentsMargins(0, 0, 0, 0)
        lb.addWidget(self.onda, 1)
        dica = QLabel(tr("Roda do mouse = zoom  |  arraste a faixa LARANJA (embaixo) = muda o atraso  |  "
                         "arraste a faixa verde = move a visão  |  Home = voltar ao início"))
        dica.setStyleSheet("color: #999; padding: 2px 6px;")
        lb.addWidget(dica)

        div = QSplitter(Qt.Orientation.Vertical)
        div.addWidget(topo)
        div.addWidget(baixo)
        div.setStretchFactor(0, 3)
        div.setStretchFactor(1, 2)
        self.setCentralWidget(div)

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
        self.b_det.setEnabled(tem_film and tem_dub and not ocupado)
        self.b_det2.setEnabled(tem_film and tem_dub and not ocupado)
        self.a_rem.setEnabled(tem_dub and not ocupado)
        self.a_teste.setEnabled(tem_film and bool(self.dubs) and not ocupado)
        self.a_final.setEnabled(tem_film and bool(self.dubs) and not ocupado)
        self.a_verif.setEnabled(tem_film and not ocupado)
        self.a_cancel.setEnabled(ocupado)
        self.a_parar_ondas.setEnabled(self.carregador.ocupado())
        self.a_abrir.setEnabled(not ocupado)
        self.editor.setEnabled(tem_dub)

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
        self._preencher_faixas_filme(arq, None)
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

    def _preencher_faixas_filme(self, arq, manter):
        """Mostra as faixas do filme com a caixa 'Manter' (todas marcadas, ou as de `manter`)."""
        self._preenchendo_filme = True
        escolhiveis = [f for f in arq.faixas if f.tipo in core.TIPOS_ESCOLHIVEIS]
        self.manter = set(f.idx for f in escolhiveis) if manter is None else \
            set(i for i in manter if any(f.idx == i for f in escolhiveis))
        self.tab_filme.setRowCount(len(arq.faixas))
        for i, f in enumerate(arq.faixas):
            if f.tipo in core.TIPOS_ESCOLHIVEIS:
                it = QTableWidgetItem("")
                it.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                it.setCheckState(Qt.CheckState.Checked if f.idx in self.manter else Qt.CheckState.Unchecked)
                it.setData(Qt.ItemDataRole.UserRole, f.idx)
            else:
                it = QTableWidgetItem(tr("sempre"))
            self.tab_filme.setItem(i, 0, it)
            for c, v in enumerate([str(f.idx), rot_tipo(f.tipo), f.codec + (" %dch" % f.canais if f.canais else ""),
                                   f.idioma, f.titulo], 1):
                self.tab_filme.setItem(i, c, QTableWidgetItem(v))
        self.tab_filme.resizeColumnsToContents()
        self._preenchendo_filme = False
        self._resumo_manter()

    def _ao_mudar_manter(self, item):
        if self._preenchendo_filme or not self.film or item.column() != 0:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self.manter.add(idx)
        else:
            self.manter.discard(idx)
        self._resumo_manter()

    def _manter_param(self):
        """None = todas as faixas do filme (mais simples para os motores)."""
        if not self.film or self.manter is None:
            return None
        todas = set(f.idx for f in self.film.faixas if f.tipo in core.TIPOS_ESCOLHIVEIS)
        return None if self.manter >= todas else set(self.manter)

    def _resumo_manter(self):
        if not self.film:
            return
        mant = core.faixas_mantidas(self.film, self.manter)
        n = {t: sum(1 for f in mant if f.tipo == t) for t in core.TIPOS_ESCOLHIVEIS}
        self.lbl_manter.setText(tr("Marque as faixas do FILME que vão para o arquivo final. Vão: %d vídeo, "
                                   "%d áudio, %d legenda(s) do filme + as %d dublagem(ns) da lista.")
                                % (n["video"], n["audio"], n["subtitle"], len(self.dubs)))

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
            self._refresh_tabela(len(self.dubs) - len(novas))

    def _dub_atual(self):
        r = self.tab.currentRow() if hasattr(self, "tab") else -1
        return self.dubs[r] if 0 <= r < len(self.dubs) else None

    def _refresh_tabela(self, selecionar=None):
        self._resumo_manter()
        if selecionar is None:
            selecionar = self.tab.currentRow()
        self.tab.blockSignals(True)
        self.tab.setRowCount(len(self.dubs))
        for i, d in enumerate(self.dubs):
            vel = "  (x%.4f)" % (1.0 / d.atempo) if abs(d.atempo - 1.0) > 1e-9 else ""
            vals = [str(i + 1), d.nome, tr("%s : faixa %d") % (os.path.basename(d.arquivo), d.faixa),
                    "%+d%s" % (d.atraso_ms, vel), tr("Sim") if d.padrao else "", d.status]
            for c, v in enumerate(vals):
                self.tab.setItem(i, c, QTableWidgetItem(v))
        self.tab.blockSignals(False)
        if self.dubs:
            self.tab.selectRow(max(0, min(selecionar, len(self.dubs) - 1)))
        self._ao_selecionar()

    def _ao_selecionar(self):
        d = self._dub_atual()
        self._carregando = True
        if d:
            self.ed_nome.setText(d.nome)
            self.ed_idioma.setText(d.idioma)
            self.sp_atraso.setValue(d.atraso_ms)
            self.chk_padrao.setChecked(d.padrao)
            self.lbl_origem.setText(tr("%s  -  faixa %d  (%s)") % (d.arquivo, d.faixa, d.detalhe))
            self.lbl_vel.setText(tr("normal") if abs(d.atempo - 1.0) < 1e-9 else
                                 tr("corrigida (atempo=%.6f; só esta dublagem será convertida para FLAC)") % d.atempo)
        else:
            self.ed_nome.clear()
            self.ed_idioma.clear()
            self.lbl_origem.setText("-")
            self.lbl_vel.setText("-")
        self._carregando = False
        self._atualizar_estado()
        if d:
            self.onda.set_atraso(d.atraso_ms, d.atempo)
            self._carregar_onda_dub(d)
        else:
            self.onda.set_dub(None)

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
        r = self.tab.currentRow()
        if 0 <= r < len(self.dubs):
            del self.dubs[r]
            self._refresh_tabela(r)

    def acao_mover(self, delta):
        r = self.tab.currentRow()
        n = r + delta
        if 0 <= r < len(self.dubs) and 0 <= n < len(self.dubs):
            self.dubs[r], self.dubs[n] = self.dubs[n], self.dubs[r]
            self._refresh_tabela(n)

    def acao_zerar(self, *_):
        d = self._dub_atual()
        if d:
            d.atraso_ms, d.atempo, d.status = 0, 1.0, ""
            self._refresh_tabela()

    # ------------------------------------------------ editor
    def _ed_nome(self, texto):
        d = self._dub_atual()
        if d and not self._carregando:
            d.nome = texto
            self.tab.item(self.tab.currentRow(), 1).setText(texto)

    def _ed_idioma(self, texto):
        d = self._dub_atual()
        if d and not self._carregando:
            d.idioma = texto.strip().lower()

    def _ed_atraso(self, valor):
        d = self._dub_atual()
        if d and not self._carregando:
            d.atraso_ms = int(valor)
            vel = "  (x%.4f)" % (1.0 / d.atempo) if abs(d.atempo - 1.0) > 1e-9 else ""
            self.tab.item(self.tab.currentRow(), 3).setText("%+d%s" % (d.atraso_ms, vel))
            self.onda.set_atraso(d.atraso_ms, d.atempo)

    def _ed_padrao(self, marcado):
        d = self._dub_atual()
        if d and not self._carregando:
            if marcado:
                for o in self.dubs:
                    o.padrao = False
            d.padrao = bool(marcado)
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
                       lambda r: self._aplicar_resultado([d], r))

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
                       lambda r: self._aplicar_resultado(alvos, r))

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
        self._submeter(tr("Detectando o atraso (análise completa)"), job, lambda res: self._aplicar_resultado([d], res))

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
        self._submeter(tr("Detectando o atraso pelo vídeo"), job, lambda res: self._aplicar_resultado([d], res))

    def _aplicar_resultado(self, alvos, r):
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
                a.atraso_ms, a.atempo = r["atraso_ms"], 1.0
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
                a.atraso_ms = r["atraso_ms"]
                a.atempo = r["atempo"] if sim else 1.0
                a.status = (tr("velocidade corrigida (x%.4f), confiança %s") % (1 / r["atempo"], rot_conf(conf)) if sim
                            else tr("velocidade DIFERENTE, confiança %s") % rot_conf(conf))
        else:                                       # CORTES
            linhas = [tr("de %s a %s: %+d ms") % (fmt_tempo(g["ini"]), fmt_tempo(g["fim"]), g["atraso_ms"])
                      for g in r["grupos"]]
            cab = (tr("As versões têm CORTES diferentes: o atraso muda ao longo do filme (tempos do filme).")
                   if r.get("tempo_grupos") == "filme" else
                   tr("As versões têm CORTES diferentes: o atraso muda ao longo do filme."))
            resp = QMessageBox.question(
                self, NOME_APP,
                cab + "\n\n" + "\n".join(linhas[:12]) + "\n\n" +
                tr("Um único atraso não serve para o filme inteiro (juntar trechos ainda não existe nesta versão).\n"
                   "Usar o atraso do primeiro trecho (%+d ms)?") % r["atraso_ms"],
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            for a in alvos:
                a.status = tr("CORTES diferentes - ver registro")
                if resp == QMessageBox.StandardButton.Yes:
                    a.atraso_ms, a.atempo = r["atraso_ms"], 1.0
            self.log(tr("Trechos com atrasos diferentes: %s") % "; ".join(linhas))
        self._refresh_tabela()

    # ------------------------------------------------ montagem
    def acao_gerar(self, teste):
        if self._ocupado() or not (self.film and self.dubs):
            return
        try:
            core.validar(self.film, self.dubs)
        except Exception as e:
            self.aviso(str(e))
            return
        base = Path(self.film.caminho)
        sufixo = tr("_dublado_TESTE") if teste else tr("_dublado")
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
        film, dubs, motor, ferr = self.film, [core.Dublagem(**vars(d)) for d in self.dubs], self.motor, self.ferr
        manter = self._manter_param()
        try:
            core.validar_manter(film, manter)
        except Exception as e:
            self.aviso(str(e))
            return
        audios_mantidos = [f.pos for f in core.faixas_mantidas(film, manter) if f.tipo == "audio"]
        ref = self._ref_pos()
        ref_saida = audios_mantidos.index(ref) if ref in audios_mantidos else None

        def job(msg, prog, cancelar):
            saida = core.montar(film, dubs, caminho, teste, motor, ferr, msg, prog, cancelar, manter)
            msg(tr("ARQUIVO PRONTO: %s") % saida)
            msg(tr("Conferindo se cada dublagem tem som e está sincronizada (lê só 3 trechos curtos; o arquivo já "
                   "está pronto, mesmo que você cancele esta conferência)..."))
            conf = core.conferir_dublagens(saida, len(audios_mantidos), ref_saida, [d.nome for d in dubs], ferr,
                                           teste, cancelar, msg, prog)
            return saida, conf

        def pronto(res):
            saida, conf = res
            self.log(tr("Pronto (%s): %s") % (motor, saida))
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
                linhas.append("%s: %s" % (c["nome"], txt))
                self.log(tr("Conferência - %s") % linhas[-1])
            resumo = "\n".join(linhas)
            if mudas:
                outro = "FFmpeg" if motor == "mkvmerge" else "mkvmerge"
                self.erro(tr("Dublagem muda no arquivo gerado"),
                          tr("Estas dublagens saíram SEM SOM no arquivo gerado:\n%s\n\nTente gerar de novo com o outro "
                             "motor (Opções > Motor de montagem > %s). Se continuar, relate o problema (Ajuda > "
                             "Relatar um problema) com o conteúdo do Registro.\n\n%s")
                          % ("\n".join(mudas), outro, resumo))
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
                              "Tente o outro motor de montagem (Opções) e confira de novo.") % "\n".join(ruins))
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
            core.salvar_projeto(caminho, self.film.caminho, self._ref_pos(), self.motor, self.dubs, self._manter_param())
            self._projeto = caminho
            self.log(tr("Projeto salvo: %s") % caminho)

    def acao_abrir_projeto(self, *_):
        caminho, _ = QFileDialog.getOpenFileName(self, tr("Abrir projeto"), self.cfg.value("pasta", ""),
                                                 tr("Projeto EternalDub (*.eternaldub *.dubsync)"))
        if not caminho:
            return
        try:
            filme, ref, motor, dubs, manter = core.abrir_projeto(caminho)
        except Exception as e:
            self.erro(tr("Não consegui abrir o projeto"), str(e))
            return
        if filme and os.path.isfile(filme):
            self._carregar_filme(filme)
            if 0 <= ref < self.cmb_ref.count():
                self.cmb_ref.setCurrentIndex(ref)
            if manter is not None and self.film:
                self._preencher_faixas_filme(self.film, manter)
        self.dubs = [d for d in dubs if os.path.isfile(d.arquivo)]
        if len(self.dubs) != len(dubs):
            self.aviso(tr("Alguns arquivos de dublagem do projeto não foram encontrados e foram ignorados."))
        self._projeto = caminho
        self._refresh_tabela(0)

    def acao_motor(self, nome):
        self.motor = nome
        self.cfg.setValue("motor_v06", nome)
        self.log(tr("Motor de montagem: %s") % nome)

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
            self.ferr = core.achar_ferramentas({k: self.cfg.value(k, "") for k in ("ffmpeg", "ffprobe", "mkvmerge")})
            if nome == "ffmpeg":                      # o ffprobe costuma ficar na mesma pasta
                probe = os.path.join(os.path.dirname(caminho), "ffprobe" + os.path.splitext(caminho)[1])
                if os.path.isfile(probe):
                    self.cfg.setValue("ffprobe", probe)
                    self.ferr = core.achar_ferramentas({k: self.cfg.value(k, "") for k in ("ffmpeg", "ffprobe", "mkvmerge")})
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
        QMessageBox.about(
            self, tr("Sobre o EternalDub"),
            "<b>%s %s</b><br><br>" % (NOME_APP, VERSAO) +
            tr("Adiciona dublagens a releases de alta qualidade (BDRemux, WEB-DL...) <b>sem recodificar</b> o vídeo.") +
            "<br><br>" +
            tr("1) Abra o filme  2) adicione as dublagens  3) <i>Detectar atraso</i> (ou arraste a faixa laranja na "
               "onda)  4) <i>Gerar teste</i> e confira  5) <i>Gerar arquivo final</i>.") +
            "<br><br>" +
            tr("Se a dublagem tiver velocidade diferente (ex.: PAL), o programa avisa e corrige só a dublagem. "
               "Se as versões tiverem cortes diferentes, ele mostra os trechos.") +
            "<br><br><b>" + tr("Créditos") + "</b><br>" +
            tr("Criação, testes e direção do projeto: %s") % AUTOR + "<br>" +
            tr("Código escrito com auxílio de IA (Claude, da Anthropic).") + "<br>" +
            tr("Usa: FFmpeg, MKVToolNix (mkvmerge), Qt for Python (PySide6) e NumPy.") + "<br>" +
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
        if self.film is None:
            self._carregar_filme(caminhos.pop(0))
        if caminhos:
            self._adicionar_arquivos(caminhos)

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
    """Idioma salvo nas opcoes; senao, o do sistema (portugues -> pt, qualquer outro -> en)."""
    salvo = QSettings("EternalDub", "EternalDub").value("idioma", "")
    if salvo in ("pt", "en"):
        return salvo
    try:
        return "pt" if QLocale.system().name().lower().startswith("pt") else "en"
    except Exception:
        return i18n.do_sistema() if i18n else "pt"


def traduzir_qt(app, codigo):
    """Botoes padrao do Qt (Sim/Nao, OK/Cancelar, Mostrar detalhes) no idioma escolhido, se houver traducao."""
    if codigo != "pt":
        return
    try:
        pasta = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        t = QTranslator(app)
        if t.load("qtbase_pt_BR", pasta) or t.load("qtbase_pt", pasta):
            app.installTranslator(t)
            app._tradutor_qt = t
    except Exception:
        pass


def problema_arquivos():
    """Texto explicando a mistura de versoes, ou None se os arquivos combinam."""
    if not ERRO_ARQUIVOS:
        return None
    pasta = os.path.dirname(os.path.abspath(__file__))
    return (tr("Os arquivos do EternalDub nesta pasta não combinam:\n%s\n\nPasta: %s\n\nComo resolver: extraia o "
               "EternalDub numa pasta NOVA e vazia, ou apague os arquivos antigos desta pasta (inclusive cópias com "
               "(1), (2) no nome, e os antigos dubsync_*.py).\nTodos estes precisam ser da versão %s: %s.")
            % (ERRO_ARQUIVOS, pasta, VERSAO_ARQUIVOS, ", ".join(ARQUIVOS)))


def principal():
    app = QApplication(sys.argv)
    app.setApplicationName(NOME_APP)
    app.setApplicationVersion(VERSAO)
    codigo = escolher_idioma()
    if i18n:
        i18n.definir(codigo)
    traduzir_qt(app, codigo)
    tema_escuro(app)
    texto = problema_arquivos()
    if texto:
        print(texto, file=sys.stderr)
        QMessageBox.critical(None, NOME_APP + " - " + tr("arquivos de versões diferentes"), texto)
        sys.exit(2)

    def gancho(tipo, valor, tb):
        texto = "".join(traceback.format_exception(tipo, valor, tb))
        try:
            pasta = Path.home() / ".eternaldub"
            pasta.mkdir(exist_ok=True)
            (pasta / "erro.log").write_text(texto, encoding="utf-8")
        except OSError:
            pass
        print(texto, file=sys.stderr)
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
    for a in sys.argv[1:]:                       # arquivos passados na linha de comando
        if os.path.isfile(a) and j.film is None:
            j._carregar_filme(os.path.normpath(a))
    sys.exit(app.exec())


if __name__ == "__main__":
    principal()
