# SPDX-License-Identifier: MIT
"""Testes do modelo de emendas (EternalDub_emendas.py): rodam sem FFmpeg e sem interface grafica."""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import EternalDub_emendas as em
from EternalDub_emendas import MapaEditavel

# mapa como o mapear() entrega: [ini_filme, fim_filme, ini_dub (tempo ORIGINAL)]
#   emenda 1 em 100 s: +2,5 s de silencio (a dublagem nao tem esse pedaco)
#   emenda 2 em 300 s: saem 1,2 s da dublagem
# Os tempos da dublagem abaixo estao no tempo ESTICADO (depois da correcao de velocidade); MAPA(atempo) os
# converte para o tempo original, como o mapear() faz.
MAPA_ESTICADO = [[10.0, 100.0, 0.0], [102.5, 300.0, 90.0], [300.0, 900.0, 288.7]]


def mapa(atempo=1.0):
    return [[fi, ff, round(ui * atempo, 4)] for fi, ff, ui in MAPA_ESTICADO]


MAPA = mapa(1.0)


def alinhamentos(pedacos, atempo):
    """Atraso de cada pedaco (filme - tempo esticado da dublagem)."""
    return [fi - di / atempo for fi, ff, di in pedacos]


class TestModelo(unittest.TestCase):
    def test_mapa_sem_editar_volta_identico(self):
        m = MapaEditavel.de_trechos(MAPA, 1.0)
        self.assertEqual(m.para_trechos(), MAPA)
        m = MapaEditavel.de_trechos(mapa(25 / 23.976), 25 / 23.976)
        self.assertEqual(m.para_trechos(), mapa(25 / 23.976))

    def test_emendas_lidas_do_mapa(self):
        m = MapaEditavel.de_trechos(MAPA, 1.0)
        self.assertEqual(len(m.emendas), 2)
        self.assertAlmostEqual(m.emendas[0].t, 100.0)
        self.assertAlmostEqual(m.emendas[0].silencio, 2.5)
        self.assertAlmostEqual(m.emendas[0].remocao, 0.0)
        self.assertAlmostEqual(m.emendas[1].remocao, 1.2, places=6)
        self.assertAlmostEqual(m.emendas[1].quantia, -1.2, places=6)
        self.assertEqual([round(a, 6) for a in m.atrasos()], [10.0, 12.5, 11.3])

    def test_mover_nao_muda_o_alinhamento(self):
        for atempo in (1.0, 25 / 23.976):
            m = MapaEditavel.de_trechos(mapa(atempo), atempo)
            antes = [round(a, 3) for a in alinhamentos(m.para_trechos(), atempo)]
            usado = m.mover_emenda(0, 97.3)
            self.assertAlmostEqual(usado, 97.3)
            P = m.para_trechos()
            depois = [round(a, 3) for a in alinhamentos(P, atempo)]
            self.assertEqual(antes, depois)
            self.assertAlmostEqual(P[0][1], 97.3, places=3)          # o 1o pedaco acaba onde a emenda foi
            self.assertAlmostEqual(P[1][0], 97.3 + 2.5, places=3)    # o silencio continua com 2,5 s
            self.assertEqual(m.problemas(), [])

    def test_mover_respeita_os_limites(self):
        m = MapaEditavel.de_trechos(MAPA, 1.0)
        lo, hi = m.limites_emenda(0)
        self.assertAlmostEqual(lo, 10.0 + em.MIN_TRECHO)
        self.assertAlmostEqual(m.mover_emenda(0, -50.0), lo)
        self.assertAlmostEqual(m.mover_emenda(0, 5000.0), hi)
        self.assertEqual(m.problemas(), [])

    def test_quantia_desloca_o_resto(self):
        m = MapaEditavel.de_trechos(MAPA, 1.0)
        m.definir_quantia(0, 2.7)                                     # +200 ms
        self.assertEqual([round(a, 6) for a in m.atrasos()], [10.0, 12.7, 11.5])
        m.definir_quantia(0, -0.4)                                    # vira remocao
        self.assertAlmostEqual(m.emendas[0].remocao, 0.4)
        self.assertAlmostEqual(m.emendas[0].silencio, 0.0)
        self.assertEqual(m.problemas(), [])
        self.assertIsNone(m.definir_quantia(0, 0.0))                  # sem efeito: recusa

    def test_silencio_limitado_pelo_trecho_seguinte(self):
        m = MapaEditavel.de_trechos(MAPA, 1.0)
        usado = m.definir_quantia(0, 1e6)
        self.assertLess(usado, 300.0)
        self.assertEqual(m.problemas(), [])

    def test_remover_emenda_mantem_os_trechos_seguintes(self):
        m = MapaEditavel.de_trechos(MAPA, 1.0)
        ultimo = m.atrasos()[2]
        m.remover_emenda(0)
        self.assertEqual(len(m.emendas), 1)
        self.assertAlmostEqual(m.atrasos()[0], 10.0)
        self.assertAlmostEqual(m.atrasos()[1], ultimo)                # o ultimo trecho nao se mexeu
        self.assertEqual(m.problemas(), [])
        m.remover_emenda(0)
        self.assertEqual(m.emendas, [])
        self.assertEqual(len(m.para_trechos()), 1)

    def test_inserir_emenda(self):
        m = MapaEditavel.de_trechos(MAPA, 1.0)
        k = m.inserir_emenda(500.0, 0.3)
        self.assertEqual(k, 2)
        self.assertEqual(len(m.emendas), 3)
        self.assertEqual([round(a, 6) for a in m.atrasos()], [10.0, 12.5, 11.3, 11.6])
        self.assertEqual(m.problemas(), [])
        self.assertIsNone(m.inserir_emenda(500.0, 0.0))               # sem efeito
        self.assertIsNone(m.inserir_emenda(5.0, 0.3))                 # antes do comeco da dublagem
        self.assertIsNone(m.inserir_emenda(100.01, 0.3))              # colada numa emenda: nao cabe

    def test_deslocar_so_um_trecho(self):
        m = MapaEditavel.de_trechos(MAPA, 1.0)
        antes = m.atrasos()
        m.deslocar_trecho(1, 0.25, so_este=True)
        depois = m.atrasos()
        self.assertAlmostEqual(depois[0], antes[0])
        self.assertAlmostEqual(depois[1], antes[1] + 0.25)
        self.assertAlmostEqual(depois[2], antes[2])
        self.assertEqual(m.problemas(), [])

    def test_deslocar_trecho_e_os_seguintes(self):
        m = MapaEditavel.de_trechos(MAPA, 1.0)
        antes = m.atrasos()
        m.deslocar_trecho(1, -0.1, so_este=False)
        depois = m.atrasos()
        self.assertAlmostEqual(depois[0], antes[0])
        self.assertAlmostEqual(depois[1], antes[1] - 0.1)
        self.assertAlmostEqual(depois[2], antes[2] - 0.1)

    def test_emenda_sem_efeito_some(self):
        m = MapaEditavel.de_trechos(MAPA, 1.0)
        m.deslocar_trecho(1, -2.5, so_este=True)          # o trecho 1 volta ao atraso do 0: emenda 0 some
        self.assertEqual(len(m.emendas), 1)
        self.assertEqual(m.problemas(), [])

    def test_um_atraso_vira_mapa(self):
        m = MapaEditavel.de_atraso(-3.2, 1.0, dur_filme=7000.0, dur_dub=7010.0)
        self.assertEqual(m.para_trechos(), [[0.0, 7000.0, 3.2]])      # o comeco da dublagem sai
        k = m.inserir_emenda(1000.0, 0.5)
        self.assertEqual(k, 0)
        P = m.para_trechos()
        self.assertEqual(len(P), 2)
        self.assertAlmostEqual(P[1][0], 1000.5)
        self.assertAlmostEqual(P[1][2], 1000.0 + 3.2)                 # a dublagem continua do mesmo ponto
        m2 = MapaEditavel.de_atraso(4.0, 1.0, dur_filme=100.0, dur_dub=50.0)
        self.assertEqual(m2.para_trechos(), [[4.0, 54.0, 0.0]])       # a dublagem acaba antes do filme

    def test_ultimo_pedaco_acompanha_o_fim_da_dublagem(self):
        m = MapaEditavel.de_atraso(0.0, 1.0, dur_filme=1000.0, dur_dub=500.0)
        m.inserir_emenda(100.0, 2.0)                                   # o resto da dublagem fica 2 s mais tarde
        P = m.para_trechos()
        self.assertAlmostEqual(P[-1][1], 502.0, places=3)

    def test_fuzz_invariantes(self):
        """Muitas edicoes aleatorias: o modelo nunca fica invalido e o alinhamento so muda onde deve."""
        rnd = random.Random(7)
        for atempo in (1.0, 25 / 23.976, 24 / 25):
            m = MapaEditavel.de_trechos(mapa(atempo), atempo, dur_filme=1000.0, dur_dub=950.0)
            for passo in range(400):
                op = rnd.choice(["mover", "quantia", "inserir", "remover", "trecho1", "trecho2"])
                n = len(m.emendas)
                if op == "mover" and n:
                    i = rnd.randrange(n)
                    antes = [round(a, 6) for a in m.atrasos()]
                    m.mover_emenda(i, rnd.uniform(0, 1000))
                    self.assertEqual(antes, [round(a, 6) for a in m.atrasos()])   # mover nao muda alinhamento
                elif op == "quantia" and n:
                    m.definir_quantia(rnd.randrange(n), rnd.uniform(-3, 3))
                elif op == "inserir":
                    m.inserir_emenda(rnd.uniform(0, 1000), rnd.uniform(-2, 2))
                elif op == "remover" and n:
                    m.remover_emenda(rnd.randrange(n))
                elif op == "trecho1":
                    m.deslocar_trecho(rnd.randrange(n + 1), rnd.uniform(-1, 1), True)
                elif op == "trecho2":
                    m.deslocar_trecho(rnd.randrange(n + 1), rnd.uniform(-1, 1), False)
                self.assertEqual(m.problemas(), [], "passo %d (%s)" % (passo, op))
                P = m.para_trechos()
                for (fi, ff, di), (fi2, ff2, di2) in zip(P, P[1:]):
                    self.assertLessEqual(ff, fi2 + 1e-3)                          # em ordem, sem sobrepor
                    self.assertGreaterEqual(di2 / atempo, di / atempo + (ff - fi) - 1e-3)  # a dublagem nao volta
                self.assertTrue(all(ff - fi > 0 for fi, ff, _ in P))
                # lido de volta, o mapa gerado tem as mesmas emendas
                volta = MapaEditavel.de_trechos(P, atempo)
                self.assertEqual(len(volta.emendas), len(m.emendas))
                for a, b in zip(volta.atrasos(), m.atrasos()):
                    self.assertAlmostEqual(a, b, places=2)


class TestSomNaEmenda(unittest.TestCase):
    def envelope(self, dur=60.0, fala=((5.0, 8.0), (10.0, 14.0)), nivel=0.5):
        n = int(dur * em.ENV_RATE)
        amp = np.full(n, 0.002, np.float32)                  # ruido de fundo
        for a, b in fala:
            amp[int(a * em.ENV_RATE):int(b * em.ENV_RATE)] = nivel
        return np.stack([-amp, amp], axis=1)

    def test_classificacao(self):
        amp = em.amplitude_do_envelope(self.envelope())
        ref = em.referencia_de_nivel(amp)
        self.assertGreater(ref, 0.3)
        m = MapaEditavel.de_atraso(0.0, 1.0, 100.0, 60.0)
        m.inserir_emenda(9.0, 0.5)                           # entre as duas falas: pausa
        self.assertEqual(em.classificar_nivel(em.nivel_da_emenda(m, 0, amp, ref)), "pausa")
        m.mover_emenda(0, 6.0)                               # no meio da primeira fala
        self.assertEqual(em.classificar_nivel(em.nivel_da_emenda(m, 0, amp, ref)), "alto")
        self.assertIsNone(em.nivel_da_emenda(m, 0, np.zeros(0, np.float32), ref))

    def test_remocao_olha_o_pedaco_que_sai(self):
        amp = em.amplitude_do_envelope(self.envelope())
        ref = em.referencia_de_nivel(amp)
        m = MapaEditavel.de_atraso(0.0, 1.0, 100.0, 60.0)
        m.inserir_emenda(8.5, -1.0)                          # sai 1 s da dublagem: de 8,5 s a 9,5 s (pausa)
        self.assertEqual(em.classificar_nivel(em.nivel_da_emenda(m, 0, amp, ref)), "pausa")
        m.mover_emenda(0, 9.6)                               # agora o pedaco que sai pega o comeco da 2a fala
        self.assertEqual(em.classificar_nivel(em.nivel_da_emenda(m, 0, amp, ref)), "alto")

    def test_achar_pausa(self):
        amp = em.amplitude_do_envelope(self.envelope())
        ref = em.referencia_de_nivel(amp)
        m = MapaEditavel.de_atraso(0.0, 1.0, 100.0, 60.0)
        m.inserir_emenda(6.0, 0.3)                           # no meio da fala de 5 a 8 s
        t = em.melhor_posicao(m, 0, amp, ref, raio=4.0)
        self.assertEqual(em.classificar_nivel(em.nivel_da_emenda(m, 0, amp, ref, t)), "pausa")
        self.assertTrue(8.0 <= t <= 10.0 or t < 5.0, t)
        # perto: prefere o ponto mais proximo entre os silenciosos (nao pula para o outro lado do filme)
        self.assertLess(abs(t - 6.0), 3.0)

    def test_encaixar_ao_arrastar(self):
        amp = em.amplitude_do_envelope(self.envelope())
        ref = em.referencia_de_nivel(amp)
        m = MapaEditavel.de_atraso(0.0, 1.0, 100.0, 60.0)
        m.inserir_emenda(9.0, 0.5)
        # soltou a 7,9 s (ainda dentro da 1a fala, que vai ate 8,0 s): encaixa na pausa logo depois
        t = em.encaixar_em_pausa(m, 0, 7.9, amp, ref)
        self.assertGreaterEqual(t, 7.9)
        self.assertLess(t, 8.4)
        self.assertEqual(em.classificar_nivel(em.nivel_da_emenda(m, 0, amp, ref, t)), "pausa")
        # ja numa pausa: nao mexe
        self.assertEqual(em.encaixar_em_pausa(m, 0, 9.0, amp, ref), 9.0)
        # no meio da fala, longe de qualquer pausa: fica onde esta
        self.assertEqual(em.encaixar_em_pausa(m, 0, 12.0, amp, ref, raio=0.4), 12.0)

    def test_taxas_batem_com_o_nucleo(self):
        try:
            import EternalDub_core as core
        except Exception as e:                               # sem numpy/ffmpeg no ambiente de teste
            self.skipTest(str(e))
        self.assertEqual(core.ENV_RATE, em.ENV_RATE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
