#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# EternalDub - Copyright (C) 2026 Moguel0818 e colaboradores / and contributors
# -*- coding: utf-8 -*-
"""
detectar_atraso.py - descobre o ATRASO (offset) de uma dublagem em relacao a um filme.

Uso basico:
    python detectar_atraso.py FILME.mkv DUBLAGEM.mp4

Como funciona (so precisa de Python 3, numpy e FFmpeg):
  AUDIO: compara a "forma" do som (energia por faixa de frequencia ao longo do tempo)
         da dublagem com a do audio original do filme, por correlacao cruzada.
         Funciona porque musica e efeitos sonoros costumam ser os mesmos nas duas
         versoes, mesmo com vozes diferentes.
  VIDEO: se a dublagem vier num arquivo com video (ex.: mp4 de baixa qualidade),
         compara os CORTES DE CENA desse video com os do filme. Como a dublagem ja esta
         sincronizada com o video dela, o atraso do video e o atraso da dublagem.
  Alem do atraso, testa varias partes do filme para avisar se ha diferenca de
  VELOCIDADE (ex.: PAL 25 fps vs 23,976 fps) ou CORTES diferentes entre as versoes.

Rapidez (modo padrao): num remux UHD, quase todos os bytes do arquivo sao VIDEO. Para
pegar o audio de um trecho, o FFmpeg tem de ler o video daquele trecho tambem. Por isso o
modo rapido le POUCO do filme: 1 minuto + 4 trechos de 40 s espalhados (pulando direto para
eles), e procura cada um numa regiao maior da dublagem, que costuma ser bem mais leve.
Nada disso altera o arquivo final: e so leitura para MEDIR.

Convencao do sinal (a mesma do Adicionar_Dublagem.bat):
    positivo = a dublagem precisa ser ATRASADA; negativo = ADIANTADA.
"""
import argparse
import json
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np

try:
    from EternalDub_i18n import tr, N_, rot_conf, rot_metodo, definir as _definir_idioma, do_sistema as _idioma_sistema
except ImportError:                      # o detector tambem funciona sozinho, em portugues
    def tr(texto):
        return texto

    def N_(texto):
        return texto
    rot_conf = rot_metodo = tr
    _definir_idioma = _idioma_sistema = None

VERSAO_DETECTOR = "1.0"     # tem de ser igual a do EternalDub_core.py

# ----------------------------------------------------------------- configuracao
SR_AUDIO = 8000            # taxa de amostragem usada na analise de audio
HOP_AUDIO = 160            # 160 amostras a 8000 Hz = 20 ms -> 50 quadros por segundo
TAXA_AUDIO = SR_AUDIO / HOP_AUDIO
TAXA_VIDEO = 24.0          # quadros por segundo usados na analise de video
N_BANDAS = 20

# r = tempo_do_filme / tempo_da_dublagem.  r > 1: a dublagem e mais RAPIDA que o filme.
CANDIDATOS_VELOCIDADE = [
    (1.0, N_("mesma velocidade")),
    (25 / 23.976, N_("dublagem 4,27% mais rápida que o filme (fonte PAL 25 fps vs 23,976 fps)")),
    (23.976 / 25, N_("dublagem 4,10% mais lenta que o filme (fonte 23,976 fps vs 25 fps)")),
    (25 / 24, N_("dublagem 4,17% mais rápida que o filme (25 fps vs 24 fps)")),
    (24 / 25, N_("dublagem 4,00% mais lenta que o filme (24 fps vs 25 fps)")),
    (24 / 23.976, N_("dublagem 0,10% mais rápida que o filme (24 fps vs 23,976 fps)")),
    (23.976 / 24, N_("dublagem 0,10% mais lenta que o filme (23,976 fps vs 24 fps)")),
]

Z_MIN_JANELA = 6.0         # pontuacao minima para um trecho contar como "confiavel"


# ----------------------------------------------------------------- FFmpeg / FFprobe
FFMPEG = "ffmpeg"      # a interface grafica pode trocar por um caminho completo
FFPROBE = "ffprobe"
_KW = {"creationflags": 0x08000000} if sys.platform == "win32" else {}   # sem janela preta no Windows


class Cancelado(Exception):
    """A leitura foi cancelada pelo usuario."""


class TempoEsgotado(RuntimeError):
    """O programa passou do tempo maximo permitido e foi encerrado."""


def _executar(cmd, ao_ler=None, cancelar=None, bloco=1 << 20, limite_s=None, basta=None):
    """
    Roda um programa lendo a saida em pedacos (nao trava a memoria).
    ao_ler(bytes)  recebe cada pedaco da saida padrao.
    cancelar       Event: encerra o programa em ~0,2 s (mesmo se ele nao estiver escrevendo nada).
    limite_s       tempo maximo; passou disso -> encerra e levanta TempoEsgotado.
    basta()        chamado ~5x/s; se devolver True o programa e encerrado e a funcao volta
                   normalmente (quem chamou ja tem o que precisava).
    Devolve o texto de erro (stderr).
    """
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             stdin=subprocess.DEVNULL, **_KW)
    except FileNotFoundError:
        raise RuntimeError(tr("FFmpeg não encontrado. Instale o FFmpeg e tente de novo."))
    erros = []
    t_err = threading.Thread(target=lambda: erros.append(p.stderr.read()), daemon=True)
    t_err.start()
    motivo = {"v": None}

    def vigiar():
        t0 = time.monotonic()
        while p.poll() is None:
            if cancelar is not None and cancelar.is_set():
                motivo["v"] = "cancelado"
            elif limite_s and time.monotonic() - t0 > limite_s:
                motivo["v"] = "tempo"
            elif basta is not None:
                try:
                    if basta():
                        motivo["v"] = "basta"
                except Exception:
                    pass
            if motivo["v"]:
                try:
                    p.kill()
                except OSError:
                    pass
                return
            time.sleep(0.2)
    t_vig = threading.Thread(target=vigiar, daemon=True)
    t_vig.start()
    terminou = False
    try:
        while True:
            dados = p.stdout.read1(bloco) if hasattr(p.stdout, "read1") else p.stdout.read(bloco)
            if not dados:
                break
            if ao_ler:
                ao_ler(dados)
            if cancelar is not None and cancelar.is_set():
                motivo["v"] = motivo["v"] or "cancelado"
                break
        terminou = True
    finally:
        if p.poll() is None:
            try:
                p.kill()                   # cancelado, erro ou basta: encerra o programa na hora
            except OSError:
                pass
        rc = p.wait()
        t_vig.join(1)
        t_err.join(1)
        try:
            p.stdout.close()
        except Exception:
            pass
        if not t_err.is_alive():           # fechar enquanto a outra linha le travaria aqui
            try:
                p.stderr.close()
            except Exception:
                pass
    texto = (erros[0] if erros else b"").decode("utf-8", "replace").strip()
    if motivo["v"] == "cancelado":
        raise Cancelado()
    if motivo["v"] == "tempo":
        raise TempoEsgotado(tr("passou de %d s") % limite_s)
    if motivo["v"] == "basta" or not terminou:
        return texto
    if rc != 0:
        raise RuntimeError(texto or tr("o FFmpeg falhou (código %s)") % rc)
    return texto


def rodar_ffmpeg(args, cancelar=None):
    partes = []
    _executar([FFMPEG, "-v", "error", "-nostdin"] + args, partes.append, cancelar)
    return b"".join(partes)


def sondar(caminho):
    """Lista as faixas de audio (com idioma) e diz se ha video."""
    try:
        p = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                            "stream=index,codec_type,codec_name:stream_tags=language,title,DURATION:format=duration",
                            "-of", "json", caminho],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_KW)
    except FileNotFoundError:
        raise SystemExit(tr("ERRO: ffprobe não encontrado. Instale o FFmpeg e tente de novo."))
    if p.returncode != 0:
        raise SystemExit(tr("ERRO: não consegui abrir: %s") % caminho)
    j = json.loads(p.stdout.decode("utf-8", "replace"))
    fluxos = j.get("streams", [])
    audios = [f for f in fluxos if f.get("codec_type") == "audio"]
    videos = [f for f in fluxos if f.get("codec_type") == "video"]
    try:
        duracao = float(j.get("format", {}).get("duration") or 0)
    except ValueError:
        duracao = 0.0
    return {"audios": audios, "tem_video": len(videos) > 0, "duracao": duracao}


def fim_faixa(info, faixa):
    """Ate onde vai o audio da faixa (tag DURATION do MKV); senao, a duracao do arquivo."""
    tags = info["audios"][faixa].get("tags", {}) or {}
    texto = tags.get("DURATION") or tags.get("duration") or ""
    try:
        h, m, s = texto.split(":")
        d = int(h) * 3600 + int(m) * 60 + float(s)
        return min(d, info["duracao"]) if info["duracao"] else d
    except ValueError:
        return info["duracao"]


def idioma(f):
    return (f.get("tags", {}).get("language") or "").lower()


# ----------------------------------------------------------------- carregar sinais
def opcoes_decodificador(codec):
    """
    DTS-HD MA / DTS:X: para MEDIR basta o nucleo DTS que vem dentro da faixa (decodificar a
    extensao sem perdas e mais lento e nao muda a medicao). Vale SO para a leitura de analise;
    o arquivo final continua recebendo a faixa original, copiada sem nenhuma alteracao.
    """
    return ["-core_only", "1"] if (codec or "").lower() == "dts" else []


def comando_pcm(caminho, faixa, inicio=0.0, duracao=None, codec="", saida="pipe:1"):
    """
    Comando do FFmpeg que extrai a faixa de audio `faixa` como mono, 8 kHz, 16 bits (leve,
    so para analise).  inicio > 0: pula DIRETO para esse ponto (usa o indice do MKV/MP4),
    sem ler o que vem antes.  duracao: le so esse tanto.
    """
    cmd = [FFMPEG, "-v", "error", "-nostdin", "-nostats"] + opcoes_decodificador(codec)
    if inicio and inicio > 0:
        cmd += ["-ss", "%.3f" % inicio]
    if duracao:
        cmd += ["-t", "%.3f" % duracao]
    # first_pts=0: se o audio comecar depois do inicio do arquivo, preenche com silencio,
    # para que o "tempo zero" seja o mesmo que o FFmpeg usa ao juntar os arquivos.
    cmd += ["-i", caminho, "-map", "0:a:%d" % faixa, "-af", "aresample=async=1:first_pts=0",
            "-ac", "1", "-ar", str(SR_AUDIO), "-c:a", "pcm_s16le", "-f", "s16le", saida]
    return cmd


def ler_pcm(caminho, faixa, inicio=0.0, duracao=None, codec="", cancelar=None):
    """Audio mono 8 kHz int16 de um trecho (ou do arquivo todo, se duracao=None)."""
    partes = []
    _executar(comando_pcm(caminho, faixa, inicio, duracao, codec), partes.append, cancelar)
    dados = b"".join(partes)
    return np.frombuffer(dados[:len(dados) // 2 * 2], dtype="<i2").copy()


def carregar_pcm16(caminho, faixa, codec="", cancelar=None):
    return ler_pcm(caminho, faixa, codec=codec, cancelar=cancelar)


def carregar_audio(caminho, faixa, codec=""):
    return carregar_pcm16(caminho, faixa, codec).astype(np.float32) / 32768.0


def carregar_video(caminho, cancelar=None):
    dados = rodar_ffmpeg(["-i", caminho, "-map", "0:v:0", "-an", "-sn", "-dn",
                          "-vf", "fps=%g:start_time=0,scale=32:18:flags=area,format=gray" % TAXA_VIDEO,
                          "-f", "rawvideo", "-"], cancelar)
    return np.frombuffer(dados, dtype=np.uint8).reshape(-1, 32 * 18)


# ----------------------------------------------------------------- caracteristicas
def passa_alta(m, janela):
    """Tira a media movel (variacoes lentas) de cada linha de m (formato F x N)."""
    k = 2 * (int(janela) // 2) + 1
    h = k // 2
    p = np.pad(m, ((0, 0), (h, h)), mode="edge").astype(np.float64)
    c = np.concatenate([np.zeros((m.shape[0], 1)), np.cumsum(p, axis=1)], axis=1)
    media = (c[:, k:] - c[:, :-k]) / k
    return (m - media[:, :m.shape[1]]).astype(np.float32)


def normalizar(m):
    m = m - m.mean(axis=1, keepdims=True)
    return (m / (m.std(axis=1, keepdims=True) + 1e-9)).astype(np.float32)


def caracteristicas_audio(x):
    n = 1024
    if len(x) < 4 * n:
        raise RuntimeError(tr("áudio curto demais para analisar"))
    janela = np.hanning(n).astype(np.float32)
    freqs = np.fft.rfftfreq(n, 1.0 / SR_AUDIO)
    idx = np.unique(np.searchsorted(freqs, np.geomspace(100, 3800, N_BANDAS + 1)))
    quadros = (len(x) - n) // HOP_AUDIO + 1
    visao = np.lib.stride_tricks.sliding_window_view(x, n)[::HOP_AUDIO]
    saida = np.empty((quadros, len(idx) - 1), np.float32)
    for i in range(0, quadros, 4096):
        esp = np.abs(np.fft.rfft(visao[i:i + 4096] * janela, axis=1)) ** 2
        saida[i:i + 4096] = np.add.reduceat(esp[:, :idx[-1]], idx[:-1], axis=1)
    piso = np.median(saida, axis=0) * 1e-2 + 1e-12
    m = np.log(saida + piso).T.copy()
    return normalizar(passa_alta(m, 2.0 * TAXA_AUDIO))


def caracteristicas_video(q):
    n = len(q)
    d = np.zeros(n, np.float32)      # diferenca entre quadros seguidos (cortes e movimento)
    lum = np.zeros(n, np.float32)    # brilho medio
    passo = 20000
    for i in range(0, n, passo):     # em blocos, para nao estourar a memoria em filmes longos
        ini = max(i - 1, 0)
        f = q[ini:i + passo].astype(np.float32)
        lum[i:i + passo] = f[i - ini:].mean(axis=1)
        dd = np.abs(np.diff(f, axis=0)).mean(axis=1)
        d[ini + 1:ini + 1 + len(dd)] = dd
    m = np.vstack([np.log1p(d), lum]).astype(np.float32)
    return normalizar(passa_alta(m, 2.0 * TAXA_VIDEO))


# ----------------------------------------------------------------- correlacao cruzada
def prox_pot2(n):
    return 1 << (int(n) - 1).bit_length()


def correlacao(a, b, lag_min, lag_max):
    """
    Correlacao de a (referencia/filme) com b (dublagem) para atrasos lag_min..lag_max
    (em quadros).  Atraso k significa: a[t + k] combina com b[t].
    """
    nb = b.shape[1]
    ini = lag_min
    tam = nb + (lag_max - lag_min)
    seg = np.zeros((a.shape[0], tam), np.float32)
    ia0, ia1 = max(ini, 0), min(ini + tam, a.shape[1])
    if ia1 > ia0:
        seg[:, ia0 - ini:ia1 - ini] = a[:, ia0:ia1]
    n = prox_pot2(tam + nb)
    s = None
    for f in range(a.shape[0]):
        p = np.fft.rfft(seg[f], n) * np.conj(np.fft.rfft(b[f], n))
        s = p if s is None else s + p
    return np.fft.irfft(s, n)[:lag_max - lag_min + 1]


def pico(c, lag_min, taxa):
    """Maior pico da correlacao -> (atraso em segundos, pontuacao z)."""
    k = int(np.argmax(c))
    delta = 0.0
    if 0 < k < len(c) - 1:
        y0, y1, y2 = float(c[k - 1]), float(c[k]), float(c[k + 1])
        den = y0 - 2 * y1 + y2
        if den != 0:
            delta = max(-1.0, min(1.0, 0.5 * (y0 - y2) / den))
    mascara = np.ones(len(c), bool)
    w = int(1.0 * taxa)
    mascara[max(0, k - w):k + w + 1] = False
    resto = c[mascara]
    if resto.size < 10:
        return (lag_min + k + delta) / taxa, 0.0
    z = (float(c[k]) - float(resto.mean())) / (float(resto.std()) + 1e-12)
    return (lag_min + k + delta) / taxa, z


def reamostrar(b, r):
    """Estica/encolhe a linha do tempo de b por r (tempo_filme = r * tempo_dub)."""
    if abs(r - 1.0) < 1e-9:
        return b
    n_novo = int(b.shape[1] * r)
    pos = np.arange(n_novo) / r
    xp = np.arange(b.shape[1])
    return np.vstack([np.interp(pos, xp, b[i]) for i in range(b.shape[0])]).astype(np.float32)


# ----------------------------------------------------------------- analise
def busca_global(a, b, taxa, max_offset_s):
    lim = int(max_offset_s * taxa)
    tabela = []
    for r, desc in CANDIDATOS_VELOCIDADE:
        br = reamostrar(b, r)
        off, z = pico(correlacao(a, br, -lim, lim), -lim, taxa)
        tabela.append({"r": r, "desc": desc, "offset": off, "z": z})
    melhor = max(tabela, key=lambda t: t["z"])
    igual = tabela[0]
    escolhido = igual if igual["z"] >= 0.75 * melhor["z"] else melhor
    return escolhido, tabela


def verificar_janelas(a, br, taxa, off_s, janela_s=60.0, folga_s=20.0):
    """Mede o atraso em varios trechos da dublagem (ja na velocidade escolhida)."""
    w = int(janela_s * taxa)
    folga = int(folga_s * taxa)
    centro = int(round(off_s * taxa))
    out = []
    for i0 in range(0, br.shape[1] - w + 1, w):
        c = correlacao(a[:, max(i0, 0):], br[:, i0:i0 + w], centro - folga, centro + folga) \
            if i0 <= a.shape[1] else None
        if c is None:
            continue
        off, z = pico(c, centro - folga, taxa)
        out.append({"t": (i0 + w / 2) / taxa, "offset": off, "z": z})
    return out


def theil_sen(t, y):
    n = len(t)
    if n < 3:
        return 0.0, float(np.median(y))
    i, j = np.triu_indices(n, 1)
    dt = t[j] - t[i]
    ok = dt > 1e-9
    m = float(np.median((y[j][ok] - y[i][ok]) / dt[ok])) if ok.any() else 0.0
    c = float(np.median(y - m * t))
    return m, c


def interpretar(janelas, escolhido, tol_s):
    """Decide: OK / VELOCIDADE / DERIVA / CORTES / BAIXA_CONFIANCA."""
    boas = [j for j in janelas if j["z"] >= Z_MIN_JANELA]
    r = escolhido["r"]
    res = {"r": r, "janelas": janelas, "n_boas": len(boas), "n_total": len(janelas),
           "z_mediano": float(np.median([j["z"] for j in boas])) if boas else 0.0,
           "grupos": [], "extra_r": 1.0}
    if len(boas) < max(3, len(janelas) // 4):
        res["status"] = "BAIXA_CONFIANCA"
        res["atraso"] = escolhido["offset"]
        return res
    t = np.array([j["t"] for j in boas])
    y = np.array([j["offset"] for j in boas])
    med = float(np.median(y))
    perto = np.abs(y - med) <= tol_s
    if perto.mean() >= 0.85:
        res["atraso"] = float(np.median(y[perto]))
        res["status"] = "OK" if abs(r - 1.0) < 1e-9 else "VELOCIDADE"
        return res
    m, c = theil_sen(t, y)
    resid = np.abs(y - (m * t + c))
    if (resid <= tol_s).mean() >= 0.85 and abs(m) > 1e-5:
        res["status"] = "DERIVA"
        res["extra_r"] = 1.0 + m
        res["atraso"] = float(c)   # atraso depois de corrigir a velocidade por completo
        return res
    # agrupa trechos consecutivos com o mesmo atraso -> cortes diferentes
    grupos = []
    for tj, yj in zip(t, y):
        if grupos and abs(yj - np.median(grupos[-1]["y"])) <= tol_s:
            grupos[-1]["y"].append(yj)
            grupos[-1]["fim"] = tj
        else:
            grupos.append({"ini": tj, "fim": tj, "y": [yj]})
    grandes = [g for g in grupos if len(g["y"]) >= 2]
    res["grupos"] = [{"ini": g["ini"] - 30, "fim": g["fim"] + 30, "atraso": float(np.median(g["y"]))}
                     for g in grandes]
    res["status"] = "CORTES"
    res["atraso"] = float(np.median(grandes[0]["y"])) if grandes else med
    return res


def analisar(nome, a, b, taxa, args):
    escolhido, tabela = busca_global(a, b, taxa, args.max_offset)
    br = reamostrar(b, escolhido["r"])
    janelas = verificar_janelas(a, br, taxa, escolhido["offset"], janela_s=args.janela)
    res = interpretar(janelas, escolhido, args.tolerancia / 1000.0)
    res["metodo"] = nome
    res["faixa_dub"] = args.faixa_dub
    res["escolhido"] = escolhido
    res["tabela"] = tabela
    res["modo"] = "completo"
    res["confianca"] = _confianca(res)
    return res


def _confianca(res):
    if res["status"] == "BAIXA_CONFIANCA":
        return "BAIXA"
    if res["z_mediano"] >= 10 and res["n_boas"] >= 0.7 * res["n_total"]:
        return "ALTA"
    return "MEDIA"


# ----------------------------------------------------------------- analise RAPIDA (le POUCO do filme)
# Num remux UHD, 1 minuto de filme ocupa ~0,5 a 0,8 GB no disco (quase tudo video), enquanto 1 minuto
# de uma fonte 1080p/MP4 ocupa bem menos. Por isso a analise rapida le POUCO do filme (trechos curtos)
# e procura cada trecho numa regiao MAIOR da dublagem, que e barata de ler.
R_MIN = min(r for r, _ in CANDIDATOS_VELOCIDADE)
R_MAX = max(r for r, _ in CANDIDATOS_VELOCIDADE)
Z_ACHAR = 8.0              # pontuacao minima para aceitar o primeiro encontro (atraso e velocidade)


def _feat_pcm(pcm):
    return caracteristicas_audio(pcm.astype(np.float32) / 32768.0)


def _casar(fw, f0, dub_feat, d0, r, taxa=TAXA_AUDIO):
    """
    Procura o trecho do filme `fw` (que comeca em f0 s) dentro da regiao da dublagem `dub_feat`
    (que comeca em d0 s), com a dublagem esticada pela velocidade r.
    Devolve (atraso_s, z), na convencao  tempo_filme = r * tempo_dub + atraso.
    """
    br = reamostrar(dub_feat, r)
    folga = br.shape[1] - fw.shape[1]
    if folga < 2 * taxa:
        return None, 0.0
    lag, z = pico(correlacao(br, fw, 0, folga), 0, taxa)
    return f0 - r * d0 - lag, z


def _interpretar_pontos(janelas, falhas, escolhido, tol_s):
    """Decide OK / VELOCIDADE / DERIVA / CORTES / BAIXA_CONFIANCA a partir de poucos pontos espalhados."""
    boas = sorted([j for j in janelas if j["z"] >= Z_MIN_JANELA], key=lambda j: j["t"])
    r = escolhido["r"]
    res = {"r": r, "janelas": janelas, "n_boas": len(boas), "n_total": len(janelas) + len(falhas),
           "z_mediano": float(np.median([j["z"] for j in boas])) if boas else 0.0,
           "grupos": [], "extra_r": 1.0, "falhas": list(falhas), "tempo_grupos": "filme"}
    if len(boas) < 3:
        res.update(status="BAIXA_CONFIANCA", atraso=escolhido["offset"])
        return res
    t = np.array([j["t"] for j in boas])
    y = np.array([j["offset"] for j in boas])
    med = float(np.median(y))
    if np.all(np.abs(y - med) <= tol_s):
        res.update(status="OK" if abs(r - 1.0) < 1e-9 else "VELOCIDADE", atraso=med)
        return res
    m, c = theil_sen(t, y)                    # atraso = c + m * tempo_do_filme
    if np.all(np.abs(y - (m * t + c)) <= tol_s) and abs(m) > 1e-5:
        res.update(status="DERIVA", extra_r=1.0 / (1.0 - m), atraso=c / (1.0 - m))
        return res
    grupos = []
    for j in boas:
        if grupos and abs(j["offset"] - np.median(grupos[-1]["y"])) <= tol_s:
            grupos[-1]["y"].append(j["offset"])
            grupos[-1]["fim"] = j["t"]
        else:
            grupos.append({"ini": j["t"], "fim": j["t"], "y": [j["offset"]]})
    res["grupos"] = [{"ini": g["ini"] - 20, "fim": g["fim"] + 20, "atraso": float(np.median(g["y"]))} for g in grupos]
    res.update(status="CORTES", atraso=res["grupos"][0]["atraso"])
    return res


def detectar_rapido(ler_filme, ler_dub, dur_filme, dur_dub, max_offset=180.0, tolerancia_ms=80.0,
                    msg=None, prog=None, janela_filme=60.0, janela_ponto=40.0, folga_ponto=12.0, n_pontos=4):
    """
    Mede o atraso lendo POUCO do filme:
      1) 1 minuto do filme (perto de 2:00) contra a regiao da dublagem onde ele pode estar
         (atraso de ate +-3 min e todas as velocidades testadas) -> atraso e velocidade.
         Se nao achar, tenta em 30% e em 55% do filme.
      2) 4 pontos de 40 s espalhados pelo filme, cada um procurado onde a dublagem DEVE estar
         -> confirma, ou mostra deriva de velocidade ou cortes diferentes.
    Num filme de 1h25 le ~3,7 min do filme (o resto e da dublagem).
    ler_filme(t0, dur) / ler_dub(t0, dur) -> audio mono 8 kHz int16.
    Devolve (resultado, None) ou (None, motivo).
    """
    msg = msg or (lambda m: None)
    prog = prog or (lambda f: None)
    dur_filme, dur_dub = float(dur_filme or 0), float(dur_dub or 0)
    lido = {"filme": 0.0, "dub": 0.0}
    if dur_filme < 4 * janela_filme or dur_dub < 4 * janela_filme:
        return None, tr("arquivo curto demais para a análise rápida")

    def ler_f(t0, d):
        if t0 + d > dur_filme:
            return None
        lido["filme"] += d
        x = ler_filme(t0, d)
        if len(x) < 0.8 * d * SR_AUDIO:        # veio sem audio (faixa acaba antes? trecho vazio?)
            msg(tr("   (o trecho do filme em %s veio com só %.0f s de áudio; pulando)") % (mmss(t0), len(x) / SR_AUDIO))
            return None
        return _feat_pcm(x)

    def ler_d(t0, t1):
        t0, t1 = max(0.0, t0), min(dur_dub, t1)
        if t1 - t0 < 20:
            return None, t0
        lido["dub"] += t1 - t0
        x = ler_dub(t0, t1 - t0)
        if len(x) < 15 * SR_AUDIO:              # a faixa da dublagem pode terminar antes do arquivo
            msg(tr("   (a dublagem em %s veio com só %.0f s de áudio; pulando)") % (mmss(t0), len(x) / SR_AUDIO))
            return None, t0
        return _feat_pcm(x), t0

    # ---- 1) achar atraso e velocidade
    achado = None
    tentativas = [min(120.0, 0.1 * dur_filme), 0.30 * dur_filme, 0.55 * dur_filme]
    for i, tf in enumerate(tentativas):
        msg(tr("Análise rápida: procurando 1 minuto do filme (em %s) na dublagem...") % mmss(tf))
        fw = ler_f(tf, janela_filme)
        if fw is None:
            continue
        db, d0 = ler_d((tf - max_offset) / R_MAX - 5, (tf + janela_filme + max_offset) / R_MIN + 5)
        prog(0.1 * (i + 1))
        if db is None:
            continue
        tabela = []
        for r, desc in CANDIDATOS_VELOCIDADE:
            off, z = _casar(fw, tf, db, d0, r)
            if off is not None and abs(off) <= max_offset + 1:
                tabela.append({"r": r, "desc": desc, "offset": off, "z": z})
        if not tabela:
            continue
        melhor = max(tabela, key=lambda x: x["z"])
        igual = next((x for x in tabela if abs(x["r"] - 1.0) < 1e-9), None)
        esc = igual if igual and igual["z"] >= 0.75 * melhor["z"] else melhor
        if esc["z"] >= Z_ACHAR:
            msg(tr("   achou: atraso %s, velocidade x%.4f (pontuação %.0f)") % (fmt_ms(esc["offset"]), esc["r"], esc["z"]))
            achado = (tf, esc, tabela)
            break
        msg(tr("   não bateu ali (melhor pontuação %.0f)") % esc["z"])
    if achado is None:
        return None, tr("não encontrei o trecho do filme na dublagem (tentei em %s)") % ", ".join(mmss(t) for t in tentativas)
    tf, esc, tabela = achado
    r = esc["r"]
    janelas = [{"t": tf + janela_filme / 2, "offset": esc["offset"], "z": esc["z"]}]
    prog(0.35)

    # ---- 2) pontos de verificacao espalhados
    falhas = []
    # espalha os pontos pela parte do filme que TEM dublagem (uma dublagem de TV pode cobrir so uma parte)
    fim_cob = min(dur_filme, esc["offset"] + r * dur_dub)
    if fim_cob < dur_filme - 120:
        msg(tr("   (a faixa da dublagem só cobre o filme até %s; os pontos de verificação ficam até ali)") % mmss(fim_cob))
    pontos = [p for p in (fim_cob * f for f in np.linspace(0.2, 0.9, n_pontos))
              if abs(p - tf) > janela_filme + janela_ponto and p + janela_ponto + 15 < fim_cob
              and p + janela_ponto + 100 < dur_filme]
    for k, tk in enumerate(pontos):
        msg(tr("Ponto de verificação %d de %d (%s do filme)...") % (k + 1, len(pontos), mmss(tk)))
        achou = False
        for desloc in (0.0, 90.0):              # se o ponto nao bater, tenta 1,5 min depois
            t = tk + desloc
            fw = ler_f(t, janela_ponto)
            if fw is None:
                continue
            prev = janelas[-1]["offset"]       # usa o ultimo atraso confirmado (acompanha deriva e cortes)
            for folga in (folga_ponto, 60.0):
                td = (t - prev) / r
                db, d0 = ler_d(td - folga, td + janela_ponto / r + folga)
                if db is None:
                    continue
                off, z = _casar(fw, t, db, d0, r)
                if off is not None and z >= Z_MIN_JANELA:
                    janelas.append({"t": t + janela_ponto / 2, "offset": off, "z": z})
                    msg(tr("   ponto %d: atraso %s (pontuação %.0f)") % (k + 1, fmt_ms(off), z))
                    achou = True
                    break
            if achou:
                break
        if not achou:
            msg(tr("   ponto %d: não achei a dublagem perto de onde deveria estar") % (k + 1))
            falhas.append(tk)
        prog(0.35 + 0.65 * (k + 1) / max(1, len(pontos)))

    final = _interpretar_pontos(janelas, falhas, esc, tolerancia_ms / 1000.0)
    final.update(metodo="audio", modo="rapido", faixa_dub=0, escolhido=esc, tabela=tabela,
                 lido_filme_s=lido["filme"], lido_dub_s=lido["dub"])
    if final["status"] == "BAIXA_CONFIANCA":
        return None, tr("poucos trechos bateram (%d de %d)") % (final["n_boas"], final["n_total"])
    if final["status"] == "CORTES" or falhas or final["z_mediano"] < 10:
        final["confianca"] = "MEDIA"
    else:
        final["confianca"] = "ALTA"
    return final, None


# ----------------------------------------------------------------- relatorio
def fmt_ms(s):
    return "%+d ms" % int(round(s * 1000))


def mmss(s):
    s = max(0, int(s))
    return "%d:%02d" % (s // 60, s % 60)


def relatorio(res, out):
    p = lambda *a: print(*a, file=out)
    p("")
    p(tr("=== RESULTADO (método: %s, análise %s) ===") % (rot_metodo(res["metodo"]),
                                                        tr("rápida") if res.get("modo") == "rapido" else tr("completa")))
    if res.get("modo") == "rapido":
        p(tr("Leu só %s do filme e %s da dublagem (trechos espalhados).") %
          (mmss(res["lido_filme_s"]), mmss(res["lido_dub_s"])))
        if res.get("falhas"):
            p(tr("Obs.: não achei a dublagem perto de %s do filme (cena sem música/efeitos, ou diferente?).")
              % ", ".join(mmss(t) for t in res["falhas"]))
    p(tr("Trechos confiáveis: %d de %d  (pontuação mediana: %.1f)") %
      (res["n_boas"], res["n_total"], res["z_mediano"]))
    st = res["status"]
    atempo = 1.0 / (res["r"] * res["extra_r"])
    conf = rot_conf(res["confianca"])
    if st == "OK":
        p(tr("Velocidade: igual à do filme. Não precisa corrigir."))
        p(tr("ATRASO SUGERIDO: %s   (confiança %s)") % (fmt_ms(res["atraso"]), conf))
    elif st in ("VELOCIDADE", "DERIVA"):
        if st == "VELOCIDADE":
            p(tr("ATENÇÃO: %s.") % tr(res["escolhido"]["desc"]))
        else:
            p(tr("ATENÇÃO: o atraso vai mudando ao longo do filme (%.2f s por hora): "
                 "as duas versões têm velocidades um pouco diferentes.") % (3600 * (res["extra_r"] - 1)))
        p(tr("Só o atraso NÃO resolve. Antes, corrija a velocidade da dublagem (sem perder qualidade, em FLAC):"))
        p('   ffmpeg -i "%s" -map 0:a:%d -af atempo=%.6f -c:a flac "%s"'
          % (tr("DUBLAGEM"), res.get("faixa_dub", 0), atempo, tr("DUBLAGEM_corrigida.flac")))
        p(tr("Depois use o arquivo corrigido com o atraso: %s   (confiança %s)") % (fmt_ms(res["atraso"]), conf))
    elif st == "CORTES":
        p(tr("ATENÇÃO: o atraso muda de repente: as versões têm CORTES diferentes."))
        ref = tr("tempo do filme") if res.get("tempo_grupos") == "filme" else tr("tempo da dublagem")
        for g in res["grupos"]:
            p(tr("   por volta de %s até %s (%s): atraso %s") %
              (mmss(g["ini"]), mmss(g["fim"]), ref, fmt_ms(g["atraso"])))
        p(tr("Um único atraso não serve para o filme inteiro. A ferramenta ainda não junta os pedaços "
             "sozinha; por enquanto, o atraso do primeiro trecho é: %s") % fmt_ms(res["atraso"]))
    else:
        p(tr("Não encontrei uma correspondência confiável entre os dois arquivos."))
        p(tr("Melhor palpite (NÃO confie): %s") % fmt_ms(res["atraso"]))
    p("")


# ----------------------------------------------------------------- principal
def escolher_faixa_filme(info, pedido):
    if pedido != "auto":
        return int(pedido)
    for i, f in enumerate(info["audios"]):
        if idioma(f) == "eng":
            return i
    return 0


def main():
    if _definir_idioma:                   # idioma: --idioma pt|en, ou o do sistema
        pedido = None
        for i, a in enumerate(sys.argv):
            if a == "--idioma" and i + 1 < len(sys.argv):
                pedido = sys.argv[i + 1]
            elif a.startswith("--idioma="):
                pedido = a.split("=", 1)[1]
        _definir_idioma(pedido or _idioma_sistema())
    ap = argparse.ArgumentParser(description=tr("Descobre o atraso de uma dublagem em relação ao filme."))
    ap.add_argument("filme")
    ap.add_argument("dublagem")
    ap.add_argument("--metodo", choices=["auto", "audio", "video"], default="auto")
    ap.add_argument("--faixa-filme", default="auto",
                    help=tr("faixa de áudio do filme usada como referência (número, ou 'auto' = a em inglês)"))
    ap.add_argument("--faixa-dub", type=int, default=0, help=tr("faixa de áudio da dublagem (padrão 0)"))
    ap.add_argument("--max-offset", type=float, default=180.0, help=tr("maior atraso procurado, em segundos"))
    ap.add_argument("--janela", type=float, default=60.0, help=tr("tamanho dos trechos de verificação (s)"))
    ap.add_argument("--tolerancia", type=float, default=80.0, help=tr("diferença aceita entre trechos (ms)"))
    ap.add_argument("--completo", action="store_true",
                    help=tr("lê os arquivos inteiros (lento em UHD); o padrão é a análise rápida por trechos"))
    ap.add_argument("--simples", action="store_true",
                    help=tr("relatório vai para a tela de erro; só linhas CHAVE=valor no resultado"))
    ap.add_argument("--idioma", choices=["pt", "en"], help=tr("idioma das mensagens (padrão: o do sistema)"))
    args = ap.parse_args()

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    out = sys.stderr if args.simples else sys.stdout

    info_f, info_d = sondar(args.filme), sondar(args.dublagem)
    resultados = []

    if args.metodo in ("auto", "audio"):
        if not info_f["audios"] or len(info_d["audios"]) <= args.faixa_dub:
            print(tr("Aviso: falta faixa de áudio em um dos arquivos; pulando o método de áudio."), file=out)
        else:
            ff = escolher_faixa_filme(info_f, args.faixa_filme)
            cf = info_f["audios"][ff].get("codec_name", "")
            cd = info_d["audios"][args.faixa_dub].get("codec_name", "")
            res = None
            if not args.completo:
                res, motivo = detectar_rapido(
                    lambda t0, d: ler_pcm(args.filme, ff, t0, d, cf),
                    lambda t0, d: ler_pcm(args.dublagem, args.faixa_dub, t0, d, cd),
                    fim_faixa(info_f, ff), fim_faixa(info_d, args.faixa_dub), args.max_offset, args.tolerancia,
                    msg=lambda m: print(m, file=out))
                if res is None:
                    print(tr("A análise rápida não foi suficiente (%s).") % motivo, file=out)
            if res is None:
                print(tr("Lendo o áudio INTEIRO do filme (faixa %d) e da dublagem (faixa %d); "
                         "em UHD isso pode levar vários minutos...") % (ff, args.faixa_dub), file=out)
                a = caracteristicas_audio(carregar_audio(args.filme, ff, cf))
                b = caracteristicas_audio(carregar_audio(args.dublagem, args.faixa_dub, cd))
                print(tr("Comparando..."), file=out)
                res = analisar("audio", a, b, TAXA_AUDIO, args)
            res["faixa_dub"] = args.faixa_dub
            resultados.append(res)
            relatorio(resultados[-1], out)

    precisa_video = args.metodo == "video" or (
        args.metodo == "auto" and (not resultados or resultados[0]["confianca"] == "BAIXA"))
    if precisa_video:
        if info_f["tem_video"] and info_d["tem_video"]:
            if args.metodo == "auto":
                print(tr("O áudio não foi conclusivo; tentando pelos CORTES DE CENA do vídeo "
                         "(pode levar vários minutos)..."), file=out)
            else:
                print(tr("Lendo o vídeo dos dois arquivos (pode levar vários minutos)..."), file=out)
            a = caracteristicas_video(carregar_video(args.filme))
            b = caracteristicas_video(carregar_video(args.dublagem))
            print(tr("Comparando..."), file=out)
            resultados.append(analisar("video", a, b, TAXA_VIDEO, args))
            relatorio(resultados[-1], out)
        elif args.metodo == "video":
            raise SystemExit(tr("ERRO: os dois arquivos precisam ter vídeo para usar --metodo video."))
        else:
            print(tr("A dublagem não tem vídeo para comparar os cortes de cena."), file=out)

    if not resultados:
        raise SystemExit(tr("ERRO: não foi possível analisar com os arquivos fornecidos."))

    ordem = {"ALTA": 2, "MEDIA": 1, "BAIXA": 0}
    final = max(resultados, key=lambda r: (ordem[r["confianca"]], r["z_mediano"]))

    # linhas para o .bat (sempre em ASCII)
    if args.simples:
        print("METODO=%s" % final["metodo"])
        print("STATUS=%s" % final["status"])
        print("CONFIANCA=%s" % final["confianca"])
        print("ATEMPO=%.6f" % (1.0 / (final["r"] * final["extra_r"])))
        print("ATRASO_MS=%d" % int(round(final["atraso"] * 1000)))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(tr("ERRO: %s") % e, file=sys.stderr)
        sys.exit(1)
