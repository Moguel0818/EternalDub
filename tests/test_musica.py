# SPDX-License-Identifier: MIT
"""
Videoclipes (1.4): a musica em alta qualidade (FLAC, MP3) no lugar do som ruim do clipe.

Tudo com sinais sinteticos (nada de arquivos de midia no repositorio): uma "musica" (sinais.musica) e o "som de
clipe" dela (sinais.som_de_clipe: mono, sem agudos, comprimido, com chiado e wow de fita, atrasado, um pouco mais
lento, com fade-in e fade-out). Confere a medicao (atraso e velocidade com ~1 ms), as pontas (fades e cortes), a
montagem (ordem das faixas, sincronia amostra a amostra, volume nas pontas, fim junto com o video), a previa igual
ao arquivo, a correcao de velocidade "como fita", as capas embutidas, a janela e o corte exato de atraso negativo.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import sinais

import EternalDub_musica as em
import detectar_atraso as da

try:
    import EternalDub_core as core
    import EternalDub_audio as audio
    TEM_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
except Exception:                                   # pragma: no cover
    TEM_FFMPEG = False

try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    TEM_QT = True
except Exception:                                   # pragma: no cover
    TEM_QT = False

SR_M = 44100            # taxa da "musica"
SR_C = 48000            # taxa do "clipe"


def rodar(*cmd):
    subprocess.run(list(cmd), check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)


def sondar(arq):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=index,codec_type,codec_name,sample_rate,channels,start_time:stream_tags=title,language"
                        ":stream_disposition=default", "-of", "json", arq],
                       stdout=subprocess.PIPE, check=True, stdin=subprocess.DEVNULL)
    return json.loads(p.stdout.decode("utf-8"))["streams"]


def decodificar(arq, pos, sr=SR_M):
    return sinais.decodificar(arq, pos, sr)


def deslocamento_ms(saida, ref, t, atraso, atempo, v0=0.0, dur=0.5, raio_ms=4.0, sr=SR_M):
    """
    Onde, na faixa `saida` (mono, sr), esta o trecho da musica `ref` que deveria tocar em t (tempo do video):
    tempo_musica = (t - atraso) * atempo. Devolve (erro em ms, correlacao). v0 = inicio do video no arquivo.
    """
    n = int(dur * sr)
    i = int(round((t + v0) * sr))
    x = saida[i:i + n].astype(np.float64)
    tt = t + np.arange(n) / sr
    melhor = None
    for k in range(-int(raio_ms / 1000 * sr), int(raio_ms / 1000 * sr) + 1):
        esp = np.interp(((tt + k / sr) - atraso) * atempo * sr, np.arange(len(ref)), ref)
        c = float(np.dot(x, esp) / (np.linalg.norm(x) * np.linalg.norm(esp) + 1e-12))
        if melhor is None or c > melhor[0]:
            melhor = (c, k)
    return melhor[1] / sr * 1000.0, melhor[0]


def ganho(saida, ref, t, atraso, atempo, v0=0.0, dur=0.25, sr=SR_M):
    """Volume da `saida` em t relativo a musica original que deveria tocar ali (1 = sem mudanca)."""
    n = int(dur * sr)
    i = int(round((t + v0) * sr))
    x = saida[i:i + n]
    u = ((t + np.arange(n) / sr) - atraso) * atempo * sr
    esp = np.interp(u, np.arange(len(ref)), ref, left=0.0, right=0.0)
    re = float(np.sqrt(np.mean(esp ** 2)))
    return float(np.sqrt(np.mean(x ** 2))) / re if re > 1e-6 else float("nan")


# ============================================================ medicao (so numpy)
class TestMedicao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mus = sinais.musica(60.0)
        cls.mus8 = sinais.para_8k(cls.mus, SR_M)

    def clipe8(self, inicio=3.0, dur=66.0, **kw):
        return sinais.som_de_clipe(self.mus, SR_M, inicio, dur, sr=8000, **kw)

    def test_atraso_e_velocidade(self):
        for vel, ini in ((1.0, 3.0), (0.999, 3.0), (1.001, -2.5), (25 / 24, 2.0), (1 / 1.005, 1.0)):
            with self.subTest(velocidade=vel, inicio=ini):
                y = self.clipe8(ini, 66.0, velocidade=vel, fade_in=(max(ini, 0), 1.0), fade_out=(ini + 52, 4.0),
                                falas=max(0.0, ini - 0.5))
                res = da.analisar_musica(y, self.mus8)
                self.assertIn(res["status"], ("OK", "VELOCIDADE", "DERIVA"))
                self.assertLess(abs(res["atraso"] - ini), 0.003, res["atraso"])
                self.assertLess(abs(res["r"] * res["extra_r"] * vel - 1.0), 5e-5)       # 5e-5 em 60 s = 3 ms
                self.assertNotEqual(res["confianca"], "BAIXA")

    def test_musica_sem_relacao_nao_bate(self):
        outra = sinais.musica(60.0, bpm=97.0, semente=21)
        y = sinais.som_de_clipe(outra, SR_M, 3.0, 66.0, sr=8000)
        res = da.analisar_musica(y, self.mus8)
        self.assertEqual(res["confianca"], "BAIXA")

    def test_edicao_diferente_vira_cortes(self):
        ed = np.concatenate([self.mus[:int(25 * SR_M)], self.mus[int(33 * SR_M):]])     # o clipe nao tem 25-33 s
        y = sinais.som_de_clipe(ed, SR_M, 3.0, 58.0, sr=8000)
        res = da.analisar_musica(y, self.mus8)
        self.assertEqual(res["status"], "CORTES")

    def test_pontas(self):
        # (opcoes do clipe, fade-in esperado, fade-out esperado); tolerancias: o comeco de um fade longo pode variar
        # ~1,5 s (as duas masterizacoes nunca tem a mesma dinamica), o fim fica a menos de 1 s, um corte a 30 ms
        casos = [(dict(fade_out=(50.0, 6.0)), None, (50.0, 56.0)),
                 (dict(fade_in=(10.0, 3.0)), (10.0, 13.0), None),
                 (dict(corte=48.0), None, (48.0, 48.0)),
                 (dict(fade_in=(3.0, 1.0), fade_out=(52.0, 4.0)), (3.0, 4.0), (52.0, 56.0)),
                 (dict(), None, None)]
        for kw, esp_in, esp_out in casos:
            with self.subTest(**{k: str(v) for k, v in kw.items()}):
                y = self.clipe8(3.0, 66.0, falas=2.5, **kw)
                p = em.medir_pontas(y, self.mus8, [[3.0, 1e7, 0.0]], 1.0, fim_s=66.0)
                self.assertTrue(p["ok"], p)
                for medido, esperado in ((p["entrada"], esp_in), (p["saida"], esp_out)):
                    if esperado is None:
                        self.assertIsNone(medido)
                        continue
                    self.assertIsNotNone(medido)
                    if esperado[0] == esperado[1]:                       # corte seco: rampa curta no ponto do corte
                        self.assertLess(abs(0.5 * (medido[0] + medido[1]) - esperado[0]), 0.015, medido)
                        self.assertLess(medido[1] - medido[0], 0.05, medido)
                    else:
                        self.assertLess(abs(medido[0] - esperado[0]), 1.6, medido)
                        self.assertLess(abs(medido[1] - esperado[1]), 1.0, medido)
                        self.assertIn(medido[2], em.FORMAS)

    def test_locutor_por_cima_do_fade(self):
        y = self.clipe8(3.0, 66.0, fade_out=(48.0, 6.0))
        rs = np.random.RandomState(9)
        for t0 in np.arange(46.0, 58.0, 0.55):                   # "falas" por cima do fim (a vinheta da TV)
            i0, m = int(t0 * 8000), int(0.35 * 8000)
            r = rs.randn(m)
            fr = np.fft.rfftfreq(m, 1 / 8000)
            r = np.fft.irfft(np.fft.rfft(r) * np.exp(-((fr - 700) / 400) ** 2), m)
            y[i0:i0 + m] += 0.3 * r / np.abs(r).max() * np.hanning(m)
        p = em.medir_pontas(y, self.mus8, [[3.0, 1e7, 0.0]], 1.0, fim_s=66.0)
        self.assertIsNotNone(p["saida"])
        self.assertLess(abs(p["saida"][1] - 54.0), 1.0, p["saida"])

    def test_sincronia_errada_nao_inventa_fade(self):
        y = self.clipe8(3.0, 66.0, fade_out=(50.0, 6.0))
        p = em.medir_pontas(y, self.mus8, [[7.0, 1e7, 0.0]], 1.0, fim_s=66.0)      # 4 s fora do lugar
        self.assertFalse(p["ok"])
        self.assertIsNone(p["saida"])

    def test_curva_de_ganho(self):
        t = np.array([0.0, 1.0, 1.5, 2.0, 3.0, 9.0, 10.0, 10.5, 11.0, 12.0])
        g = em.ganho_fades(t, [1.0, 2.0, "lin"], [10.0, 11.0, "lin"])
        np.testing.assert_allclose(g, [0, 0, 0.5, 1, 1, 1, 1, 0.5, 0, 0], atol=1e-9)
        for forma in em.FORMAS:
            tt = np.linspace(9.0, 12.0, 301)
            g = em.ganho_fades(tt, None, [10.0, 11.0, forma])
            self.assertTrue(np.all(np.diff(g) <= 1e-12), forma)                     # so desce
            self.assertAlmostEqual(float(g[0]), 1.0)
            self.assertEqual(float(g[-1]), 0.0)
        c = em.CurvaGanho([1.0, 2.0, "cos"], None, 100, inicio=50)                   # pos 0 = amostra 50 (0,5 s)
        self.assertIsNone(c(200, 100))                                              # 2,5 s a 3,5 s: volume normal
        np.testing.assert_allclose(c(0, 300), em.ganho_fades((50 + np.arange(300)) / 100.0, [1.0, 2.0, "cos"]),
                                   atol=1e-6)
        self.assertFalse(em.CurvaGanho(None, None, 100))

    def test_reconhecer_musica(self):
        def arquivo(nome, tags=None, capa=False, idioma="", video=False):
            faixas = [core.Faixa(idx=0, tipo="audio", codec="flac", idioma=idioma)]
            if capa or video:
                faixas.append(core.Faixa(idx=1, tipo="video", codec="mjpeg" if capa else "h264",
                                         disposicao={"attached_pic": 1 if capa else 0}))
            return core.Arquivo(caminho=nome, faixas=faixas, duracao=200.0, tags=tags or {})
        clipe = core.Arquivo(caminho="clipe.mkv", duracao=230.0)
        filme = core.Arquivo(caminho="filme.mkv", duracao=7200.0)
        self.assertTrue(em.parece_musica(arquivo("x.flac", {"artist": "Banda"}), filme))
        self.assertTrue(em.parece_musica(arquivo("01 - Faixa.flac", capa=True), clipe))
        self.assertFalse(em.parece_musica(arquivo("dub.flac", idioma="por"), clipe))
        self.assertFalse(em.parece_musica(arquivo("dub.flac"), filme))
        self.assertFalse(em.parece_musica(arquivo("x.mkv", {"artist": "Banda"}, video=True), clipe))
        self.assertEqual(em.nome_da_musica(arquivo("x.flac", {"artist": "Banda", "title": "Canção"})), "Banda - Canção")
        self.assertEqual(em.nome_da_musica(arquivo("/m/03 - Minha Canção.flac")), "Minha Canção")
        self.assertAlmostEqual(em.cents(2 ** (1 / 12)), 100.0, places=6)


# ============================================================ arquivos de verdade (FFmpeg)
@unittest.skipUnless(TEM_FFMPEG, "precisa do FFmpeg")
class TestMontagemMusica(unittest.TestCase):
    INICIO, VELOCIDADE, DUR_CLIPE = 2.5, 0.999, 46.0

    @classmethod
    def setUpClass(cls):
        cls.pasta = p = tempfile.mkdtemp(prefix="eternaldub_musica_")
        cls.ferr = core.achar_ferramentas()
        cls.mus = sinais.musica(40.0)
        wav = os.path.join(p, "musica.wav")
        sinais.gravar_wav_estereo(wav, cls.mus, SR_M)
        capa = os.path.join(p, "capa.jpg")
        rodar("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", capa)
        cls.flac = os.path.join(p, "musica.flac")              # FLAC de CD: tags e capa embutida
        rodar("ffmpeg", "-v", "error", "-y", "-i", wav, "-i", capa, "-map", "0", "-map", "1", "-c:a", "flac",
              "-c:v", "copy", "-disposition:v", "attached_pic", "-metadata", "ARTIST=Banda Teste",
              "-metadata", "TITLE=Canção Teste", cls.flac)
        cls.mp3 = os.path.join(p, "musica.mp3")
        rodar("ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a", "libmp3lame", "-b:a", "320k", cls.mp3) \
            if b"libmp3lame" in subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], stdout=subprocess.PIPE,
                                               stdin=subprocess.DEVNULL).stdout else None
        cls.ref = decodificar(cls.flac, 0)                      # a musica como o FFmpeg a entrega (mono, 44,1 kHz)
        # o clipe: video + o som "de fita" em AAC num MP4 (como uma captura de VHS), mais uma versao com capa
        y = sinais.som_de_clipe(cls.mus, SR_M, cls.INICIO, cls.DUR_CLIPE, sr=SR_C, velocidade=cls.VELOCIDADE,
                                fade_in=(cls.INICIO, 1.0), fade_out=(38.0, 4.0), falas=2.0)
        wav_c = os.path.join(p, "clipe.wav")
        sinais.gravar_wav(wav_c, y, SR_C)
        cls.clipe = os.path.join(p, "clipe.mp4")
        rodar("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
              "color=c=black:s=64x48:r=30000/1001:d=%.3f" % cls.DUR_CLIPE, "-i", wav_c, "-c:v", "mpeg4", "-q:v", "10",
              "-c:a", "aac", "-b:a", "128k", "-shortest", cls.clipe)
        cls.clipe_capa = os.path.join(p, "clipe_capa.mp4")
        rodar("ffmpeg", "-v", "error", "-y", "-i", cls.clipe, "-i", capa, "-map", "0", "-map", "1", "-c", "copy",
              "-c:v:1", "mjpeg", "-disposition:v:1", "attached_pic", cls.clipe_capa)
        # um clipe "limpo", mais longo que a musica, sem fades: a musica cabe inteira (copia exata)
        y2 = sinais.som_de_clipe(cls.mus, SR_M, 2.0, cls.DUR_CLIPE, sr=SR_C)
        sinais.gravar_wav(wav_c, y2, SR_C)
        cls.clipe_longo = os.path.join(p, "clipe_longo.mkv")
        rodar("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x48:r=25:d=%.3f" % cls.DUR_CLIPE,
              "-i", wav_c, "-c:v", "mpeg4", "-q:v", "10", "-c:a", "flac", "-shortest", cls.clipe_longo)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def musica(self, arquivo=None, **kw):
        base = dict(arquivo=arquivo or self.flac, faixa=0, nome="Banda Teste - Canção Teste", idioma="und",
                    tipo="musica", modo_velocidade="fita")
        base.update(kw)
        return core.Dublagem(**base)

    @staticmethod
    def inicio_video(arq):
        return float(next(s for s in sondar(arq) if s["codec_type"] == "video").get("start_time") or 0.0)

    def test_fluxo_completo(self):
        film = core.sondar_arquivo(self.clipe)
        r = core.detectar(self.clipe, 0, self.flac, 0, musica=True)
        self.assertEqual(r["status"], "DERIVA")
        self.assertLess(abs(r["atraso_ms"] - 1000 * self.INICIO), 3)
        self.assertLess(abs(r["atempo"] - self.VELOCIDADE), 5e-5)
        d = self.musica(atraso_ms=r["atraso_ms"], atempo=r["atempo"])
        self.assertTrue(core.pontas_desatualizadas(d))
        core.aplicar_pontas(d, core.medir_pontas(film, 0, d))
        self.assertFalse(core.pontas_desatualizadas(d))
        self.assertIsNotNone(d.fade_entrada)
        self.assertIsNotNone(d.fade_saida)
        self.assertLess(abs(d.fade_saida[1] - 42.0), 1.0, d.fade_saida)
        org = core.organizar_padrao(film, [d], [])
        self.assertEqual(core.itens_saida(film, [d], [], org)["audio"], [("dub", d), ("filme", 1)])
        saida = os.path.join(self.pasta, "final.mkv")
        core.montar(film, [d], saida, False, self.ferr, lambda m: None, lambda v: None, org=org)
        st = sondar(saida)
        self.assertEqual([s["codec_type"] for s in st], ["video", "audio", "audio"])
        self.assertEqual((st[1]["codec_name"], st[1]["sample_rate"], st[1]["channels"]), ("flac", "44100", 2))
        self.assertEqual(st[1]["tags"].get("title"), "Banda Teste - Canção Teste")
        self.assertEqual([s["disposition"]["default"] for s in st[1:]], [1, 0])
        # sincronia amostra a amostra em relacao ao VIDEO (o FFmpeg pode deslocar o arquivo todo por causa do AAC)
        v0 = self.inicio_video(saida)
        x = decodificar(saida, 0)
        atraso, atempo = d.atraso_ms / 1000.0, d.atempo
        for t in (8.0, 20.0, 33.0):
            ms, c = deslocamento_ms(x, self.ref, t, atraso, atempo, v0)
            self.assertLess(abs(ms), 1.0, "t=%.0f: %.3f ms" % (t, ms))
            self.assertGreater(c, 0.9)
        # volume: normal no meio, descendo no fade-out do clipe, nada depois
        self.assertAlmostEqual(ganho(x, self.ref, 20.0, atraso, atempo, v0), 1.0, delta=0.05)
        self.assertLess(ganho(x, self.ref, 40.5, atraso, atempo, v0), 0.75)
        self.assertLess(float(np.sqrt(np.mean(x[int((42.5 + v0) * SR_M):] ** 2))), 1e-3)
        # nada depois do fim do video
        self.assertLessEqual(len(x) / SR_M, core.fim_do_video(film) + v0 + 0.05)

    def test_copia_exata_quando_cabe(self):
        film = core.sondar_arquivo(self.clipe_longo)
        r = core.detectar(self.clipe_longo, 0, self.flac, 0, musica=True)
        self.assertEqual(r["status"], "OK")
        self.assertLess(abs(r["atraso_ms"] - 2000), 3)
        d = self.musica(atraso_ms=r["atraso_ms"], seguir_pontas=False)
        self.assertFalse(core.vai_virar_flac(d, film))           # cabe no video e nao tem fades: copia exata
        saida = os.path.join(self.pasta, "copia.mkv")
        core.montar(film, [d], saida, False, self.ferr, lambda m: None, lambda v: None,
                    org=core.organizar_padrao(film, [d], []))
        h_orig = core._hashes(self.flac, ["0:a:0"], self.ferr)
        h_saida = core._hashes(saida, ["0:a:0"], self.ferr)
        self.assertEqual(h_orig, h_saida)                        # o FLAC entrou identico (sem recodificar)
        x = decodificar(saida, 0)
        ms, c = deslocamento_ms(x, self.ref, 15.0, d.atraso_ms / 1000.0, 1.0, self.inicio_video(saida))
        self.assertLess(abs(ms), 0.5)

    def test_mp3(self):
        if not os.path.isfile(self.mp3):
            self.skipTest("FFmpeg sem libmp3lame")
        film = core.sondar_arquivo(self.clipe_longo)
        r = core.detectar(self.clipe_longo, 0, self.mp3, 0, musica=True)
        self.assertLess(abs(r["atraso_ms"] - 2000), 3)
        for pontas in (False, True):                 # copia do MP3 e montagem em FLAC: as duas no lugar certo
            with self.subTest(pontas=pontas):
                d = self.musica(self.mp3, atraso_ms=r["atraso_ms"], seguir_pontas=pontas,
                                fade_saida=[30.0, 33.0, "lin"] if pontas else None)
                saida = os.path.join(self.pasta, "mp3_%d.mkv" % pontas)
                core.montar(film, [d], saida, False, self.ferr, lambda m: None, lambda v: None,
                            org=core.organizar_padrao(film, [d], []))
                self.assertEqual(sondar(saida)[1]["codec_name"], "flac" if pontas else "mp3")
                x = decodificar(saida, 0)
                ms, c = deslocamento_ms(x, decodificar(self.mp3, 0), 15.0, d.atraso_ms / 1000.0, 1.0,
                                        self.inicio_video(saida))
                self.assertLess(abs(ms), 1.0, ms)

    def test_previa_igual_ao_arquivo(self):
        film = core.sondar_arquivo(self.clipe)
        d = self.musica(atraso_ms=2500, atempo=self.VELOCIDADE, fade_entrada=[2.5, 3.5, "lin"],
                        fade_saida=[38.0, 42.0, "cos"])
        lim = core.limite_da_faixa(d, film)
        final = os.path.join(self.pasta, "previa_ref.flac")
        core.montar_por_pedacos(d.arquivo, d.faixa, core.pedacos_efetivos(d), d.atempo, final, self.ferr,
                                limite_s=lim, modo_velocidade="fita", fades=d.fades(), dur_s=core.duracao_da_faixa(d))
        ref = sinais.decodificar(final)                                     # 48 kHz mono, como a previa
        for t0, t1 in ((1.5, 5.0), (20.0, 23.0), (37.0, 44.0)):
            blocos = []
            audio.Previa(self.ferr, "dub", t0, t1, dub=d, limite_s=lim).executar(blocos.append)
            x = np.concatenate(blocos)
            esperado = ref[int(round(t0 * SR_C)):int(round(t1 * SR_C))]
            n = min(len(x), len(esperado))
            borda = int(0.02 * SR_C)
            a, b = x[borda:n - borda].astype(np.float64), esperado[borda:n - borda].astype(np.float64)
            if np.sqrt(np.mean(b ** 2)) < 1e-4:                              # (o fim: silencio dos dois lados)
                self.assertLess(float(np.sqrt(np.mean(a ** 2))), 1e-3)
                continue
            # depois de pular para o meio (-ss) o reamostrador comeca em outra fase: a forma de onda difere em fracoes de
            # amostra (agudos), mas o TEMPO e o volume tem de bater
            K = int(0.002 * SR_C)
            cs = [float(np.dot(a[K + k:len(a) - K + k], b[K:len(b) - K]) /
                        (np.linalg.norm(a[K + k:len(a) - K + k]) * np.linalg.norm(b[K:len(b) - K]))) for k in range(-K, K + 1)]
            k = int(np.argmax(cs)) - K
            self.assertEqual(k, 0, "janela %.1f-%.1f: deslocada %d amostras" % (t0, t1, k))
            self.assertGreater(cs[K], 0.99, "janela %.1f-%.1f: correlacao %.5f" % (t0, t1, cs[K]))
            self.assertAlmostEqual(float(np.linalg.norm(a) / np.linalg.norm(b)), 1.0, delta=0.01)

    def test_velocidade_como_fita_e_exata(self):
        sr = SR_C
        x = np.zeros(int(30 * sr), np.float32)
        for tc in (2.0, 10.0, 25.0):                               # cliques marcados
            x[int(tc * sr)] = 0.9
        src = sinais.dublagem_flac(self.pasta, "cliques", x)
        for atempo in (0.999, 1.0015, 24 / 25):
            saida = os.path.join(self.pasta, "fita.flac")
            core.montar_por_pedacos(src, 0, [[0.0, 1e7, 0.0]], atempo, saida, self.ferr, modo_velocidade="fita",
                                    dur_s=30.0)
            y = sinais.decodificar(saida)
            for tc in (2.0, 10.0, 25.0):
                esp = tc / atempo
                i0 = int((esp - 0.02) * sr)
                pos = (i0 + int(np.argmax(np.abs(y[i0:i0 + int(0.04 * sr)])))) / sr
                self.assertLess(abs(pos - esp) * 1000, 0.1, "atempo %.4f, clique de %.0f s" % (atempo, tc))

    def test_capas_embutidas(self):
        mus = core.sondar_arquivo(self.flac)
        self.assertEqual(len(mus.videos), 1)
        self.assertEqual(mus.imagens, [])                         # a capa do FLAC nao e video
        self.assertFalse(em.tem_video(mus))
        film = core.sondar_arquivo(self.clipe_capa)
        capa = next(f for f in film.videos if f.capa())
        self.assertNotIn(capa.idx, core.faixas_padrao(film))
        org = core.organizar_padrao(film, [], [])
        self.assertNotIn(capa.idx, org.manter)
        self.assertAlmostEqual(core.fim_do_video(film), self.DUR_CLIPE, delta=0.1)
        saida = os.path.join(self.pasta, "sem_capa.mkv")
        core.montar(film, [], saida, False, self.ferr, lambda m: None, lambda v: None, org=org)
        self.assertEqual([s["codec_type"] for s in sondar(saida)], ["video", "audio"])

    def test_atraso_negativo_por_copia_e_exato(self):
        """
        Correcao da 1.4: o corte por copia so acontece entre quadros de audio, e a 1.3 jogava fora o resto (a dublagem
        ficava adiantada ate 1 quadro: ~84 ms num FLAC, 20 ms num AC3).
        """
        sr = SR_C
        dub_x = sinais.tons(30.0, semente=1)
        filme = core.sondar_arquivo(sinais.filme_com_video(self.pasta, "filme_neg", sinais.tons(30.0, base=500.0,
                                                                                               semente=2)))
        wav = os.path.join(self.pasta, "dub_neg.wav")
        sinais.gravar_wav(wav, dub_x)
        for codec, opcoes in (("flac", ["-c:a", "flac"]), ("ac3", ["-c:a", "ac3", "-b:a", "448k"])):
            src = os.path.join(self.pasta, "dub_neg_%s.mka" % codec)
            sinais.codificar(wav, src, *opcoes)
            xs = sinais.decodificar(src)
            for ms in (-300, -1234):
                with self.subTest(codec=codec, atraso=ms):
                    saida = os.path.join(self.pasta, "neg_%s_%d.mkv" % (codec, -ms))
                    core.montar(filme, [core.Dublagem(arquivo=src, faixa=0, atraso_ms=ms)], saida, False, self.ferr,
                                lambda m: None, lambda v: None)
                    y = sinais.decodificar(saida, 1)
                    v0 = self.inicio_video(saida)
                    n, K = int(1.0 * sr), int(0.12 * sr)
                    x = xs[int(10.0 * sr):int(10.0 * sr) + n].astype(np.float64)
                    i = int(round((10.0 + ms / 1000.0 + v0) * sr))
                    seg = y[i - K:i + n + K].astype(np.float64)
                    c = np.correlate(seg, x, "valid") / (np.sqrt(np.convolve(seg ** 2, np.ones(n), "valid")) *
                                                         np.linalg.norm(x) + 1e-12)
                    erro = (int(np.argmax(c)) - K) / sr * 1000.0
                    self.assertLess(abs(erro), 0.5, "%s %+d ms: erro de %.2f ms" % (codec, ms, erro))


# ============================================================ janela
@unittest.skipUnless(TEM_QT and TEM_FFMPEG, "precisa do PySide6 e do FFmpeg")
class TestJanelaMusica(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import EternalDub_gui as gui
        import EternalDub_i18n as i18n
        cls.gui = gui
        cls.app = QApplication.instance() or QApplication([])
        i18n.definir("pt")
        cls.pasta = p = tempfile.mkdtemp(prefix="eternaldub_janela_musica_")
        QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, os.path.join(p, "config"))
        mus = sinais.musica(30.0)
        wav = os.path.join(p, "m.wav")
        sinais.gravar_wav_estereo(wav, mus, SR_M)
        cls.flac = os.path.join(p, "musica.flac")
        rodar("ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a", "flac", "-metadata", "ARTIST=Banda Teste",
              "-metadata", "TITLE=Canção Teste", cls.flac)
        y = sinais.som_de_clipe(mus, SR_M, 1.5, 34.0, sr=SR_C, fade_out=(27.0, 3.0))
        wav_c = os.path.join(p, "c.wav")
        sinais.gravar_wav(wav_c, y, SR_C)
        cls.clipe = os.path.join(p, "Banda - Canção (VHS).mkv")
        rodar("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x48:r=25:d=34", "-i", wav_c,
              "-c:v", "mpeg4", "-q:v", "10", "-c:a", "flac", "-shortest", cls.clipe)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def setUp(self):
        self.avisos, self.erros = [], []
        self._info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: self.avisos.append(a[2] if len(a) > 2 else ""))
        self.j = self.gui.Janela()
        self.j.erro = lambda titulo, detalhe: self.erros.append((titulo, detalhe))
        self.j._perguntar_velocidade = lambda r, mus: "fita"
        self.j.show()
        self.j._carregar_filme(self.clipe)

    def tearDown(self):
        QMessageBox.information = self._info
        self.j.player.parar(silencioso=True)
        self.j.close()
        self.j.carregador.encerrar()

    def esperar(self, cond, limite=120.0):
        fim = time.monotonic() + limite
        while time.monotonic() < fim:
            QApplication.processEvents()
            if cond():
                return True
            time.sleep(0.02)
        return False

    def test_videoclipe_de_ponta_a_ponta(self):
        j = self.j
        j._adicionar_arquivos([self.flac])                    # (como ao arrastar: descobre que e musica pelas tags)
        self.assertEqual(len(j.dubs), 1)
        d = j.dubs[0]
        self.assertTrue(d.eh_musica())
        self.assertEqual(d.nome, "Banda Teste - Canção Teste")
        self.assertEqual(d.modo_velocidade, "fita")
        self.assertEqual(j.editor.title(), "Música selecionada")
        self.assertEqual(j.cmb_tipo.currentData(), "musica")
        self.assertFalse(j.caixa_pontas.isHidden())
        self.assertEqual(j.b_padrao_saida.text(), "Aplicar o padrão de videoclipe")
        audio_saida = [k for k in core.itens_saida(j.film, j.dubs, j.legendas, j._organizacao())["audio"]]
        self.assertEqual(audio_saida, [("dub", d), ("filme", 1)])                    # a musica primeiro, padrao
        self.assertEqual(j._efetivo()[1], ("dub", d))
        j.acao_detectar()
        self.assertTrue(self.esperar(lambda: not j._ocupado() and d.pontas_sinc), "a deteccao nao terminou")
        self.assertEqual(self.erros, [])
        self.assertLess(abs(d.atraso_ms - 1500), 3)
        self.assertIsNotNone(d.fade_saida)                    # as pontas foram medidas sozinhas
        self.assertIn("fim:", j.lbl_pontas.text())
        sugestao = []
        saida = os.path.join(self.pasta, "final.mkv")
        original = QFileDialog.getSaveFileName
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (sugestao.append(a[2]), (saida, ""))[1])
        try:
            j.acao_gerar(False)
        finally:
            QFileDialog.getSaveFileName = original
        self.assertTrue(sugestao[0].endswith("Banda - Canção (VHS)_musica.mkv"), sugestao)
        self.assertTrue(self.esperar(lambda: not j._ocupado(), 120), "a geracao nao terminou")
        self.assertEqual(self.erros, [])
        st = sondar(saida)
        aud = [s for s in st if s["codec_type"] == "audio"]
        self.assertEqual([(s["codec_name"], s["disposition"]["default"]) for s in aud], [("flac", 1), ("flac", 0)])
        self.assertEqual(aud[0]["tags"].get("title"), "Banda Teste - Canção Teste")
        self.assertTrue(any("sincronizada" in a for a in self.avisos), self.avisos)  # conferencia automatica
        # trocar o tipo para dublagem volta ao padrao BDRemux
        j.cmb_tipo.setCurrentIndex(j.cmb_tipo.findData("dublagem"))
        self.assertFalse(d.eh_musica())
        self.assertEqual(j.editor.title(), "Dublagem selecionada")
        self.assertTrue(j.caixa_pontas.isHidden())

    def test_projeto_guarda_a_musica(self):
        j = self.j
        j._adicionar_arquivos([self.flac], como_musica=True)
        d = j.dubs[0]
        d.atraso_ms, d.fade_saida = 1500, [27.0, 30.0, "lin"]
        d.pontas_sinc = core.assinatura_sinc(d)
        caminho = os.path.join(self.pasta, "clipe.eternaldub")
        core.salvar_projeto(caminho, j.film.caminho, 0, j.dubs, j._manter_param(), j.legendas, j._organizacao())
        p = core.abrir_projeto(caminho)
        d2 = p["dublagens"][0]
        self.assertTrue(d2.eh_musica())
        self.assertEqual((d2.fade_saida, d2.modo_velocidade, d2.pontas_sinc),
                         ([27.0, 30.0, "lin"], "fita", core.assinatura_sinc(d)))
        self.assertFalse(core.pontas_desatualizadas(d2))
        self.assertEqual(p["padrao_audio"], None)
        self.assertEqual(json.load(open(caminho, encoding="utf-8"))["versao"], core.PROJETO_VERSAO)


if __name__ == "__main__":
    unittest.main(verbosity=2)
