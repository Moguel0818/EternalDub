# SPDX-License-Identifier: MIT
# EternalDub - Copyright (C) 2026 Moguel0818 e colaboradores / and contributors
# -*- coding: utf-8 -*-
"""
EternalDub_musica.py - VIDEOCLIPES: a musica em alta qualidade (FLAC, MP3...) no lugar do som ruim do clipe.

Nada aqui depende da interface grafica nem do FFmpeg (so de numpy):
  * reconhecer um arquivo de musica e sugerir o nome da faixa (tags ARTIST e TITLE);
  * PONTAS: medir como o clipe faz a musica aparecer e sumir (fade-in, fade-out ou corte seco) e descrever isso
    como uma curva de volume, que a montagem (EternalDub_core.MontadorPedacos) aplica a musica. Assim a musica em
    alta qualidade comeca e termina como no clipe, em vez de tocar inteira por cima da vinheta da TV ou depois de o
    clipe ja ter feito o fade.

Como as pontas sao medidas: o clipe e a musica sao a MESMA gravacao. Em cada quadro de 100 ms, o ganho coerente
<clipe, musica> / <musica, musica> (na banda de 80 a 1000 Hz, com uma busca de +-2 ms para acompanhar o wow da fita)
diz quanto da musica esta no clipe naquele momento. Falas, aplausos e o chiado da fita quase nao entram nessa conta
(nao se parecem com a musica), entao um locutor falando por cima do fim nao atrapalha. Dividindo pelo ganho tipico
(a mediana da musica inteira), o fade aparece como uma curva que vai de 1 a 0. Uma curva lisa (linear, cosseno ou
exponencial) e ajustada a ela: duas masterizacoes nunca tem exatamente a mesma dinamica, e a curva ajustada ignora
essas pequenas variacoes. Um corte seco (o clipe corta a musica de uma vez) e localizado com quadros de 20 ms.

O meio da musica nunca e mexido: so o comeco e o fim seguem o clipe.
"""
import os
import re

import numpy as np

VERSAO_MUSICA = "1.4"

EXT_MUSICA = (".flac", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".aif", ".aiff", ".wv", ".ape",
              ".wma", ".alac", ".dsf", ".dff", ".tta", ".mpc")
DUR_MAX_CLIPE = 15 * 60.0          # um video mais longo que isto nao e tratado sozinho como videoclipe
TAGS_DE_MUSICA = ("artist", "album", "album_artist", "albumartist")

FORMAS = ("lin", "cos", "exp")     # linear, cosseno (suave nas pontas) e exponencial (reta em dB, ate -60 dB)
NOMES_FORMAS = {"lin": "linear", "cos": "cosseno", "exp": "exponencial"}

SR_ANALISE = 8000                  # o audio leve de analise do EternalDub (mono, 8 kHz)
CHEIO = 0.6                        # a musica esta "inteira" no clipe (relativo ao ganho tipico)
SUMIU = 0.06                       # ... e "sumiu" (-24 dB): fim do fade-out / comeco do fade-in
CORTE_MAX = 0.5                    # s: fade mais curto que isto e conferido com quadros de 20 ms (corte seco?)
BORDA_S = 90.0                     # s analisados com resolucao fina no comeco e no fim da musica dentro do clipe


# ----------------------------------------------------------------- arquivos de musica
def tem_video(arq):
    """O arquivo tem imagem de verdade? (capa de disco embutida, 'attached_pic', nao conta)"""
    return any(f.tipo == "video" and not f.disposicao.get("attached_pic") for f in arq.faixas)


def parece_musica(arq, filme=None):
    """
    Um arquivo adicionado parece ser a MUSICA de um videoclipe (e nao uma dublagem)? So audio (a capa nao conta) e:
    tags de musica (ARTIST, ALBUM), ou extensao de musica sem idioma marcado na faixa com um video curto (clipe).
    """
    if tem_video(arq) or not arq.audios:
        return False
    tags = getattr(arq, "tags", None) or {}
    if any(tags.get(k) for k in TAGS_DE_MUSICA):
        return True
    curto = filme is None or not filme.duracao or filme.duracao <= DUR_MAX_CLIPE
    sem_idioma = all((f.idioma or "und") in ("und", "zxx", "mul") for f in arq.audios)
    return curto and sem_idioma and os.path.splitext(arq.caminho)[1].lower() in EXT_MUSICA


def nome_da_musica(arq, padrao="Música"):
    """'Artista - Título' pelas tags; senao o nome do arquivo sem o numero da faixa ('01 - Musica.flac' -> 'Musica')."""
    tags = getattr(arq, "tags", None) or {}
    artista = (tags.get("artist") or tags.get("album_artist") or tags.get("albumartist") or "").strip()
    titulo = (tags.get("title") or "").strip()
    if artista and titulo:
        return "%s - %s" % (artista, titulo)
    if titulo:
        return titulo
    base = os.path.splitext(os.path.basename(arq.caminho))[0]
    base = re.sub(r"^\s*\d{1,3}\s*[-._)]+\s*", "", base).strip()
    return base or padrao


def cents(atempo):
    """Quanto o tom muda (cents; 100 = um semitom) ao mudar a velocidade como numa fita (tempo_esticado = t / atempo)."""
    return 1200.0 * float(np.log2(float(atempo or 1.0)))


# ----------------------------------------------------------------- curva de volume (fade-in e fade-out)
def _forma(nome, s):
    """Ganho de um fade-out na fracao s (0 = comeco do fade, 1 = fim): 1 -> 0."""
    s = np.clip(s, 0.0, 1.0)
    if nome == "cos":
        return 0.5 * (1.0 + np.cos(np.pi * s))
    if nome == "exp":
        return np.where(s >= 1.0, 0.0, 10.0 ** (-3.0 * s))          # reta em dB ate -60 dB, depois silencio
    return 1.0 - s


def ganho_fades(t, entrada=None, saida=None):
    """
    Ganho (0 a 1) da musica em cada tempo t (s, linha do tempo do filme/clipe).
      entrada: [t0, t1, forma]  silencio ate t0, sobe ate o volume normal em t1 (fade-in);
      saida:   [t0, t1, forma]  volume normal ate t0, desce ate o silencio em t1 (fade-out), silencio depois.
    """
    t = np.asarray(t, dtype=np.float64)
    g = np.ones(t.shape, np.float64)
    if entrada:
        t0, t1, f = float(entrada[0]), float(entrada[1]), entrada[2]
        g = g * _forma(f, 1.0 - (t - t0) / max(t1 - t0, 1e-6))
    if saida:
        t0, t1, f = float(saida[0]), float(saida[1]), saida[2]
        g = g * _forma(f, (t - t0) / max(t1 - t0, 1e-6))
    return g


class CurvaGanho:
    """
    Aplica ganho_fades() a blocos de amostras na linha do tempo do filme. Usada pela montagem do FLAC e pela previa
    (o mesmo ganho nas duas). __call__(pos, n) -> ganhos float32 (n,) ou None quando o bloco inteiro fica no volume
    normal (nada a fazer). `inicio`: amostra do filme que corresponde a pos = 0 (a previa comeca no meio).
    """

    def __init__(self, entrada, saida, sr, inicio=0):
        self.entrada = list(entrada) if entrada else None
        self.saida = list(saida) if saida else None
        self.sr = float(sr)
        self.inicio = int(inicio)
        self._livre0 = float(self.entrada[1]) if self.entrada else -np.inf
        self._livre1 = float(self.saida[0]) if self.saida else np.inf

    def __bool__(self):
        return bool(self.entrada or self.saida)

    def __call__(self, pos, n):
        if n <= 0 or not self:
            return None
        a = (self.inicio + pos) / self.sr
        b = (self.inicio + pos + n - 1) / self.sr
        if a >= self._livre0 and b <= self._livre1:
            return None
        t = (self.inicio + pos + np.arange(n, dtype=np.float64)) / self.sr
        return ganho_fades(t, self.entrada, self.saida).astype(np.float32)


def descrever_fade(f, fmt):
    """'0:06.0 a 0:07.5 (linear)' (fmt formata segundos)."""
    if not f:
        return ""
    return "%s - %s (%s)" % (fmt(f[0]), fmt(f[1]), NOMES_FORMAS.get(f[2], f[2]))


# ----------------------------------------------------------------- medir as pontas no clipe
def _banda(x, sr, f0=80.0, f1=1000.0):
    """
    Passa-faixa de fase zero (~80 a 1000 Hz) com bordas suaves (gaussianas). Um corte "de tijolo" na frequencia faria
    ecos antes de cada batida (o som de uma batida apareceria dezenas de ms antes dela) e um corte seco do clipe
    pareceria um fade curto.
    """
    n = len(x)
    if n == 0:
        return np.zeros(0, np.float32)
    X = np.fft.rfft(np.asarray(x, dtype=np.float64), n)
    f = np.fft.rfftfreq(n, 1.0 / sr)
    X *= (1.0 - np.exp(-(f / f0) ** 2)) * np.exp(-(f / f1) ** 2)
    return np.fft.irfft(X, n).astype(np.float32)


def musica_na_linha_do_clipe(mus, pedacos, atempo, n, sr=SR_ANALISE):
    """
    A musica (tempo original) posta na linha do tempo do clipe pelos pedacos [[ini_filme, fim_filme, ini_dub], ...]
    (ini_dub no tempo original; tempo_dub = ini_dub + (t - ini_filme) * atempo). Devolve (audio, onde_ha_musica).
    """
    t = np.arange(n, dtype=np.float64) / sr
    u = np.full(n, np.nan)
    for fi, ff, di in pedacos:
        dentro = (t >= fi) & (t < ff)
        u[dentro] = di + (t[dentro] - fi) * float(atempo or 1.0)
    pos = u * sr
    ok = np.isfinite(pos) & (pos >= 0) & (pos < len(mus) - 1)
    y = np.zeros(n, np.float32)
    if ok.any():
        y[ok] = np.interp(pos[ok], np.arange(len(mus)), mus)
    return y, ok


def _ganhos(ref, m, ok_m, inis, L, K):
    """Ganho coerente, energia da musica e correlacao normalizada em cada quadro [i0, i0+L) (busca de +-K amostras)."""
    g = np.full(len(inis), np.nan)
    e = np.zeros(len(inis))
    c = np.zeros(len(inis))
    for j, i0 in enumerate(inis):
        if i0 - K < 0 or i0 + L + K > len(m) or i0 + L > len(ref) or not ok_m[i0:i0 + L].all():
            continue
        r = ref[i0:i0 + L].astype(np.float64)
        M = np.lib.stride_tricks.sliding_window_view(m[i0 - K:i0 + L + K].astype(np.float64), L)
        dots = M @ r
        nm = np.einsum("ij,ij->i", M, M) + 1e-12
        ncc = dots / np.sqrt(nm * (float(r @ r) + 1e-12))
        k = int(np.argmax(ncc))
        g[j], e[j], c[j] = dots[k] / nm[k], nm[k] / L, ncc[k]
    return g, e, c


def _mediana_movel(x, k):
    if len(x) == 0:
        return x
    pad = np.concatenate([np.full(k, np.nan), x, np.full(k, np.nan)])
    jan = np.lib.stride_tricks.sliding_window_view(pad, 2 * k + 1)
    out = np.full(len(x), np.nan)
    ok = np.isfinite(jan).any(axis=1)
    if ok.any():
        out[ok] = np.nanmedian(jan[ok], axis=1)
    return out


def _ajustar_saida(tt, rel, v):
    """
    Fade-out que melhor explica rel (ja normalizado) nos tempos tt (v = quadros validos). Devolve (t0, t1, forma, erro)
    ou None (a musica nao some no clipe).
    """
    cheios = np.where(v & (rel >= CHEIO))[0]
    if not len(cheios):
        return None
    ult = cheios[-1]
    depois = np.where(v[ult:] & (rel[ult:] <= SUMIU))[0]
    if len(depois):
        t_some = tt[ult + depois[0]]
    else:                                          # a musica (ou o clipe) acaba no meio do fade
        resto = np.where(v[ult + 1:])[0]
        if not len(resto) or rel[ult + 1 + resto[-1]] > 0.35:
            return None
        t_some = tt[ult + 1 + resto[-1]]
    perto = (tt >= t_some - 45.0) & (tt <= t_some + 5.0)      # so a regiao do fade entra no ajuste (mais rapido)
    tt, rel, v = tt[perto], rel[perto], v[perto]
    melhor = None
    duracoes = np.concatenate([np.arange(0.05, 1.0, 0.05), np.arange(1.0, 30.01, 0.25)])
    for t1 in np.arange(t_some - 1.0, t_some + 3.01, 0.05):
        for dur in duracoes:
            t0 = t1 - dur
            # o volume de referencia e o de LOGO antes do fade (2,5 s): numa transmissao de TV o compressor faz o
            # volume do clipe mudar de uma parte da musica para outra, e uma janela longa confundiria isso com o fade
            jan = v & (tt >= t0 - 1.5) & (tt <= min(t1 + 1.0, t_some + 1.0))
            if jan.sum() < 6:
                continue
            antes = v & (tt >= t0 - 2.5) & (tt < t0 - 0.05)
            nivel = float(np.median(rel[antes])) if antes.sum() >= 5 else 1.0
            nivel = min(max(nivel, 0.5), 2.0)
            s = (tt[jan] - t0) / dur
            y = rel[jan] / nivel
            for nome in FORMAS:
                err = float(np.mean((y - _forma(nome, s)) ** 2))
                if melhor is None or err < melhor[3]:
                    melhor = (float(t0), float(t1), nome, err)
    return melhor


def _refinar_curto(refb, m, ok, sr, g0, t0, t1, saida):
    """
    Fade curto ou corte seco: mede de novo com quadros de 20 ms (passo de 5 ms) e ajusta uma rampa (linear) por minimos
    quadrados, com passos de 5 ms. Um corte seco vira uma rampa de ~20 ms centrada no ponto do corte (o quadro que
    cruza o corte tem so parte da musica). None se nao der para medir.
    """
    L, H, K = int(0.02 * sr), int(0.005 * sr), max(1, int(0.001 * sr))
    i_a, i_b = int((t0 - 0.4) * sr), int((t1 + 0.4) * sr)
    inis = np.arange(max(K, i_a), max(K, i_b), H)
    g, e, _ = _ganhos(refb, m, ok, inis, L, K)
    tt = (inis + L / 2.0) / sr
    v = np.isfinite(g)
    if v.sum() < 8:
        return None
    rel = np.where(v, g / g0, np.nan)
    if not saida:                                  # fade-in: o mesmo, com o tempo ao contrario
        tt, rel, v = -tt[::-1], rel[::-1], v[::-1]
    tt, rel = tt[v], rel[v]
    meio = len(tt) // 3                            # o volume "inteiro" e o do comeco da janela (antes do fade)
    nivel = min(max(float(np.median(rel[:max(1, meio)])), 0.5), 2.0)
    y = rel / nivel
    melhor = None
    for b in np.arange(tt[0] + 0.05, tt[-1] - 0.02, 0.005):
        for dur in (0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.17, 0.25, 0.35, 0.5, 0.65):
            err = float(np.mean((y - _forma("lin", (tt - (b - dur)) / dur)) ** 2))
            if melhor is None or err < melhor[0]:
                melhor = (err, b - dur, b)
    if melhor is None:
        return None
    f = [melhor[1], melhor[2]]
    if not saida:
        f = [-f[1], -f[0]]
    return [round(float(f[0]), 4), round(float(f[1]), 4), "lin"]


def medir_pontas(ref, mus, pedacos, atempo=1.0, sr=SR_ANALISE, fim_s=None, cancelar=None):
    """
    Mede o fade-in e o fade-out (ou cortes secos) que o CLIPE faz na musica.
      ref:     audio do clipe (mono, sr; int16 ou float), linha do tempo do clipe a partir de 0;
      mus:     audio da musica (mono, sr), tempo original;
      pedacos: como a musica entra no clipe (EternalDub_core.pedacos_efetivos), atempo: velocidade;
      fim_s:   fim do video (a musica nunca passa dali).
    Devolve dict: entrada ([t0, t1, forma] ou None), saida (idem), ok (deu para medir), motivo (se nao deu),
    ncc (semelhanca tipica clipe x musica, 0 a 1), ganho (volume tipico do clipe em relacao a musica).
    """
    ref = np.asarray(ref)
    mus = np.asarray(mus)
    if ref.dtype.kind in "iu":
        ref = ref.astype(np.float32) / 32768.0
    if mus.dtype.kind in "iu":
        mus = mus.astype(np.float32) / 32768.0
    n = len(ref)
    if fim_s:
        n = min(n, int(fim_s * sr))
    vazio = {"entrada": None, "saida": None, "ok": False, "motivo": "", "ncc": 0.0, "ganho": 0.0}
    if n < 2 * sr or len(mus) < 2 * sr:
        vazio["motivo"] = "curto"
        return vazio
    refb = _banda(ref[:n], sr)
    m, ok = musica_na_linha_do_clipe(_banda(mus, sr), pedacos, atempo, n, sr)
    if ok.sum() < 2 * sr:
        vazio["motivo"] = "sem_musica"
        return vazio
    L, H, K = int(0.1 * sr), int(0.05 * sr), max(1, int(0.002 * sr))
    onde = np.where(ok)[0]
    a_ini, a_fim = int(onde[0]), int(onde[-1])
    # quadros finos (50 ms) nas bordas, um por segundo no meio (so para o volume tipico)
    finos = np.concatenate([np.arange(a_ini, min(a_fim, a_ini + int(BORDA_S * sr)), H),
                            np.arange(max(a_ini, a_fim - int(BORDA_S * sr)), a_fim, H)])
    meio = np.arange(a_ini, a_fim, sr)
    inis = np.unique(np.concatenate([finos, meio]))
    if cancelar is not None and cancelar.is_set():
        return vazio
    g, e, c = _ganhos(refb, m, ok, inis, L, K)
    tt = (inis + L / 2.0) / sr
    com_som = np.isfinite(g) & (e > 0)
    if com_som.sum() < 10:
        vazio["motivo"] = "sem_musica"
        return vazio
    v = com_som & (e > 1e-3 * np.median(e[com_som]))           # quadros em que a musica tem som (-30 dB)
    if v.sum() < 10:
        vazio["motivo"] = "sem_musica"
        return vazio
    forte = v & (e >= np.median(e[v]))
    g0 = float(np.median(g[forte]))
    ncc = float(np.median(c[forte]))
    vazio.update(ncc=ncc, ganho=g0)
    if g0 <= 0 or ncc < 0.3:
        vazio["motivo"] = "nao_bate"                            # sincronia errada, ou a musica nao e a do clipe
        return vazio
    rel = np.where(v, g / g0, np.nan)
    corpo = v & (tt > tt[0] + 20.0) & (tt < tt[-1] - 20.0)
    if corpo.sum() >= 10 and np.mean((rel[corpo] >= 0.4) & (rel[corpo] <= 2.5)) < 0.6:
        vazio["motivo"] = "nao_bate"
        return vazio
    # so os quadros finos (passo de 50 ms) entram no ajuste das curvas
    fino = np.isin(inis, finos)
    tt_f, rel_f, v_f = tt[fino], _mediana_movel(np.where(v[fino], rel[fino], np.nan), 2), v[fino]
    saida = _ajustar_saida(tt_f, rel_f, v_f & np.isfinite(rel_f))
    r_in = _ajustar_saida(-tt_f[::-1], rel_f[::-1], (v_f & np.isfinite(rel_f))[::-1])
    entrada = (-r_in[1], -r_in[0], r_in[2], r_in[3]) if r_in else None
    resultado = {"entrada": None, "saida": None, "ok": True, "motivo": "", "ncc": ncc, "ganho": g0}
    if saida:
        f = [round(saida[0], 3), round(saida[1], 3), saida[2]]
        if f[1] - f[0] < CORTE_MAX:
            f = _refinar_curto(refb, m, ok, sr, g0, f[0], f[1], True) or f
        resultado["saida"] = f
    if entrada:
        f = [round(entrada[0], 3), round(entrada[1], 3), entrada[2]]
        if f[1] - f[0] < CORTE_MAX:
            f = _refinar_curto(refb, m, ok, sr, g0, f[0], f[1], False) or f
        if f[0] <= a_ini / sr + 0.02 and f[1] - f[0] <= 0.03:
            f = None                                            # so o comeco da propria musica: nada a fazer
        resultado["entrada"] = f
    if resultado["entrada"] and resultado["saida"] and resultado["entrada"][1] > resultado["saida"][0]:
        resultado["entrada"] = None                             # nao se cruzam: fica so o fade-out (o mais comum)
    return resultado
