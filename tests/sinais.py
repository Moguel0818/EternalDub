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
