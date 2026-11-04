# SPDX-License-Identifier: MIT
# EternalDub - Copyright (C) 2026 Moguel0818 e colaboradores / and contributors
# -*- coding: utf-8 -*-
"""
EternalDub_i18n.py - idiomas da interface.

Como funciona: o texto em portugues (Brasil) e a "chave". tr("Abrir filme...") devolve o proprio texto quando o
idioma e portugues, ou a traducao que esta no arquivo do idioma (pasta `idiomas/`). Se o idioma escolhido nao tiver
uma traducao, usa a do ingles; se nem essa existir, o proprio texto em portugues.

TRADUZIR NAO PRECISA DE PROGRAMACAO: copie idiomas/en.json para idiomas/<codigo>.json (ex.: fr.json), troque
"codigo", "nome" e "tradutores" e traduza o que vem depois dos dois pontos em "textos". O idioma aparece
sozinho em Opcoes > Idioma. Mantenha %s, %d, %.1f, %+d... na MESMA ordem e \\n onde ha quebra de linha.
Para conferir o arquivo: python tests/test_idiomas.py

Translating needs no programming: copy idiomas/en.json to idiomas/<code>.json (e.g. fr.json), change "codigo",
"nome" and "tradutores", and translate the values in "textos". The language shows up by itself in Options >
Language. Keep %s, %d, %.1f, %+d... in the SAME order and \\n wherever there is a line break.
"""
import json
import locale
import os
import sys
from pathlib import Path

VERSAO_IDIOMAS = "1.4"

NOME_PT = "Português (Brasil)"
_atual = "pt"
_textos = {}          # traducoes do idioma atual
_textos_en = {}       # traducoes do ingles (usadas quando faltar uma no idioma atual)
_cache = {}           # codigo -> dados do arquivo


def pasta_idiomas():
    """Pasta `idiomas/` ao lado dos arquivos .py (ou dentro do programa empacotado)."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent
    return base / "idiomas"


def _ler(arquivo):
    with open(arquivo, "r", encoding="utf-8") as f:
        dados = json.load(f)
    if not isinstance(dados.get("textos"), dict):
        raise ValueError("falta 'textos'")
    return dados


def descobrir():
    """{codigo: dados} de todos os arquivos da pasta idiomas/ que estiverem validos (os com erro sao ignorados)."""
    achados = {}
    try:
        arquivos = sorted(pasta_idiomas().glob("*.json"))
    except OSError:
        arquivos = []
    for a in arquivos:
        try:
            dados = _ler(a)
        except (OSError, ValueError):
            continue
        codigo = str(dados.get("codigo") or a.stem).strip().lower()
        if codigo and codigo != "pt":
            dados["codigo"] = codigo
            dados["arquivo"] = str(a)
            achados[codigo] = dados
    return achados


def _montar_lista():
    achados = descobrir()
    _cache.clear()
    _cache.update(achados)
    nomes = sorted(((d.get("nome") or c, c) for c, d in achados.items()),
                   key=lambda x: (x[1] != "en", x[0].lower()))          # ingles primeiro, depois por nome
    return (("pt", NOME_PT),) + tuple((c, n) for n, c in nomes)


IDIOMAS = _montar_lista()       # (("pt", "Português (Brasil)"), ("en", "English"), ...)
PASTA_OK = len(IDIOMAS) > 1     # False: a pasta idiomas/ nao foi encontrada (so o portugues funciona)


def disponiveis():
    return [c for c, _ in IDIOMAS]


def definir(codigo):
    """Escolhe o idioma. Um codigo que nao existe vira portugues."""
    global _atual, _textos, _textos_en
    codigo = (codigo or "pt").lower()
    _atual = codigo if codigo in _cache else "pt"
    _textos = _cache[_atual]["textos"] if _atual != "pt" else {}
    _textos_en = _cache["en"]["textos"] if "en" in _cache else {}


def atual():
    return _atual


def tradutores(codigo=None):
    """Nomes de quem traduziu o idioma (para a janela 'Sobre')."""
    d = _cache.get(codigo or _atual)
    return list(d.get("tradutores") or []) if d else []


def para_codigo(nome):
    """'es_MX.UTF-8' -> 'es'; 'pt_BR' -> 'pt'; 'French_France' -> 'fr'; um idioma sem traducao -> 'en'."""
    v = (nome or "").lower().replace("-", "_")
    por_nome = {"portuguese": "pt", "spanish": "es", "french": "fr", "german": "de", "italian": "it",
                "english": "en", "japanese": "ja", "russian": "ru", "chinese": "zh", "korean": "ko"}
    base = v.split("_")[0].split(".")[0]
    base = por_nome.get(base, base)
    return base if base == "pt" or base in _cache else "en"


def do_sistema():
    """Idioma do sistema se houver traducao dele ('pt' inclui o portugues de Portugal); senao 'en'."""
    for nome in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        v = os.environ.get(nome, "")
        if v:
            return para_codigo(v.split(":")[0])
    try:
        v = locale.getlocale()[0] or ""
    except Exception:
        v = ""
    return para_codigo(v) if v else "pt"


def tr(texto):
    """Traduz um texto da interface (a chave e o texto em portugues)."""
    if _atual == "pt":
        return texto
    t = _textos.get(texto)
    return t if t is not None else _textos_en.get(texto, texto)


def N_(texto):
    """Marca um texto para traducao sem traduzir agora (ele e traduzido depois, com tr())."""
    return texto


def rot_conf(c):
    return {"ALTA": tr("ALTA"), "MEDIA": tr("MÉDIA"), "BAIXA": tr("BAIXA")}.get(c, c)


def rot_metodo(m):
    return {"audio": tr("áudio"), "video": tr("vídeo")}.get(m, m)


def rot_status(s):
    return {"OK": "OK", "VELOCIDADE": tr("VELOCIDADE"), "DERIVA": tr("DERIVA"), "CORTES": tr("CORTES"),
            "BAIXA_CONFIANCA": tr("SEM CORRESPONDÊNCIA")}.get(s, s)


def rot_tipo(t):
    return {"video": tr("vídeo"), "audio": tr("áudio"), "subtitle": tr("legenda"), "attachment": tr("anexo"),
            "data": tr("dados")}.get(t, t)
