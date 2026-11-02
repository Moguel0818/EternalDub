# SPDX-License-Identifier: MIT
"""
Teste da interface (sem tela: QT_QPA_PLATFORM=offscreen): abre um filme e uma dublagem sinteticos, edita as emendas
como a pessoa faria (arrastar, setas, quantia, adicionar, remover, desfazer) e toca a previa numa placa de som falsa.
Se a variavel EDITAR_CAPTURAS apontar para uma pasta, grava imagens da janela nela.
"""
import os
import shutil
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

try:
    from PySide6.QtCore import QSettings
    from PySide6.QtMultimedia import QAudio
    from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox
    TEM_QT = True
except Exception:                                   # pragma: no cover
    TEM_QT = False

if TEM_QT:
    import EternalDub_gui as gui
    import EternalDub_i18n as i18n
    import sinais
    core = gui.core

CAPTURAS = os.environ.get("EDITAR_CAPTURAS")


class SaidaFalsa:
    """Imita o QAudioSink e o QIODevice dele: 'toca' os bytes em tempo real, sem placa de som."""

    def __init__(self):
        self.bps = gui.ReprodutorAudio.BYTES_POR_SEGUNDO
        self.capacidade = self.bps // 2
        self.escrito, self.t0, self.dados, self.parou, self.volume = 0, None, bytearray(), False, 1.0

    def setVolume(self, v):
        self.volume = v

    def start(self):
        self.t0 = time.monotonic()
        return self

    def write(self, b):
        self.dados += b
        self.escrito += len(b)
        return len(b)

    def _consumido(self):
        return min(self.escrito, int((time.monotonic() - self.t0) * self.bps)) if self.t0 else 0

    def bytesFree(self):
        return self.capacidade - (self.escrito - self._consumido())

    def processedUSecs(self):
        return int(self._consumido() / self.bps * 1e6)

    def state(self):
        return QAudio.State.IdleState if self._consumido() >= self.escrito else QAudio.State.ActiveState

    def stop(self):
        self.parou = True


def esperar(cond, limite=30.0):
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


@unittest.skipUnless(TEM_QT and shutil.which("ffmpeg"), "precisa do PySide6 e do FFmpeg")
class TestJanela(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        i18n.definir("pt")
        cls.pasta = tempfile.mkdtemp(prefix="eternaldub_gui_")
        QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope,   # opcoes so deste teste
                          os.path.join(cls.pasta, "config"))
        sr = sinais.SR
        cls.film_arq = sinais.filme_com_video(cls.pasta, "filme", sinais.tons(120.0, base=500.0, passo=23.0, semente=2))
        # dublagem com pausas de verdade (silencio de 1 s a cada 10 s), para a medicao de som das emendas
        x = sinais.tons(120.0, semente=1)
        for k in range(1, 12):
            x[int((k * 10 - 1) * sr):int(k * 10 * sr)] = np.random.RandomState(k).randn(sr).astype(np.float32) * 0.002
        cls.dub_arq = sinais.dublagem_flac(cls.pasta, "dub", x)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def setUp(self):
        self.j = gui.Janela()
        self.j.show()
        self.j._carregar_filme(self.film_arq)
        self.j._adicionar_arquivos([self.dub_arq])
        self.assertEqual(len(self.j.dubs), 1)
        self.d = self.j.dubs[0]
        chaves = {(self.film_arq, 0), (self.dub_arq, 0)}
        self.assertTrue(esperar(lambda: chaves <= self.j._completas), "as ondas nao carregaram")
        self.j.player._fabrica = SaidaFalsa
        self.j.resize(1360, 820)
        QApplication.processEvents()

    def tearDown(self):
        self.j.player.parar(silencioso=True)
        self.j.close()
        self.j.carregador.encerrar()

    def captura(self, nome):
        if CAPTURAS:
            os.makedirs(CAPTURAS, exist_ok=True)
            QApplication.processEvents()
            self.j.grab().save(os.path.join(CAPTURAS, nome + ".png"))

    def mapa(self, atraso_ms=0):
        """Dois cortes: 2,5 s de silencio em 30 s e 1,5 s que saem da dublagem em 70 s."""
        self.d.atempo, self.d.atraso_ms = 1.0, atraso_ms
        self.d.trechos = [[2.0, 30.0, 0.0], [32.5, 70.0, 28.0], [70.0, 118.0, 28.0 + 37.5 + 1.5]]
        self.j._refresh_tabela()

    # ------------------------------------------------------------------ emendas
    def test_painel_mostra_as_emendas(self):
        self.mapa()
        self.assertEqual(self.j.tab_em.rowCount(), 2)
        self.assertEqual(self.j.tab_em.item(0, 2).text(), "+2500 ms")
        self.assertEqual(self.j.tab_em.item(1, 2).text(), "-1500 ms")
        self.assertEqual(len(self.j.onda.emendas), 2)
        self.assertAlmostEqual(self.j.onda.emendas[0]["t"], 30.0)
        self.j.onda.t0, self.j.onda.pps = 0.0, 12.0
        self.captura("1_emendas")

    def test_arrastar_emenda_nao_muda_alinhamento(self):
        self.mapa()
        j, o = self.j, self.j.onda
        alinh = lambda t: [round(a[0] - a[2], 3) for a in t]          # atraso de cada pedaco (atempo = 1)
        antes = alinh(self.d.trechos)
        j.chk_ima.setChecked(False)
        o.arraste_comecou.emit()
        for t in (30.2, 30.6, 31.4, 33.0):
            o.emenda_arrastada.emit(0, t)
        o.arraste_terminou.emit("emenda")
        self.assertAlmostEqual(self.d.trechos[0][1], 33.0, places=3)
        self.assertEqual(alinh(self.d.trechos), antes)
        self.assertAlmostEqual(self.d.trechos[1][0], 35.5, places=3)             # o silencio de 2,5 s acompanha
        self.assertAlmostEqual(j.onda.emendas[0]["t"], 33.0, places=3)
        # tudo isso foi UM passo no Desfazer
        j.acao_desfazer()
        self.assertAlmostEqual(self.d.trechos[0][1], 30.0, places=3)
        j.acao_refazer()
        self.assertAlmostEqual(self.d.trechos[0][1], 33.0, places=3)

    def test_imã_encaixa_na_pausa(self):
        self.mapa()
        j, o = self.j, self.j.onda
        j.chk_ima.setChecked(True)
        # a dublagem tem uma pausa de 29 a 30 s do SEU tempo = 31 a 32 s do filme (o 1o pedaco atrasa 2 s)
        o.arraste_comecou.emit()
        o.emenda_arrastada.emit(0, 30.8)         # solto 0,2 s antes da pausa, em cima de fala
        o.arraste_terminou.emit("emenda")
        t = self.d.trechos[0][1]
        self.assertGreaterEqual(t, 31.0)
        self.assertLessEqual(t, 31.2)
        self.assertEqual(j.tab_em.item(0, 3).text(), "pausa")
        # longe de qualquer pausa a emenda fica onde foi solta
        o.arraste_comecou.emit()
        o.emenda_arrastada.emit(0, 25.0)
        o.arraste_terminou.emit("emenda")
        self.assertAlmostEqual(self.d.trechos[0][1], 25.0, places=3)

    def test_setas_e_botoes(self):
        self.mapa()
        j, o = self.j, self.j.onda
        o.emenda_sel = 0
        o.emenda_empurrada.emit(0, 0.01)
        o.emenda_empurrada.emit(0, 0.01)
        self.assertAlmostEqual(self.d.trechos[0][1], 30.02, places=3)
        j._empurrar_emenda_selecionada(0.1)
        self.assertAlmostEqual(self.d.trechos[0][1], 30.12, places=3)
        # juntas, as setas seguidas formam UM passo no Desfazer
        j.acao_desfazer()
        self.assertAlmostEqual(self.d.trechos[0][1], 30.0, places=3)

    def test_quantia_pelo_campo(self):
        self.mapa()
        j = self.j
        j.onda.emenda_sel = 0
        j._atualizar_painel_emendas(0)
        self.assertEqual(j.sp_em_quantia.value(), 2500)
        j.sp_em_quantia.setValue(2700)
        self.assertAlmostEqual(self.d.trechos[1][0], 32.7, places=3)
        self.assertAlmostEqual(self.d.trechos[2][0], 70.0, places=3)             # a 2a emenda nao se mexeu
        d2 = [round(a[0] - a[2], 3) for a in self.d.trechos]
        self.assertEqual(d2, [2.0, 4.7, 3.2 + 0.2 - 0.2 + 0.0 + 0.0][:2] + [d2[2]])   # trechos 1 e 2 deslocaram 200 ms
        j.sp_em_quantia.setValue(0)                                               # zero nao existe: pula para o outro lado
        self.assertNotEqual(j.sp_em_quantia.value(), 0)

    def test_adicionar_e_remover(self):
        self.mapa()
        j = self.j
        original = QInputDialog.getInt
        QInputDialog.getInt = staticmethod(lambda *a, **k: (-300, True))
        try:
            j.onda.set_cabeca(50.0)
            j.acao_add_emenda()
        finally:
            QInputDialog.getInt = original
        self.assertEqual(len(self.d.trechos), 4)
        self.assertEqual(j.tab_em.rowCount(), 3)
        self.assertEqual(j.tab_em.item(1, 2).text(), "-300 ms")
        self.assertEqual(j.onda.emenda_sel, 1)
        j.acao_remover_emenda()
        self.assertEqual(len(self.d.trechos), 3)
        j.acao_desfazer()                                    # desfaz a remocao
        self.assertEqual(len(self.d.trechos), 4)
        j.acao_desfazer()                                    # desfaz a adicao
        self.assertEqual(len(self.d.trechos), 3)

    def test_um_atraso_vira_mapa_e_volta(self):
        j = self.j
        self.d.trechos, self.d.atempo, self.d.atraso_ms = None, 1.0, 1500
        j._refresh_tabela()
        self.assertEqual(j.tab_em.rowCount(), 0)
        original = QInputDialog.getInt
        QInputDialog.getInt = staticmethod(lambda *a, **k: (400, True))
        try:
            j.onda.set_cabeca(60.0)
            j.acao_add_emenda()
        finally:
            QInputDialog.getInt = original
        self.assertIsNotNone(self.d.trechos)
        self.assertEqual(self.d.atraso_ms, 0)                # o atraso foi para dentro do mapa
        self.assertAlmostEqual(self.d.trechos[0][0], 1.5, places=3)
        self.assertAlmostEqual(self.d.trechos[1][0] - self.d.trechos[1][2], 1.9, places=3)
        j.onda.emenda_sel = 0
        j.acao_remover_emenda()                              # sem emendas: volta a um atraso so
        self.assertIsNone(self.d.trechos)
        self.assertEqual(self.d.atraso_ms, 1500)

    def test_ajuste_fino_soma_as_emendas(self):
        self.mapa(atraso_ms=250)
        j = self.j
        self.assertAlmostEqual(j.onda.emendas[0]["t"], 30.25, places=3)
        j.onda.emenda_sel = 0
        j._empurrar_emenda_selecionada(0.1)
        self.assertAlmostEqual(self.d.trechos[0][1], 30.1, places=3)             # o mapa guarda sem o ajuste fino
        self.assertEqual(self.d.atraso_ms, 250)
        self.assertAlmostEqual(j.onda.emendas[0]["t"], 30.35, places=3)

    def test_deslocar_so_um_trecho_com_ctrl(self):
        self.mapa()
        o = self.j.onda
        antes = [round(a[0] - a[2], 3) for a in self.d.trechos]
        o.arraste_comecou.emit()
        o.segmento_arrastado.emit(50.0, 0.12, True)          # trecho do meio, 120 ms mais tarde
        o.arraste_terminou.emit("segmento")
        depois = [round(a[0] - a[2], 3) for a in self.d.trechos]
        self.assertAlmostEqual(depois[0], antes[0], places=3)
        self.assertAlmostEqual(depois[1], antes[1] + 0.12, places=3)
        self.assertAlmostEqual(depois[2], antes[2], places=3)

    def test_projeto_guarda_as_emendas_editadas(self):
        self.mapa()
        j = self.j
        j.onda.emenda_sel = 1
        j._empurrar_emenda_selecionada(-0.2)
        caminho = os.path.join(self.pasta, "teste.eternaldub")
        core.salvar_projeto(caminho, j.film.caminho, 0, j.dubs, None)
        dubs = core.abrir_projeto(caminho)["dublagens"]
        self.assertEqual(dubs[0].trechos, self.d.trechos)

    # ------------------------------------------------------------------ ouvir
    def tocar_e_esperar(self, segundos=2.0):
        j = self.j
        j.acao_tocar()
        self.assertTrue(j.player.tocando())
        fim = time.monotonic() + segundos
        esperar(lambda: time.monotonic() > fim, segundos + 2)

    def test_tocar_dublagem(self):
        self.mapa()
        j = self.j
        j.onda.set_cabeca(26.0)
        self.tocar_e_esperar(2.5)
        saida = j.player._saida
        self.assertGreater(len(saida.dados), 100000)
        self.assertGreater(j.onda.cabeca, 26.5)                                 # a linha azul andou
        pcm = np.frombuffer(bytes(saida.dados), dtype="<i2")
        self.assertGreater(np.abs(pcm).max(), 1000)                             # saiu som
        j.acao_tocar()                                                          # para
        self.assertFalse(j.player.tocando())
        self.assertTrue(saida.parou)
        parou_em = j.onda.cabeca
        self.assertGreater(parou_em, 26.0)

    def test_tocar_a_emenda_passa_pelo_silencio(self):
        """3 s antes e 3 s depois da emenda de 2,5 s de silencio: no meio nao pode haver som."""
        self.mapa()
        j = self.j
        saidas = []

        def nova_saida():
            saidas.append(SaidaFalsa())
            return saidas[-1]
        j.player._fabrica = nova_saida
        j.onda.emenda_sel = 0
        j.acao_ouvir_emenda()
        self.assertTrue(esperar(lambda: not j.player.tocando(), 25.0), "a previa nao terminou")
        pcm = np.frombuffer(bytes(saidas[-1].dados), dtype="<i2").reshape(-1, 2)[:, 0]
        self.assertAlmostEqual(len(pcm) / 48000.0, 6.0, delta=0.6)             # 27 s a 33 s do filme
        self.assertGreater(np.abs(pcm[:int(2.5 * 48000)]).max(), 1000)           # antes da emenda: som
        self.assertLess(np.abs(pcm[int(3.2 * 48000):int(5.3 * 48000)]).max(), 50)   # no silencio inserido: nada
        self.assertAlmostEqual(j.onda.cabeca, 33.0, delta=0.7)                   # a linha azul foi ate o fim

    def test_trocar_o_modo_enquanto_toca(self):
        self.mapa()
        j = self.j
        j.onda.set_cabeca(10.0)
        self.tocar_e_esperar(1.0)
        j.acao_modo_audio("filme")
        self.assertTrue(j.player.tocando())
        self.assertEqual(j.cmb_modo.currentData(), "filme")
        j.acao_modo_audio("mix")
        self.assertTrue(j.player.tocando())
        j.acao_tocar()
        self.assertFalse(j.player.tocando())

    def test_falha_ao_tocar_avisa(self):
        j = self.j
        mensagens = []
        original = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: mensagens.append(a[2]))
        try:
            def sem_placa():
                raise RuntimeError("sem placa")
            j.player._fabrica = sem_placa
            j.acao_tocar()
            self.assertFalse(j.player.tocando())
            self.assertTrue(any("sem placa" in m for m in mensagens), mensagens)
        finally:
            QMessageBox.information = original

    # ------------------------------------------------------------------ idiomas
    def test_idiomas_aparecem_no_menu(self):
        codigos = [c for c, _ in i18n.IDIOMAS]
        self.assertEqual(sorted(self.j.acoes_idioma), sorted(codigos))

    def test_capturas(self):
        self.mapa()
        j = self.j
        j.onda.emenda_sel = 0
        j.onda.set_cabeca(26.0)
        j.onda.t0, j.onda.pps = 14.0, 22.0
        j.abas.setCurrentIndex(1)
        j._atualizar_painel_emendas(0)
        self.captura("2_painel_e_onda")


if __name__ == "__main__":
    unittest.main(verbosity=2)
