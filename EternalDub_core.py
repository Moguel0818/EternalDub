# SPDX-License-Identifier: MIT
# EternalDub - Copyright (C) 2026 Moguel0818 e colaboradores / and contributors
# -*- coding: utf-8 -*-
"""
EternalDub_core.py - nucleo do EternalDub (tudo que NAO e interface grafica).

  * le as faixas dos arquivos (ffprobe);
  * le o audio LEVE so para analise (mono 8 kHz): trechos com salto direto para detectar,
    e a onda completa em segundo plano, com progresso e cache (o filme UHD so e lido uma vez);
  * detecta o atraso (usa o detectar_atraso.py; analise rapida por trechos);
  * monta o MKV final SEM RECODIFICAR (FFmpeg com -c copy, ou mkvmerge);
  * verifica se os fluxos originais do filme continuam identicos (hash).

A unica conversao que existe e opcional: corrigir a VELOCIDADE de uma dublagem
(ex.: PAL 25 fps -> 23,976 fps) converte SO essa dublagem para FLAC. O video nunca e tocado.
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from EternalDub_i18n import tr
import detectar_atraso as da

VERSAO_NUCLEO = "1.0"
if getattr(da, "VERSAO_DETECTOR", None) != VERSAO_NUCLEO:
    raise ImportError(tr("detectar_atraso.py (versão %s) e EternalDub_core.py (versão %s) não combinam.\n"
                         "Arquivo encontrado: %s") % (getattr(da, "VERSAO_DETECTOR", tr("antiga")), VERSAO_NUCLEO,
                                                      getattr(da, "__file__", "?")))

CRIAR_SEM_JANELA = 0x08000000 if sys.platform == "win32" else 0
CACHE_DIR = Path.home() / ".eternaldub" / "cache"
ENV_BASE = 80                                  # amostras por ponto do envelope (10 ms a 8 kHz)
ENV_RATE = da.SR_AUDIO / ENV_BASE              # pontos de envelope por segundo (100)
Cancelado = da.Cancelado


# ----------------------------------------------------------------- ferramentas
MKVMERGE_EXTRAS = [r"C:\Program Files\MKVToolNix\mkvmerge.exe",
                   r"C:\Program Files (x86)\MKVToolNix\mkvmerge.exe"]


@dataclass
class Ferramentas:
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    mkvmerge: str = ""

    def aplicar(self):
        da.FFMPEG, da.FFPROBE = self.ffmpeg, self.ffprobe


def achar_ferramentas(salvas=None):
    salvas = salvas or {}
    f = Ferramentas()
    for nome in ("ffmpeg", "ffprobe"):
        caminho = salvas.get(nome) or shutil.which(nome) or ""
        setattr(f, nome, caminho if caminho and (os.path.isfile(caminho) or shutil.which(caminho)) else nome)
    mk = salvas.get("mkvmerge") or shutil.which("mkvmerge") or ""
    if not mk:
        for e in MKVMERGE_EXTRAS:
            if os.path.isfile(e):
                mk = e
                break
    f.mkvmerge = mk
    f.aplicar()
    return f


def versoes(f):
    """Texto curto com as versoes do FFmpeg e do mkvmerge (ajuda a diagnosticar problemas)."""
    partes = []
    for nome, cmd in (("ffmpeg", [f.ffmpeg, "-version"]), ("mkvmerge", [f.mkvmerge, "--version"] if f.mkvmerge else None)):
        if not cmd:
            continue
        try:
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=CRIAR_SEM_JANELA,
                               timeout=15)
            linha = p.stdout.decode("utf-8", "replace").strip().splitlines()[0]
            partes.append(" ".join(linha.split()[:3]))
        except Exception:
            partes.append(nome + " (?)")
    return " | ".join(partes)


def ffmpeg_ok(f):
    return bool(shutil.which(f.ffmpeg) or os.path.isfile(f.ffmpeg)) and \
           bool(shutil.which(f.ffprobe) or os.path.isfile(f.ffprobe))


# ----------------------------------------------------------------- arquivos e faixas
@dataclass
class Faixa:
    idx: int            # indice do fluxo no arquivo
    tipo: str           # video / audio / subtitle / attachment ...
    codec: str = ""
    canais: int = 0
    idioma: str = ""
    titulo: str = ""
    pos: int = 0        # posicao dentro do proprio tipo (0 = primeira faixa de audio, etc.)
    inicio: float = 0.0     # onde a faixa comeca (s)
    duracao: float = 0.0    # duracao DA FAIXA (s); 0 = desconhecida (usa a do arquivo)

    def rotulo(self):
        partes = [self.codec]
        if self.canais:
            partes.append("%dch" % self.canais)
        if self.idioma:
            partes.append(self.idioma)
        if self.titulo:
            partes.append(self.titulo)
        return " | ".join(p for p in partes if p)


@dataclass
class Arquivo:
    caminho: str
    faixas: list = field(default_factory=list)
    duracao: float = 0.0
    inicio: float = 0.0

    def do_tipo(self, tipo):
        return [f for f in self.faixas if f.tipo == tipo]

    def fim_audio(self, pos):
        """Ate onde vai o audio da faixa `pos` (s). Uma dublagem de TV pode acabar antes do video."""
        f = self.audios[pos]
        if f.duracao > 0:
            return min(self.duracao, f.inicio + f.duracao) if self.duracao else f.inicio + f.duracao
        return self.duracao

    @property
    def audios(self):
        return self.do_tipo("audio")

    @property
    def videos(self):
        return self.do_tipo("video")

    @property
    def legendas(self):
        return self.do_tipo("subtitle")


def _flt(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def sondar_arquivo(caminho):
    cmd = [da.FFPROBE, "-v", "error", "-show_entries",
           "stream=index,codec_type,codec_name,channels,start_time,duration:stream_tags=language,title,DURATION"
           ":format=duration,start_time",
           "-of", "json", caminho]
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=CRIAR_SEM_JANELA)
    except FileNotFoundError:
        raise RuntimeError(tr("ffprobe não encontrado. Instale o FFmpeg (ou indique o caminho em Opções)."))
    if p.returncode != 0:
        raise RuntimeError(tr("Não consegui abrir o arquivo:\n%s\n%s") % (caminho, p.stderr.decode("utf-8", "replace")))
    j = json.loads(p.stdout.decode("utf-8", "replace"))
    arq = Arquivo(caminho=caminho, duracao=_flt(j.get("format", {}).get("duration")),
                  inicio=_flt(j.get("format", {}).get("start_time")))
    contagem = {}
    for s in j.get("streams", []):
        tipo = s.get("codec_type", "")
        tags = s.get("tags", {}) or {}
        pos = contagem.get(tipo, 0)
        contagem[tipo] = pos + 1
        dur = _flt(s.get("duration")) or _segundos(tags.get("DURATION") or tags.get("duration") or "")
        arq.faixas.append(Faixa(idx=int(s.get("index", 0)), tipo=tipo, codec=s.get("codec_name", ""),
                                canais=int(s.get("channels", 0) or 0),
                                idioma=(tags.get("language") or tags.get("LANGUAGE") or "").lower(),
                                titulo=tags.get("title") or tags.get("TITLE") or "", pos=pos,
                                inicio=_flt(s.get("start_time")), duracao=dur))
    return arq


def nome_sugerido(titulo, padrao="Dublagem"):
    """'Herbert Richers - MP3 2.0' -> 'Herbert Richers'."""
    t = re.sub(r"[\s\-_]*\b(MP3|AC3|E-?AC3|DTS(-HD)?|AAC|FLAC|PCM|TRUEHD)\b[\s\-_.0-9]*$", "", titulo or "",
               flags=re.I).strip(" -_")
    return t or padrao


def faixa_ingles(arq):
    for f in arq.audios:
        if f.idioma in ("eng", "en"):
            return f.pos
    return 0


# ----------------------------------------------------------------- audio para ANALISE (leve)
# O audio e lido como mono, 8 kHz, 16 bits (~1 MB por minuto) SO para medir e desenhar a onda.
# O arquivo final nunca usa isto: ele recebe as faixas ORIGINAIS, copiadas sem alteracao.
#
# Onde estava a demora: num remux UHD ~95% dos bytes sao VIDEO, intercalado com o audio no
# disco.  Para tirar o audio do filme inteiro, o FFmpeg precisa ler o arquivo INTEIRO (dezenas
# de GB), nao importa a taxa de amostragem usada.  Por isso:
#   * a DETECCAO le so trechos, pulando direto para eles (trecho());
#   * a ONDA completa e lida uma vez so, em segundo plano, com progresso, e fica guardada
#     (carregar_completo()); varias faixas do mesmo arquivo saem na MESMA leitura.
_TRAVA = threading.Lock()
_MEM = OrderedDict()          # (caminho, pos) -> audio completo ja carregado (os mais recentes)
_MEM_MAX = 3
_TRECHOS = OrderedDict()      # trechos lidos com salto (cache pequeno)
_EM_ANDAMENTO = {}            # chave -> {"evento": Event, "fracao": float}


def _chave(caminho, pos):
    st = os.stat(caminho)
    base = "%s|%d|%d|%d|%d|v3" % (os.path.abspath(caminho), st.st_size, int(st.st_mtime), pos, da.SR_AUDIO)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def arquivo_cache(caminho, pos):
    return CACHE_DIR / (_chave(caminho, pos) + ".s16")


def em_cache(caminho, pos):
    try:
        return arquivo_cache(caminho, pos).is_file()
    except OSError:
        return False


def _do_disco(caminho, pos):
    k = (os.path.abspath(caminho), pos)
    with _TRAVA:
        if k in _MEM:
            _MEM.move_to_end(k)
            return _MEM[k]
    x = np.fromfile(arquivo_cache(caminho, pos), dtype="<i2")
    with _TRAVA:
        _MEM[k] = x
        while len(_MEM) > _MEM_MAX:
            _MEM.popitem(last=False)
    return x


def _ler_novos(caminho_tmp, inicio_bytes):
    """Le o que o FFmpeg ja escreveu no arquivo temporario a partir de inicio_bytes."""
    try:
        with open(caminho_tmp, "rb") as f:
            f.seek(inicio_bytes)
            dados = f.read()
    except OSError:
        return np.zeros(0, np.int16), inicio_bytes
    n = len(dados) // 2 * 2
    return np.frombuffer(dados[:n], dtype="<i2").copy(), inicio_bytes + n


def _esperar_e_registrar(caminho, posicoes, cancelar, ao_progresso, duracao):
    """
    Se outra parte do programa ja esta lendo estas faixas, espera ela terminar. Depois registra
    as faixas que ainda faltam como "sendo lidas" por quem chamou. Devolve (faltam, registro).
    """
    while True:
        with _TRAVA:
            outros = [_EM_ANDAMENTO[_chave(caminho, p)] for p in posicoes if _chave(caminho, p) in _EM_ANDAMENTO]
            if not outros:
                faltam = [p for p in posicoes if not em_cache(caminho, p)]
                registro = {}
                for p in faltam:
                    registro[p] = {"evento": threading.Event(), "fracao": 0.0}
                    _EM_ANDAMENTO[_chave(caminho, p)] = registro[p]
                return faltam, registro
        while not outros[0]["evento"].wait(0.25):
            if cancelar.is_set():
                raise Cancelado()
            if ao_progresso:
                ao_progresso(outros[0]["fracao"], outros[0]["fracao"] * (duracao or 0))


def _liberar(caminho, registro):
    with _TRAVA:
        for p, reg in registro.items():
            _EM_ANDAMENTO.pop(_chave(caminho, p), None)
            reg["evento"].set()


class LeituraCompleta:
    """
    Leitura COMPLETA de uma ou mais faixas de um arquivo (todas na MESMA passada pelo disco),
    que pode ser PAUSADA e depois CONTINUADA do ponto onde parou: o que ja foi lido fica guardado
    em pedacos no cache, e a continuacao pede ao FFmpeg para pular direto ate la (-ss).
    """

    def __init__(self, caminho, posicoes, codecs=None, duracao=0.0):
        self.caminho = caminho
        self.posicoes = sorted({int(p) for p in posicoes})
        self.codecs = dict(codecs or {})
        self.duracao = float(duracao or 0.0)
        self.amostras = 0                        # amostras ja guardadas (o mesmo em todas as faixas)
        self.segs = {p: [] for p in self.posicoes}
        self._rodada = 0
        self._id = "%d.%x" % (os.getpid(), id(self))

    def concluida(self):
        return all(em_cache(self.caminho, p) for p in self.posicoes)

    def fracao(self):
        return min(1.0, self.amostras / da.SR_AUDIO / self.duracao) if self.duracao else 0.0

    def descartar(self):
        for lista in self.segs.values():
            for arq in lista:
                try:
                    os.remove(arq)
                except OSError:
                    pass
        self.segs = {p: [] for p in self.posicoes}
        self.amostras = 0

    def rodar(self, cancelar=None, ao_progresso=None, ao_parcial=None, ao_cortar=None, intervalo=2.0):
        """
        Le (ou continua lendo) ate o fim e grava o cache. Se `cancelar` for acionado, guarda o
        que ja leu (cortado no mesmo ponto em todas as faixas), chama ao_cortar(amostras_validas)
        e levanta Cancelado; chamar rodar() de novo continua dali.
        """
        cancelar = cancelar or threading.Event()
        faltam, registro = _esperar_e_registrar(self.caminho, self.posicoes, cancelar, ao_progresso, self.duracao)
        for p in self.posicoes:                  # faixas que outra leitura ja terminou
            if p not in faltam and self.segs.get(p):
                for arq in self.segs[p]:
                    try:
                        os.remove(arq)
                    except OSError:
                        pass
                self.segs[p] = []
        if not faltam:
            _liberar(self.caminho, registro)
            return
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._rodada += 1
        inicio = self.amostras / da.SR_AUDIO
        tmp = {p: "%s.%s.%d.part" % (arquivo_cache(self.caminho, p), self._id, self._rodada) for p in faltam}
        cmd = [da.FFMPEG, "-v", "error", "-nostdin", "-nostats", "-y", "-progress", "pipe:1"]
        if any((self.codecs.get(p) or "").lower() == "dts" for p in faltam):
            cmd += da.opcoes_decodificador("dts")   # so o nucleo DTS: mais leve, so para medir
        if inicio > 0:
            cmd += ["-ss", "%.4f" % inicio]        # continua de onde parou (pula direto)
        cmd += ["-i", self.caminho]
        for p in faltam:
            cmd += ["-map", "0:a:%d" % p, "-af", "aresample=async=1:first_pts=0", "-ac", "1",
                    "-ar", str(da.SR_AUDIO), "-c:a", "pcm_s16le", "-f", "s16le", tmp[p]]
        lidos = {p: 0 for p in faltam}
        estado = {"t": 0.0, "ult_prog": 0.0, "ult_parcial": time.monotonic()}

        def entregar_parciais():
            if ao_parcial:
                for p in faltam:
                    novos, lidos[p] = _ler_novos(tmp[p], lidos[p])
                    if len(novos):
                        ao_parcial(p, novos)
            estado["ult_parcial"] = time.monotonic()

        def linha(texto):
            if texto.startswith("out_time_us=") or texto.startswith("out_time_ms="):
                try:
                    estado["t"] = max(estado["t"], int(texto.split("=", 1)[1]) / 1e6)
                except ValueError:
                    return
                agora = time.monotonic()
                total = inicio + estado["t"]
                fr = min(0.999, total / self.duracao) if self.duracao else 0.0
                for reg in registro.values():
                    reg["fracao"] = fr
                if ao_progresso and agora - estado["ult_prog"] >= 0.4:
                    estado["ult_prog"] = agora
                    ao_progresso(fr, total)
                if agora - estado["ult_parcial"] >= intervalo:
                    entregar_parciais()

        sobra = [b""]

        def bloco(dados):
            partes = (sobra[0] + dados).split(b"\n")
            sobra[0] = partes.pop()
            for l in partes:
                linha(l.decode("ascii", "replace").strip())

        try:
            try:
                da._executar(cmd, bloco, cancelar, bloco=4096)
            except Cancelado:
                self._guardar_parcial(faltam, tmp)
                if ao_cortar:
                    ao_cortar(self.amostras)
                raise
            except Exception:
                for arq in tmp.values():
                    try:
                        os.remove(arq)
                    except OSError:
                        pass
                raise
            entregar_parciais()
            for p in faltam:                     # junta os pedacos na ordem e grava o cache final
                self.segs[p].append(tmp[p])
                final = arquivo_cache(self.caminho, p)
                junta = "%s.%s.junta.part" % (final, self._id)
                with open(junta, "wb") as saida:
                    for arq in self.segs[p]:
                        with open(arq, "rb") as f:
                            shutil.copyfileobj(f, saida, 1 << 20)
                os.replace(junta, final)
                for arq in self.segs[p]:
                    try:
                        os.remove(arq)
                    except OSError:
                        pass
                self.segs[p] = []
            if ao_progresso:
                ao_progresso(1.0, self.duracao)
        finally:
            _liberar(self.caminho, registro)

    def _guardar_parcial(self, faltam, tmp):
        tamanhos = []
        for p in faltam:
            try:
                tamanhos.append(os.path.getsize(tmp[p]) // 2)
            except OSError:
                tamanhos.append(0)
        n = min(tamanhos) // ENV_BASE * ENV_BASE if tamanhos else 0
        for p in faltam:
            try:
                if n > 0:
                    with open(tmp[p], "r+b") as f:
                        f.truncate(n * 2)
                    self.segs[p].append(tmp[p])
                elif os.path.exists(tmp[p]):
                    os.remove(tmp[p])
            except OSError:
                pass
        self.amostras += n


def carregar_completo(caminho, posicoes, codecs=None, duracao=0.0, cancelar=None,
                      ao_progresso=None, ao_parcial=None, intervalo_parcial=2.0, devolver=True):
    """
    Audio COMPLETO (mono 8 kHz int16) das faixas `posicoes` do arquivo, numa passada so pelo
    disco, guardado em cache (da 2a vez e instantaneo). Se for cancelada, descarta o que leu.
    """
    leitura = LeituraCompleta(caminho, posicoes, codecs, duracao)
    try:
        leitura.rodar(cancelar, ao_progresso, ao_parcial, None, intervalo_parcial)
    except Cancelado:
        leitura.descartar()
        raise
    return {p: _do_disco(caminho, p) for p in leitura.posicoes} if devolver else {}


def envelope_do_cache(caminho, pos):
    """Onda da faixa completa lida direto do cache no disco (sem guardar o audio na memoria)."""
    mm = np.memmap(arquivo_cache(caminho, pos), dtype="<i2", mode="r")
    try:
        return envelope(mm)
    finally:
        del mm


def trecho(caminho, pos, inicio, duracao, codec="", cancelar=None):
    """
    Audio de um TRECHO (mono 8 kHz int16). Se a faixa completa ja estiver no cache, recorta
    dela; senao pede ao FFmpeg para pular direto ao ponto e ler so aquele pedaco.
    """
    if em_cache(caminho, pos):
        mm = np.memmap(arquivo_cache(caminho, pos), dtype="<i2", mode="r")
        i0 = max(0, int(round(inicio * da.SR_AUDIO)))
        return np.array(mm[i0:i0 + int(round(duracao * da.SR_AUDIO))])
    k = (os.path.abspath(caminho), pos, round(inicio, 3), round(duracao, 3))
    with _TRAVA:
        if k in _TRECHOS:
            return _TRECHOS[k]
    x = da.ler_pcm(caminho, pos, inicio, duracao, codec, cancelar)
    with _TRAVA:
        _TRECHOS[k] = x
        while len(_TRECHOS) > 48:
            _TRECHOS.popitem(last=False)
    return x


def limpar_cache():
    with _TRAVA:
        _MEM.clear()
        _TRECHOS.clear()
    n = 0
    if CACHE_DIR.exists():
        for f in list(CACHE_DIR.glob("*.s16")) + list(CACHE_DIR.glob("*.npy")) + list(CACHE_DIR.glob("*.part")):
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
    return n


def envelope(pcm):
    """Minimo e maximo a cada 10 ms (para desenhar a onda). Formato: (N, 2) float32."""
    n = len(pcm) // ENV_BASE * ENV_BASE
    if n == 0:
        return np.zeros((0, 2), np.float32)
    x = pcm[:n].reshape(-1, ENV_BASE)
    return np.stack([x.min(axis=1), x.max(axis=1)], axis=1).astype(np.float32) / 32768.0


class EnvelopeIncremental:
    """Monta a onda aos poucos, a medida que o audio vai sendo lido."""

    def __init__(self):
        self.partes = []
        self.resto = np.zeros(0, np.int16)

    def adicionar(self, amostras):
        x = np.concatenate([self.resto, amostras]) if len(self.resto) else amostras
        n = len(x) // ENV_BASE * ENV_BASE
        if n:
            self.partes.append(envelope(x[:n]))
        self.resto = x[n:].copy()

    def valor(self):
        return np.concatenate(self.partes) if self.partes else np.zeros((0, 2), np.float32)

    def truncar(self, n_amostras):
        """Descarta o que passou de n_amostras (usado quando uma leitura pausada guarda menos do que mostrou)."""
        v = self.valor()[:max(0, int(n_amostras) // ENV_BASE)]
        self.partes = [v] if len(v) else []
        self.resto = np.zeros(0, np.int16)


# ----------------------------------------------------------------- deteccao
def resumir(res):
    r = res["r"] * res["extra_r"]
    return {"metodo": res["metodo"], "status": res["status"], "confianca": res["confianca"],
            "atraso_ms": int(round(res["atraso"] * 1000)), "atempo": 1.0 / r,
            "descricao_velocidade": res["escolhido"]["desc"], "deriva_s_por_hora": 3600.0 * (res["extra_r"] - 1.0),
            "grupos": [{"ini": g["ini"], "fim": g["fim"], "atraso_ms": int(round(g["atraso"] * 1000))}
                       for g in res["grupos"]],
            "boas": res["n_boas"], "total": res["n_total"], "z": res["z_mediano"],
            "modo": res.get("modo", "completo"), "lido_filme_s": res.get("lido_filme_s"),
            "lido_dub_s": res.get("lido_dub_s"), "falhas": res.get("falhas", []),
            "tempo_grupos": res.get("tempo_grupos", "dublagem")}


def _args_deteccao(faixa_dub=0):
    return SimpleNamespace(max_offset=180.0, janela=60.0, tolerancia=80.0, faixa_dub=faixa_dub)


_SONDAS = {}


def _sondar_cache(caminho):
    st = os.stat(caminho)
    k = (os.path.abspath(caminho), st.st_size, int(st.st_mtime))
    if k not in _SONDAS:
        _SONDAS[k] = sondar_arquivo(caminho)
    return _SONDAS[k]


def detectar(film_caminho, film_pos, dub_caminho, dub_pos, cancelar=None, msg=None, prog=None, completo=False,
             completo_se_falhar=False):
    """
    Detecta o atraso. Padrao: analise RAPIDA (le ~4 min do filme, em trechos). Se ela nao achar,
    devolve status BAIXA_CONFIANCA com o motivo; a analise COMPLETA (le os arquivos inteiros) so
    acontece se pedida (completo=True) ou com completo_se_falhar=True.
    Se as duas faixas completas ja estiverem no cache, usa-as direto (sem ler nada).
    """
    cancelar = cancelar or threading.Event()
    msg = msg or (lambda m: None)
    prog = prog or (lambda v: None)
    fa, fd = _sondar_cache(film_caminho), _sondar_cache(dub_caminho)
    if film_pos >= len(fa.audios) or dub_pos >= len(fd.audios):
        raise RuntimeError(tr("Faixa de áudio inexistente."))
    cf, cd = fa.audios[film_pos].codec, fd.audios[dub_pos].codec
    fim_f, fim_d = fa.fim_audio(film_pos), fd.fim_audio(dub_pos)
    if fim_d and fim_f and fim_d < fim_f - 120:
        msg(tr("Aviso: a faixa da dublagem termina em %s, mas o filme vai até %s (dublagem incompleta ou de "
               "versão cortada?).") % (da.mmss(fim_d), da.mmss(fim_f)))
    if em_cache(film_caminho, film_pos) and em_cache(dub_caminho, dub_pos):
        completo = True
    if not completo:
        res, motivo = da.detectar_rapido(
            lambda t0, d: trecho(film_caminho, film_pos, t0, d, cf, cancelar),
            lambda t0, d: trecho(dub_caminho, dub_pos, t0, d, cd, cancelar),
            fim_f, fim_d, msg=msg, prog=lambda f: prog(int(f * 100)))
        if res is not None:
            res["faixa_dub"] = dub_pos
            return resumir(res)
        if not completo_se_falhar:
            return {"metodo": "audio", "status": "BAIXA_CONFIANCA", "confianca": "BAIXA", "atraso_ms": 0,
                    "atempo": 1.0, "descricao_velocidade": "", "deriva_s_por_hora": 0.0, "grupos": [],
                    "boas": 0, "total": 0, "z": 0.0, "modo": "rapido", "motivo": motivo,
                    "lido_filme_s": None, "lido_dub_s": None, "falhas": []}
        msg(tr("A análise rápida não foi suficiente (%s). Lendo os arquivos inteiros "
               "(em UHD pode levar vários minutos; o resultado fica guardado)...") % motivo)
    a = carregar_completo(film_caminho, [film_pos], {film_pos: cf}, fa.duracao, cancelar,
                          ao_progresso=lambda f, s: prog(int(f * 60)))[film_pos]
    b = carregar_completo(dub_caminho, [dub_pos], {dub_pos: cd}, fd.duracao, cancelar,
                          ao_progresso=lambda f, s: prog(60 + int(f * 30)))[dub_pos]
    msg(tr("Comparando as duas faixas inteiras..."))
    fa_ = da.caracteristicas_audio(a.astype(np.float32) / 32768.0)
    fb_ = da.caracteristicas_audio(b.astype(np.float32) / 32768.0)
    prog(95)
    return resumir(da.analisar("audio", fa_, fb_, da.TAXA_AUDIO, _args_deteccao(dub_pos)))


def detectar_video(arquivo_filme, arquivo_dub, msg=None, cancelar=None):
    if msg:
        msg(tr("Lendo o vídeo do filme (UHD pode levar muito tempo)..."))
    a = da.caracteristicas_video(da.carregar_video(arquivo_filme, cancelar))
    if msg:
        msg(tr("Lendo o vídeo da dublagem..."))
    b = da.caracteristicas_video(da.carregar_video(arquivo_dub, cancelar))
    return resumir(da.analisar("video", a, b, da.TAXA_VIDEO, _args_deteccao()))


# ----------------------------------------------------------------- projeto
@dataclass
class Dublagem:
    arquivo: str
    faixa: int                 # numero da faixa de audio dentro do arquivo (0 = primeira)
    nome: str = "Dublagem PT-BR"
    idioma: str = "por"
    atraso_ms: int = 0
    padrao: bool = False
    atempo: float = 1.0        # 1.0 = sem correcao de velocidade
    status: str = ""
    detalhe: str = ""

    def chave(self):
        return (os.path.abspath(self.arquivo), self.faixa)


def salvar_projeto(caminho, filme, ref, motor, dubs, manter=None):
    dados = {"versao": 2, "filme": filme, "faixa_referencia": ref, "motor": motor,
             "dublagens": [asdict(d) for d in dubs], "manter": sorted(manter) if manter is not None else None}
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def abrir_projeto(caminho):
    with open(caminho, "r", encoding="utf-8") as f:
        j = json.load(f)
    campos = Dublagem.__dataclass_fields__.keys()
    dubs = [Dublagem(**{k: v for k, v in d.items() if k in campos}) for d in j.get("dublagens", [])]
    manter = j.get("manter")
    return (j.get("filme", ""), int(j.get("faixa_referencia", 0)), j.get("motor", ""), dubs,
            set(manter) if manter is not None else None)


# ----------------------------------------------------------------- executar programas
def _rodar(cmd, ao_ler_linha=None, tolerar=(0,), cancelar=None):
    """Roda um programa, repassando cada linha de saida; respeita o cancelamento."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         universal_newlines=True, encoding="utf-8", errors="replace",
                         creationflags=CRIAR_SEM_JANELA)
    parado = {"v": False}

    def vigiar():                            # encerra em ~0,2 s ao cancelar, mesmo sem saida do programa
        while p.poll() is None:
            if cancelar.wait(0.2):
                parado["v"] = True
                try:
                    p.terminate()
                except OSError:
                    pass
                return
    if cancelar is not None:
        threading.Thread(target=vigiar, daemon=True).start()
    cauda = []
    try:
        for linha in p.stdout:
            linha = linha.rstrip()
            if linha:
                cauda.append(linha)
                cauda = cauda[-25:]
                if ao_ler_linha:
                    ao_ler_linha(linha)
            if cancelar is not None and cancelar.is_set():
                parado["v"] = True
                break
    finally:
        if parado["v"] and p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass
        try:
            p.stdout.close()
        except Exception:
            pass
        rc = p.wait()
    if parado["v"]:
        raise Cancelado()
    if rc not in tolerar:
        raise RuntimeError(tr("O programa terminou com erro (código %s):\n%s\n\n%s")
                           % (rc, " ".join(cmd[:1]), "\n".join(cauda[-12:])))
    return cauda


def _segundos(texto):
    m = re.match(r"(\d+):(\d+):(\d+(?:\.\d+)?)", texto)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


# ----------------------------------------------------------------- montagem
def validar(film, dubs):
    if not dubs:
        raise RuntimeError(tr("Adicione pelo menos uma dublagem."))
    vistos = set()
    for d in dubs:
        if not os.path.isfile(d.arquivo):
            raise RuntimeError(tr("Arquivo da dublagem não encontrado:\n%s") % d.arquivo)
        if d.chave() in vistos:
            raise RuntimeError(tr("A mesma faixa foi adicionada duas vezes: %s (faixa %d)") % (d.arquivo, d.faixa))
        vistos.add(d.chave())
    if sum(1 for d in dubs if d.padrao) > 1:
        raise RuntimeError(tr("Só uma dublagem pode ser a faixa padrão."))


def _preparar_velocidade(dubs, tmp, ferr, msg, cancelar=None):
    fontes = []
    for i, d in enumerate(dubs, 1):
        src, idx = d.arquivo, d.faixa
        if abs(d.atempo - 1.0) > 1e-9:
            msg(tr("Dublagem %d: corrigindo a velocidade (só esta dublagem vira FLAC)...") % i)
            novo = os.path.join(tmp, "dub%d_velocidade.mka" % i)
            _rodar([ferr.ffmpeg, "-y", "-v", "error", "-nostdin", "-i", src, "-map", "0:a:%d" % idx, "-vn",
                    "-af", "atempo=%.8f" % d.atempo, "-c:a", "flac", novo], cancelar=cancelar)
            src, idx = novo, 0
        fontes.append({"d": d, "src": src, "idx": idx})
    return fontes


TIPOS_ESCOLHIVEIS = ("video", "audio", "subtitle")


def faixas_mantidas(film, manter=None):
    """Faixas do filme que vao para o arquivo final, na ordem original. manter=None: todas."""
    return [f for f in film.faixas if f.tipo in TIPOS_ESCOLHIVEIS and (manter is None or f.idx in manter)]


def validar_manter(film, manter):
    if manter is not None and not any(f.tipo == "video" for f in faixas_mantidas(film, manter)):
        raise RuntimeError(tr("Mantenha pelo menos uma faixa de vídeo do filme."))


def comando_ffmpeg(film, fontes, saida, teste, ferr, tmp, msg, cancelar=None, manter=None):
    """
    Prepara os cortes (atraso negativo) e devolve o comando final do FFmpeg (copia sem recodificar).
    Dublagens do MESMO arquivo com o MESMO atraso entram por UMA entrada so (o arquivo e lido uma vez).
    """
    mantidas = faixas_mantidas(film, manter)
    n_a = sum(1 for f in mantidas if f.tipo == "audio")
    cmd = [ferr.ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-v", "warning", "-progress", "pipe:1", "-y",
           "-i", film.caminho]
    entradas = {}
    mapas, meta = [], []
    padrao_idx = None
    for k, f in enumerate(fontes, 1):
        d, src, idx, atraso = f["d"], f["src"], f["idx"], f["d"].atraso_ms
        if atraso < 0:
            msg(tr("Dublagem %d: cortando o começo da dublagem (cópia exata, sem recodificar)...") % k)
            corte = os.path.join(tmp, "dub%d_corte.mka" % k)
            _rodar([ferr.ffmpeg, "-y", "-v", "error", "-nostdin", "-i", src, "-map", "0:a:%d" % idx, "-c", "copy",
                    "-ss", "%dms" % (-atraso), corte], cancelar=cancelar)
            src, idx, atraso = corte, 0, 0
        chave = (os.path.abspath(src), atraso)
        if chave not in entradas:
            entradas[chave] = len(entradas) + 1
            if atraso > 0:
                cmd += ["-itsoffset", "%dms" % atraso]
            cmd += ["-i", src]
        mapas += ["-map", "%d:a:%d" % (entradas[chave], idx)]
        saida_a = n_a + k - 1
        meta += ["-metadata:s:a:%d" % saida_a, "language=%s" % (d.idioma or "und"),
                 "-metadata:s:a:%d" % saida_a, "title=%s" % d.nome]
        if d.padrao:
            padrao_idx = saida_a
    for f in mantidas:
        cmd += ["-map", "0:%d" % f.idx]
    cmd += mapas + ["-map", "0:t?", "-c", "copy"] + meta     # 0:t? = anexos do filme (fontes etc.)
    if padrao_idx is not None:
        for i in range(n_a + len(fontes)):
            cmd += ["-disposition:a:%d" % i, "default" if i == padrao_idx else "0"]
    if teste:
        cmd += ["-t", "300"]
    cmd.append(saida)
    return cmd


TIPO_MKVMERGE = {"video": "video", "audio": "audio", "subtitle": "subtitles"}


def _ids_mkvmerge(caminho, ferr):
    """IDs das faixas no mkvmerge, por tipo, na ordem do arquivo (a mesma ordem do ffprobe)."""
    p = subprocess.run([ferr.mkvmerge, "-J", caminho], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       creationflags=CRIAR_SEM_JANELA)
    if p.returncode not in (0, 1):
        raise RuntimeError(tr("O mkvmerge não conseguiu ler:\n%s\n%s") % (caminho, p.stderr.decode("utf-8", "replace")))
    j = json.loads(p.stdout.decode("utf-8", "replace"))
    ids = {"video": [], "audio": [], "subtitles": []}
    for t in j.get("tracks", []):
        if t.get("type") in ids:
            ids[t["type"]].append(t["id"])
    return ids


def comando_mkvmerge(film, fontes, saida, teste, ferr, manter=None):
    """
    mkvmerge: junta sem recodificar; atraso com --sync (negativo tambem funciona). Varias dublagens do
    mesmo arquivo entram juntas (o arquivo e lido uma vez so).
    """
    ids_f = _ids_mkvmerge(film.caminho, ferr)
    cmd = [ferr.mkvmerge, "--gui-mode", "-o", saida]
    escolhidas = {"video": [], "audio": [], "subtitles": []}
    for f in faixas_mantidas(film, manter):
        tipo = TIPO_MKVMERGE[f.tipo]
        if f.pos < len(ids_f[tipo]):
            escolhidas[tipo].append(ids_f[tipo][f.pos])
    for tipo, liga, desliga in (("video", "--video-tracks", "--no-video"), ("audio", "--audio-tracks", "--no-audio"),
                                ("subtitles", "--subtitle-tracks", "--no-subtitles")):
        if escolhidas[tipo]:
            if len(escolhidas[tipo]) != len(ids_f[tipo]):
                cmd += [liga, ",".join(str(i) for i in escolhidas[tipo])]
        elif ids_f[tipo]:
            cmd.append(desliga)
    if any(f["d"].padrao for f in fontes):
        for i in escolhidas["audio"]:
            cmd += ["--default-track-flag", "%d:0" % i]
    cmd.append(film.caminho)
    grupos = {}
    for f in fontes:
        grupos.setdefault(os.path.abspath(f["src"]), []).append(f)
    for src, itens in grupos.items():
        ids = _ids_mkvmerge(src, ferr)["audio"]
        try:   # o FFmpeg conta o tempo a partir do inicio de cada arquivo; o mkvmerge nao. Compensa a diferenca.
            ajuste = int(round((_sondar_cache(src).inicio - film.inicio) * 1000))
        except Exception:
            ajuste = 0
        escolhidos, opcoes = [], []
        for f in itens:
            if f["idx"] >= len(ids):
                raise RuntimeError(tr("O mkvmerge não achou a faixa de áudio %d em %s") % (f["idx"], src))
            tid, d = ids[f["idx"]], f["d"]
            escolhidos.append(str(tid))
            opcoes += ["--sync", "%d:%d" % (tid, d.atraso_ms - ajuste), "--track-name", "%d:%s" % (tid, d.nome),
                       "--language", "%d:%s" % (tid, d.idioma or "und"),
                       "--default-track-flag", "%d:%d" % (tid, 1 if d.padrao else 0)]
        cmd += ["--no-video", "--no-subtitles", "--no-chapters", "--no-attachments", "--no-global-tags",
                "--no-track-tags", "--audio-tracks", ",".join(escolhidos)] + opcoes + [src]
    if teste:
        cmd[2:2] = ["--split", "parts:00:00:00-00:05:00"]     # antes do "-o"
    return cmd


def montar(film, dubs, saida, teste, motor, ferr, msg, prog, cancelar=None, manter=None):
    """
    Gera o MKV final. motor: 'mkvmerge' ou 'ffmpeg'. manter: indices das faixas do FILME que entram
    (None = todas). Devolve o caminho do arquivo gerado.
    """
    cancelar = cancelar or threading.Event()
    validar(film, dubs)
    validar_manter(film, manter)
    if motor == "mkvmerge" and not ferr.mkvmerge:
        raise RuntimeError(tr("mkvmerge não encontrado. Escolha o FFmpeg ou indique o caminho em Opções."))
    tmp = tempfile.mkdtemp(prefix="eternaldub_")
    try:
        fontes = _preparar_velocidade(dubs, tmp, ferr, msg, cancelar)
        total = 300.0 if teste else max(film.duracao, 1.0)
        msg(tr("Montando o arquivo (só copia os fluxos, sem recodificar)..."))

        if motor == "mkvmerge":
            cmd = comando_mkvmerge(film, fontes, saida, teste, ferr, manter)

            def ler(l):
                m = re.search(r"(\d+)%", l)
                if m:
                    prog(min(99, int(m.group(1))))
            _rodar(cmd, ler, tolerar=(0, 1), cancelar=cancelar)
            if teste:                      # o mkvmerge acrescenta -001 ao nome
                base, ext = os.path.splitext(saida)
                achados = sorted(glob.glob(glob.escape(base) + "-*" + ext))
                if achados:
                    os.replace(achados[0], saida)
                    for extra in achados[1:]:
                        os.remove(extra)
        else:
            cmd = comando_ffmpeg(film, fontes, saida, teste, ferr, tmp, msg, cancelar, manter)

            def ler(l):
                if l.startswith("out_time="):
                    prog(min(99, int(100 * _segundos(l[9:]) / total)))
            _rodar(cmd, ler, cancelar=cancelar)
        if not os.path.isfile(saida):
            raise RuntimeError(tr("O arquivo final não foi criado."))
        prog(100)
        return saida
    except Cancelado:
        if os.path.isfile(saida):
            try:
                os.remove(saida)
            except OSError:
                pass
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------- verificacao (lossless)
def _hashes(caminho, mapas, ferr, duracao=0.0, prog=None, cancelar=None):
    """MD5 de cada fluxo copiado (sem decodificar). Mostra progresso e pode ser cancelado."""
    fd, saida = tempfile.mkstemp(prefix="eternaldub_hash_", suffix=".txt")
    os.close(fd)
    cmd = [ferr.ffmpeg, "-v", "error", "-nostdin", "-nostats", "-y", "-progress", "pipe:1", "-i", caminho]
    for m in mapas:
        cmd += ["-map", m]
    cmd += ["-c", "copy", "-f", "streamhash", "-hash", "md5", saida]

    def ler(l):
        if prog and duracao and l.startswith("out_time="):
            prog(min(1.0, _segundos(l[9:]) / duracao))
    try:
        _rodar(cmd, ler, cancelar=cancelar)
        with open(saida, "r", encoding="ascii", errors="replace") as f:
            return [l.strip().split("MD5=")[1] for l in f if "MD5=" in l]
    finally:
        try:
            os.remove(saida)
        except OSError:
            pass


LETRA = {"video": "v", "audio": "a", "subtitle": "s"}


def verificar_integridade(film, arquivo_final, ferr, msg, prog, cancelar=None, manter=None):
    """
    Compara o hash de cada fluxo ORIGINAL do filme que foi mantido (video, audio, legenda) com o
    fluxo correspondente no arquivo final. Le os dois arquivos inteiros.
    """
    mantidas = faixas_mantidas(film, manter)
    mapas_f, mapas_s, nomes = [], [], []
    for tipo, rot in (("video", tr("vídeo")), ("audio", tr("áudio")), ("subtitle", tr("legenda"))):
        for pos_saida, f in enumerate(x for x in mantidas if x.tipo == tipo):
            mapas_f.append("0:%s:%d" % (LETRA[tipo], f.pos))
            mapas_s.append("0:%s:%d" % (LETRA[tipo], pos_saida))
            nomes.append("%s %d (%s)" % (rot, f.pos + 1, f.rotulo()))
    msg(tr("Calculando o hash do filme original (lê o arquivo inteiro)..."))
    h1 = _hashes(film.caminho, mapas_f, ferr, film.duracao, lambda f: prog(int(f * 50)), cancelar)
    msg(tr("Calculando o hash do arquivo final..."))
    h2 = _hashes(arquivo_final, mapas_s, ferr, film.duracao, lambda f: prog(50 + int(f * 50)), cancelar)
    prog(100)
    resultado = []
    for i, nome in enumerate(nomes):
        a = h1[i] if i < len(h1) else None
        b = h2[i] if i < len(h2) else None
        resultado.append((nome, a is not None and a == b))
    return resultado


def _ler_janela_varias(caminho, posicoes, inicio, duracao, ferr, cancelar=None, limite_s=60.0):
    """
    Le o mesmo trecho de varias faixas de audio numa passada so (mono 8 kHz int16).

    Cuidado que motivou esta funcao: se uma das faixas pedidas NAO tem audio no trecho (dublagem que
    acaba antes ou tem um buraco), o FFmpeg ignora o limite (-t) e segue lendo ate o FIM do arquivo
    -- num UHD num HD lento, sao dezenas de minutos. Por isso ela vigia o tamanho dos arquivos de
    saida e encerra o FFmpeg assim que as faixas com audio ja tem o trecho inteiro (as que nao
    crescem por 3 s sao dadas como vazias), e nunca passa de `limite_s`.
    Devolve {faixa: amostras} (vazio = sem audio no trecho).
    """
    pasta = tempfile.mkdtemp(prefix="eternaldub_conf_")
    alvo = int(duracao * da.SR_AUDIO * 2 * 0.98)          # bytes esperados por faixa
    try:
        cmd = [ferr.ffmpeg, "-v", "error", "-nostdin", "-nostats", "-y"]
        if inicio > 0:
            cmd += ["-ss", "%.3f" % inicio]
        cmd += ["-t", "%.3f" % duracao, "-i", caminho]
        arqs = {}
        for p in posicoes:
            arqs[p] = os.path.join(pasta, "a%d.raw" % p)
            cmd += ["-map", "0:a:%d" % p, "-af", "aresample=async=1:first_pts=0", "-ac", "1",
                    "-ar", str(da.SR_AUDIO), "-c:a", "pcm_s16le", "-t", "%.3f" % duracao,
                    "-flush_packets", "1", "-f", "s16le", arqs[p]]     # grava cada pedaco na hora (a vigia ve o tamanho real)
        estado = {"tam": {}, "mudou": time.monotonic()}

        def basta():
            tam = {p: (os.path.getsize(a) if os.path.exists(a) else 0) for p, a in arqs.items()}
            if tam != estado["tam"]:
                estado["tam"], estado["mudou"] = tam, time.monotonic()
            cheias = [p for p, t in tam.items() if t >= alvo]
            if len(cheias) == len(tam):
                return True                                    # todas com o trecho completo
            return bool(cheias) and time.monotonic() - estado["mudou"] > 3.0   # o resto nao cresce mais
        try:
            da._executar(cmd, None, cancelar, limite_s=limite_s, basta=basta)
        except da.TempoEsgotado:
            pass                                               # usa o que ja foi lido
        saida = {}
        for p, a in arqs.items():
            x = np.fromfile(a, dtype="<i2") if os.path.exists(a) else np.zeros(0, np.int16)
            saida[p] = x[:int(duracao * da.SR_AUDIO)]
        return saida
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def conferir_dublagens(saida, n_audios_filme, ref_saida, nomes, ferr, teste=False, cancelar=None, msg=None, prog=None):
    """
    Confere, DENTRO do arquivo gerado, se cada dublagem nova tem som e esta alinhada com o audio
    original (faixa `ref_saida` do arquivo gerado; None = so confere o som).
    Le 2 ou 3 trechos curtos (cada leitura tem tempo maximo; nunca trava). Devolve, por dublagem:
      com_som: True / False / None (None = nao deu para conferir)
      sobra_ms: diferenca de sincronia medida (None = nao medida)
      sem_audio_em: tempos (s) dos trechos em que a faixa nao tinha audio nenhum
    """
    msg = msg or (lambda m: None)
    prog = prog or (lambda v: None)
    arq = sondar_arquivo(saida)
    dur = arq.duracao or (300.0 if teste else 0.0)
    pontos = [45.0, 170.0] if teste else [dur * 0.15, dur * 0.5, dur * 0.85]
    pontos = [p for p in pontos if p + 30 < dur] or [max(0.0, dur / 3)]
    novas = list(range(n_audios_filme, len(arq.audios)))
    res = {p: {"nome": nomes[i] if i < len(nomes) else tr("faixa %d") % p, "rms": 0.0, "atrasos": [], "lidos": 0,
               "sem_audio_em": []} for i, p in enumerate(novas)}
    for k, t in enumerate(pontos):
        msg(tr("Conferindo as dublagens no arquivo gerado (%d de %d, em %s)...") % (k + 1, len(pontos), da.mmss(t)))
        alvo = novas + ([ref_saida] if ref_saida is not None else [])
        t0 = time.monotonic()
        try:
            janela = _ler_janela_varias(saida, alvo, max(0.0, t - 3), 26.0, ferr, cancelar)
        except Cancelado:
            raise
        except Exception as e:
            msg(tr("   não consegui ler este trecho (%s); pulando") % str(e).strip().splitlines()[-1][:120])
            prog(int(100 * (k + 1) / len(pontos)))
            continue
        if time.monotonic() - t0 > 20:
            msg(tr("   (este trecho demorou %.0f s para ler: disco lento)") % (time.monotonic() - t0))
        ref = janela.get(ref_saida) if ref_saida is not None else None
        for p in novas:
            x = janela.get(p, np.zeros(0, np.int16))
            if len(x) < da.SR_AUDIO:
                res[p]["sem_audio_em"].append(t)
                continue
            res[p]["lidos"] += len(x)
            res[p]["rms"] = max(res[p]["rms"], float(np.sqrt(np.mean((x.astype(np.float64) / 32768.0) ** 2))))
            if ref is not None and len(ref) >= 23 * da.SR_AUDIO and len(x) >= 20 * da.SR_AUDIO:
                fw = da._feat_pcm(ref[3 * da.SR_AUDIO:23 * da.SR_AUDIO])
                off, z = da._casar(fw, t, da._feat_pcm(x), max(0.0, t - 3), 1.0)
                if off is not None and z >= da.Z_MIN_JANELA:
                    res[p]["atrasos"].append(off)
        prog(int(100 * (k + 1) / len(pontos)))
    saida_lista = []
    for p in novas:
        r = res[p]
        r["faixa"] = p
        r["com_som"] = None if r["lidos"] == 0 else (r["rms"] >= 0.001)
        r["sobra_ms"] = int(round(1000 * float(np.median(r["atrasos"])))) if r["atrasos"] else None
        saida_lista.append(r)
    return saida_lista
