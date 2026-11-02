# SPDX-License-Identifier: MIT
"""
Aba 'Arquivo final' da janela (sem tela: QT_QPA_PLATFORM=offscreen): padrao BDRemux PT-BR ao abrir o filme,
Marcar/Desmarcar tudo, Subir/Descer, faixa padrao, legendas externas, projeto e a geracao de verdade (com e sem
dublagem), conferida com o ffprobe.
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

try:
    from PySide6.QtCore import QMimeData, QSettings, Qt, QUrl
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    TEM_QT = True
except Exception:                                   # pragma: no cover
    TEM_QT = False

if TEM_QT:
    import EternalDub_gui as gui
    import EternalDub_i18n as i18n
    import sinais
    core = gui.core
    J = gui.Janela


def esperar(cond, limite=60.0):
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def srt(linhas):
    def t(s):
        ms = int(round(s * 1000))
        return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)
    return "".join("%d\n%s --> %s\n%s\n\n" % (i, t(a), t(b), txt) for i, (a, b, txt) in enumerate(linhas, 1))


def sondar(arq):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=index,codec_type:stream_tags=language,title:stream_disposition=default,forced",
                        "-of", "json", arq], stdout=subprocess.PIPE, check=True, stdin=subprocess.DEVNULL)
    return json.loads(p.stdout.decode("utf-8"))["streams"]


@unittest.skipUnless(TEM_QT and shutil.which("ffmpeg"), "precisa do PySide6 e do FFmpeg")
class TestArquivoFinal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        i18n.definir("pt")
        cls.pasta = p = tempfile.mkdtemp(prefix="eternaldub_saida_")
        QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, os.path.join(p, "config"))
        for nome, base, semente in (("eng", 300.0, 3), ("por", 700.0, 4), ("com", 900.0, 6)):
            sinais.gravar_wav(os.path.join(p, nome + ".wav"), sinais.tons(20.0, base=base, semente=semente))
        for nome, linhas in (("s_eng", [(1, 2, "Hello")]), ("s_for", [(5, 6, "PLACA")]),
                             ("s_por", [(1, 2, "Olá"), (8, 9, "Até já")])):
            with open(os.path.join(p, nome + ".srt"), "w", encoding="utf-8") as f:
                f.write(srt(linhas))
        # um remux tipico: video, ingles (padrao), portugues, comentario; legendas: ingles, PT forcada, PT completa
        cls.filme = os.path.join(p, "filme.mkv")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x48:r=24:d=20"] +
                       sum((["-i", os.path.join(p, n)] for n in ("eng.wav", "por.wav", "com.wav", "s_eng.srt",
                                                                  "s_for.srt", "s_por.srt")), []) +
                       sum((["-map", str(i)] for i in range(7)), []) +
                       ["-c:v", "mpeg4", "-c:a", "flac", "-c:s", "srt",
                        "-metadata:s:a:0", "language=eng", "-metadata:s:a:0", "title=Original",
                        "-metadata:s:a:1", "language=por",
                        "-metadata:s:a:2", "language=eng", "-metadata:s:a:2", "title=Commentary",
                        "-metadata:s:s:0", "language=eng", "-metadata:s:s:1", "language=por",
                        "-metadata:s:s:1", "title=Forçada", "-metadata:s:s:2", "language=por",
                        "-disposition:a:0", "default", "-disposition:a:2", "comment",
                        "-disposition:s:0", "default", "-disposition:s:1", "forced", cls.filme],
                       check=True, stdin=subprocess.DEVNULL)
        cls.dub = sinais.dublagem_flac(p, "dub", sinais.tons(20.0, base=500.0, semente=5))
        cls.dub2 = sinais.dublagem_flac(p, "dub2", sinais.tons(20.0, base=550.0, semente=7))
        cls.externa = os.path.join(p, "Filme.pt-BR.srt")              # em Windows-1252, como muitas legendas
        with open(cls.externa, "wb") as f:
            f.write(srt([(3.0, 4.0, "Não há ação aqui")]).encode("cp1252"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def setUp(self):
        self.avisos, self.erros = [], []
        self._info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: self.avisos.append(a[2] if len(a) > 2 else ""))
        self.j = gui.Janela()
        self.j.erro = lambda titulo, detalhe: self.erros.append((titulo, detalhe))
        self.j.show()
        self.j._carregar_filme(self.filme)

    def tearDown(self):
        QMessageBox.information = self._info
        self.j.player.parar(silencioso=True)
        self.j.close()
        self.j.carregador.encerrar()

    # ------------------------------------------------------------------ ajudantes
    def linhas(self):
        """[(chave, entra, numero, padrao)] na ordem da tabela."""
        t, out = self.j.tab_filme, []
        for r, k in enumerate(self.j._linhas_saida):
            if k is None:
                continue
            entra = t.item(r, J.COL_MANTER).checkState() == Qt.CheckState.Checked
            padrao = t.item(r, J.COL_PADRAO).flags() & Qt.ItemFlag.ItemIsUserCheckable and \
                t.item(r, J.COL_PADRAO).checkState() == Qt.CheckState.Checked
            out.append((k, entra, t.item(r, J.COL_NUM).text(), bool(padrao)))
        return out

    def entram(self, tipo=None):
        return [k for k, entra, _, _ in self.linhas() if entra and (tipo is None or self.j._tipo_chave(k) == tipo)]

    def selecionar(self, k):
        self.j.tab_filme.selectRow(self.j._linhas_saida.index(k))
        QApplication.processEvents()

    def clicar(self, k, coluna, marcado=True):
        r = self.j._linhas_saida.index(k)
        self.j.tab_filme.item(r, coluna).setCheckState(Qt.CheckState.Checked if marcado else Qt.CheckState.Unchecked)
        QApplication.processEvents()

    def gerar(self, nome):
        saida = os.path.join(self.pasta, nome)
        original = QFileDialog.getSaveFileName
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (saida, ""))
        try:
            self.j.acao_gerar(False)
        finally:
            QFileDialog.getSaveFileName = original
        self.assertTrue(esperar(lambda: not self.j._ocupado(), 120), "a geracao nao terminou")
        self.assertEqual(self.erros, [])
        self.assertTrue(os.path.isfile(saida))
        return saida

    # ------------------------------------------------------------------ testes
    def test_padrao_ao_abrir_o_filme(self):
        self.assertEqual(self.entram("video"), [("filme", 0)])
        self.assertEqual(self.entram("audio"), [("filme", 2), ("filme", 1)])          # PT-BR, depois o original
        self.assertEqual(self.entram("subtitle"), [("filme", 6), ("filme", 5)])       # PT completa, PT forcada
        fora = [k for k, entra, _, _ in self.linhas() if not entra]
        self.assertEqual(fora, [("filme", 3), ("filme", 4)])                         # comentario e legenda em ingles
        self.assertEqual([n for _, entra, n, _ in self.linhas() if entra], ["1", "2", "3", "4", "5"])
        padroes = [k for k, _, _, p in self.linhas() if p]
        self.assertEqual(padroes, [("filme", 2)])                                    # so o audio PT-BR
        self.assertEqual(self.j.cmb_original.currentData(), "")                     # automatico (eng)
        self.assertIn("eng", self.j.cmb_original.currentText())

    def test_marcar_e_desmarcar_tudo(self):
        self.j.b_desmarcar.click()
        self.assertEqual(self.entram(), [("filme", 0)])                              # o video continua
        self.j.b_marcar.click()
        self.assertEqual(len(self.entram()), 7)
        self.assertTrue(self.j._org_manual)
        # nao da para tirar o unico video
        self.clicar(("filme", 0), J.COL_MANTER, False)
        self.assertIn(("filme", 0), self.entram())
        # o padrao volta com o botao
        self.j.b_padrao_saida.click()
        self.assertFalse(self.j._org_manual)
        self.assertEqual(self.entram("audio"), [("filme", 2), ("filme", 1)])

    def test_subir_descer_e_faixa_padrao(self):
        j = self.j
        self.selecionar(("filme", 1))
        self.assertTrue(j.b_saida_sobe.isEnabled())
        j.b_saida_sobe.click()
        self.assertEqual(self.entram("audio"), [("filme", 1), ("filme", 2)])
        self.assertEqual(j._chave_escolhida_saida(), ("filme", 1))                  # continua escolhida
        self.assertFalse(j.b_saida_sobe.isEnabled())                                # ja e o primeiro audio
        j.b_saida_desce.click()
        self.assertEqual(self.entram("audio"), [("filme", 2), ("filme", 1)])
        # a legenda nao sobe para o meio dos audios: cada tipo fica no seu grupo
        self.selecionar(("filme", 6))
        self.assertFalse(j.b_saida_sobe.isEnabled())
        # faixa padrao: o original em ingles toca sozinho; a legenda forcada aparece sozinha
        self.clicar(("filme", 1), J.COL_PADRAO)
        self.clicar(("filme", 5), J.COL_PADRAO)
        self.assertEqual([k for k, _, _, p in self.linhas() if p], [("filme", 1), ("filme", 5)])
        self.clicar(("filme", 5), J.COL_PADRAO, False)
        self.assertEqual([k for k, _, _, p in self.linhas() if p], [("filme", 1)])
        # escolher como padrao uma faixa desmarcada faz ela entrar
        self.clicar(("filme", 3), J.COL_PADRAO)
        self.assertIn(("filme", 3), self.entram("audio"))
        self.assertEqual(j.padrao_audio, ("filme", 3))

    def test_dublagem_entra_primeiro_e_a_lista_acompanha(self):
        j = self.j
        j._adicionar_arquivos([self.dub])
        d = j.dubs[0]
        self.assertEqual(self.entram("audio"), [("dub", d), ("filme", 2), ("filme", 1)])
        self.assertEqual(j.tab.item(0, 4).text(), "Sim")                              # padrao na lista tambem
        self.assertTrue(j.chk_padrao.isChecked())
        j._adicionar_arquivos([self.dub2])
        d2 = j.dubs[1]
        self.assertEqual(self.entram("audio"), [("dub", d), ("dub", d2), ("filme", 2), ("filme", 1)])
        # mudar a ordem na lista de dublagens muda no arquivo final
        j.tab.selectRow(1)
        j.acao_mover(-1)
        self.assertEqual(j.dubs, [d2, d])
        self.assertEqual(self.entram("audio"), [("dub", d2), ("dub", d), ("filme", 2), ("filme", 1)])
        self.assertEqual(j.tab.item(0, 4).text(), "Sim")                              # o 1o audio e o padrao
        # 'Faixa padrao' no editor da dublagem
        j.tab.selectRow(1)
        j.chk_padrao.setChecked(True)
        self.assertEqual(j.padrao_audio, ("dub", d))
        self.assertEqual([k for k, _, _, p in self.linhas() if p], [("dub", d)])
        # remover a dublagem padrao: o padrao volta para o primeiro audio
        j.tab.selectRow(1)
        j.acao_remover()
        self.assertEqual(j.dubs, [d2])
        self.assertIsNone(j.padrao_audio)
        self.assertEqual(self.entram("audio"), [("dub", d2), ("filme", 2), ("filme", 1)])

    def test_legenda_externa_substitui_as_do_filme(self):
        j = self.j
        j._adicionar_legendas([self.externa])
        self.assertEqual(len(j.legendas), 1)
        x = j.legendas[0]
        self.assertEqual((x.idioma, x.nome, x.forcada), ("por", "Português (Brasil)", False))
        # a externa (completa) substitui a completa do filme; a forcada do filme continua
        self.assertEqual(self.entram("subtitle"), [("leg", x), ("filme", 5)])
        # editar: atraso e forcada
        self.selecionar(("leg", x))
        self.assertTrue(j.b_leg_editar.isEnabled() and j.b_leg_rem.isEnabled())
        dlg = gui.EditarLegenda(x, j)
        dlg.atraso.setValue(-250)
        dlg.forcada.setChecked(True)
        dlg.aplicar(x)
        j._mudou_a_lista()
        self.assertEqual((x.atraso_ms, x.forcada), (-250, True))
        self.assertEqual(self.entram("subtitle"), [("filme", 6), ("leg", x)])     # agora ela e a forcada
        # remover: as legendas PT-BR do filme voltam
        self.selecionar(("leg", x))
        j.acao_remover_legenda()
        self.assertEqual(j.legendas, [])
        self.assertEqual(self.entram("subtitle"), [("filme", 6), ("filme", 5)])

    def test_arrastar_legenda_para_a_janela(self):
        class Evento:
            def __init__(self, caminhos):
                self.m = QMimeData()
                self.m.setUrls([QUrl.fromLocalFile(c) for c in caminhos])

            def mimeData(self):
                return self.m
        self.j.dropEvent(Evento([self.externa]))
        self.assertEqual(len(self.j.legendas), 1)
        self.assertEqual(self.j.dubs, [])

    def test_gerar_sem_dublagem(self):
        """So reorganiza o filme: PT-BR primeiro (padrao), o original, legendas PT-BR (sem legenda padrao)."""
        saida = self.gerar("remux.mkv")
        st = sondar(saida)
        aud = [s for s in st if s["codec_type"] == "audio"]
        leg = [s for s in st if s["codec_type"] == "subtitle"]
        self.assertEqual([s["tags"].get("language") for s in aud], ["por", "eng"])
        self.assertEqual([s["disposition"]["default"] for s in aud], [1, 0])
        self.assertEqual([s["tags"].get("language") for s in leg], ["por", "por"])
        self.assertEqual([s["disposition"]["default"] for s in leg], [0, 0])
        self.assertEqual([s["disposition"]["forced"] for s in leg], [0, 1])          # a forcada continua forcada
        self.assertTrue(any("nenhuma dublagem" in a for a in self.avisos), self.avisos)

    def test_gerar_com_dublagem_e_legenda_externa(self):
        j = self.j
        j._adicionar_arquivos([self.dub])
        j._adicionar_legendas([self.externa])
        self.j.dubs[0].nome = "Dublagem VHS"
        saida = self.gerar("final.mkv")
        st = sondar(saida)
        aud = [s for s in st if s["codec_type"] == "audio"]
        leg = [s for s in st if s["codec_type"] == "subtitle"]
        self.assertEqual([s["tags"].get("title", "") for s in aud], ["Dublagem VHS", "", "Original"])
        self.assertEqual([s["disposition"]["default"] for s in aud], [1, 0, 0])
        self.assertEqual([(s["tags"].get("language"), s["tags"].get("title")) for s in leg],
                         [("por", "Português (Brasil)"), ("por", "Forçada")])
        self.assertEqual([s["disposition"]["forced"] for s in leg], [0, 1])
        texto = subprocess.run(["ffmpeg", "-v", "error", "-i", saida, "-map", "0:s:0", "-f", "srt", "-"],
                               stdout=subprocess.PIPE, check=True, stdin=subprocess.DEVNULL).stdout.decode("utf-8")
        self.assertIn("Não há ação aqui", texto)                                    # acentos certos
        self.assertTrue(any("Dublagem VHS" in a for a in self.avisos), self.avisos)  # conferencia da dublagem

    def test_projeto_guarda_a_organizacao(self):
        j = self.j
        j._adicionar_arquivos([self.dub])
        j._adicionar_legendas([self.externa])
        self.selecionar(("filme", 1))
        j.b_saida_sobe.click()
        j.b_saida_sobe.click()                                        # original em ingles em primeiro
        self.clicar(("filme", 6), J.COL_MANTER)                       # mais a legenda PT completa do filme
        self.clicar(("filme", 6), J.COL_PADRAO)                       # ... como padrao
        antes = [(k[0], k[1] if k[0] == "filme" else None) for k in self.entram()]
        caminho = os.path.join(self.pasta, "org.eternaldub")
        orig_s, orig_a = QFileDialog.getSaveFileName, QFileDialog.getOpenFileName
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (caminho, ""))
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (caminho, ""))
        try:
            j.acao_salvar_projeto()
            j2 = gui.Janela()
            j2.erro = j.erro
            try:
                j2.acao_abrir_projeto()
                self.j, outro = j2, j
                depois = [(k[0], k[1] if k[0] == "filme" else None) for k in self.entram()]
                self.assertEqual(depois, antes)
                self.assertTrue(j2._org_manual)
                self.assertEqual(j2.padrao_legenda, ("filme", 6))
                self.assertEqual(len(j2.legendas), 1)
                self.j = outro
            finally:
                j2.close()
                j2.carregador.encerrar()
        finally:
            QFileDialog.getSaveFileName, QFileDialog.getOpenFileName = orig_s, orig_a

    def test_organizar_sozinho_desligado(self):
        j = self.j
        j.chk_org_auto.setChecked(False)
        try:
            j._carregar_filme(self.filme)
            self.assertEqual(len(self.entram()), 7)                   # tudo, na ordem do arquivo
            self.assertEqual(self.entram("audio"), [("filme", 1), ("filme", 2), ("filme", 3)])
        finally:
            j.chk_org_auto.setChecked(True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
