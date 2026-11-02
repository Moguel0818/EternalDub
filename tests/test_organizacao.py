# SPDX-License-Identifier: MIT
"""Organizacao do arquivo final: ordem das faixas, padrao BDRemux PT-BR, legendas externas e montagem real."""
import codecs
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import EternalDub_core as core
from EternalDub_core import Arquivo, Faixa, Dublagem, LegendaExterna, Organizacao


def filme_ficticio():
    """Um remux tipico: video, 6 audios e 5 legendas (nada e lido do disco)."""
    f = Arquivo(caminho="filme.mkv", duracao=6000.0)
    linhas = [
        ("video", "hevc", "eng", "", {}),
        ("audio", "truehd", "eng", "TrueHD 7.1 Atmos", {"default": 1}),
        ("audio", "dts", "eng", "DTS-HD MA 7.1", {}),
        ("audio", "ac3", "eng", "Commentary with the director", {"comment": 1}),
        ("audio", "ac3", "ger", "DD 5.1", {}),
        ("audio", "ac3", "por", "Português - Audiodescrição", {}),
        ("audio", "ac3", "por", "DD 5.1", {}),
        ("subtitle", "hdmv_pgs_subtitle", "eng", "", {}),
        ("subtitle", "hdmv_pgs_subtitle", "por", "Forçada", {"forced": 1}),
        ("subtitle", "hdmv_pgs_subtitle", "por", "Português (Portugal)", {}),
        ("subtitle", "hdmv_pgs_subtitle", "por", "", {}),
        ("subtitle", "hdmv_pgs_subtitle", "spa", "", {}),
    ]
    pos = {}
    for idx, (tipo, codec, idioma, titulo, disp) in enumerate(linhas):
        f.faixas.append(Faixa(idx=idx, tipo=tipo, codec=codec, idioma=idioma, titulo=titulo,
                              pos=pos.get(tipo, 0), disposicao=dict(disp)))
        pos[tipo] = pos.get(tipo, 0) + 1
    return f


class TestPadrao(unittest.TestCase):
    def setUp(self):
        self.f = filme_ficticio()

    def test_idioma_original(self):
        self.assertEqual(core.idioma_original_auto(self.f), "eng")

    def test_so_o_filme(self):
        org = core.organizar_padrao(self.f)
        itens = core.itens_saida(self.f, [], [], org)
        self.assertEqual(itens["video"], [("filme", 0)])
        # PT-BR do filme (nao a audiodescricao), depois a principal em ingles (TrueHD, nao o comentario)
        self.assertEqual(itens["audio"], [("filme", 6), ("filme", 1)])
        # legendas PT-BR do filme: a completa, depois a forcada; a de Portugal fica de fora
        self.assertEqual(itens["subtitle"], [("filme", 10), ("filme", 8)])
        pa, pl = core.padroes_efetivos(itens, org)
        self.assertEqual(pa, ("filme", 6))
        self.assertIsNone(pl)
        # o que nao entrou continua na lista (desmarcado), para poder marcar de novo
        self.assertEqual(len(org.ordem), len([x for x in self.f.faixas]))

    def test_com_dublagens_e_legenda_externa(self):
        pt = Dublagem(arquivo="dub.mkv", faixa=0, nome="Herbert Richers", idioma="por")
        es = Dublagem(arquivo="dub.mkv", faixa=1, nome="Latino", idioma="spa")
        leg = LegendaExterna(arquivo="filme.srt", idioma="por", nome="Português")
        org = core.organizar_padrao(self.f, [es, pt], [leg])
        itens = core.itens_saida(self.f, [es, pt], [leg], org)
        self.assertEqual(itens["audio"], [("dub", pt), ("filme", 6), ("filme", 1), ("dub", es)])
        # a externa (completa) substitui a completa do filme; a forcada do filme continua
        self.assertEqual(itens["subtitle"], [("leg", leg), ("filme", 8)])
        self.assertEqual(core.padroes_efetivos(itens, org)[0], ("dub", pt))
        # uma externa forcada substitui a forcada do filme (a completa do filme continua)
        leg.forcada = True
        org = core.organizar_padrao(self.f, [es, pt], [leg])
        self.assertEqual(core.itens_saida(self.f, [es, pt], [leg], org)["subtitle"], [("filme", 10), ("leg", leg)])
        # completa e forcada externas: nenhuma PT-BR do filme
        leg.forcada = False
        leg2 = LegendaExterna(arquivo="filme.forced.srt", idioma="por", forcada=True)
        org = core.organizar_padrao(self.f, [], [leg2, leg])
        self.assertEqual(core.itens_saida(self.f, [], [leg2, leg], org)["subtitle"], [("leg", leg), ("leg", leg2)])

    def test_idioma_original_escolhido(self):
        org = core.organizar_padrao(self.f, idioma_original="ger")
        self.assertEqual(core.itens_saida(self.f, [], [], org)["audio"], [("filme", 6), ("filme", 4)])

    def test_filme_nacional(self):
        f = Arquivo(caminho="x.mkv", faixas=[Faixa(0, "video"), Faixa(1, "audio", idioma="por", pos=0),
                                             Faixa(2, "audio", idioma="eng", titulo="Commentary", pos=1,
                                                   disposicao={"comment": 1})])
        self.assertEqual(core.idioma_original_auto(f), "por")
        self.assertEqual(core.itens_saida(f, [], [], core.organizar_padrao(f))["audio"], [("filme", 1)])


class TestOrdem(unittest.TestCase):
    def test_completar_e_remover(self):
        f = filme_ficticio()
        d = Dublagem(arquivo="dub.mkv", faixa=0)
        ordem = core.completar_ordem(f, [d], [], [("dub", d), ("filme", 6), ("filme", 99)])
        self.assertEqual(ordem[:2], [("dub", d), ("filme", 6)])      # o que existe fica na posicao
        self.assertNotIn(("filme", 99), ordem)                       # faixa que nao existe sai
        self.assertEqual(len(ordem), 12 + 1)
        ordem2 = core.completar_ordem(f, [], [], ordem)              # a dublagem saiu da lista
        self.assertNotIn(("dub", d), ordem2)

    def test_dublagens_iguais_sao_faixas_diferentes(self):
        a, b = Dublagem(arquivo="x.mkv", faixa=0), Dublagem(arquivo="x.mkv", faixa=0)
        self.assertNotEqual(("dub", a), ("dub", b))

    def test_sem_organizacao_e_o_jeito_antigo(self):
        f = filme_ficticio()
        d = Dublagem(arquivo="dub.mkv", faixa=0)
        itens = core.itens_saida(f, [d], [], Organizacao())
        self.assertEqual(itens["audio"][-1], ("dub", d))
        self.assertEqual(len(itens["audio"]), 7)

    def test_disposicoes(self):
        f = filme_ficticio()
        fx = core._faixa_por_idx(f)
        self.assertEqual(core.disposicao(f, ("filme", 8), False, fx), "forced")
        self.assertEqual(core.disposicao(f, ("filme", 8), True, fx), "default+forced")
        self.assertEqual(core.disposicao(f, ("filme", 3), False, fx), "comment")
        self.assertEqual(core.disposicao(f, ("filme", 1), False, fx), "0")          # o "default" antigo sai
        self.assertEqual(core.disposicao(f, ("leg", LegendaExterna("a.srt", forcada=True)), False), "forced")


class TestUtf8(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.pasta, ignore_errors=True)

    def gravar(self, nome, dados):
        p = os.path.join(self.pasta, nome)
        with open(p, "wb") as f:
            f.write(dados)
        return p

    TEXTO = "1\r\n00:00:01,000 --> 00:00:02,000\r\nAção, coração e pão!\r\n"

    def test_windows_1252(self):
        p = self.gravar("a.srt", self.TEXTO.encode("cp1252"))
        novo, origem = core.para_utf8(p, os.path.join(self.pasta, "b.srt"))
        self.assertEqual(origem, "windows-1252")
        with open(novo, encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), self.TEXTO)

    def test_utf16(self):
        p = self.gravar("a.srt", codecs.BOM_UTF16_LE + self.TEXTO.encode("utf-16-le"))
        novo, origem = core.para_utf8(p, os.path.join(self.pasta, "b.srt"))
        self.assertEqual(origem, "utf-16")
        with open(novo, encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), self.TEXTO)

    def test_utf8_fica_como_esta(self):
        for dados in (self.TEXTO.encode("utf-8"), codecs.BOM_UTF8 + self.TEXTO.encode("utf-8")):
            p = self.gravar("a.srt", dados)
            self.assertEqual(core.para_utf8(p, os.path.join(self.pasta, "b.srt")), (p, "utf-8"))


def srt(linhas):
    """[(ini, fim, texto)] -> texto SRT."""
    def t(s):
        ms = int(round(s * 1000))
        return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)
    return "".join("%d\r\n%s --> %s\r\n%s\r\n\r\n" % (i + 1, t(a), t(b), x) for i, (a, b, x) in enumerate(linhas))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "precisa do FFmpeg")
class TestMontagemReal(unittest.TestCase):
    """Monta de verdade e confere com o ffprobe: ordem, idiomas, titulos, marcas, acentos e atraso da legenda."""

    @classmethod
    def setUpClass(cls):
        import sinais
        cls.pasta = p = tempfile.mkdtemp(prefix="eternaldub_org_")
        cls.ferr = core.achar_ferramentas()
        x_eng = sinais.tons(30.0, base=300.0, semente=3)
        x_por = sinais.tons(30.0, base=700.0, semente=4)
        for nome, x in (("eng", x_eng), ("por", x_por)):
            sinais.gravar_wav(os.path.join(p, nome + ".wav"), x)
        with open(os.path.join(p, "s_eng.srt"), "w", encoding="utf-8") as f:
            f.write(srt([(1, 2, "Hello"), (20, 21, "Bye")]))
        with open(os.path.join(p, "s_por.srt"), "w", encoding="utf-8") as f:
            f.write(srt([(5, 6, "Placa: SAÍDA")]))
        cls.filme = os.path.join(p, "filme.mkv")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x48:r=24:d=30",
                        "-i", os.path.join(p, "eng.wav"), "-i", os.path.join(p, "por.wav"),
                        "-i", os.path.join(p, "s_eng.srt"), "-i", os.path.join(p, "s_por.srt"),
                        "-map", "0", "-map", "1", "-map", "2", "-map", "3", "-map", "4",
                        "-c:v", "mpeg4", "-c:a", "flac", "-c:s", "srt",
                        "-metadata:s:a:0", "language=eng", "-metadata:s:a:1", "language=por",
                        "-metadata:s:s:0", "language=eng", "-metadata:s:s:1", "language=por",
                        "-metadata:s:s:1", "title=Forçada", "-disposition:a:0", "default",
                        "-disposition:s:1", "forced", cls.filme], check=True, stdin=subprocess.DEVNULL)
        cls.dub = sinais.dublagem_flac(p, "dub", sinais.tons(30.0, base=500.0, semente=5))
        cls.srt_ansi = os.path.join(p, "externa.srt")              # legenda externa em Windows-1252
        with open(cls.srt_ansi, "wb") as f:
            f.write(srt([(3.0, 4.0, "Não há ação aqui"), (10.0, 11.5, "Coração")]).encode("cp1252"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def sondar(self, arq):
        return core.sondar_arquivo(arq)

    def legenda_do_arquivo(self, arq, pos):
        return subprocess.run(["ffmpeg", "-v", "error", "-i", arq, "-map", "0:s:%d" % pos, "-f", "srt", "-"],
                              stdout=subprocess.PIPE, check=True, stdin=subprocess.DEVNULL).stdout.decode("utf-8")

    def test_padrao_bdremux_ptbr(self):
        film = self.sondar(self.filme)
        d = Dublagem(arquivo=self.dub, faixa=0, nome="Herbert Richers", idioma="por", atraso_ms=250)
        leg = LegendaExterna(arquivo=self.srt_ansi, nome="Português (Brasil)", idioma="por", atraso_ms=-1000)
        org = core.organizar_padrao(film, [d], [leg])
        saida = os.path.join(self.pasta, "final.mkv")
        core.montar(film, [d], saida, False, self.ferr, lambda m: None, lambda v: None, org=org, legendas=[leg])
        out = self.sondar(saida)
        tipos = [f.tipo for f in out.faixas]
        self.assertEqual(tipos, ["video", "audio", "audio", "audio", "subtitle", "subtitle"])
        a = out.audios
        self.assertEqual([x.idioma for x in a], ["por", "por", "eng"])     # dublagem, PT do filme, original
        self.assertEqual(a[0].titulo, "Herbert Richers")
        self.assertEqual([x.disposicao.get("default") for x in a], [1, 0, 0])   # so a 1a toca sozinha
        s, forcada = out.legendas
        self.assertEqual((s.idioma, s.titulo), ("por", "Português (Brasil)"))
        self.assertEqual(s.disposicao.get("default"), 0)                   # legenda nao aparece sozinha
        self.assertEqual((forcada.idioma, forcada.titulo), ("por", "Forçada"))   # a forcada do filme continua
        self.assertEqual((forcada.disposicao.get("forced"), forcada.disposicao.get("default")), (1, 0))
        texto = self.legenda_do_arquivo(saida, 0)
        self.assertIn("Não há ação aqui", texto)                           # acentos da legenda ANSI
        self.assertIn("00:00:02,000 --> 00:00:03,000", texto)              # 1 s mais cedo
        self.assertIn("00:00:09,000 --> 00:00:10,500", texto)
        # a verificacao de integridade acha os fluxos do filme mesmo em outra ordem
        res = core.verificar_integridade(film, saida, self.ferr, lambda m: None, lambda v: None, manter=org.manter)
        self.assertTrue(res and all(ok for _, ok in res), res)
        # e a conferencia sabe onde ficou a dublagem
        pos, nomes, ref = core.posicoes_para_conferencia(film, [d], [leg], org, 0)
        self.assertEqual((pos, nomes, ref), ([0], ["Herbert Richers"], 2))

    def test_legendas_do_filme_mantem_forcada_e_ordem_escolhida(self):
        film = self.sondar(self.filme)
        legs = [f.idx for f in film.legendas]
        org = Organizacao(ordem=[("filme", legs[1]), ("filme", legs[0])], padrao_legenda=("filme", legs[0]))
        saida = os.path.join(self.pasta, "final2.mkv")
        core.montar(film, [], saida, False, self.ferr, lambda m: None, lambda v: None, org=org)  # sem dublagem
        out = self.sondar(saida)
        self.assertEqual([x.idioma for x in out.legendas], ["por", "eng"])
        self.assertEqual(out.legendas[0].disposicao.get("forced"), 1)        # continua forcada
        self.assertEqual(out.legendas[0].disposicao.get("default"), 0)
        self.assertEqual(out.legendas[1].disposicao.get("default"), 1)       # a escolhida como padrao
        self.assertEqual([x.idioma for x in out.audios], ["eng", "por"])     # audios na ordem do arquivo
        self.assertIn("SAÍDA", self.legenda_do_arquivo(saida, 0))

    def test_atraso_positivo_da_legenda(self):
        film = self.sondar(self.filme)
        leg = LegendaExterna(arquivo=self.srt_ansi, idioma="por", atraso_ms=2500)
        org = Organizacao(manter={f.idx for f in film.videos} | {film.audios[0].idx})
        saida = os.path.join(self.pasta, "final3.mkv")
        core.montar(film, [], saida, False, self.ferr, lambda m: None, lambda v: None, org=org, legendas=[leg])
        self.assertIn("00:00:05,500 --> 00:00:06,500", self.legenda_do_arquivo(saida, 0))

    def test_legenda_de_um_mp4_vira_srt(self):
        """Legenda mov_text (de um .mp4): o MKV nao aceita, entao ela entra como SRT, com o texto certo."""
        mp4 = os.path.join(self.pasta, "legenda.mp4")
        with open(os.path.join(self.pasta, "mp4.srt"), "w", encoding="utf-8") as f:
            f.write(srt([(2.0, 3.0, "Legenda do MP4: ação")]))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x48:r=24:d=10",
                        "-i", os.path.join(self.pasta, "mp4.srt"), "-map", "0", "-map", "1", "-c:v", "mpeg4",
                        "-c:s", "mov_text", "-metadata:s:s:0", "language=por", mp4], check=True,
                       stdin=subprocess.DEVNULL)
        arq = core.sondar_arquivo(mp4)
        self.assertEqual(arq.legendas[0].codec, "mov_text")
        film = self.sondar(self.filme)
        leg = LegendaExterna(arquivo=mp4, faixa=0, idioma="por", codec="mov_text")
        org = core.organizar_padrao(film, [], [leg])
        saida = os.path.join(self.pasta, "mp4.mkv")
        core.montar(film, [], saida, False, self.ferr, lambda m: None, lambda v: None, org=org, legendas=[leg])
        final = self.sondar(saida)
        self.assertEqual(final.legendas[0].codec, "subrip")             # a do MP4, primeiro (a forcada do filme depois)
        self.assertIn("Legenda do MP4: ação", self.legenda_do_arquivo(saida, 0))

    def test_projeto_guarda_a_organizacao(self):
        film = self.sondar(self.filme)
        d = Dublagem(arquivo=self.dub, faixa=0)
        leg = LegendaExterna(arquivo=self.srt_ansi, idioma="por")
        org = core.organizar_padrao(film, [d], [leg])
        org.padrao_legenda = ("leg", leg)
        caminho = os.path.join(self.pasta, "p.eternaldub")
        core.salvar_projeto(caminho, self.filme, 0, [d], org.manter, [leg], org, "eng", True)
        p = core.abrir_projeto(caminho)
        d2, l2 = p["dublagens"][0], p["legendas"][0]
        self.assertEqual(p["padrao_legenda"], ("leg", l2))
        self.assertEqual(p["manter"], org.manter)
        self.assertTrue(p["organizacao_manual"])
        trad = {id(d): d2, id(leg): l2}
        esperado = [(k[0], trad[id(k[1])]) if k[0] != "filme" else k for k in org.ordem]
        self.assertEqual(p["ordem"], esperado)
        self.assertIsNone(p["padrao_audio"])                    # o primeiro audio
        # a dublagem marcada como padrao num projeto antigo nao volta a ser padrao se a organizacao diz outra coisa
        d.padrao = True
        core.salvar_projeto(caminho, self.filme, 0, [d], org.manter, [leg], org, "eng", True)
        self.assertIsNone(core.abrir_projeto(caminho)["padrao_audio"])
        org.padrao_audio = ("dub", d)
        core.salvar_projeto(caminho, self.filme, 0, [d], org.manter, [leg], org, "eng", True)
        p = core.abrir_projeto(caminho)
        self.assertEqual(p["padrao_audio"], ("dub", p["dublagens"][0]))
        self.assertTrue(p["dublagens"][0].padrao)               # (o que as versoes antigas leem)
        # projeto antigo (sem organizacao): vale a dublagem marcada
        core.salvar_projeto(caminho, self.filme, 0, [d], None)
        p = core.abrir_projeto(caminho)
        self.assertEqual(p["padrao_audio"], ("dub", p["dublagens"][0]))
        self.assertIsNone(p["ordem"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
