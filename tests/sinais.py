# SPDX-License-Identifier: MIT
"""Sinais sinteticos para os testes (nada de arquivos de midia no repositorio)."""
import os
import subprocess
import wave

import numpy as np

SR = 48000


def tons(dur, sr=SR, base=220.0, passo=37.0, bloco=0.5, ruido=0.004, semente=1):
    """
    Um tom diferente a cada `bloco` s (frequencia = base + passo * numero_do_bloco): qualquer deslocamento ou
    corte errado, por menor que seja, muda a forma de onda. Devolve float32 mono.
    """
    t = np.arange(int(round(dur * sr))) / sr
    f = base + passo * np.floor(t / bloco)
    fase = 2 * np.pi * np.cumsum(f) / sr
    x = 0.5 * np.sin(fase) * (0.6 + 0.4 * np.sin(2 * np.pi * 3.1 * t))
    return (x + np.random.RandomState(semente).randn(len(t)) * ruido).astype(np.float32)


def gravar_wav(caminho, x, sr=SR):
    with wave.open(caminho, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def codificar(entrada, saida, *opcoes):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", entrada, *opcoes, saida], check=True,
                   stdin=subprocess.DEVNULL)


def dublagem_flac(pasta, nome, x, sr=SR):
    wav = os.path.join(pasta, nome + ".wav")
    gravar_wav(wav, x, sr)
    saida = os.path.join(pasta, nome + ".mka")
    codificar(wav, saida, "-c:a", "flac")
    return saida


def filme_com_video(pasta, nome, x, sr=SR):
    """MKV com um video minusculo e o audio x (o audio dentro de um arquivo com video, como num remux)."""
    wav = os.path.join(pasta, nome + ".wav")
    gravar_wav(wav, x, sr)
    saida = os.path.join(pasta, nome + ".mkv")
    dur = len(x) / sr
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x48:r=24:d=%.3f" % dur,
                    "-i", wav, "-c:v", "mpeg4", "-q:v", "8", "-c:a", "flac", "-shortest", saida], check=True,
                   stdin=subprocess.DEVNULL)
    return saida


def decodificar(caminho, pos=0, sr=SR):
    """Audio inteiro da faixa `pos`, mono float32 em `sr` (o que o FFmpeg entrega, sem nenhum corte)."""
    p = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", caminho, "-map", "0:a:%d" % pos,
                        "-af", "aresample=async=1:first_pts=0", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                       stdout=subprocess.PIPE, check=True, stdin=subprocess.DEVNULL)
    return np.frombuffer(p.stdout, dtype="<f4")


# ---------------------------------------------------------------- videoclipes (1.4)
def musica(dur, sr=44100, bpm=112.0, semente=7):
    """
    Uma "musica" sintetica (bumbo, caixa, chimbal, baixo, acordes e melodia), estereo float32. Repete compassos e
    acordes como uma musica de verdade, o que torna a medicao trecho a trecho mais dificil (picos vizinhos altos).
    """
    rs = np.random.RandomState(semente)
    n = int(round(dur * sr))
    x = np.zeros(n, np.float64)
    batida = 60.0 / bpm
    prog = [0, 5, 7, 3, 0, 8, 10, 7]

    def nota(f, t0, d, forma, amp, ataque, soltura):
        i0, i1 = int(t0 * sr), min(n, int((t0 + d + soltura) * sr))
        if i0 >= n or i1 <= i0:
            return
        tt = np.arange(i1 - i0) / sr
        env = np.minimum(1.0, tt / ataque) * np.where(tt < d, 1.0, np.exp(-(tt - d) / max(soltura / 4, 1e-3)))
        if forma == "saw":
            y = sum(np.sin(2 * np.pi * f * k * tt) / k for k in range(1, 8))
        else:
            y = np.sin(2 * np.pi * f * tt + 1.5 * np.sin(2 * np.pi * 2 * f * tt) + 0.8 * np.sin(2 * np.pi * 5.5 * tt))
        x[i0:i1] += amp * env * y

    k, tb = 0, 0.0
    while tb < dur:
        grau = prog[(k // 8) % len(prog)]
        f0 = 110.0 * 2 ** (grau / 12)
        secao = int(tb // 16) % 4
        b = k % 4
        i0 = int(tb * sr)
        if b in (0, 2):                                    # bumbo
            m = min(n - i0, int(0.25 * sr))
            tt = np.arange(m) / sr
            x[i0:i0 + m] += 0.6 * np.sin(2 * np.pi * (50 + 80 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 12)
        else:                                              # caixa
            m = min(n - i0, int(0.2 * sr))
            x[i0:i0 + m] += 0.3 * rs.randn(m) * np.exp(-np.arange(m) / sr * 18)
        for h in range(2):                                 # chimbal
            j0 = int((tb + h * batida / 2) * sr)
            m = max(0, min(n - j0, int(0.05 * sr)))
            if m:
                ru = np.diff(np.concatenate([[0], rs.randn(m)]))
                x[j0:j0 + m] += 0.08 * ru * np.exp(-np.arange(m) / sr * 80)
        nota(f0 / 2, tb, batida * 0.8, "saw", 0.12, 0.005, 0.05)                    # baixo
        if b == 0:                                                                  # acorde
            for semi in (0, 4 if grau not in (3, 8) else 3, 7):
                nota(f0 * 2 * 2 ** (semi / 12), tb, 4 * batida * 0.95, "saw", 0.035, 0.05, 0.3)
        if secao in (1, 2) and rs.rand() < 0.8:                                     # melodia
            escala = [0, 2, 3, 5, 7, 8, 10, 12]
            fm = 440.0 * 2 ** ((grau + escala[rs.randint(len(escala))]) / 12)
            nota(fm, tb + (batida / 2 if rs.rand() < 0.3 else 0), batida * (0.9 if rs.rand() < 0.7 else 1.8),
                 "fm", 0.07, 0.02, 0.1)
        k += 1
        tb += batida
    x = np.tanh(1.2 * x) * 0.7
    d = int(0.0007 * sr)
    return np.stack([x, np.concatenate([np.zeros(d), x[:-d]]) * 0.95], axis=1).astype(np.float32)


def som_de_clipe(mus, sr_mus, inicio, dur, sr=48000, velocidade=1.0, fade_in=None, fade_out=None, corte=None,
                 falas=0.0, ruido_db=-45.0, wow_ms=0.3, semente=3):
    """
    O som de um videoclipe gravado de fita: a musica `mus` comeca em `inicio` s do clipe (negativo = o clipe comeca no
    meio dela), tocada `velocidade` vezes mais rapido (o tom muda junto, como numa fita), em mono, sem agudos,
    comprimida, com chiado e wow; fade_in/fade_out = (t0, duracao) no tempo do clipe; corte = a musica some de uma vez;
    falas = segundos de "falas" (rajadas de ruido) antes da musica.   tempo_clipe = inicio + tempo_musica / velocidade
    """
    rs = np.random.RandomState(semente)
    n = int(round(dur * sr))
    tc = np.arange(n) / sr
    wow = wow_ms / 1000.0 * (np.sin(2 * np.pi * 0.7 * tc) + 0.3 * np.sin(2 * np.pi * 6.1 * tc))
    pos = (tc - inicio + wow) * velocidade * sr_mus
    mono = mus.mean(axis=1).astype(np.float64)
    ok = (pos >= 0) & (pos < len(mono) - 1)
    y = np.zeros(n)
    y[ok] = np.interp(pos[ok], np.arange(len(mono)), mono)
    f = np.fft.rfftfreq(n, 1 / sr)
    y = np.fft.irfft(np.fft.rfft(y) / np.sqrt(1 + (f / 8000.0) ** 6) * (f / 90.0) ** 2 / (1 + (f / 90.0) ** 2), n)
    y = np.tanh(1.6 * y) / 1.6 * 1.1
    g = np.ones(n)
    if fade_in:
        g *= np.clip((tc - fade_in[0]) / fade_in[1], 0, 1)
    if fade_out:
        g *= np.clip(1 - (tc - fade_out[0]) / fade_out[1], 0, 1)
    if corte is not None:
        g[tc >= corte] = 0.0
    y *= g
    for t0 in np.arange(0.3, falas - 0.4, 0.55):
        i0, m = int(t0 * sr), int(0.35 * sr)
        r = rs.randn(m)
        fr = np.fft.rfftfreq(m, 1 / sr)
        r = np.fft.irfft(np.fft.rfft(r) * np.exp(-((fr - 700) / 400) ** 2), m)
        y[i0:i0 + m] += 0.25 * r / (np.abs(r).max() + 1e-9) * np.hanning(m)
    y += 10 ** (ruido_db / 20) * rs.randn(n)
    return y.astype(np.float32)


def gravar_wav_estereo(caminho, x, sr):
    with wave.open(caminho, "wb") as w:
        w.setnchannels(x.shape[1] if x.ndim > 1 else 1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def para_8k(x, sr):
    """Mono 8 kHz float32 (como o audio leve de analise), por interpolacao (so para os testes de medicao)."""
    mono = x.mean(axis=1) if x.ndim > 1 else x
    n = int(len(mono) / sr * 8000)
    return np.interp(np.arange(n) / 8000.0 * sr, np.arange(len(mono)), mono).astype(np.float32)
