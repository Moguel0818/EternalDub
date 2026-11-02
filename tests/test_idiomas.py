# SPDX-License-Identifier: MIT
"""
Confere os arquivos de idioma (idiomas/*.json). Quem traduz pode rodar:   python tests/test_idiomas.py
Mostra o que falta traduzir e o que esta errado (marcadores %s/%d trocados, quebras de linha perdidas...).

Translators can run:   python tests/test_idiomas.py   to see what is missing and what is wrong.
"""
import glob
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chaves_tr

RAIZ = chaves_tr.RAIZ
MARCADORES = re.compile(r"%%|%[-+#0]*\d*(?:\.\d+)?[sdifxXeEgGc]")
OFICIAIS = ("en", "es", "fr", "it", "de")           # estes precisam estar COMPLETOS


def carregar(arquivo):
    with open(arquivo, encoding="utf-8") as f:
        return json.load(f)


def problemas(dados, chaves_do_codigo):
    """(erros, faltando): erros = o que esta errado; faltando = chaves sem traducao (cai no ingles)."""
    erros = []
    textos = dados.get("textos", {})
    for campo in ("codigo", "nome", "textos"):
        if campo not in dados:
            erros.append("falta o campo '%s'" % campo)
    for k, v in textos.items():
        if not isinstance(v, str) or not v.strip():
            erros.append("traducao vazia: %r" % k[:60])
            continue
        if MARCADORES.findall(k) != MARCADORES.findall(v):
            erros.append("marcadores diferentes em %r -> %r (esperado %s)" % (k[:50], v[:50], MARCADORES.findall(k)))
        if k.count("\n") != v.count("\n"):
            erros.append("quebras de linha diferentes em %r" % k[:50])
        if k.endswith("...") and not v.rstrip().endswith(("...", "…")):
            erros.append("o original termina em '...' e a traducao nao: %r -> %r" % (k[:50], v[:50]))
    faltando = [k for k in chaves_do_codigo if k not in textos and k not in chaves_tr.SEM_TRADUCAO]
    return erros, faltando


class TestIdiomas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chaves = chaves_tr.chaves_do_codigo()
        cls.arquivos = sorted(glob.glob(os.path.join(RAIZ, "idiomas", "*.json")))

    def test_ha_idiomas(self):
        nomes = [os.path.basename(a)[:-5] for a in self.arquivos]
        for oficial in OFICIAIS:
            self.assertIn(oficial, nomes, "falta idiomas/%s.json" % oficial)

    def test_cada_arquivo_e_valido(self):
        for arq in self.arquivos:
            with self.subTest(arq=os.path.basename(arq)):
                dados = carregar(arq)
                self.assertEqual(dados["codigo"], os.path.basename(arq)[:-5])
                erros, _ = problemas(dados, self.chaves)
                self.assertEqual(erros, [], "\n".join(erros[:15]))

    def test_idiomas_oficiais_estao_completos(self):
        for codigo in OFICIAIS:
            arq = os.path.join(RAIZ, "idiomas", codigo + ".json")
            if not os.path.isfile(arq):
                continue
            with self.subTest(idioma=codigo):
                _, faltando = problemas(carregar(arq), self.chaves)
                self.assertEqual(faltando, [], "faltam %d textos, por exemplo:\n%s" % (
                    len(faltando), "\n".join(repr(k[:70]) for k in faltando[:10])))

    def test_ingles_nao_tem_textos_que_o_codigo_nao_usa(self):
        en = carregar(os.path.join(RAIZ, "idiomas", "en.json"))["textos"]
        sobram = [k for k in en if k not in self.chaves]
        self.assertEqual(sobram, [], "textos de en.json que nenhum tr() usa:\n%s" % "\n".join(repr(k[:70]) for k in sobram))

    def test_carregador_usa_os_arquivos(self):
        import EternalDub_i18n as i18n
        self.assertIn("en", i18n.disponiveis())
        i18n.definir("en")
        try:
            self.assertEqual(i18n.tr("Abrir filme..."), "Open movie...")
            self.assertEqual(i18n.tr("texto que ninguem traduziu"), "texto que ninguem traduziu")
        finally:
            i18n.definir("pt")
        self.assertEqual(i18n.tr("Abrir filme..."), "Abrir filme...")

    def test_idioma_do_sistema(self):
        import EternalDub_i18n as i18n
        self.assertEqual(i18n.para_codigo("pt_PT.UTF-8"), "pt")
        self.assertEqual(i18n.para_codigo("en_GB"), "en")
        self.assertEqual(i18n.para_codigo("sw_KE"), "en")                       # sem traducao: ingles
        if "es" in i18n.disponiveis():
            self.assertEqual(i18n.para_codigo("es_MX.UTF-8"), "es")
            self.assertEqual(i18n.para_codigo("Spanish_Spain"), "es")


def relatorio():
    chaves = chaves_tr.chaves_do_codigo()
    print("Textos da interface no codigo: %d\n" % len(chaves))
    for arq in sorted(glob.glob(os.path.join(RAIZ, "idiomas", "*.json"))):
        dados = carregar(arq)
        erros, faltando = problemas(dados, chaves)
        print("%-6s %-22s %s  | faltam: %d | erros: %d" % (dados.get("codigo"), dados.get("nome"),
              "completo" if not faltando else "incompleto", len(faltando), len(erros)))
        for e in erros[:20]:
            print("    ERRO:", e)
        for k in faltando[:10]:
            print("    falta:", repr(k[:80]))
        if len(faltando) > 10:
            print("    ... e mais %d" % (len(faltando) - 10))


if __name__ == "__main__":
    if len(sys.argv) == 1:
        relatorio()
    else:
        unittest.main()
