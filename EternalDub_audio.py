# SPDX-License-Identifier: MIT
# EternalDub - Copyright (C) 2026 Moguel0818 e colaboradores / and contributors
# -*- coding: utf-8 -*-
"""
EternalDub_audio.py - PREVIA de audio: ouvir a dublagem (e o filme) sem gerar nenhum arquivo.

A previa usa o MESMO montador do arquivo final (EternalDub_core.MontadorPedacos): a dublagem passa pela
mesma correcao de velocidade, pelo mesmo atraso e pelas mesmas emendas, com os mesmos cruzamentos de 8 ms.
O que se ouve aqui e o que vai para o arquivo (em mono, para ser leve).

Como funciona: so e lido o trecho que vai tocar. O FFmpeg pula direto para o ponto (-ss) e decodifica
daquele ponto em diante; o montador pula o que a dublagem nao usa e entrega o audio na linha do tempo do filme,
em blocos de 0,25 s, para quem chama (a interface) ir tocando enquanto o resto ainda esta sendo decodificado.

Nada aqui depende da interface grafica (so de FFmpeg e numpy); a parte do Qt fica no EternalDub_gui.py.
"""
import subprocess
import tempfile
import threading

import numpy as np

import EternalDub_core as core
from EternalDub_i18n import tr

VERSAO_AUDIO = "1.3"

SR_PREVIA = 48000        # taxa da previa (mono, float32 -> 16 bits ao tocar)
PRE_ROLL = 0.3           # s lidos antes do ponto de partida, so para o filtro de velocidade "aquecer"
BLOCO_S = 0.25           # s por bloco entregue a quem esta tocando
MODOS = ("dub", "filme", "mix")


def recortar_plano(plano, w0, w1):
    """
    Restringe o plano de montagem (core.plano_de_pedacos) a janela [w0, w1) da saida (amostras).
    Devolve (plano_da_janela, base): na janela, as posicoes de saida contam a partir de w0 e as de entrada a
    partir de `base` (onde o decodificador precisa comecar, ja no tempo esticado). ([], 0) se nada toca ali.
    """
    Q = []
    for o0, o1, i0 in plano:
        a, b = max(o0, w0), min(o1, w1)
        if b > a:
            Q.append([a - w0, b - w0, i0 + (a - o0)])
    if not Q:
        return [], 0
    base = Q[0][2]
    return [[o0, o1, i0 - base] for o0, o1, i0 in Q], base


def comando_dublagem(ferr, src, idx, ss, atempo, sr):
    """Decodifica a faixa `idx` de `src` a partir de `ss` s (tempo ORIGINAL): mono, float32, WAV no pipe."""
    filtro = "aresample=async=1:first_pts=0"
    if abs(1.0 / float(atempo or 1.0) - 1.0) > 1e-9:
        filtro += ",atempo=%.8f" % atempo
    return [ferr.ffmpeg, "-v", "error", "-nostdin", "-ss", "%.6f" % max(0.0, ss), "-i", src, "-map", "0:a:%d" % idx,
            "-vn", "-sn", "-dn", "-af", filtro, "-ac", "1", "-ar", str(sr), "-c:a", "pcm_f32le", "-f", "wav", "pipe:1"]


def comando_referencia(ferr, caminho, pos, codec, ss, dur, sr):
    """Decodifica o audio de referencia do filme de `ss` a `ss + dur`: mono, float32 bruto no pipe."""
    cmd = [ferr.ffmpeg, "-v", "error", "-nostdin"]
    if (codec or "").lower() == "dts":
        cmd += ["-core_only", "1"]                 # o nucleo DTS basta para ouvir e e bem mais leve
    return cmd + ["-ss", "%.6f" % max(0.0, ss), "-t", "%.6f" % dur, "-i", caminho, "-map", "0:a:%d" % pos,
                  "-vn", "-sn", "-dn", "-af", "aresample=async=1:first_pts=0", "-ac", "1", "-ar", str(sr),
                  "-c:a", "pcm_f32le", "-f", "f32le", "pipe:1"]


def para_pcm16_estereo(x, ganho=1.0):
    """Mono float32 (-1..1) -> bytes de 16 bits estereo intercalado (o formato que a placa de som recebe)."""
    y = np.clip(np.asarray(x, dtype=np.float32) * float(ganho), -1.0, 1.0)
    s = (y * 32767.0).astype("<i2")
    return np.repeat(s, 2).tobytes()


class _Processo:
    """Um programa lendo para um pipe, encerrado na hora se `cancelar` for acionado."""

    def __init__(self, cmd, cancelar):
        self.erro = tempfile.TemporaryFile()
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=self.erro, stdin=subprocess.DEVNULL,
                                  creationflags=core.CRIAR_SEM_JANELA)
        self._fim = threading.Event()
        self._cancelar = cancelar
        threading.Thread(target=self._vigiar, daemon=True).start()

    def _vigiar(self):
        while not self._fim.is_set():
            if self._cancelar.wait(0.1):
                try:
                    self.p.kill()
                except OSError:
                    pass
                return

    def texto_do_erro(self):
        try:
            self.erro.seek(0)
            return self.erro.read().decode("utf-8", "replace").strip()[-600:]
        except (OSError, ValueError):
            return ""

    def fechar(self):
        self._fim.set()
        if self.p.poll() is None:
            try:
                self.p.kill()
            except OSError:
                pass
        try:
            self.p.wait(10)
        except Exception:
            pass
        for f in (self.p.stdout, self.p.stdin):
            try:
                if f:
                    f.close()
            except Exception:
                pass
        self.erro.close()


class Previa:
    """
    Gera a previa do trecho [t_ini, t_fim) do filme (segundos) e entrega, em ordem, blocos mono float32.

      modo:    'dub'   a dublagem ja sincronizada (atraso, velocidade e emendas do projeto)
               'filme' o audio de referencia do filme
               'mix'   os dois somados (se o som dos dois combina, a sincronia esta certa; senao da eco)
      filme:   (caminho, faixa_de_audio, codec) da referencia (obrigatorio em 'filme' e 'mix')
      dub:     core.Dublagem (obrigatorio em 'dub' e 'mix')
    """

    def __init__(self, ferr, modo, t_ini, t_fim, filme=None, dub=None, sr=SR_PREVIA, cancelar=None):
        if modo not in MODOS:
            raise ValueError(modo)
        if modo in ("filme", "mix") and not filme:
            raise ValueError("falta o filme")
        if modo in ("dub", "mix") and dub is None:
            raise ValueError("falta a dublagem")
        self.ferr, self.modo, self.filme, self.dub = ferr, modo, filme, dub
        self.t_ini, self.t_fim = float(t_ini), float(t_fim)
        self.sr = int(sr)
        self.cancelar = cancelar or threading.Event()
        self.total = max(0, int(round(self.t_fim * self.sr)) - int(round(self.t_ini * self.sr)))
        self.entregues = 0

    # ---- execucao (numa linha de execucao propria; entrega os blocos por `saida`)
    def executar(self, saida):
        """saida(array float32 1D) recebe os blocos. Levanta core.Cancelado se for cancelado."""
        ref = None
        try:
            if self.modo in ("filme", "mix"):
                caminho, pos, codec = self.filme
                ref = _Processo(comando_referencia(self.ferr, caminho, pos, codec, self.t_ini,
                                                   self.total / self.sr, self.sr), self.cancelar)
            if self.modo == "filme":
                self._so_referencia(ref, saida)
            else:
                self._com_dublagem(ref, saida)
            if self.cancelar.is_set():
                raise core.Cancelado()
        finally:
            if ref is not None:
                ref.fechar()

    def _ler_ref(self, ref, n):
        """Ate n amostras da referencia (menos so se o audio do filme acabar)."""
        dados = bytearray()
        while len(dados) < 4 * n:
            parte = ref.p.stdout.read(4 * n - len(dados))
            if not parte:
                break
            dados += parte
        return np.frombuffer(bytes(dados[:len(dados) // 4 * 4]), dtype="<f4")

    def _erro_ref(self, ref):
        """Levanta o erro do FFmpeg se a referencia nao entregou nada (arquivo ruim, faixa inexistente...)."""
        if self.cancelar.is_set():
            raise core.Cancelado()
        raise RuntimeError(tr("O FFmpeg não entregou o áudio do filme.") + "\n" + ref.texto_do_erro())

    def _entregar(self, x):
        if self.cancelar.is_set():
            raise core.Cancelado()
        self.entregues += len(x)
        self._saida(np.ascontiguousarray(x, dtype=np.float32))

    def _so_referencia(self, ref, saida):
        self._saida = saida
        bloco = int(BLOCO_S * self.sr)
        while self.entregues < self.total:
            n = min(bloco, self.total - self.entregues)
            x = self._ler_ref(ref, n)
            if not len(x):
                if self.entregues == 0:
                    self._erro_ref(ref)
                break                                     # o audio do filme acabou
            self._entregar(x)
            if len(x) < n:
                break

    def _com_dublagem(self, ref, saida):
        self._saida = saida
        sr, d = self.sr, self.dub
        w0, w1 = int(round(self.t_ini * sr)), int(round(self.t_fim * sr))
        plano = core.plano_de_pedacos(core.pedacos_efetivos(d), d.atempo, sr)
        P, base = recortar_plano(plano, w0, w1)
        mix = ref is not None

        def sair(x):                                         # x: dublagem deste bloco (1D)
            if mix:
                y = self._ler_ref(ref, len(x))
                if not len(y) and self.entregues == 0:
                    self._erro_ref(ref)
                x = 0.5 * x + 0.5 * np.pad(y, (0, len(x) - len(y)))
            self._entregar(x)

        dec = None
        try:
            if P:
                pre = min(base, int(round(PRE_ROLL * sr)))   # comeca um pouco antes: o filtro de velocidade aquece
                P = [[o0, o1, i0 + pre] for o0, o1, i0 in P]
                dec = _Processo(comando_dublagem(self.ferr, d.arquivo, d.faixa, (base - pre) / sr * d.atempo,
                                                 d.atempo, sr), self.cancelar)
                try:
                    _, C, bits = core._cabecalho_wav(dec.p.stdout)
                except RuntimeError as e:
                    if self.cancelar.is_set():
                        raise core.Cancelado()
                    raise RuntimeError(str(e) + "\n" + dec.texto_do_erro())
                if bits != 32 or C != 1:
                    raise RuntimeError(tr("O FFmpeg não entregou o áudio da dublagem."))
                core.MontadorPedacos(P, 1, sr, dec.p.stdout.read, lambda arr: sair(arr[:, 0]),
                                     self.cancelar, bloco=int(BLOCO_S * sr)).executar()
            while mix and self.entregues < self.total:         # a dublagem acabou antes: segue so o filme
                n = min(int(BLOCO_S * sr), self.total - self.entregues)
                y = self._ler_ref(ref, n)
                if not len(y):
                    if self.entregues == 0:
                        self._erro_ref(ref)
                    break
                self._entregar(0.5 * y)                        # no mix o filme fica com a mesma metade do volume
        finally:
            if dec is not None:
                dec.fechar()
