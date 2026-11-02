# SPDX-License-Identifier: MIT
"""Testes da previa de audio: o que se ouve na previa tem de ser o que vai para o arquivo final."""
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import sinais
from sinais import SR

try:
    import EternalDub_core as core
    import EternalDub_audio as audio
    TEM_FFMPEG = shutil.which("ffmpeg") is not None
except Exception:                                   # pragma: no cover
    TEM_FFMPEG = False


def coletar(previa):
    blocos = []
    previa.executar(blocos.append)
    return np.concatenate(blocos) if blocos else np.zeros(0, np.float32)


@unittest.skipUnless(TEM_FFMPEG, "precisa do FFmpeg")
class TestPrevia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.mkdtemp(prefix="eternaldub_teste_")
        cls.ferr = core.achar_ferramentas()
        cls.dub_x = sinais.tons(60.0, semente=1)
        cls.dub = sinais.dublagem_flac(cls.pasta, "dub", cls.dub_x)
        cls.film_x = sinais.tons(60.0, base=500.0, passo=23.0, semente=2)
        cls.film = sinais.filme_com_video(cls.pasta, "filme", cls.film_x)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    # mapa regular (tempos da dublagem no tempo esticado; veja test_emendas): emenda em 20 s com 2,5 s de
    # silencio e emenda em 40 s em que saem 1,5 s da dublagem
    def dublagem(self, atempo=1.0, atraso_ms=0):
        ui = [[2.0, 20.0, 0.0], [22.5, 40.0, 18.0], [40.0, 58.0, 18.0 + 17.5 + 1.5]]
        trechos = [[fi, ff, round(u * atempo, 4)] for fi, ff, u in ui]
        return core.Dublagem(arquivo=self.dub, faixa=0, trechos=trechos, atempo=atempo, atraso_ms=atraso_ms)

    def final(self, d, nome):
        saida = os.path.join(self.pasta, nome + ".flac")
        core.montar_por_pedacos(d.arquivo, d.faixa, core.pedacos_efetivos(d), d.atempo, saida, self.ferr)
        return sinais.decodificar(saida)

    def comparar(self, d, janelas, ref, tolerancia=2e-4):
        """A previa de cada janela tem de ser igual ao pedaco correspondente do arquivo final."""
        for t0, t1 in janelas:
            x = coletar(audio.Previa(self.ferr, "dub", t0, t1, dub=d))
            a, b = int(round(t0 * SR)), int(round(t1 * SR))
            esperado = ref[a:b]
            n = min(len(x), len(esperado))
            self.assertGreater(n, 0, (t0, t1))
            borda = int(0.012 * SR)                    # o comeco/fim da janela ganham um cruzamento de 8 ms
            dif = np.abs(x[borda:n - borda] - esperado[borda:n - borda])
            self.assertLess(float(dif.max()), tolerancia, "janela %.1f-%.1f s: diferenca %.5f" % (t0, t1, dif.max()))

    JANELAS = [(0.0, 8.0), (5.3, 12.1), (19.0, 26.0), (38.0, 45.0), (30.0, 31.0), (57.0, 59.0)]

    def test_dub_igual_ao_arquivo_final(self):
        d = self.dublagem()
        self.comparar(d, self.JANELAS, self.final(d, "final1"))

    @staticmethod
    def atraso_entre(a, b, max_ms=40):
        """(atraso_em_ms, correlacao) de `a` em relacao a `b` (correlacao cruzada normalizada)."""
        n = min(len(a), len(b))
        a, b = a[:n].astype(np.float64), b[:n].astype(np.float64)
        norma = np.linalg.norm(a) * np.linalg.norm(b) + 1e-12
        melhor = (-2.0, 0)
        for k in range(-int(max_ms / 1000 * SR), int(max_ms / 1000 * SR) + 1, 2):
            c = (np.dot(a[k:], b[:n - k]) if k >= 0 else np.dot(a[:n + k], b[-k:])) / norma
            melhor = max(melhor, (c, k))
        return melhor[1] / SR * 1000, melhor[0]

    def test_dub_com_correcao_de_velocidade(self):
        """
        O filtro de velocidade (atempo) escolhe sozinho onde emendar os pedacinhos de som, entao ler a partir
        do meio nao reproduz a forma de onda amostra por amostra, mas o TEMPO tem de bater (menos de 2 ms).
        """
        d = self.dublagem(atempo=25 / 23.976)
        ref = self.final(d, "final2")
        for t0, t1 in self.JANELAS[:5]:
            x = coletar(audio.Previa(self.ferr, "dub", t0, t1, dub=d))
            esperado = ref[int(round(t0 * SR)):int(round(t1 * SR))]
            ms, corr = self.atraso_entre(x, esperado)
            self.assertLess(abs(ms), 2.0, "janela %.1f-%.1f s: atraso de %.2f ms" % (t0, t1, ms))
            self.assertGreater(corr, 0.9, "janela %.1f-%.1f s: correlacao %.3f" % (t0, t1, corr))

    def test_dub_com_ajuste_fino(self):
        d = self.dublagem(atraso_ms=-137)
        self.comparar(d, self.JANELAS, self.final(d, "final3"))

    def test_atraso_unico_positivo_e_negativo(self):
        for ms in (1500, -2250):
            d = core.Dublagem(arquivo=self.dub, faixa=0, atraso_ms=ms)
            ref = self.final(d, "unico%d" % ms)
            self.comparar(d, [(0.0, 6.0), (10.1, 14.3), (50.0, 56.0)], ref)

    def test_dub_alinha_com_o_tempo_do_filme(self):
        """Medida direta: um tom marcado na dublagem tem de aparecer no instante certo do filme."""
        d = self.dublagem()
        x = coletar(audio.Previa(self.ferr, "dub", 17.0, 27.0, dub=d))
        # dublagem em t_dub = 10 s toca no filme em 12 s (primeiro pedaco: atraso 2 s). Em 22,5 s (filme) volta
        # a tocar a dublagem a partir de t_dub = 18 s (apos o silencio de 2,5 s). Confere pelas frequencias.
        def freq(sinal, t0):
            seg = sinal[int(t0 * SR):int((t0 + 0.4) * SR)]
            espectro = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
            return np.fft.rfftfreq(len(seg), 1 / SR)[int(np.argmax(espectro))]
        # filme 19,0..19,4 s <- dublagem 17,0..17,4 s (bloco 34 -> 220+37*34 Hz)
        esperado_a = 220 + 37 * np.floor(17.1 / 0.5)
        self.assertAlmostEqual(freq(x, 19.1 - 17.0), esperado_a, delta=6)
        # filme 22,6..23,0 s <- dublagem 18,1 s (depois do silencio)
        esperado_b = 220 + 37 * np.floor(18.2 / 0.5)
        self.assertAlmostEqual(freq(x, 22.6 - 17.0), esperado_b, delta=6)
        # no silencio (20,5 s do filme) nao ha som
        self.assertLess(float(np.abs(x[int(3.6 * SR):int(5.3 * SR)]).max()), 1e-4)

    def test_filme(self):
        x = coletar(audio.Previa(self.ferr, "filme", 12.0, 18.0, filme=(self.film, 0, "flac")))
        esperado = self.film_x[int(12.0 * SR):int(18.0 * SR)]
        self.assertAlmostEqual(len(x), len(esperado), delta=2)
        n = min(len(x), len(esperado))
        self.assertLess(float(np.abs(x[:n] - esperado[:n]).max()), 6e-4)    # (16 bits do WAV de origem)

    def test_mix_e_a_media_dos_dois(self):
        d = self.dublagem()
        ref_dub = self.final(d, "final_mix")
        x = coletar(audio.Previa(self.ferr, "mix", 24.0, 30.0, filme=(self.film, 0, "flac"), dub=d))
        esperado = 0.5 * ref_dub[int(24 * SR):int(30 * SR)] + 0.5 * self.film_x[int(24 * SR):int(30 * SR)]
        n = min(len(x), len(esperado))
        borda = int(0.012 * SR)
        self.assertLess(float(np.abs(x[borda:n - borda] - esperado[borda:n - borda]).max()), 8e-4)

    def test_mix_depois_do_fim_da_dublagem_segue_so_o_filme(self):
        d = self.dublagem()
        x = coletar(audio.Previa(self.ferr, "mix", 56.0, 60.0, filme=(self.film, 0, "flac"), dub=d))
        self.assertAlmostEqual(len(x), 4 * SR, delta=2)
        resto = x[int(2.5 * SR):]                          # depois de 58,5 s so tem o filme (metade do volume)
        esperado = 0.5 * self.film_x[int(58.5 * SR):int(60 * SR)]
        n = min(len(resto), len(esperado))
        self.assertLess(float(np.abs(resto[:n] - esperado[:n]).max()), 6e-4)

    def test_cancelar(self):
        d = self.dublagem()
        cancelar = threading.Event()
        previa = audio.Previa(self.ferr, "dub", 0.0, 60.0, dub=d, cancelar=cancelar)
        blocos = []

        def saida(x):
            blocos.append(x)
            if len(blocos) == 3:
                cancelar.set()
        t0 = time.monotonic()
        with self.assertRaises(core.Cancelado):
            previa.executar(saida)
        self.assertLess(time.monotonic() - t0, 5.0)
        self.assertLess(len(blocos), 8)

    def test_arquivo_inexistente_da_erro_claro(self):
        d = core.Dublagem(arquivo=os.path.join(self.pasta, "nao_existe.mka"), faixa=0, atraso_ms=0)
        with self.assertRaises(RuntimeError):
            coletar(audio.Previa(self.ferr, "dub", 0.0, 5.0, dub=d))
        with self.assertRaises(RuntimeError):
            coletar(audio.Previa(self.ferr, "filme", 0.0, 5.0, filme=(os.path.join(self.pasta, "x.mkv"), 0, "")))


class TestPlano(unittest.TestCase):
    def test_recortar_plano(self):
        plano = [[100, 200, 0], [250, 400, 100], [400, 500, 260]]
        self.assertEqual(audio.recortar_plano(plano, 0, 50), ([], 0))
        P, base = audio.recortar_plano(plano, 150, 420)
        self.assertEqual(base, 50)                                   # a entrada comeca 50 amostras dentro do 1o pedaco
        self.assertEqual(P, [[0, 50, 0], [100, 250, 50], [250, 270, 210]])
        P, base = audio.recortar_plano(plano, 120, 130)
        self.assertEqual((P, base), ([[0, 10, 0]], 20))

    def test_pcm16(self):
        b = audio.para_pcm16_estereo(np.array([0.0, 1.0, -1.0, 2.0], np.float32))
        a = np.frombuffer(b, dtype="<i2")
        self.assertEqual(a.tolist(), [0, 0, 32767, 32767, -32767, -32767, 32767, 32767])


if __name__ == "__main__":
    unittest.main(verbosity=2)
