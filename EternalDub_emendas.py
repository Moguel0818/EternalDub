# SPDX-License-Identifier: MIT
# EternalDub - Copyright (C) 2026 Moguel0818 e colaboradores / and contributors
# -*- coding: utf-8 -*-
"""
EternalDub_emendas.py - edicao MANUAL das emendas da sincronia por trechos (nada de interface grafica).

A sincronia por trechos (Dublagem.trechos) e uma lista de PEDACOS [[ini_filme, fim_filme, ini_dub], ...]:
cada pedaco da dublagem e colocado num intervalo do filme. A emenda e o ponto onde um pedaco acaba e o
proximo comeca. Aqui o mapa vira um modelo que se edita pelo que importa para o ouvido:

    tempo do filme em que a emenda acontece   (t)
    silencio inserido logo depois             (silencio, s)   <- a dublagem nao tem esse pedaco
    pedaco da dublagem que sai                (remocao,  s)   <- ela tem algo que o filme nao tem
    quantia = silencio - remocao              (>0 atrasa o resto da dublagem, <0 adianta)

Regras que o modelo garante (a prioridade do projeto e a precisao dos tempos):
  * mover uma emenda NUNCA muda o alinhamento de nenhum pedaco: so muda onde a troca acontece;
  * a dublagem nunca volta no tempo, e nenhum trecho fica menor que MIN_TRECHO;
  * um mapa que nao foi editado volta IDENTICO (para_trechos devolve exatamente o que entrou);
  * emenda sem efeito (quantia ~0) nao existe: ela e removida (senao viraria um corte de 16 ms no meio da fala).

Tambem ha aqui as funcoes que dizem se uma emenda cai numa PAUSA da dublagem ou no meio de som (voz, musica),
para a pessoa nao cortar fala sem querer.

Convencoes: tempos em segundos; tempo "esticado" = tempo da dublagem depois da correcao de velocidade
(tempo_original / atempo). Os tempos do filme aqui sao os do MAPA, sem o ajuste fino (Dublagem.atraso_ms),
que quem chama soma ou subtrai.
"""
from dataclasses import dataclass

import numpy as np

VERSAO_EMENDAS = "1.3"

MIN_TRECHO = 0.05        # s: menor trecho permitido entre duas emendas
MIN_QUANTIA = 0.001      # s: quantia menor que isto = emenda sem efeito
ARRED = 4                # casas decimais (0,1 ms) dos pedacos guardados no projeto
ENV_RATE = 100.0         # pontos do envelope da onda por segundo (10 ms), o mesmo do EternalDub_core

# nivel do som na emenda, relativo ao volume tipico da dublagem (picos da onda)
NIVEL_PAUSA = 0.06       # abaixo disto: pausa
NIVEL_ALTO = 0.25        # acima disto: som alto (provavelmente voz ou musica forte)
TOLERANCIA_NIVEL = 0.01  # niveis assim proximos contam como empatados (vence a posicao mais perto)


def _limpar(x):
    """Zera o que e so ruido de arredondamento (menos de 0,1 ms)."""
    return 0.0 if abs(x) < 1e-4 else x


@dataclass
class Emenda:
    t: float                 # tempo do filme em que o trecho anterior termina
    silencio: float = 0.0    # silencio inserido logo depois (tempo do filme)
    remocao: float = 0.0     # pedaco da dublagem que sai (tempo do filme, ja esticado)

    @property
    def quantia(self):
        """>0: o resto da dublagem fica mais tarde (silencio); <0: fica mais cedo (sai um pedaco)."""
        return self.silencio - self.remocao

    @property
    def fim(self):
        """Onde o proximo trecho comeca no filme."""
        return self.t + self.silencio


class MapaEditavel:
    """
    Mapa por trechos como lista de emendas. Veja o topo do arquivo.

      atempo:  correcao de velocidade da dublagem (1.0 = nenhuma)
      inicio:  tempo do filme em que a dublagem comeca (primeiro pedaco)
      ui0:     tempo esticado da dublagem nesse ponto (>= 0; > 0 = o comeco da dublagem fica de fora)
      fim:     tempo do filme em que o ultimo pedaco termina
      emendas: [Emenda, ...] em ordem
      dur_filme / dur_dub: ate onde vai o audio do filme e da dublagem (tempo original; None = desconhecido).
               Servem so para o ultimo pedaco acompanhar a dublagem quando uma edicao a desloca.
    """

    def __init__(self, atempo, inicio, ui0, fim, emendas, dur_filme=None, dur_dub=None):
        self.atempo = float(atempo or 1.0)
        self.inicio = float(inicio)
        self.ui0 = float(ui0)
        self.fim = float(fim)
        self.emendas = list(emendas)
        self.dur_filme = float(dur_filme) if dur_filme else None
        self.dur_dub = float(dur_dub) if dur_dub else None
        self._original = None            # pedacos como entraram (devolvidos enquanto nada for editado)

    # ------------------------------------------------------------ construcao
    @classmethod
    def de_trechos(cls, trechos, atempo=1.0, dur_filme=None, dur_dub=None):
        """Modelo a partir de Dublagem.trechos ([[ini_filme, fim_filme, ini_dub], ...])."""
        atempo = float(atempo or 1.0)
        r = 1.0 / atempo
        P = sorted(([float(a), float(b), float(c) * r] for a, b, c in trechos), key=lambda x: x[0])
        if not P:
            raise ValueError("sem trechos")
        emendas = []
        for (fi, ff, ui), (fi2, _, ui2) in zip(P, P[1:]):
            # o mapa guarda 4 casas decimais: diferencas menores que 0,1 ms sao so arredondamento
            emendas.append(Emenda(t=ff, silencio=_limpar(fi2 - ff), remocao=_limpar(ui2 - (ui + ff - fi))))
        m = cls(atempo, P[0][0], P[0][2], P[-1][1], emendas, dur_filme, dur_dub)
        m._original = [[round(a, ARRED), round(b, ARRED), round(c, ARRED)] for a, b, c in trechos]
        return m

    @classmethod
    def de_atraso(cls, atraso_s, atempo=1.0, dur_filme=None, dur_dub=None):
        """Modelo de uma dublagem com UM atraso so (sem emendas ainda): tempo_filme = tempo_dub / atempo + atraso."""
        atempo = float(atempo or 1.0)
        fim = 1e7
        limites = [x for x in (dur_filme, (dur_dub / atempo + atraso_s) if dur_dub else None) if x]
        if limites:
            fim = min(limites)
        return cls(atempo, max(0.0, atraso_s), max(0.0, -atraso_s), fim, [], dur_filme, dur_dub)

    def copia(self):
        m = MapaEditavel(self.atempo, self.inicio, self.ui0, self.fim,
                         [Emenda(e.t, e.silencio, e.remocao) for e in self.emendas], self.dur_filme, self.dur_dub)
        m._original = self._original
        return m

    # ------------------------------------------------------------ leitura
    def atrasos(self):
        """Atraso de cada trecho (s): tempo_filme - tempo_esticado_da_dublagem. Tem len(emendas)+1 valores."""
        a = [self.inicio - self.ui0]
        for e in self.emendas:
            a.append(a[-1] + e.quantia)
        return a

    def inicio_do_trecho(self, k):
        return self.inicio if k == 0 else self.emendas[k - 1].fim

    def fim_do_trecho(self, k):
        return self.emendas[k].t if k < len(self.emendas) else self._fim()

    def _fim(self):
        """Fim do ultimo pedaco: o fim do filme ou da dublagem (o que vier primeiro), acompanhando as edicoes."""
        if self._original is not None:
            return self.fim
        limites = []
        if self.dur_filme:
            limites.append(self.dur_filme)
        if self.dur_dub:
            limites.append(self.dur_dub / self.atempo + self.atrasos()[-1])
        return max(self.inicio_do_trecho(len(self.emendas)) + MIN_TRECHO, min(limites)) if limites else self.fim

    def trechos_info(self):
        """[(ini_filme, fim_filme, atraso)] de cada trecho, no filme."""
        at = self.atrasos()
        return [(self.inicio_do_trecho(k), self.fim_do_trecho(k), at[k]) for k in range(len(at))]

    def para_trechos(self):
        """Pedacos [[ini_filme, fim_filme, ini_dub]] para Dublagem.trechos (ini_dub no tempo ORIGINAL)."""
        if self._original is not None:
            return [list(p) for p in self._original]
        pedacos = []
        fi, ui = self.inicio, self.ui0
        for k in range(len(self.emendas) + 1):
            ff = self.fim_do_trecho(k)
            if ui < 0:                      # a dublagem nao existe antes do zero: o trecho comeca mais tarde
                fi, ui = fi - ui, 0.0
            if ff > fi:
                pedacos.append([round(fi, ARRED), round(ff, ARRED), round(ui * self.atempo, ARRED)])
            if k < len(self.emendas):
                e = self.emendas[k]
                ui += (ff - fi) + e.remocao
                fi = e.fim
        return pedacos

    def tem_emendas(self):
        """False = um atraso so serve (nao ha emendas): a dublagem pode seguir por copia exata."""
        return bool(self.emendas)

    def atraso_unico(self):
        return self.atrasos()[0]

    # ------------------------------------------------------------ edicao
    def _editou(self):
        self._original = None

    @staticmethod
    def _definir_quantia(e, quantia):
        e.silencio, e.remocao = max(0.0, quantia), max(0.0, -quantia)

    def _teto_silencio(self, i):
        """Maior silencio que a emenda i aceita sem deixar o trecho seguinte menor que MIN_TRECHO."""
        return self.fim_do_trecho(i + 1) - self.emendas[i].t - MIN_TRECHO

    def limites_emenda(self, i):
        """(menor, maior) tempo em que a emenda i pode ficar. Se menor > maior, ela nao pode andar."""
        e = self.emendas[i]
        return self.inicio_do_trecho(i) + MIN_TRECHO, self.fim_do_trecho(i + 1) - e.silencio - MIN_TRECHO

    def mover_emenda(self, i, t):
        """
        Muda o tempo do filme em que a emenda i acontece. O alinhamento de todos os pedacos continua o
        mesmo (so a troca de um alinhamento para o outro anda). Devolve o tempo realmente usado.
        """
        lo, hi = self.limites_emenda(i)
        if lo > hi:
            return self.emendas[i].t
        self._editou()
        self.emendas[i].t = min(max(float(t), lo), hi)
        return self.emendas[i].t

    def definir_quantia(self, i, quantia):
        """
        Muda a quantia da emenda i (>0 silencio, <0 sai um pedaco da dublagem). TUDO o que vem depois
        desloca junto (cada emenda seguinte continua somando a sua quantia). Quantia ~0 e recusada: use
        remover_emenda. Devolve a quantia usada (o silencio e limitado pelo trecho seguinte) ou None.
        """
        if abs(quantia) < MIN_QUANTIA:
            return None
        self._editou()
        if quantia > 0:
            quantia = min(quantia, self._teto_silencio(i))
            if quantia < MIN_QUANTIA:
                return None
        self._definir_quantia(self.emendas[i], quantia)
        return quantia

    def inserir_emenda(self, t, quantia):
        """
        Cria uma emenda no tempo t do filme com a quantia dada (o resto da dublagem desloca junto). Devolve o
        indice da nova emenda, ou None se nao couber (precisa de MIN_TRECHO livre dos dois lados) ou se a
        quantia for ~0.
        """
        if abs(quantia) < MIN_QUANTIA:
            return None
        k = sum(1 for e in self.emendas if e.t <= t)           # trecho onde t cai
        silencio = max(0.0, quantia)
        if not (self.inicio_do_trecho(k) + MIN_TRECHO <= t <= self.fim_do_trecho(k) - silencio - MIN_TRECHO):
            return None
        self._editou()
        self.emendas.insert(k, Emenda(float(t), silencio, max(0.0, -quantia)))
        return k

    def remover_emenda(self, i):
        """
        Tira a emenda i: os dois trechos viram um so (com o atraso do primeiro). Os trechos DEPOIS dela
        mantem o alinhamento: a emenda seguinte absorve a quantia (se ela ficar sem efeito, some tambem).
        """
        self._editou()
        e = self._tirar(i)
        self._arrumar(i)
        return e

    def _tirar(self, i):
        """Remove a emenda i sem mexer no alinhamento dos trechos seguintes (a proxima absorve a quantia)."""
        e = self.emendas.pop(i)
        if i < len(self.emendas):
            prox = self.emendas[i]
            self._definir_quantia(prox, prox.quantia + e.quantia)
        return e

    def deslocar_trecho(self, k, x, so_este=True):
        """
        Desloca o alinhamento do trecho k em x segundos (>0 = a dublagem toca mais tarde).
        so_este=True: so este trecho muda (as emendas dos dois lados absorvem); False: este e todos os seguintes.
        """
        if abs(x) < 1e-9:
            return
        self._editou()
        if k == 0:
            v = self.inicio - self.ui0 + x
            self.inicio, self.ui0 = max(0.0, v), max(0.0, -v)
            if self.emendas and self.inicio + MIN_TRECHO > self.emendas[0].t:
                self.inicio = max(0.0, self.emendas[0].t - MIN_TRECHO)
        else:
            e = self.emendas[k - 1]
            self._definir_quantia(e, e.quantia + x)
        if so_este and k < len(self.emendas):
            e = self.emendas[k]
            self._definir_quantia(e, e.quantia - x)
        self._arrumar()

    def _arrumar(self, a_partir=0):
        """Limita os silencios (nenhum trecho fica menor que MIN_TRECHO) e tira as emendas sem efeito."""
        i = max(0, a_partir - 1)
        while i < len(self.emendas):
            e = self.emendas[i]
            if e.silencio > 0:
                e.silencio = min(e.silencio, max(0.0, self._teto_silencio(i)))
            if abs(e.quantia) < MIN_QUANTIA:                    # sem efeito: os dois trechos viram um
                self._tirar(i)
                i = max(0, i - 1)
                continue
            i += 1

    # ------------------------------------------------------------ conferencia (usada nos testes)
    def problemas(self):
        """Lista de textos descrevendo o que esta errado no modelo (vazia = tudo certo)."""
        erros = []
        if self.atempo <= 0:
            erros.append("atempo invalido")
        t_ant = None
        for k, (ini, fim, _) in enumerate(self.trechos_info()):
            if fim - ini < MIN_TRECHO - 1e-9:
                erros.append("trecho %d menor que o minimo (%.4f s)" % (k, fim - ini))
            if t_ant is not None and ini < t_ant - 1e-9:
                erros.append("trecho %d comeca antes de o anterior terminar" % k)
            t_ant = fim
        for i, e in enumerate(self.emendas):
            if e.silencio < -1e-9 or e.remocao < -1e-9:
                erros.append("emenda %d com silencio ou remocao negativos" % i)
            if abs(e.quantia) < MIN_QUANTIA - 1e-12:
                erros.append("emenda %d sem efeito" % i)
        return erros


# ----------------------------------------------------------------- som na emenda (pausa ou meio de fala?)
def amplitude_do_envelope(env):
    """(N,) maior valor absoluto de cada ponto do envelope (N, 2) minimo/maximo da onda."""
    env = np.asarray(env)
    if env.ndim != 2 or len(env) == 0:
        return np.zeros(0, np.float32)
    return np.maximum(np.abs(env[:, 0]), np.abs(env[:, 1])).astype(np.float32)


def referencia_de_nivel(amp):
    """Volume de referencia da dublagem (os picos tipicos): o mesmo criterio de escala da onda na tela."""
    if len(amp) == 0:
        return 0.0
    return float(np.percentile(amp, 99.5))


def _pico(amp, x0, x1):
    """Maior amplitude entre os tempos x0 e x1 (s, tempo ORIGINAL da dublagem). None se fora do audio lido."""
    a, b = int(np.floor(max(0.0, x0) * ENV_RATE)), int(np.ceil(max(0.0, x1) * ENV_RATE)) + 1
    if a >= len(amp):
        return None
    return float(np.max(amp[a:min(b, len(amp))])) if b > a else None


def nivel_da_emenda(mapa, i, amp, ref, t=None):
    """
    Quao alto e o som da dublagem no lugar da emenda i (0 = silencio; 1 = picos tipicos da dublagem).
      * emenda com silencio inserido: olha 40 ms de cada lado do ponto onde a dublagem e interrompida;
      * emenda que remove um pedaco: olha o pedaco que sai mais 50 ms de cada lado.
    t: testa outra posicao para a emenda (mesmo alinhamento). None = nao deu para medir (onda ainda carregando).
    """
    if ref <= 0 or len(amp) == 0:
        return None
    e = mapa.emendas[i]
    t = e.t if t is None else t
    x_fim = t - mapa.atrasos()[i]                       # onde a dublagem (esticada) e cortada
    if e.remocao > e.silencio:
        x0, x1 = x_fim - 0.05, x_fim + e.remocao + 0.05
    else:
        x0, x1 = x_fim - 0.04, x_fim + 0.04
    p = _pico(amp, x0 * mapa.atempo, x1 * mapa.atempo)
    return None if p is None else p / ref


def classificar_nivel(nivel):
    """'pausa', 'baixo' ou 'alto' (None se nao foi medido)."""
    if nivel is None:
        return None
    return "pausa" if nivel < NIVEL_PAUSA else ("baixo" if nivel < NIVEL_ALTO else "alto")


def melhor_posicao(mapa, i, amp, ref, raio=1.5, passo=0.01):
    """
    Procura, ate `raio` s em volta da emenda i, a posicao em que ela corta o som mais baixo (uma pausa).
    Entre posicoes quase empatadas escolhe a mais perto da atual. Devolve o tempo do filme, ou o atual se nao
    deu para medir.
    """
    e = mapa.emendas[i]
    lo, hi = mapa.limites_emenda(i)
    if lo > hi or ref <= 0:
        return e.t
    cand = np.arange(max(lo, e.t - raio), min(hi, e.t + raio) + 1e-9, passo)
    niveis = [nivel_da_emenda(mapa, i, amp, ref, t) for t in cand]
    ok = [(c, n) for c, n in zip(cand, niveis) if n is not None]
    if not ok:
        return e.t
    menor = min(n for _, n in ok)
    perto = [c for c, n in ok if n <= menor + TOLERANCIA_NIVEL]
    return float(min(perto, key=lambda c: abs(c - e.t)))


def encaixar_em_pausa(mapa, i, t, amp, ref, raio=0.4, passo=0.01):
    """
    Usada ao ARRASTAR uma emenda ate t: se ali ela cortaria som, devolve a pausa mais perto (ate `raio` s); se
    ali ja e uma pausa (ou nao ha pausa por perto, ou nao deu para medir), devolve o proprio t.
    """
    n = nivel_da_emenda(mapa, i, amp, ref, t)
    if n is None or n < NIVEL_PAUSA:
        return t
    lo, hi = mapa.limites_emenda(i)
    if lo > hi:
        return t
    boas = []
    for c in np.arange(max(lo, t - raio), min(hi, t + raio) + 1e-9, passo):
        v = nivel_da_emenda(mapa, i, amp, ref, c)
        if v is not None and v < NIVEL_PAUSA:
            boas.append(float(c))
    return min(boas, key=lambda c: abs(c - t)) if boas else t
