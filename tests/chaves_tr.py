# SPDX-License-Identifier: MIT
"""Acha todos os textos de interface (chamadas tr("...") e N_("...")) nos arquivos .py do projeto."""
import ast
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVOS = ["EternalDub_gui.py", "EternalDub_core.py", "EternalDub_emendas.py", "EternalDub_audio.py",
            "EternalDub_i18n.py", "detectar_atraso.py"]
# textos que nao precisam de traducao (nomes proprios, siglas, formatos)
SEM_TRADUCAO = {"OK"}


def chaves_do_codigo():
    """{texto: [(arquivo, linha), ...]}"""
    achados = {}
    for nome in ARQUIVOS:
        with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
            arvore = ast.parse(f.read(), nome)
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id in ("tr", "N_") \
                    and no.args and isinstance(no.args[0], ast.Constant) and isinstance(no.args[0].value, str):
                achados.setdefault(no.args[0].value, []).append((nome, no.lineno))
    return achados


if __name__ == "__main__":
    import json
    chaves = chaves_do_codigo()
    en = json.load(open(os.path.join(RAIZ, "idiomas", "en.json"), encoding="utf-8"))["textos"]
    faltam = [k for k in chaves if k not in en and k not in SEM_TRADUCAO]
    sobram = [k for k in en if k not in chaves]
    print("no codigo: %d | em en.json: %d | FALTAM: %d | SOBRAM: %d" % (len(chaves), len(en), len(faltam), len(sobram)))
    for k in faltam:
        print("FALTA:", repr(k))
    for k in sobram:
        print("SOBRA:", repr(k))
