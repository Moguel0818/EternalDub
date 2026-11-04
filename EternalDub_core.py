# SPDX-License-Identifier: MIT
# EternalDub - Copyright (C) 2026 Moguel0818 e colaboradores / and contributors
# -*- coding: utf-8 -*-
"""
EternalDub_core.py - nucleo do EternalDub (tudo que NAO e interface grafica).

  * le as faixas dos arquivos (ffprobe);
  * le o audio LEVE so para analise (mono 8 kHz): trechos com salto direto para detectar,
    e a onda completa em segundo plano, com progresso e cache (o filme UHD so e lido uma vez);
  * detecta o atraso (usa o detectar_atraso.py; analise rapida por trechos);
  * monta o MKV final SEM RECODIFICAR (FFmpeg com -c copy), na ordem de faixas escolhida (Organizacao),
    com legendas externas (LegendaExterna) se houver;
  * verifica se os fluxos originais do filme continuam identicos (hash).

A unica conversao que existe e opcional, e so na DUBLAGEM (vira FLAC, sem perdas):
  * corrigir a VELOCIDADE (ex.: PAL 25 fps -> 23,976 fps);
  * sincronizar TRECHO POR TRECHO, quando as versoes tem cortes diferentes (mapear()).
O video e as faixas do filme nunca sao tocados.

VIDEOCLIPES: a "dublagem" pode ser uma MUSICA (Dublagem.tipo = "musica"): o FLAC/MP3 em alta qualidade no lugar do
som ruim do clipe. A deteccao e mais exigente (detectar_atraso.analisar_musica), a velocidade e corrigida como numa
fita (reamostrando: o tempo fica exato e o som nao ganha artefatos), a musica termina junto com o video e segue o
fade-in/fade-out do clipe (EternalDub_musica.medir_pontas). Veja EternalDub_musica.py.
"""
import hashlib
import codecs
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
import EternalDub_musica as musica

VERSAO_NUCLEO = "1.4"
for _mod, _ver in ((da, "VERSAO_DETECTOR"), (musica, "VERSAO_MUSICA")):
    if getattr(_mod, _ver, None) != VERSAO_NUCLEO:
        raise ImportError(tr("%s (versão %s) e EternalDub_core.py (versão %s) não combinam.\nArquivo encontrado: %s")
                          % (os.path.basename(getattr(_mod, "__file__", "?")), getattr(_mod, _ver, tr("antiga")),
                             VERSAO_NUCLEO, getattr(_mod, "__file__", "?")))

CRIAR_SEM_JANELA = 0x08000000 if sys.platform == "win32" else 0
CACHE_DIR = Path.home() / ".eternaldub" / "cache"
ENV_BASE = 80                                  # amostras por ponto do envelope (10 ms a 8 kHz)
ENV_RATE = da.SR_AUDIO / ENV_BASE              # pontos de envelope por segundo (100)
Cancelado = da.Cancelado


# ----------------------------------------------------------------- ferramentas
def pasta_do_programa():
    """Pasta onde o EternalDub esta: a do .exe (programa empacotado) ou a dos arquivos .py."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _candidatos_ffmpeg(nome):
    """
    Onde procurar o FFmpeg alem do PATH. Devolve (proprios, comuns):
      proprios: a pasta do proprio EternalDub (quem baixa o ffmpeg.exe e o ffprobe.exe e os coloca ao lado
                do EternalDub.exe nao precisa mexer em nada);
      comuns:   pastas onde o winget e outras instalacoes costumam deixa-lo no Windows (o PATH de um
                programa que ja estava aberto nao enxerga uma instalacao feita depois).
    """
    exe = nome + (".exe" if sys.platform == "win32" else "")
    base = pasta_do_programa()
    proprios = [base / exe, base / "ffmpeg" / exe, base / "ffmpeg" / "bin" / exe, base / "bin" / exe]
    comuns = []
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            comuns.append(Path(local) / "Microsoft" / "WinGet" / "Links" / exe)
            try:
                comuns += sorted((Path(local) / "Microsoft" / "WinGet" / "Packages").glob(
                    "Gyan.FFmpeg*/ffmpeg-*/bin/" + exe), reverse=True)
            except OSError:
                pass
        for raiz in (os.environ.get("ProgramFiles", r"C:\Program Files"), "C:\\"):
            comuns += [Path(raiz) / "ffmpeg" / "bin" / exe, Path(raiz) / "ffmpeg" / exe]
    return [str(x) for x in proprios], [str(x) for x in comuns]


@dataclass
class Ferramentas:
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"

    def aplicar(self):
        da.FFMPEG, da.FFPROBE = self.ffmpeg, self.ffprobe


def achar_ferramentas(salvas=None):
    """Caminho salvo nas opcoes > pasta do programa > PATH > pastas comuns do Windows."""
    salvas = salvas or {}
    f = Ferramentas()
    for nome in ("ffmpeg", "ffprobe"):
        salvo = salvas.get(nome) or ""
        proprios, comuns = _candidatos_ffmpeg(nome)
        if salvo and (os.path.isfile(salvo) or shutil.which(salvo)):
            escolhido = salvo
        else:
            escolhido = (next((c for c in proprios if os.path.isfile(c)), None) or shutil.which(nome)
                         or next((c for c in comuns if os.path.isfile(c)), None) or nome)
        setattr(f, nome, escolhido)
    f.aplicar()
    return f


def versoes(f):
    """Texto curto com a versao do FFmpeg (ajuda a diagnosticar problemas)."""
    try:
        p = subprocess.run([f.ffmpeg, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           stdin=subprocess.DEVNULL, creationflags=CRIAR_SEM_JANELA, timeout=15)
        linha = p.stdout.decode("utf-8", "replace").strip().splitlines()[0]
        return " ".join(linha.split()[:3])
    except Exception:
        return "ffmpeg (?)"


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
    disposicao: dict = field(default_factory=dict)   # marcas da faixa: default, forced, comment...

    def forcada(self):
        return bool(self.disposicao.get("forced"))

    def capa(self):
        """Imagem fixa embutida (capa do disco, miniatura): o MKV a receberia como uma segunda faixa de video."""
        return self.tipo == "video" and bool(self.disposicao.get("attached_pic"))

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
    tags: dict = field(default_factory=dict)   # tags do arquivo em minusculas (artist, title, album...)

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
    def imagens(self):
        """Videos de verdade (sem as capas embutidas)."""
        return [f for f in self.videos if not f.capa()]

    @property
    def legendas(self):
        return self.do_tipo("subtitle")


# marcas que passam do filme para o arquivo final (a de "padrao" e decidida pela organizacao do arquivo)
DISPOSICOES_PRESERVADAS = ("forced", "hearing_impaired", "visual_impaired", "comment", "original", "captions",
                           "descriptions")


def _flt(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def sondar_arquivo(caminho):
    cmd = [da.FFPROBE, "-v", "error", "-show_entries",
           "stream=index,codec_type,codec_name,channels,start_time,duration"
           ":stream_tags=language,title,DURATION,artist,album,album_artist"
           ":stream_disposition=" + ",".join(("default", "attached_pic") + DISPOSICOES_PRESERVADAS) +
           ":format=duration,start_time:format_tags", "-of", "json", caminho]
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                           creationflags=CRIAR_SEM_JANELA)
    except FileNotFoundError:
        raise RuntimeError(tr("ffprobe não encontrado. Instale o FFmpeg (ou indique o caminho em Opções)."))
    if p.returncode != 0:
        raise RuntimeError(tr("Não consegui abrir o arquivo:\n%s\n%s") % (caminho, p.stderr.decode("utf-8", "replace")))
    j = json.loads(p.stdout.decode("utf-8", "replace"))
    arq = Arquivo(caminho=caminho, duracao=_flt(j.get("format", {}).get("duration")),
                  inicio=_flt(j.get("format", {}).get("start_time")),
                  tags={str(k).lower(): str(v) for k, v in (j.get("format", {}).get("tags") or {}).items()})
    for s in j.get("streams", []):           # Ogg/Opus guardam artista e titulo na faixa de audio
        if s.get("codec_type") == "audio":
            for k, v in (s.get("tags") or {}).items():
                if str(k).lower() in ("artist", "album", "album_artist", "title"):
                    arq.tags.setdefault(str(k).lower(), str(v))
            break
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
                                inicio=_flt(s.get("start_time")), duracao=dur,
                                disposicao={k: int(v) for k, v in (s.get("disposition") or {}).items()
                                            if str(v).isdigit()}))
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


def fim_do_video(film):
    """Onde a imagem do filme/clipe acaba (s): o fim da primeira faixa de video de verdade, ou a duracao do arquivo."""
    for f in film.imagens:
        if f.duracao > 0:
            fim = f.inicio + f.duracao
            return min(fim, film.duracao) if film.duracao else fim
    return film.duracao


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
            "tempo_grupos": res.get("tempo_grupos", "dublagem"), "musica": bool(res.get("musica"))}


def _args_deteccao(faixa_dub=0, dur_s=None):
    """Parametros da analise completa (dublagens). Arquivos curtos usam trechos menores (da.janela_para)."""
    return SimpleNamespace(max_offset=180.0, janela=da.janela_para(dur_s) if dur_s else 60.0, tolerancia=80.0,
                           faixa_dub=faixa_dub)


CURTO_S = 4 * 60.0        # mais curto que isto, a analise rapida nao funciona: le tudo (e pouco)


_SONDAS = {}


def _sondar_cache(caminho):
    st = os.stat(caminho)
    k = (os.path.abspath(caminho), st.st_size, int(st.st_mtime))
    if k not in _SONDAS:
        _SONDAS[k] = sondar_arquivo(caminho)
    return _SONDAS[k]


def detectar(film_caminho, film_pos, dub_caminho, dub_pos, cancelar=None, msg=None, prog=None, completo=False,
             completo_se_falhar=False, musica=False):
    """
    Detecta o atraso. Padrao: analise RAPIDA (le ~4 min do filme, em trechos). Se ela nao achar,
    devolve status BAIXA_CONFIANCA com o motivo; a analise COMPLETA (le os arquivos inteiros) so
    acontece se pedida (completo=True) ou com completo_se_falhar=True.
    Se as duas faixas completas ja estiverem no cache, usa-as direto (sem ler nada).
    Arquivos curtos (menos de 4 min) e MUSICA (videoclipe) sempre usam a analise completa: e pouco para ler. A musica
    usa a medicao propria (detectar_atraso.analisar_musica: tolerancia de 25 ms, trechos do clipe).
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
    if musica or (fim_f and fim_d and min(fim_f, fim_d) < CURTO_S):
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
    if musica:
        res = da.analisar_musica(a.astype(np.float32) / 32768.0, b.astype(np.float32) / 32768.0, faixa_dub=dub_pos,
                                 cancelar=cancelar)
        prog(95)
        return resumir(res)
    fa_ = da.caracteristicas_audio(a.astype(np.float32) / 32768.0)
    fb_ = da.caracteristicas_audio(b.astype(np.float32) / 32768.0)
    prog(95)
    return resumir(da.analisar("audio", fa_, fb_, da.TAXA_AUDIO,
                               _args_deteccao(dub_pos, min(len(a), len(b)) / da.SR_AUDIO)))


def detectar_video(arquivo_filme, arquivo_dub, msg=None, cancelar=None):
    if msg:
        msg(tr("Lendo o vídeo do filme (UHD pode levar muito tempo)..."))
    a = da.caracteristicas_video(da.carregar_video(arquivo_filme, cancelar))
    if msg:
        msg(tr("Lendo o vídeo da dublagem..."))
    b = da.caracteristicas_video(da.carregar_video(arquivo_dub, cancelar))
    return resumir(da.analisar("video", a, b, da.TAXA_VIDEO, _args_deteccao()))


def _energia_10ms(pcm):
    """RMS a cada 10 ms (80 amostras a 8 kHz) do audio leve de analise."""
    n = len(pcm) // ENV_BASE * ENV_BASE
    if n == 0:
        return np.zeros(0, np.float32)
    x = np.asarray(pcm[:n], dtype=np.float32).reshape(-1, ENV_BASE) / 32768.0
    return np.sqrt(np.mean(x * x, axis=1))


def mapear(film_caminho, film_pos, dub_caminho, dub_pos, atempo=1.0, centro_ms=None, grupos_ms=None,
           cancelar=None, msg=None, prog=None, musica=False):
    """
    Sincronia POR TRECHOS (versoes com cortes diferentes, ou dublagem remontada por quem a publicou).
    Le as duas faixas inteiras (o que ja esta no cache das ondas e instantaneo), mede o atraso a cada
    segundo e devolve os pedacos para montar a dublagem na linha do tempo do filme.
      atempo/centro_ms: velocidade e atraso principal da deteccao (centro_ms=None: mede aqui).
      grupos_ms: atrasos dos trechos vistos na deteccao (so para saber ate onde procurar).
    Devolve dict: pedacos [[ini_filme, fim_filme, ini_dub(tempo original)]], trechos, cortes, atempo,
    concordancia, silencio_s, removido_s, inicio_fora_s, fim_fora_s.
    """
    cancelar = cancelar or threading.Event()
    msg = msg or (lambda m: None)
    prog = prog or (lambda v: None)
    fa, fd = _sondar_cache(film_caminho), _sondar_cache(dub_caminho)
    if film_pos >= len(fa.audios) or dub_pos >= len(fd.audios):
        raise RuntimeError(tr("Faixa de áudio inexistente."))
    cf, cd = fa.audios[film_pos].codec, fd.audios[dub_pos].codec
    msg(tr("Sincronia por trechos: lendo as duas faixas inteiras (o que já está no cache é instantâneo; "
           "um UHD num HD pode levar vários minutos)..."))
    a = carregar_completo(film_caminho, [film_pos], {film_pos: cf}, fa.duracao, cancelar,
                          ao_progresso=lambda f, s: prog(int(f * 45)))[film_pos]
    b = carregar_completo(dub_caminho, [dub_pos], {dub_pos: cd}, fd.duracao, cancelar,
                          ao_progresso=lambda f, s: prog(45 + int(f * 15)))[dub_pos]
    msg(tr("Medindo o atraso a cada segundo do filme..."))
    fa_ = da.caracteristicas_audio(a.astype(np.float32) / 32768.0)
    fb_ = da.caracteristicas_audio(b.astype(np.float32) / 32768.0)
    if cancelar.is_set():
        raise Cancelado()
    if centro_ms is None:                      # sem deteccao antes: mede o atraso principal e a velocidade
        if musica:
            res = da.analisar_musica(a.astype(np.float32) / 32768.0, b.astype(np.float32) / 32768.0,
                                     faixa_dub=dub_pos, cancelar=cancelar)
        else:
            res = da.analisar("audio", fa_, fb_, da.TAXA_AUDIO,
                              _args_deteccao(dub_pos, min(len(a), len(b)) / da.SR_AUDIO))
        if res["status"] == "BAIXA_CONFIANCA":
            raise RuntimeError(tr("Não encontrei uma correspondência confiável entre a dublagem e o filme."))
        atempo = 1.0 / (res["r"] * res["extra_r"])
        centro_ms = res["atraso"] * 1000.0
        grupos_ms = [g["atraso"] * 1000.0 for g in res["grupos"]]
    r = 1.0 / float(atempo or 1.0)
    alcance = da.MAPA_ALCANCE
    if grupos_ms:                              # os trechos vistos na deteccao cabem na busca (ate 60 s)
        alcance = min(60.0, max(alcance, max(abs(g - centro_ms) for g in grupos_ms) / 1000.0 + 5.0))
    dur_f = fa.fim_audio(film_pos) or len(a) / da.SR_AUDIO
    dur_d = len(b) / da.SR_AUDIO
    m, r = da.mapa_com_velocidade(fa_, fb_, da.TAXA_AUDIO, r, centro_ms / 1000.0, energia=_energia_10ms(b),
                                  taxa_energia=100.0, dur_filme=dur_f, dur_dub=dur_d, alcance_s=alcance, msg=msg,
                                  prog=lambda f: prog(60 + int(f * 39)), cancelar=cancelar)
    atempo = 1.0 / r
    if not m["pedacos"]:
        raise RuntimeError(tr("O mapa por trechos não encontrou nenhum pedaço da dublagem dentro do filme."))
    pedacos = [[round(fi, 4), round(ff, 4), round(ui / r, 4)] for fi, ff, ui in m["pedacos"]]
    ult = pedacos[-1]
    usado_fim = ult[2] + (ult[1] - ult[0]) / r
    m.update(pedacos=pedacos, atempo=float(atempo), centro_ms=float(centro_ms),
             silencio_s=float(sum(c["delta"] for c in m["cortes"] if c["delta"] > 0)),
             removido_s=float(-sum(c["delta"] for c in m["cortes"] if c["delta"] < 0)),
             inicio_fora_s=float(pedacos[0][2]), fim_fora_s=float(max(0.0, dur_d - usado_fim)))
    prog(100)
    return m


# ----------------------------------------------------------------- pontas de uma musica (videoclipe)
def assinatura_sinc(d):
    """A sincronia de `d` resumida num texto: as pontas medidas so valem para a sincronia com que foram medidas."""
    t = json.dumps(d.trechos, separators=(",", ":")) if d.trechos else ""
    return "%d|%.9f|%s|%s" % (int(d.atraso_ms), float(d.atempo), d.modo_velocidade,
                              hashlib.sha1(t.encode("utf-8")).hexdigest()[:12] if t else "-")


def pontas_desatualizadas(d):
    """A musica segue as pontas do clipe, mas elas foram medidas com outra sincronia (ou ainda nao foram medidas)."""
    return d.eh_musica() and d.seguir_pontas and d.pontas_sinc != assinatura_sinc(d)


def medir_pontas(film, ref_pos, d, cancelar=None, msg=None, prog=None):
    """
    Mede no clipe (faixa de referencia `ref_pos` do filme) como a musica `d` comeca e termina, com a sincronia atual
    de `d`: fade-in, fade-out ou corte seco (EternalDub_musica.medir_pontas). Le o audio leve dos dois arquivos (o
    que ja esta no cache e instantaneo). Nao muda `d`: veja aplicar_pontas(). O resultado traz 'sinc'.
    """
    msg = msg or (lambda m: None)
    prog = prog or (lambda v: None)
    fa, fd = _sondar_cache(film.caminho), _sondar_cache(d.arquivo)
    if ref_pos >= len(fa.audios) or d.faixa >= len(fd.audios):
        raise RuntimeError(tr("Faixa de áudio inexistente."))
    cf, cd = fa.audios[ref_pos].codec, fd.audios[d.faixa].codec
    a = carregar_completo(film.caminho, [ref_pos], {ref_pos: cf}, fa.duracao, cancelar,
                          ao_progresso=lambda f, s: prog(int(f * 45)))[ref_pos]
    b = carregar_completo(d.arquivo, [d.faixa], {d.faixa: cd}, fd.duracao, cancelar,
                          ao_progresso=lambda f, s: prog(45 + int(f * 25)))[d.faixa]
    msg(tr("Medindo como o clipe faz a música começar e terminar (fade-in, fade-out ou corte)..."))
    res = musica.medir_pontas(a, b, pedacos_efetivos(d), d.atempo, da.SR_AUDIO, fim_do_video(film), cancelar)
    if cancelar is not None and cancelar.is_set():
        raise Cancelado()
    res["sinc"] = assinatura_sinc(d)
    prog(100)
    return res


def aplicar_pontas(d, res):
    """Grava em `d` as pontas medidas (medir_pontas)."""
    d.fade_entrada = list(res["entrada"]) if res.get("entrada") else None
    d.fade_saida = list(res["saida"]) if res.get("saida") else None
    d.pontas_sinc = res.get("sinc") or assinatura_sinc(d)


# ----------------------------------------------------------------- projeto
@dataclass(eq=False)                 # cada dublagem e um objeto proprio (duas iguais continuam sendo duas)
class Dublagem:
    arquivo: str
    faixa: int                 # numero da faixa de audio dentro do arquivo (0 = primeira)
    nome: str = "Dublagem PT-BR"
    idioma: str = "por"
    atraso_ms: int = 0
    padrao: bool = False       # (projetos antigos; a faixa padrao agora fica na Organizacao)
    atempo: float = 1.0        # 1.0 = sem correcao de velocidade
    status: str = ""
    detalhe: str = ""
    # Sincronia POR TRECHOS (versoes com cortes diferentes): [[ini_filme, fim_filme, ini_dub], ...] em
    # segundos (ini_dub no tempo ORIGINAL da dublagem). Com trechos, atraso_ms vira um AJUSTE FINO somado
    # a todos. None = um atraso so (atraso_ms), montado por copia exata.
    trechos: list = None
    # --- 1.4: videoclipes
    tipo: str = "dublagem"           # "dublagem" ou "musica" (a musica em alta qualidade no lugar do som do clipe)
    modo_velocidade: str = "tempo"   # correcao de velocidade: "tempo" (atempo: o tom nao muda) ou "fita" (reamostra:
    #                                  o tom acompanha a velocidade, como numa fita; tempo exato e sem artefatos)
    seguir_pontas: bool = True       # (musica) copiar do clipe o fade-in/fade-out (ou corte seco) do comeco e do fim
    fade_entrada: list = None        # [t0, t1, forma] no tempo do filme: silencio ate t0, volume normal a partir de t1
    fade_saida: list = None          # [t0, t1, forma]: volume normal ate t0, silencio a partir de t1
    pontas_sinc: str = ""            # sincronia (assinatura_sinc) com que as pontas foram medidas

    def chave(self):
        return (os.path.abspath(self.arquivo), self.faixa)

    def eh_musica(self):
        return self.tipo == "musica"

    def tem_fades(self):
        """Uma musica que segue as pontas do clipe e tem fade-in ou fade-out medido."""
        return self.eh_musica() and bool(self.seguir_pontas) and bool(self.fade_entrada or self.fade_saida)

    def fades(self):
        """(fade_entrada, fade_saida) que a montagem aplica (None, None se nao houver)."""
        return (self.fade_entrada, self.fade_saida) if self.tem_fades() else (None, None)


EXT_LEGENDA_TEXTO = (".srt", ".ass", ".ssa", ".vtt")
LEGENDAS_PARA_SRT = ("mov_text",)          # legendas de MP4: o MKV nao as aceita como estao
EXT_LEGENDA = EXT_LEGENDA_TEXTO + (".sup", ".idx", ".mks")


@dataclass(eq=False)
class LegendaExterna:
    """Uma legenda que vem de fora do filme (.srt, .ass, .sup... ou uma faixa de legenda de outro MKV/MP4)."""
    arquivo: str
    faixa: int = 0             # posicao da faixa de legenda dentro do arquivo (0 = primeira)
    nome: str = ""             # titulo da faixa no arquivo final
    idioma: str = "por"
    atraso_ms: int = 0         # >0: a legenda aparece mais tarde; <0: mais cedo
    forcada: bool = False
    codec: str = ""
    detalhe: str = ""

    def chave(self):
        return (os.path.abspath(self.arquivo), self.faixa)


PROJETO_VERSAO = 6        # 6: musicas (videoclipes); 5: legendas externas e organizacao; le 5 e anteriores


def _indice(lista, obj):
    return next((i for i, x in enumerate(lista) if x is obj), None)


def chave_para_json(k, dubs, legendas):
    """("dub", objeto) -> ["dub", posicao na lista] (para gravar no projeto). None se a faixa nao existe mais."""
    if k is None:
        return None
    if k[0] == "filme":
        return ["filme", int(k[1])]
    i = _indice(dubs if k[0] == "dub" else legendas, k[1])
    return None if i is None else [k[0], i]


def chave_do_json(v, dubs, legendas):
    try:
        tipo, i = v[0], int(v[1])
    except (TypeError, ValueError, IndexError):
        return None
    if tipo == "filme":
        return ("filme", i)
    lista = dubs if tipo == "dub" else (legendas if tipo == "leg" else [])
    return (tipo, lista[i]) if 0 <= i < len(lista) else None


def salvar_projeto(caminho, filme, ref, dubs, manter=None, legendas=(), org=None, idioma_original="",
                   organizacao_manual=False):
    legendas = list(legendas)
    lista = [asdict(d) for d in dubs]
    if org is not None:      # 'padrao' da dublagem acompanha a organizacao (versoes antigas leem so ele)
        for d, j in zip(dubs, lista):
            j["padrao"] = org.padrao_audio is not None and org.padrao_audio[0] == "dub" and org.padrao_audio[1] is d
    dados = {"versao": PROJETO_VERSAO, "filme": filme, "faixa_referencia": ref,
             "dublagens": lista, "manter": sorted(manter) if manter is not None else None,
             "legendas": [asdict(x) for x in legendas], "idioma_original": idioma_original or "",
             "organizacao_manual": bool(organizacao_manual)}
    if org is not None:
        dados["ordem"] = [c for c in (chave_para_json(k, dubs, legendas) for k in org.ordem) if c is not None]
        dados["padrao_audio"] = chave_para_json(org.padrao_audio, dubs, legendas)
        dados["padrao_legenda"] = chave_para_json(org.padrao_legenda, dubs, legendas)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def abrir_projeto(caminho):
    """
    Devolve um dicionario: filme, ref, dublagens, legendas, manter, ordem, padrao_audio, padrao_legenda,
    idioma_original, organizacao_manual (os que um projeto antigo nao tem vem vazios). Campos que nao existem
    mais sao ignorados.
    """
    with open(caminho, "r", encoding="utf-8") as f:
        j = json.load(f)
    campos = Dublagem.__dataclass_fields__.keys()
    dubs = [Dublagem(**{k: v for k, v in d.items() if k in campos}) for d in j.get("dublagens", [])]
    campos_l = LegendaExterna.__dataclass_fields__.keys()
    legendas = [LegendaExterna(**{k: v for k, v in x.items() if k in campos_l}) for x in j.get("legendas", [])]
    manter = j.get("manter")
    ordem = None
    if j.get("ordem") is not None:
        ordem = [c for c in (chave_do_json(v, dubs, legendas) for v in j["ordem"]) if c is not None]
    if "padrao_audio" in j:                           # projeto 1.3 (None = o primeiro audio)
        padrao_audio = chave_do_json(j["padrao_audio"], dubs, legendas) if j["padrao_audio"] else None
    else:                                             # projetos antigos: a dublagem marcada como padrao
        padrao_audio = next((("dub", d) for d in dubs if d.padrao), None)
    return {"filme": j.get("filme", ""), "ref": int(j.get("faixa_referencia", 0)), "dublagens": dubs,
            "legendas": legendas, "manter": set(manter) if manter is not None else None, "ordem": ordem,
            "padrao_audio": padrao_audio,
            "padrao_legenda": chave_do_json(j["padrao_legenda"], dubs, legendas) if j.get("padrao_legenda") else None,
            "idioma_original": j.get("idioma_original", "") or "",
            "organizacao_manual": bool(j.get("organizacao_manual", False))}


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
def validar(film, dubs, legendas=()):
    """Arquivos existem e nada foi adicionado duas vezes. (Sem dublagem tambem vale: so reorganizar o filme.)"""
    vistos = set()
    for d in dubs:
        if not os.path.isfile(d.arquivo):
            raise RuntimeError(tr("Arquivo da dublagem não encontrado:\n%s") % d.arquivo)
        if d.chave() in vistos:
            raise RuntimeError(tr("A mesma faixa foi adicionada duas vezes: %s (faixa %d)") % (d.arquivo, d.faixa))
        vistos.add(d.chave())
    vistas = set()
    for x in legendas:
        if not os.path.isfile(x.arquivo):
            raise RuntimeError(tr("Arquivo da legenda não encontrado:\n%s") % x.arquivo)
        if x.chave() in vistas:
            raise RuntimeError(tr("A mesma legenda foi adicionada duas vezes: %s (faixa %d)") % (x.arquivo, x.faixa))
        vistas.add(x.chave())


def _sondar_faixa_audio(caminho, pos, ferr):
    """Codec, taxa de amostragem, canais e bits da faixa de audio `pos` (para escolher o FLAC certo)."""
    p = subprocess.run([ferr.ffprobe, "-v", "error", "-select_streams", "a:%d" % pos, "-show_entries",
                        "stream=codec_name,sample_rate,channels,bits_per_raw_sample,bits_per_sample,sample_fmt",
                        "-of", "json", caminho], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       stdin=subprocess.DEVNULL, creationflags=CRIAR_SEM_JANELA)
    try:
        st = json.loads(p.stdout.decode("utf-8", "replace")).get("streams", [])[0]
    except (ValueError, IndexError):
        raise RuntimeError(tr("Não consegui ler a faixa de áudio %d de:\n%s") % (pos, caminho))
    bits = int(_flt(st.get("bits_per_raw_sample")) or _flt(st.get("bits_per_sample")) or 0)
    return {"codec": st.get("codec_name", ""), "sr": int(_flt(st.get("sample_rate")) or 48000),
            "canais": int(st.get("channels", 2) or 2), "bits": bits}


_TAXAS = {}


def taxa_da_faixa(caminho, pos, ferr):
    """Taxa de amostragem da faixa de audio `pos` (guardada: a previa pede a cada vez que toca)."""
    try:
        st = os.stat(caminho)
        k = (os.path.abspath(caminho), int(pos), st.st_size, int(st.st_mtime))
    except OSError:
        k = None
    if k is None or k not in _TAXAS:
        sr = _sondar_faixa_audio(caminho, pos, ferr)["sr"]
        if k is None:
            return sr
        _TAXAS[k] = sr
    return _TAXAS[k]


def _cabecalho_wav(f):
    """Le o cabecalho WAV que o FFmpeg escreve num pipe. Devolve (bytes_do_fmt, canais, bits)."""
    def ler(n):
        dados = b""
        while len(dados) < n:
            parte = f.read(n - len(dados))
            if not parte:
                raise RuntimeError(tr("O FFmpeg não entregou o áudio da dublagem."))
            dados += parte
        return dados
    cab = ler(12)
    if cab[:4] not in (b"RIFF", b"RF64") or cab[8:12] != b"WAVE":
        raise RuntimeError(tr("O FFmpeg não entregou o áudio da dublagem."))
    fmt = None
    while True:
        cid, tam = ler(4), int.from_bytes(ler(4), "little")
        if cid == b"data":
            break
        corpo = ler(tam + (tam & 1))
        if cid == b"fmt ":
            fmt = corpo[:tam]
    if fmt is None:
        raise RuntimeError(tr("O FFmpeg não entregou o áudio da dublagem."))
    canais, bits = int.from_bytes(fmt[2:4], "little"), int.from_bytes(fmt[14:16], "little")
    return fmt, canais, bits


def filtro_velocidade(sr, atempo, modo="tempo", dur_s=None):
    """
    Filtro do FFmpeg que decodifica a faixa na mesma linha do tempo da analise e corrige a velocidade.
    Devolve (filtro, atempo_efetivo): o tempo "esticado" e tempo_original / atempo_efetivo.
      'tempo': atempo (o tom nao muda: e o certo para falas). O filtro escolhe onde sobrepor os pedacinhos de som,
               entao o tempo de cada som pode variar alguns ms, e em musica sustentada aparecem artefatos.
      'fita':  reamostra, como uma fita tocando mais rapido ou mais devagar: o tom acompanha a velocidade (0,1% =
               1,7 cents, inaudivel), o tempo fica exato e o som nao ganha artefatos. E o padrao para musica.
               A taxa da "fita" tem de ser um numero inteiro: o audio e antes levado a K vezes a taxa (K ate 16),
               para o arredondamento nao passar de ~0,5 ms ao longo da faixa (dur_s); a montagem usa o atempo efetivo.
    """
    base = "aresample=async=1:first_pts=0"
    a = float(atempo or 1.0)
    if abs(1.0 / a - 1.0) <= 1e-9:
        return base, 1.0
    if modo != "fita":
        return base + ",atempo=%.8f" % a, a
    sr = int(sr)
    dur = float(dur_s or 3600.0)
    K = 1
    while K < 16 and dur / (2.0 * K * sr) > 0.0005:
        K *= 2
    R = int(round(a * K * sr))
    return (base + (",aresample=%d" % (K * sr) if K > 1 else "") + ",asetrate=%d,aresample=%d" % (R, sr),
            R / float(K * sr))


def duracao_da_faixa(d):
    """Duracao (s) da faixa de audio da dublagem/musica `d` (sondagem guardada)."""
    try:
        return _sondar_cache(d.arquivo).fim_audio(d.faixa) or 0.0
    except (OSError, IndexError, RuntimeError):
        return 0.0


def plano_de_pedacos(pedacos, atempo, sr, limite_s=None):
    """
    Converte os pedacos [[ini_filme, fim_filme, ini_dub], ...] (segundos; ini_dub no tempo ORIGINAL da
    dublagem) no plano de montagem, em amostras: [[o0, o1, i0], ...] = a saida [o0, o1) vem da entrada a
    partir de i0, ja depois da correcao de velocidade (o tempo esticado da dublagem: ini_dub / atempo).
    """
    r = 1.0 / float(atempo or 1.0)
    lim = int(round(limite_s * sr)) if limite_s else None
    plano = []
    for fi, ff, di in sorted(pedacos, key=lambda x: x[0]):
        o0, o1, i0 = int(round(fi * sr)), int(round(min(ff, 1e7) * sr)), int(round(di * r * sr))
        if lim is not None:
            o1 = min(o1, lim)
        if o1 > o0:
            plano.append([o0, o1, i0])
    return plano


class MontadorPedacos:
    """
    Monta o audio da dublagem na linha do tempo do FILME a partir de UMA leitura sequencial da dublagem
    (o que e usado tanto para gerar o FLAC final quanto para a previa dentro do programa: o que se ouve
    na previa e o que vai para o arquivo).

      plano:       [[o0, o1, i0], ...] em amostras (veja plano_de_pedacos): a saida [o0, o1) vem da entrada
                   a partir de i0. Entre os pedacos fica silencio; o que fica de fora da dublagem nao entra.
      canais, sr:  formato das amostras (float32) que `ler_bytes` entrega.
      ler_bytes:   ler_bytes(n) devolve ate n bytes da entrada (menos que n so no fim da dublagem).
      escrever:    escrever(array float32 (k, canais)) recebe a saida, em ordem, sem lacunas.
      cancelar:    Event; acionado, a montagem para com Cancelado.
      prog:        prog(0..99), chamado ~1x por segundo.
      ganho:       ganho(pos, n) -> ganhos (n,) ou None (= 1): volume aplicado a saida (fade-in/fade-out de uma musica,
                   EternalDub_musica.CurvaGanho), pela posicao na linha do tempo do filme.
    Cada emenda ganha um cruzamento de 8 ms (sem estalos) e a dublagem nunca volta no tempo.
    """

    def __init__(self, plano, canais, sr, ler_bytes, escrever, cancelar=None, prog=None, bloco=None, ganho=None):
        self.ganho = ganho
        self.P = plano
        self.C = int(canais)
        self.sr = int(sr)
        self.ler_bytes = ler_bytes
        self.escrever_saida = escrever
        self.cancelar = cancelar or threading.Event()
        self.prog = prog or (lambda v: None)
        self.bloco = int(bloco or sr)                  # amostras por vez (1 s por padrao)
        self.total = plano[-1][1] if plano else 0
        self.entrada = 0                               # amostras ja lidas da entrada
        self.saida = 0                                 # amostras ja escritas na saida
        self.fim = False                               # a entrada acabou
        self._t = time.monotonic()
        F = max(1, int(round(0.008 * self.sr)))        # cruzamento de 8 ms nas emendas
        x = (np.arange(F, dtype=np.float32) + 0.5) / F
        self.F = F
        self.sobe, self.desce = np.sin(0.5 * np.pi * x)[:, None], np.cos(0.5 * np.pi * x)[:, None]

    # ---- entrada e saida
    def _ler(self, n):
        nb = n * 4 * self.C
        dados = bytearray()
        while len(dados) < nb:
            parte = self.ler_bytes(nb - len(dados))
            if not parte:
                self.fim = True
                break
            dados += parte
        k = len(dados) // (4 * self.C)
        self.entrada += k
        return np.frombuffer(bytes(dados[:k * 4 * self.C]), dtype="<f4").reshape(k, self.C)

    def _escrever(self, arr):
        if self.cancelar.is_set():
            raise Cancelado()
        if self.ganho is not None:
            g = self.ganho(self.saida, len(arr))
            if g is not None:
                arr = arr * g[:, None]
        self.escrever_saida(arr)
        self.saida += len(arr)
        agora = time.monotonic()
        if agora - self._t > 1.0:
            self._t = agora
            self.prog(min(99, int(100 * self.saida / max(1, self.total))))

    def _silencio(self, n):
        while n > 0:
            k = min(n, self.bloco)
            self._escrever(np.zeros((k, self.C), np.float32))
            n -= k

    def _pular(self, n):
        while n > 0 and not self.fim:
            n -= len(self._ler(min(n, self.bloco)))

    # ---- montagem
    def executar(self):
        P, F, sobe, desce = self.P, self.F, self.sobe, self.desce
        cauda = None                               # fim do pedaco anterior (sumindo), para cruzar com o proximo
        for k, (o0, o1, i0) in enumerate(P):
            if cauda is not None and o0 != self.saida:
                self._escrever(cauda * desce[:len(cauda)])       # nao emenda direto: so some
                cauda = None
            if o0 > self.saida:
                self._silencio(o0 - self.saida)
            elif o0 < self.saida:                  # (arredondamentos) nunca volta no tempo
                i0 += self.saida - o0
                o0 = self.saida
            if i0 > self.entrada:
                self._pular(i0 - self.entrada)
            elif i0 < self.entrada:                # a dublagem nunca volta: o que ja passou vira silencio
                self._silencio(self.entrada - i0)
                o0 += self.entrada - i0
            if self.fim or o1 <= o0:
                break
            n = o1 - o0
            prox = P[k + 1] if k + 1 < len(P) else None
            emenda_direta = prox is not None and prox[0] == o1 and prox[2] - (self.entrada + n) >= F
            feitos = 0
            while feitos < n:
                y = self._ler(min(self.bloco, n - feitos)).copy()
                if not len(y):
                    break
                if feitos == 0:                    # comeco do pedaco: cruza com a cauda ou aparece suave
                    m = min(F, len(y))
                    y[:m] *= sobe[:m]
                    if cauda is not None:
                        y[:m] += cauda[:m] * desce[:m]
                    cauda = None
                feitos += len(y)
                if feitos >= n and not emenda_direta:
                    m = min(F, len(y))             # fim do pedaco: some suave
                    y[-m:] *= desce[F - m:]
                self._escrever(y)
            if emenda_direta and feitos >= n:
                cauda = self._ler(F).copy()        # o que vem logo depois (vai sair): so para o cruzamento
        if cauda is not None:
            self._escrever(cauda * desce[:len(cauda)])


def montar_por_pedacos(src, idx, pedacos, atempo, saida, ferr, msg=None, prog=None, cancelar=None,
                       limite_s=None, modo_velocidade="tempo", fades=None, dur_s=None):
    """
    Monta UMA dublagem (ou musica) na linha do tempo do FILME, em FLAC (sem perdas):
      pedacos: [[ini_filme, fim_filme, ini_dub], ...] em segundos (ini_dub no tempo ORIGINAL da dublagem).
      Entre os pedacos fica silencio; o que fica de fora da dublagem nao entra; nada passa de limite_s.
    A faixa e decodificada UMA vez, com a mesma linha do tempo da analise (aresample first_pts=0, que
    respeita o atraso embutido no arquivo), passa pela correcao de velocidade se houver (filtro_velocidade:
    modo 'tempo' ou 'fita'), e cada emenda ganha um cruzamento de 8 ms (sem estalos): veja MontadorPedacos.
      fades: (fade_entrada, fade_saida) de uma musica (EternalDub_musica.ganho_fades), no tempo do filme.
      dur_s: duracao da faixa (so para a precisao do modo 'fita').
    O arquivo final comeca no tempo 0 do filme.
    """
    msg = msg or (lambda m: None)
    prog = prog or (lambda v: None)
    cancelar = cancelar or threading.Event()
    info = _sondar_faixa_audio(src, idx, ferr)
    sr = info["sr"]
    filtro, atempo_ef = filtro_velocidade(sr, atempo, modo_velocidade, dur_s)
    P = plano_de_pedacos(pedacos, atempo_ef, sr, limite_s)
    ganho = musica.CurvaGanho(fades[0], fades[1], sr) if fades and (fades[0] or fades[1]) else None
    if not P:
        raise RuntimeError(tr("Nenhum pedaço da dublagem cai dentro do filme."))
    bits_flac = ["-sample_fmt", "s16"] if info["codec"] in ("pcm_s16le", "pcm_s16be", "flac", "alac") \
        and 0 < info["bits"] <= 16 else ["-sample_fmt", "s32", "-bits_per_raw_sample", "24"]
    dec = [ferr.ffmpeg, "-v", "error", "-nostdin", "-i", src, "-map", "0:a:%d" % idx, "-vn", "-sn", "-dn",
           "-af", filtro, "-c:a", "pcm_f32le", "-fflags", "+bitexact", "-map_metadata", "-1", "-f", "wav", "pipe:1"]
    enc = [ferr.ffmpeg, "-v", "error", "-nostdin", "-y", "-ignore_length", "1", "-f", "wav", "-i", "pipe:0",
           "-map", "0:a:0", "-c:a", "flac", "-compression_level", "5"] + bits_flac + [saida]
    err_dec, err_enc = tempfile.TemporaryFile(), tempfile.TemporaryFile()
    p_dec = subprocess.Popen(dec, stdout=subprocess.PIPE, stderr=err_dec, stdin=subprocess.DEVNULL,
                             creationflags=CRIAR_SEM_JANELA)
    p_enc = None
    ok = False
    try:
        fmt, C, bits = _cabecalho_wav(p_dec.stdout)
        if bits != 32:
            raise RuntimeError(tr("O FFmpeg não entregou o áudio da dublagem."))
        p_enc = subprocess.Popen(enc, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err_enc,
                                 creationflags=CRIAR_SEM_JANELA)
        p_enc.stdin.write(b"RIFF\xff\xff\xff\xffWAVEfmt " + len(fmt).to_bytes(4, "little") + fmt +
                          (b"\0" if len(fmt) & 1 else b"") + b"data\xff\xff\xff\xff")
        MontadorPedacos(P, C, sr, p_dec.stdout.read,
                        lambda arr: p_enc.stdin.write(np.ascontiguousarray(arr, dtype="<f4").tobytes()),
                        cancelar, prog, ganho=ganho).executar()
        p_enc.stdin.close()
        rc = p_enc.wait()
        if rc != 0:
            err_enc.seek(0)
            raise RuntimeError(tr("O FFmpeg falhou ao gravar o FLAC da dublagem:\n%s")
                               % err_enc.read().decode("utf-8", "replace")[-800:])
        prog(100)
        ok = True
        return saida
    except RuntimeError as e:                    # junta o que o FFmpeg disse (arquivo ruim, faixa estranha...)
        if cancelar.is_set():
            raise Cancelado()
        try:
            p_dec.wait(5)
        except Exception:
            pass
        err_dec.seek(0)
        detalhe = err_dec.read().decode("utf-8", "replace").strip()[-600:]
        raise RuntimeError(str(e) + ("\n" + detalhe if detalhe else ""))
    except (BrokenPipeError, OSError):
        if cancelar.is_set():
            raise Cancelado()
        err_dec.seek(0)
        err_enc.seek(0)
        raise RuntimeError(tr("O FFmpeg falhou ao montar a dublagem:\n%s\n%s") % (
            err_dec.read().decode("utf-8", "replace")[-600:], err_enc.read().decode("utf-8", "replace")[-600:]))
    finally:
        for pr in (p_dec, p_enc):
            if pr is not None and pr.poll() is None:
                try:
                    pr.kill()
                except OSError:
                    pass
        for pr in (p_dec, p_enc):
            if pr is not None:
                try:
                    pr.wait(10)
                except Exception:
                    pass
                for fl in (pr.stdout, pr.stdin):
                    try:
                        if fl:
                            fl.close()
                    except Exception:
                        pass
        err_dec.close()
        err_enc.close()
        if not ok and os.path.exists(saida):
            try:
                os.remove(saida)
            except OSError:
                pass


def pedacos_efetivos(d):
    """Pedacos de uma dublagem processada: o mapa (com o ajuste fino) ou, so com velocidade, um pedaco unico."""
    aj = d.atraso_ms / 1000.0
    if d.trechos:
        return [[fi + aj, ff + aj, di] for fi, ff, di in d.trechos]
    # tempo_filme = tempo_dub / atempo + atraso
    return [[max(0.0, aj), 1e7, max(0.0, -aj) * d.atempo]]


def limite_da_faixa(d, film, teste=False):
    """Ate onde (s do filme) a faixa montada vai: a musica termina junto com a imagem; a dublagem, 1 s depois do fim."""
    if d.eh_musica():
        fim = fim_do_video(film) or ((film.duracao or 0) + 1.0)
        return min(300.0, fim) if teste else fim
    return 300.0 if teste else (film.duracao or 0) + 1.0


def vai_virar_flac(d, film=None):
    """
    A faixa entra no arquivo como FLAC montado (e nao por copia exata)? Com correcao de velocidade, sincronia por
    trechos e, numa musica, com as pontas copiadas do clipe ou quando ela passaria do fim do video.
    """
    if d.trechos or abs(d.atempo - 1.0) > 1e-9:
        return True
    if d.eh_musica():
        if d.tem_fades():
            return True
        if film is not None:
            fim, dur = fim_do_video(film), duracao_da_faixa(d)
            if fim and dur and d.atraso_ms / 1000.0 + dur > fim + 0.05:
                return True
    return False


def _preparar_dublagens(dubs, film, tmp, ferr, msg, prog=None, cancelar=None, teste=False):
    """
    Dublagens com correcao de velocidade ou sincronia por trechos (e musicas com pontas ou mais longas que o video)
    viram FLAC ja na linha do tempo do filme (atraso 0). As outras seguem por copia exata, com o atraso aplicado
    na juncao.
    """
    prog = prog or (lambda v: None)
    fontes = []
    for i, d in enumerate(dubs, 1):
        src, idx, atraso = d.arquivo, d.faixa, d.atraso_ms
        if vai_virar_flac(d, film):
            if d.eh_musica():
                if d.trechos:
                    msg(tr("Música %d: montando trecho por trecho (%d trechos; só esta faixa vira FLAC, sem "
                           "perdas)...") % (i, len(d.trechos)))
                elif abs(d.atempo - 1.0) > 1e-9:
                    msg(tr("Música %d: corrigindo a velocidade (só esta faixa vira FLAC, sem perdas)...") % i)
                else:
                    msg(tr("Música %d: seguindo o clipe no começo e no fim (só esta faixa vira FLAC, sem perdas)...")
                        % i)
            elif d.trechos:
                msg(tr("Dublagem %d: montando trecho por trecho (%d trechos; só esta dublagem vira FLAC, "
                       "sem perdas)...") % (i, len(d.trechos)))
            else:
                msg(tr("Dublagem %d: corrigindo a velocidade (só esta dublagem vira FLAC, sem perdas)...") % i)
            novo = os.path.join(tmp, "dub%d_sincronizada.mka" % i)
            fita = d.modo_velocidade == "fita"
            montar_por_pedacos(src, idx, pedacos_efetivos(d), d.atempo, novo, ferr, msg, prog, cancelar,
                               limite_s=limite_da_faixa(d, film, teste), modo_velocidade=d.modo_velocidade,
                               fades=d.fades(),
                               dur_s=duracao_da_faixa(d) if fita else None)
            src, idx, atraso = novo, 0, 0
        fontes.append({"d": d, "src": src, "idx": idx, "atraso": atraso})
    return fontes


TIPOS_ESCOLHIVEIS = ("video", "audio", "subtitle")


def faixas_mantidas(film, manter=None):
    """Faixas do filme que vao para o arquivo final, na ordem original. manter=None: todas."""
    return [f for f in film.faixas if f.tipo in TIPOS_ESCOLHIVEIS and (manter is None or f.idx in manter)]


def validar_manter(film, manter):
    reais = film.imagens                       # (uma capa embutida nao conta como video)
    if manter is not None and not any(f.tipo == "video" and (f in reais or not reais)
                                      for f in faixas_mantidas(film, manter)):
        raise RuntimeError(tr("Mantenha pelo menos uma faixa de vídeo do filme."))


def faixas_padrao(film):
    """Indices das faixas do filme que entram quando nada foi escolhido: todas, menos as capas embutidas."""
    return set(f.idx for f in film.faixas if f.tipo in TIPOS_ESCOLHIVEIS and not f.capa())


# ----------------------------------------------------------------- organizacao do arquivo final
# Uma faixa do arquivo final e identificada por uma CHAVE:
#   ("filme", indice_do_fluxo)   faixa do proprio filme
#   ("dub", Dublagem)            dublagem adicionada
#   ("leg", LegendaExterna)      legenda externa adicionada
# O arquivo final sempre tem os videos, depois os audios, depois as legendas; DENTRO de cada tipo vale a
# ordem da lista `ordem`. Faixas do filme fora de `manter` nao entram (dublagens e legendas da lista entram).
IDIOMAS_PT = ("por", "pt", "pob", "pt-br", "ptb")
_SINAIS_PORTUGAL = ("portugal", "pt-pt", "european", "europeu", "europeo", "européen", "europäisch")
_SINAIS_COMENTARIO = ("comment", "coment", "kommentar", "commento", "commentaire")
_SINAIS_DESCRICAO = ("descri", "audiodesc", "audio desc", "hörfilm")


@dataclass
class Organizacao:
    ordem: list = field(default_factory=list)   # chaves em ordem (as que faltarem entram no fim do seu tipo)
    manter: set = None                          # indices das faixas do FILME que entram (None = todas)
    padrao_audio: tuple = None                  # chave do audio que toca sozinho (None = o primeiro)
    padrao_legenda: tuple = None                # chave da legenda que aparece sozinha (None = nenhuma)


def eh_portugues(idioma):
    return (idioma or "").strip().lower() in IDIOMAS_PT


def eh_ptbr(idioma, titulo=""):
    """Portugues do Brasil: portugues sem sinal de ser de Portugal no titulo ('pob' e 'pt-BR' contam)."""
    t = (titulo or "").lower()
    return eh_portugues(idioma) and not any(x in t for x in _SINAIS_PORTUGAL)


def eh_comentario(f):
    """Faixa de comentarios (diretor, elenco...): marcada assim no arquivo ou com isso no titulo."""
    return bool(f.disposicao.get("comment")) or any(x in (f.titulo or "").lower() for x in _SINAIS_COMENTARIO)


def eh_extra(f):
    """Comentarios ou audiodescricao: faixas que o padrao nao poe no arquivo."""
    return eh_comentario(f) or bool(f.disposicao.get("visual_impaired")) or \
        any(x in (f.titulo or "").lower() for x in _SINAIS_DESCRICAO)


def idioma_original_auto(film):
    """
    Idioma original do filme: o da primeira faixa de audio que nao e portugues nem comentario (num remux, a
    primeira faixa costuma ser a do idioma original). Filme nacional (so audio em portugues): 'por'.
    """
    for f in film.audios:
        if f.idioma and f.idioma not in ("und", "zxx", "mul", "mis") and not eh_portugues(f.idioma) \
                and not eh_extra(f):
            return f.idioma
    return next((f.idioma for f in film.audios if f.idioma), "")


def _faixa_por_idx(film):
    return {f.idx: f for f in film.faixas}


def tipo_da_chave(film, k, _cache=None):
    if k[0] == "dub":
        return "audio"
    if k[0] == "leg":
        return "subtitle"
    f = (_cache or _faixa_por_idx(film)).get(k[1])
    return f.tipo if f else None


def completar_ordem(film, dubs=(), legendas=(), ordem=None):
    """
    A ordem com todas as faixas que existem agora: tira o que saiu da lista (dublagem removida...) e poe no fim
    o que ainda nao estava (faixas do filme na ordem do arquivo, depois dublagens e legendas na ordem da lista).
    """
    fx = _faixa_por_idx(film)
    validas = [("filme", f.idx) for f in film.faixas if f.tipo in TIPOS_ESCOLHIVEIS] + \
              [("dub", d) for d in dubs] + [("leg", x) for x in legendas]
    nova = []
    for k in ordem or []:
        if k in validas and k not in nova and tipo_da_chave(film, k, fx):
            nova.append(k)
    return nova + [k for k in validas if k not in nova]


def itens_saida(film, dubs=(), legendas=(), org=None):
    """{"video": [...], "audio": [...], "subtitle": [...]}: as chaves que entram no arquivo final, em ordem."""
    org = org or Organizacao()
    fx = _faixa_por_idx(film)
    grupos = {t: [] for t in TIPOS_ESCOLHIVEIS}
    for k in completar_ordem(film, dubs, legendas, org.ordem):
        if k[0] == "filme" and org.manter is not None and k[1] not in org.manter:
            continue
        grupos[tipo_da_chave(film, k, fx)].append(k)
    return grupos


def padroes_efetivos(itens, org):
    """(chave do audio padrao, chave da legenda padrao ou None) do que realmente entra no arquivo."""
    a = org.padrao_audio if org.padrao_audio is not None and org.padrao_audio in itens["audio"] else \
        (itens["audio"][0] if itens["audio"] else None)
    s = org.padrao_legenda if org.padrao_legenda is not None and org.padrao_legenda in itens["subtitle"] else None
    return a, s


def disposicao(film, k, padrao, _cache=None):
    """Marcas da faixa no arquivo final (ex.: 'default', 'forced', 'default+forced'; '0' = nenhuma)."""
    marcas = []
    if k[0] == "filme":
        f = (_cache or _faixa_por_idx(film)).get(k[1])
        marcas = [m for m in DISPOSICOES_PRESERVADAS if f is not None and f.disposicao.get(m)]
    elif k[0] == "leg" and k[1].forcada:
        marcas = ["forced"]
    if padrao:
        marcas.insert(0, "default")
    return "+".join(marcas) or "0"


def organizar_padrao(film, dubs=(), legendas=(), idioma_original=None):
    """
    VIDEOCLIPE (alguma faixa adicionada e musica): 1) as musicas, na ordem da lista (a primeira toca sozinha),
    2) o som original do clipe (a primeira faixa dele que nao e comentario; a do idioma original, se escolhido),
    3) as outras faixas adicionadas. As legendas seguem a regra abaixo.

    O padrao de BDRemux do EternalDub (pedido do criador do projeto):
      audio:   1) as dublagens em PT-BR (na ordem da lista)  2) as faixas PT-BR que o filme ja tem
               3) a faixa principal do idioma original (a primeira dele que nao e comentario nem audiodescricao)
               4) as outras dublagens adicionadas
      legenda: 1) PT-BR completa  2) PT-BR forcada  3) as outras legendas externas. Uma legenda externa PT-BR
               substitui as do filme do MESMO tipo (uma completa externa tira as completas do filme, mas a
               forcada do filme continua: ela traduz placas e falas em outro idioma enquanto se ouve a dublagem).
               Entre as do filme, a comum vem antes da para surdos.
    O video entra inteiro. As outras faixas do filme ficam desmarcadas, no fim da lista (da para marcar de novo).
    O primeiro audio e o padrao; nenhuma legenda e padrao (as forcadas continuam forcadas).
    """
    idioma_original = (idioma_original or idioma_original_auto(film) or "").lower()
    ordem, manter = [], set()

    def por(f, k=None):
        k = k or ("filme", f.idx)
        if k not in ordem:
            ordem.append(k)
            if k[0] == "filme":
                manter.add(f.idx)

    for f in film.imagens or film.videos:                      # (as capas embutidas ficam de fora)
        por(f)
    musicas = [d for d in dubs if d.eh_musica()]
    if musicas:                                                # videoclipe
        for d in musicas:                                      # 1) a musica em alta qualidade
            por(None, ("dub", d))
        principais = [f for f in film.audios if not eh_extra(f)]
        original = next((f for f in principais if (f.idioma or "").lower() == idioma_original), None) \
            if idioma_original else None
        original = original or (principais[0] if principais else None)
        if original is not None:                               # 2) o som original do clipe
            por(original)
    else:
        for d in dubs:                                         # 1) dublagens PT-BR
            if eh_ptbr(d.idioma, d.nome):
                por(None, ("dub", d))
        for f in film.audios:                                  # 2) PT-BR do proprio filme
            if eh_ptbr(f.idioma, f.titulo) and not eh_extra(f):
                por(f)
        principais = [f for f in film.audios if not eh_extra(f) and not eh_ptbr(f.idioma, f.titulo)]
        original = next((f for f in principais if (f.idioma or "").lower() == idioma_original), None)
        if original is None and not eh_portugues(idioma_original):  # idioma sem marca no arquivo: a 1a nao-PT
            original = next((f for f in principais if (f.idioma or "") in ("", "und")), None)
        if original is not None:                               # 3) idioma original
            por(original)
    for d in dubs:                                             # 4) outras dublagens adicionadas
        por(None, ("dub", d))
    ext_pt = [x for x in legendas if eh_ptbr(x.idioma, x.nome)]
    pt_filme = [f for f in film.legendas if eh_ptbr(f.idioma, f.titulo)]
    for forcada in (False, True):                              # legendas: 1) PT-BR completa  2) PT-BR forcada
        externas = [x for x in ext_pt if bool(x.forcada) == forcada]
        for x in externas:
            por(None, ("leg", x))
        if not externas:                                       # sem externa desse tipo: as do filme
            for f in sorted((f for f in pt_filme if f.forcada() == forcada),
                            key=lambda f: bool(f.disposicao.get("hearing_impaired"))):
                por(f)
    for x in legendas:                                         # 3) outras externas
        por(None, ("leg", x))
    resto = [k for k in completar_ordem(film, dubs, legendas) if k not in ordem]   # desmarcadas, no fim
    return Organizacao(ordem=ordem + resto, manter=manter, padrao_audio=None, padrao_legenda=None)


def musicas_primeiro(film, dubs=(), legendas=(), ordem=None):
    """A ordem com as musicas (videoclipe) no comeco dos audios, na ordem da lista; o resto fica como estava."""
    ordem = completar_ordem(film, dubs, legendas, ordem)
    mus = [("dub", d) for d in dubs if d.eh_musica()]
    resto = [k for k in ordem if k not in mus]
    fx = _faixa_por_idx(film)
    i = next((j for j, k in enumerate(resto) if tipo_da_chave(film, k, fx) == "audio"), len(resto))
    return resto[:i] + mus + resto[i:]


def posicoes_para_conferencia(film, dubs, legendas, org, ref_pos):
    """
    Para a conferencia depois de gerar: (posicoes das dublagens entre os audios do arquivo final, nomes delas,
    posicao da faixa de referencia do filme ou None se ela nao entrou).
    """
    audio = itens_saida(film, dubs, legendas, org)["audio"]
    posicoes = [i for i, k in enumerate(audio) if k[0] == "dub"]
    nomes = [audio[i][1].nome for i in posicoes]
    ref = ("filme", film.audios[ref_pos].idx) if 0 <= ref_pos < len(film.audios) else None
    return posicoes, nomes, (audio.index(ref) if ref in audio else None)


_DEFAULT_MODE = {}


def suporta_default_mode(ferr):
    """O FFmpeg conhece a opcao -default_mode do MKV (4.4 ou mais novo)? Sem ela, o MKV marcaria sozinho a
    primeira legenda como padrao (e ela apareceria sem ninguem pedir)."""
    if ferr.ffmpeg not in _DEFAULT_MODE:
        try:
            p = subprocess.run([ferr.ffmpeg, "-hide_banner", "-h", "muxer=matroska"], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=CRIAR_SEM_JANELA,
                               timeout=20)
            _DEFAULT_MODE[ferr.ffmpeg] = b"default_mode" in p.stdout
        except Exception:
            _DEFAULT_MODE[ferr.ffmpeg] = False
    return _DEFAULT_MODE[ferr.ffmpeg]


# ----------------------------------------------------------------- legendas externas
def para_utf8(caminho, destino):
    """
    Legendas de texto em portugues muitas vezes vem em Windows-1252 (ANSI) ou UTF-16; o FFmpeg espera UTF-8 e
    perderia os acentos (ou linhas inteiras). Devolve (arquivo a usar, codificacao original): o proprio arquivo
    se ja for UTF-8, ou uma copia em UTF-8 gravada em `destino`.
    """
    with open(caminho, "rb") as f:
        dados = f.read()
    if dados.startswith(codecs.BOM_UTF8):
        return caminho, "utf-8"
    if dados.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        texto, origem = dados.decode("utf-16"), "utf-16"
    else:
        try:
            dados.decode("utf-8")
            return caminho, "utf-8"
        except UnicodeDecodeError:
            texto, origem = dados.decode("cp1252", errors="replace"), "windows-1252"
    with open(destino, "w", encoding="utf-8", newline="") as f:
        f.write(texto)
    return destino, origem


def _preparar_legendas(legendas, tmp, msg):
    """Legendas de texto que nao estao em UTF-8 viram uma copia em UTF-8 (o conteudo nao muda)."""
    saida = []
    for k, x in enumerate(legendas, 1):
        src = x.arquivo
        ext = os.path.splitext(src)[1].lower()
        if ext in EXT_LEGENDA_TEXTO:
            src, origem = para_utf8(src, os.path.join(tmp, "legenda%d%s" % (k, ext)))
            if origem != "utf-8":
                msg(tr("Legenda %d: texto em %s convertido para UTF-8 (os acentos ficam certos).") % (k, origem))
        saida.append({"l": x, "src": src, "idx": x.faixa, "atraso": int(x.atraso_ms or 0)})
    return saida


def inicio_do_arquivo(caminho, ferr):
    """Tempo inicial do arquivo (s), como o FFmpeg o ve ao junta-lo (0 se nao der para ler)."""
    try:
        p = subprocess.run([ferr.ffprobe, "-v", "error", "-show_entries", "format=start_time", "-of", "json", caminho],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                           creationflags=CRIAR_SEM_JANELA, timeout=60)
        return max(0.0, _flt(json.loads(p.stdout.decode("utf-8", "replace")).get("format", {}).get("start_time")))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


# ----------------------------------------------------------------- comando final
def comando_ffmpeg(film, fontes, saida, teste, ferr, tmp, msg, cancelar=None, org=None, legendas=(), manter=None):
    """
    Prepara os cortes (atraso negativo) e devolve o comando final do FFmpeg (copia sem recodificar), com as
    faixas na ordem da Organizacao: videos, depois audios, depois legendas.
      fontes:   dublagens prontas (de _preparar_dublagens);  legendas: legendas prontas (de _preparar_legendas).
    Dublagens do MESMO arquivo com o MESMO atraso entram por UMA entrada so (o arquivo e lido uma vez).

    LEGENDAS DO FILME: entram por uma entrada PROPRIA (o mesmo arquivo do filme, so com as legendas). Motivo: o
    FFmpeg escolhe qual arquivo ler pela faixa mais "atrasada"; uma legenda que fica um tempo sem fala
    parece atrasada, entao ele so le o arquivo do filme e para de ler a dublagem ate aparecer a proxima
    legenda. O audio desse intervalo acaba gravado muito depois no arquivo (ate minutos) e os players
    tocam SILENCIO ali (cada um aguenta um pouco diferente). Com a entrada propria, ele avanca so a
    leitura das legendas ate a proxima fala, e filme e dublagem seguem lado a lado. A segunda leitura
    acontece quase junto da primeira, entao o sistema normalmente a serve da memoria (cache do disco).
    As legendas externas ja sao entradas proprias.

    PADRAO: todas as faixas de audio e de legenda recebem as marcas explicitas (uma de audio e no maximo uma de
    legenda como padrao; forcada, comentario etc. do filme continuam), e o MKV nao inventa uma legenda padrao.
    """
    if org is None:
        org = Organizacao(manter=manter)
    fx = _faixa_por_idx(film)
    dubs = [f["d"] for f in fontes]
    legs = [x["l"] for x in legendas]
    itens = itens_saida(film, dubs, legs, org)
    cmd = [ferr.ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-v", "warning", "-progress", "pipe:1", "-y",
           "-i", film.caminho]
    n_entradas = 1
    entradas, mapa_dub = {}, {}
    for k, f in enumerate(fontes, 1):
        d, src, idx, atraso = f["d"], f["src"], f["idx"], f.get("atraso", f["d"].atraso_ms)
        offset = "%dms" % atraso if atraso > 0 else None
        if atraso < 0:
            msg(tr("Dublagem %d: cortando o começo da dublagem (cópia exata, sem recodificar)...") % k)
            corte = os.path.join(tmp, "dub%d_corte.mka" % k)
            _rodar([ferr.ffmpeg, "-y", "-v", "error", "-nostdin", "-i", src, "-map", "0:a:%d" % idx, "-c", "copy",
                    "-ss", "%dms" % (-atraso), corte], cancelar=cancelar)
            # A copia so corta entre quadros de audio: o primeiro quadro que fica comeca um pouco DEPOIS do ponto
            # pedido (ate 1 quadro: ~21 ms em AAC, 32 ms em AC3, ~90 ms em FLAC), e o arquivo cortado guarda esse resto
            # como o seu tempo inicial. Ao juntar, o FFmpeg leva cada entrada para o zero e jogaria o resto fora (a
            # dublagem ficaria adiantada). O -itsoffset devolve o resto: fica exato (ate 0,5 ms, o arredondamento do MKV).
            resto = inicio_do_arquivo(corte, ferr)
            src, idx, atraso = corte, 0, 0
            offset = "%.6f" % resto if resto > 0 else None
        chave = (os.path.abspath(src), offset)
        if chave not in entradas:
            entradas[chave] = n_entradas
            n_entradas += 1
            if offset:
                cmd += ["-itsoffset", offset]
            cmd += ["-i", src]
        mapa_dub[id(d)] = "%d:a:%d" % (entradas[chave], idx)
    entrada_leg = None
    if any(k[0] == "filme" for k in itens["subtitle"]):        # legendas do filme por uma entrada propria
        entrada_leg = n_entradas
        n_entradas += 1
        cmd += ["-vn", "-an", "-dn", "-i", film.caminho]
    mapa_leg = {}
    for x in legendas:
        if x["atraso"] > 0:
            cmd += ["-itsoffset", "%dms" % x["atraso"]]
        elif x["atraso"] < 0:                                   # mais cedo: pula o comeco da legenda (sem
            cmd += ["-ss", "%.3f" % (-x["atraso"] / 1000.0)]    # tempos negativos, que deslocariam o arquivo)
        cmd += ["-i", x["src"]]
        mapa_leg[id(x["l"])] = "%d:s:%d" % (n_entradas, x["idx"])
        n_entradas += 1

    def mapa(k):
        if k[0] == "dub":
            return mapa_dub[id(k[1])]
        if k[0] == "leg":
            return mapa_leg[id(k[1])]
        return "%d:%d" % (entrada_leg if fx[k[1]].tipo == "subtitle" else 0, k[1])

    for tipo in TIPOS_ESCOLHIVEIS:
        for k in itens[tipo]:
            cmd += ["-map", mapa(k)]
    cmd += ["-map", "0:t?", "-c", "copy"]                     # 0:t? = anexos do filme (fontes etc.)
    for i, k in enumerate(itens["subtitle"]):
        codec = k[1].codec if k[0] == "leg" else fx[k[1]].codec
        if codec in LEGENDAS_PARA_SRT:                        # o MKV nao aceita: vira SRT (e texto, nada se perde)
            cmd += ["-c:s:%d" % i, "srt"]
    pa, pl = padroes_efetivos(itens, org)
    for i, k in enumerate(itens["audio"]):
        if k[0] == "dub":
            cmd += ["-metadata:s:a:%d" % i, "language=%s" % (k[1].idioma or "und"),
                    "-metadata:s:a:%d" % i, "title=%s" % k[1].nome]
        cmd += ["-disposition:a:%d" % i, disposicao(film, k, k == pa, fx)]
    for i, k in enumerate(itens["subtitle"]):
        if k[0] == "leg":
            cmd += ["-metadata:s:s:%d" % i, "language=%s" % (k[1].idioma or "und")]
            if k[1].nome:
                cmd += ["-metadata:s:s:%d" % i, "title=%s" % k[1].nome]
        cmd += ["-disposition:s:%d" % i, disposicao(film, k, pl is not None and k == pl, fx)]
    if itens["subtitle"] and suporta_default_mode(ferr):
        cmd += ["-default_mode", "infer_no_subs"]
    if teste:
        cmd += ["-t", "300"]
    cmd.append(saida)
    return cmd


def montar(film, dubs, saida, teste, ferr, msg, prog, cancelar=None, org=None, legendas=(), manter=None):
    """
    Gera o MKV final com o FFmpeg (copia dos fluxos, sem recodificar), organizado por `org` (Organizacao;
    None = faixas do filme na ordem original e dublagens depois dos audios do filme). `manter` so vale sem `org`.
    Devolve o caminho do arquivo gerado.
    """
    cancelar = cancelar or threading.Event()
    if org is None:          # sem organizacao: como nas versoes antigas (a dublagem marcada como padrao toca sozinha)
        org = Organizacao(manter=manter, padrao_audio=next((("dub", d) for d in dubs if d.padrao), None))
    legendas = list(legendas)
    validar(film, dubs, legendas)
    validar_manter(film, org.manter)
    tmp = tempfile.mkdtemp(prefix="eternaldub_")
    try:
        fontes = _preparar_dublagens(dubs, film, tmp, ferr, msg, prog, cancelar, teste)
        legs = _preparar_legendas(legendas, tmp, msg)
        total = 300.0 if teste else max(film.duracao, 1.0)
        msg(tr("Montando o arquivo (só copia os fluxos, sem recodificar)..."))
        cmd = comando_ffmpeg(film, fontes, saida, teste, ferr, tmp, msg, cancelar, org, legs)

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


def verificar_integridade(film, arquivo_final, ferr, msg, prog, cancelar=None, manter=None):
    """
    Confere se cada fluxo ORIGINAL do filme que foi mantido (video, audio, legenda) esta no arquivo final
    exatamente igual (mesmo hash), em qualquer posicao: a ordem das faixas pode ter mudado. Le os dois
    arquivos inteiros.
    """
    mantidas = faixas_mantidas(film, manter)
    nomes = ["%s %d (%s)" % ({"video": tr("vídeo"), "audio": tr("áudio"), "subtitle": tr("legenda")}[f.tipo],
                             f.pos + 1, f.rotulo()) for f in mantidas]
    msg(tr("Calculando o hash do filme original (lê o arquivo inteiro)..."))
    h1 = _hashes(film.caminho, ["0:%d" % f.idx for f in mantidas], ferr, film.duracao,
                 lambda f: prog(int(f * 50)), cancelar)
    final = sondar_arquivo(arquivo_final)
    fluxos = [f for f in final.faixas if f.tipo in TIPOS_ESCOLHIVEIS]
    msg(tr("Calculando o hash do arquivo final..."))
    h2 = _hashes(arquivo_final, ["0:%d" % f.idx for f in fluxos], ferr, film.duracao,
                 lambda f: prog(50 + int(f * 50)), cancelar)
    prog(100)
    no_final = {(f.tipo, h) for f, h in zip(fluxos, h2)}
    return [(nome, i < len(h1) and (f.tipo, h1[i]) in no_final) for i, (nome, f) in enumerate(zip(nomes, mantidas))]


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


def _entrelacamento(saida, inicio, duracao, ferr, esperadas=(), limite_s=60.0):
    """
    Na ORDEM FISICA do arquivo, quanto o audio de cada faixa fica atras do video, num trecho.
    Os players leem o arquivo em ordem: se o audio de um momento estiver gravado muito depois do video
    desse momento, eles tocam silencio ali. Devolve {indice_do_fluxo: atraso_maximo_s}; uma faixa de
    `esperadas` que nao aparece no trecho enquanto o video anda conta como atrasada pelo trecho todo.
    {} se nao deu para ler.
    """
    try:
        p = subprocess.run([ferr.ffprobe, "-v", "error", "-read_intervals", "%.3f%%+%.3f" % (max(0.0, inicio), duracao),
                            "-show_entries", "packet=stream_index,codec_type,pts_time,dts_time,pos", "-of", "csv=p=0",
                            saida], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                           timeout=limite_s, creationflags=CRIAR_SEM_JANELA)
    except (subprocess.TimeoutExpired, OSError):
        return {}
    pacotes = []
    for linha in p.stdout.decode("ascii", "replace").splitlines():
        c = linha.split(",")
        if len(c) < 5:
            continue
        try:
            t = float(c[3]) if c[3] not in ("", "N/A") else float(c[2])
            pacotes.append((int(c[4]), c[0], int(c[1]), t))
        except ValueError:
            continue
    pacotes.sort()
    video, video_ini, audio, pior = None, None, {}, {}
    for _, tipo, idx, t in pacotes:
        if tipo == "video":
            video = t if video is None else max(video, t)
            video_ini = t if video_ini is None else min(video_ini, t)
        elif tipo == "audio":
            audio[idx] = t if idx not in audio else max(audio[idx], t)
        else:
            continue
        if video is not None:
            for i, ta in audio.items():
                pior[i] = max(pior.get(i, 0.0), video - ta)
    if video is not None:
        for i in esperadas:                   # a faixa nem apareceu: o audio dela esta gravado longe dali
            if i not in audio:
                pior[i] = max(0.0, video - max(video_ini, inicio))
    return pior


def conferir_dublagens(saida, posicoes, ref_saida, nomes, ferr, teste=False, cancelar=None, msg=None, prog=None):
    """
    Confere, DENTRO do arquivo gerado, se cada dublagem nova tem som e esta alinhada com o audio
    original (faixa `ref_saida` do arquivo gerado; None = so confere o som).
      posicoes: posicoes das dublagens entre os audios do arquivo gerado (veja posicoes_para_conferencia);
                um numero n (forma antiga) = todas as faixas de audio a partir da n.
    Le 2 ou 3 trechos curtos (cada leitura tem tempo maximo; nunca trava). Devolve, por dublagem:
      com_som: True / False / None (None = nao deu para conferir)
      sobra_ms: diferenca de sincronia medida (None = nao medida)
      sem_audio_em: tempos (s) dos trechos em que a faixa nao tinha audio nenhum
      entrelacamento_s: quanto o audio ficou gravado atras do video no arquivo (None = nao medido).
        Acima de ~2 s, alguns players tocam silencio ali.
    """
    msg = msg or (lambda m: None)
    prog = prog or (lambda v: None)
    arq = sondar_arquivo(saida)
    dur = arq.duracao or (300.0 if teste else 0.0)
    if arq.videos and arq.videos[0].duracao > 0:    # a dublagem pode passar do fim do filme
        dur = min(dur, arq.videos[0].duracao) if dur else arq.videos[0].duracao
    pontos = [45.0, 170.0] if teste else [dur * 0.15, dur * 0.5, dur * 0.85]
    pontos = [p for p in pontos if p + 30 < dur] or [max(0.0, dur / 3)]
    novas = list(range(posicoes, len(arq.audios))) if isinstance(posicoes, int) else \
        [p for p in posicoes if p < len(arq.audios)]
    idx_fluxo = {f.pos: f.idx for f in arq.audios}
    res = {p: {"nome": nomes[i] if i < len(nomes) else tr("faixa %d") % p, "rms": 0.0, "atrasos": [], "lidos": 0,
               "sem_audio_em": [], "entrelacamento_s": None} for i, p in enumerate(novas)}
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
        entre = _entrelacamento(saida, max(0.0, t - 3), 26.0, ferr,
                                [idx_fluxo[p] for p in novas]) if arq.videos else {}
        for p in novas:
            x = janela.get(p, np.zeros(0, np.int16))
            if len(x) < da.SR_AUDIO:
                res[p]["sem_audio_em"].append(t)
                continue
            if idx_fluxo.get(p) in entre:
                res[p]["entrelacamento_s"] = max(res[p]["entrelacamento_s"] or 0.0, entre[idx_fluxo[p]])
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
