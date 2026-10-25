# SPDX-License-Identifier: MIT
# EternalDub - Copyright (C) 2026 Moguel0818 e colaboradores / and contributors
# -*- coding: utf-8 -*-
"""
EternalDub_i18n.py - idiomas da interface (portugues do Brasil e ingles).

Como funciona: o texto em portugues e a "chave". tr("Abrir filme...") devolve o proprio texto
quando o idioma e portugues, ou a traducao do dicionario EN quando e ingles.

Para adicionar um idioma: crie um dicionario igual ao EN (mesmas chaves), inclua-o em
TRADUCOES e em IDIOMAS. Marcadores como %s, %d, %.1f, %+d precisam aparecer na traducao
na MESMA ordem.  (Contribuicoes de traducao sao bem-vindas!)

EternalDub interface languages (Brazilian Portuguese and English). To add a language, copy the
EN dictionary, translate the values (keep %s/%d/%.1f/%+d placeholders in the same order) and
register it in TRADUCOES and IDIOMAS. Translation contributions are welcome!
"""
import locale
import os

VERSAO_IDIOMAS = "1.0"

IDIOMAS = (("pt", "Português (Brasil)"), ("en", "English"))
_atual = "pt"


def definir(codigo):
    """Escolhe o idioma ('pt' ou 'en'). Qualquer outro valor vira portugues."""
    global _atual
    _atual = codigo if codigo in TRADUCOES or codigo == "pt" else "pt"


def atual():
    return _atual


def do_sistema():
    """'pt' se o sistema estiver em portugues; 'en' para qualquer outro idioma."""
    for nome in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        v = os.environ.get(nome, "")
        if v:
            return "pt" if v.lower().startswith("pt") else "en"
    try:
        v = (locale.getlocale()[0] or "").lower()
    except Exception:
        v = ""
    if not v:
        return "pt"
    return "pt" if v.startswith("pt") or "portuguese" in v else "en"


def tr(texto):
    """Traduz um texto da interface (a chave e o texto em portugues)."""
    if _atual == "pt":
        return texto
    return TRADUCOES.get(_atual, {}).get(texto, texto)


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


# ----------------------------------------------------------------------------- ENGLISH
EN = {
    # ---- rotulos curtos
    "ALTA": "HIGH",
    "MÉDIA": "MEDIUM",
    "BAIXA": "LOW",
    "áudio": "audio",
    "vídeo": "video",
    "legenda": "subtitle",
    "anexo": "attachment",
    "dados": "data",
    "VELOCIDADE": "SPEED",
    "DERIVA": "DRIFT",
    "CORTES": "CUTS",
    "SEM CORRESPONDÊNCIA": "NO MATCH",
    "rápida": "quick",
    "completa": "full",
    "antiga": "old",
    "%d min": "%d min",
    "%d s": "%d s",
    "faltam ~%s": "~%s left",
    "(levou %s)": "(took %s)",
    "filme": "movie",
    "Filme": "Movie",
    "Dublagem": "Dub",
    "Dublagem PT-BR": "Dub",
    "Filme (referência)": "Movie (reference)",
    "Filme - faixa %d": "Movie - track %d",
    "(carregando...)": "(loading...)",
    "(sem onda - %s)": "(no waveform - %s)",
    "%s   (atraso %+d ms)": "%s   (delay %+d ms)",
    "faixa %d": "track %d",
    "faixa %d: %s": "track %d: %s",
    "faixa %d:  %s": "track %d:  %s",
    "%s : faixa %d": "%s : track %d",
    "%s  -  faixa %d  (%s)": "%s  -  track %d  (%s)",
    "Sim": "Yes",
    "sempre": "always",
    "normal": "normal",
    "IDÊNTICO": "IDENTICAL",
    "DIFERENTE": "DIFFERENT",
    "_dublado": "_dubbed",
    "_dublado_TESTE": "_dubbed_TEST",

    # ---- menus, barra de ferramentas e acoes
    "Arquivo": "File",
    "Dublagens": "Dubs",
    "Sincronização": "Sync",
    "Montar": "Mux",
    "Ferramentas": "Tools",
    "Opções": "Options",
    "Ajuda": "Help",
    "Principal": "Main",
    "Motor de montagem": "Muxing engine",
    "FFmpeg (cópia sem recodificar)": "FFmpeg (copy without re-encoding)",
    "mkvmerge (cópia sem recodificar - recomendado)": "mkvmerge (copy without re-encoding - recommended)",
    "mkvmerge (não encontrado)": "mkvmerge (not found)",
    "Abrir filme...": "Open movie...",
    "Escolha o filme de alta qualidade (.mkv)": "Choose the high-quality movie (.mkv)",
    "Adicionar dublagem...": "Add dub...",
    "Adicione arquivos com dublagens (várias faixas de uma vez)": "Add files with dubs (several tracks at once)",
    "Remover": "Remove",
    "Mover para cima": "Move up",
    "Mover para baixo": "Move down",
    "Detectar atraso": "Detect delay",
    "Detectar atraso (F5)": "Detect delay (F5)",
    "Compara música e efeitos da dublagem com o áudio do filme":
        "Compares the dub's music and sound effects with the movie's audio",
    "Detectar usando outra faixa do arquivo...": "Detect using another track of the file...",
    "Ex.: usar a faixa em inglês da mesma fonte e aplicar a todas as dublagens dela":
        "E.g. use the English track of the same source and apply the result to all of its dubs",
    "Detectar pelo vídeo (lento)...": "Detect by video (slow)...",
    "Compara os cortes de cena dos vídeos": "Compares the scene cuts of both videos",
    "Detectar lendo os arquivos inteiros (lento)...": "Detect by reading the whole files (slow)...",
    "Para quando a análise rápida não acha a dublagem": "For when the quick analysis can't find the dub",
    "Zerar atraso e velocidade": "Reset delay and speed",
    "Gerar teste (5 min)": "Make test (5 min)",
    "Gera só os 5 primeiros minutos para conferir a sincronia": "Makes only the first 5 minutes, to check the sync",
    "Gerar arquivo final": "Make final file",
    "Gera o MKV completo (sem recodificar)": "Makes the complete MKV (no re-encoding)",
    "Cancelar tarefa": "Cancel task",
    "Verificar integridade (hash)...": "Verify integrity (hash)...",
    "Confere se vídeo, áudios e legendas originais continuam idênticos":
        "Checks that the original video, audio and subtitle tracks are still identical",
    "Limpar cache de áudio": "Clear audio cache",
    "Abrir projeto...": "Open project...",
    "Salvar projeto...": "Save project...",
    "Sair": "Exit",
    "Localizar FFmpeg...": "Locate FFmpeg...",
    "Localizar mkvmerge...": "Locate mkvmerge...",
    "Sobre o EternalDub / créditos": "About EternalDub / credits",
    "Página do projeto (GitHub)": "Project page (GitHub)",
    "Relatar um problema...": "Report a problem...",
    "Ver o início na onda": "Go to the start of the waveform",
    "Carregar as ondas (filme e dublagens)": "Load the waveforms (movie and dubs)",
    "Lê o áudio completo em segundo plano só para desenhar a onda":
        "Reads the full audio in the background, only to draw the waveform",
    "Parar a leitura das ondas": "Stop loading the waveforms",

    # ---- janela principal
    "Nome": "Name",
    "Origem": "Source",
    "Atraso (ms)": "Delay (ms)",
    "Padrão": "Default",
    "Status": "Status",
    "Idioma": "Language",
    "Atraso": "Delay",
    "Velocidade": "Speed",
    "Manter": "Keep",
    "Tipo": "Type",
    "Codec": "Codec",
    "Título": "Title",
    "Registro": "Log",
    "Dublagem selecionada": "Selected dub",
    "Código de 3 letras: por, eng, spa...": "3-letter code: por, eng, spa...",
    "Faixa padrão (toca sozinha)": "Default track (plays automatically)",
    "Nenhum filme aberto. Arraste o .mkv para a janela.": "No movie open. Drag the .mkv into the window.",
    "Marque as faixas do FILME que vão para o arquivo final (as dublagens da lista entram todas).":
        "Check the MOVIE tracks that go into the final file (all dubs in the list are included).",
    "Marque as faixas do FILME que vão para o arquivo final. Vão: %d vídeo, %d áudio, %d legenda(s) do filme + "
    "as %d dublagem(ns) da lista.":
        "Check the MOVIE tracks that go into the final file. Included: %d video, %d audio, %d subtitle track(s) "
        "from the movie + the %d dub(s) in the list.",
    "Faixa de referência (áudio ORIGINAL do filme, usada para comparar):":
        "Reference track (the movie's ORIGINAL audio, used for comparison):",
    "Roda do mouse = zoom  |  arraste a faixa LARANJA (embaixo) = muda o atraso  |  arraste a faixa verde = move "
    "a visão  |  Home = voltar ao início":
        "Mouse wheel = zoom  |  drag the ORANGE track (bottom) = change the delay  |  drag the green track = "
        "move the view  |  Home = back to the start",
    "Onda: pausada enquanto a tarefa roda (continua depois)": "Waveform: paused while the task runs (resumes later)",
    "Onda (%s): %d%%%s": "Waveform (%s): %d%%%s",

    # ---- dialogos e mensagens
    "Quais faixas deste arquivo são dublagens?": "Which tracks of this file are dubs?",
    "Marque as faixas de áudio que você quer adicionar:": "Check the audio tracks you want to add:",
    "EternalDub pronto. Arraste o filme para a janela (ou use Arquivo > Abrir filme).":
        "EternalDub ready. Drag the movie into the window (or use File > Open movie).",
    "ATENÇÃO: FFmpeg não encontrado. Instale o FFmpeg ou use Opções > Localizar FFmpeg.":
        "WARNING: FFmpeg not found. Install FFmpeg or use Options > Locate FFmpeg.",
    "Montagem: %s | %s": "Muxing: %s | %s",
    "mkvmerge não encontrado: a montagem usa o FFmpeg. Instalar o MKVToolNix (só o programa; a janela dele não "
    "precisa ser usada) deixa o EternalDub usar o mkvmerge, que é o recomendado.":
        "mkvmerge not found: muxing will use FFmpeg. Installing MKVToolNix (just the program; you don't need to use "
        "its window) lets EternalDub use mkvmerge, which is recommended.",
    "Abrir filme": "Open movie",
    "Vídeos (*.mkv *.mp4 *.m2ts *.ts *.avi *.mov);;Todos os arquivos (*)":
        "Videos (*.mkv *.mp4 *.m2ts *.ts *.avi *.mov);;All files (*)",
    "Adicionar dublagem(ns)": "Add dub(s)",
    "Áudio/vídeo (*.mkv *.mka *.mp4 *.m4a *.mp3 *.ac3 *.eac3 *.dts *.flac *.wav *.aac *.ogg *.m2ts);;"
    "Todos os arquivos (*)":
        "Audio/video (*.mkv *.mka *.mp4 *.m4a *.mp3 *.ac3 *.eac3 *.dts *.flac *.wav *.aac *.ogg *.m2ts);;"
        "All files (*)",
    "Programas (*.exe);;Todos os arquivos (*)": "Programs (*.exe);;All files (*)",
    "Não consegui abrir o filme": "Could not open the movie",
    "Esse arquivo não tem nenhuma faixa de áudio.": "This file has no audio track.",
    "Filme aberto: %s (%d faixas de áudio). A onda carrega em segundo plano; você já pode adicionar dublagens "
    "e detectar o atraso.":
        "Movie opened: %s (%d audio tracks). The waveform loads in the background; you can already add dubs "
        "and detect the delay.",
    "Abra primeiro o filme de alta qualidade.": "First open the high-quality movie.",
    "Não consegui abrir a dublagem": "Could not open the dub",
    "Sem faixa de áudio em:\n%s": "No audio track in:\n%s",
    "%d dublagem(ns) adicionada(s).": "%d dub(s) added.",
    "corrigida (atempo=%.6f; só esta dublagem será convertida para FLAC)":
        "corrected (atempo=%.6f; only this dub will be converted to FLAC)",
    "Não consegui ler a onda de %s: %s": "Could not read the waveform of %s: %s",
    "Cancelado.": "Cancelled.",
    "Cancelando...": "Cancelling...",
    "Leitura das ondas interrompida (Sincronização > Carregar as ondas para continuar).":
        "Waveform loading stopped (Sync > Load the waveforms to continue).",
    "Falhou: %s": "Failed: %s",
    "Erro ao concluir: %s": "Error while finishing: %s",

    # ---- deteccao
    "Detectando o atraso (análise rápida: lê só trechos do filme)":
        "Detecting the delay (quick analysis: reads only parts of the movie)",
    "Não consegui abrir o arquivo": "Could not open the file",
    "Faixa usada na medição": "Track used for the measurement",
    "Medir o atraso usando qual faixa deste arquivo?\n(o resultado vale para TODAS as dublagens que vieram "
    "deste arquivo)":
        "Measure the delay using which track of this file?\n(the result applies to ALL dubs that came from "
        "this file)",
    "Detectando o atraso (faixa %d do arquivo)": "Detecting the delay (track %d of the file)",
    "A análise completa lê o filme INTEIRO (%.0f GB) e a dublagem inteira.\nNum HD isso leva vários minutos "
    "(a onda do filme aproveita a mesma leitura). Continuar?":
        "The full analysis reads the ENTIRE movie (%.0f GB) and the entire dub.\nOn a hard drive this takes "
        "several minutes (the movie's waveform reuses the same read). Continue?",
    "Detectando o atraso (análise completa)": "Detecting the delay (full analysis)",
    "Comparar os cortes de cena dos vídeos pode levar MUITO tempo com um UHD 4K (de vários minutos a mais de "
    "uma hora).\n\nA dublagem precisa estar num arquivo com vídeo.  Continuar?":
        "Comparing the scene cuts of the videos can take a VERY long time with a 4K UHD (from several minutes to "
        "over an hour).\n\nThe dub must be in a file that has video.  Continue?",
    "Detectando o atraso pelo vídeo": "Detecting the delay by video",
    "Resultado (%s): %s, confiança %s, atraso %+d ms, velocidade x%.5f":
        "Result (%s): %s, confidence %s, delay %+d ms, speed x%.5f",
    "Análise rápida: leu só %s do filme e %s da dublagem (trechos espalhados).":
        "Quick analysis: read only %s of the movie and %s of the dub (spread-out excerpts).",
    "Obs.: não achei a dublagem perto de %s do filme (cena sem música/efeitos, ou diferente?).":
        "Note: could not find the dub near %s of the movie (scene without music/effects, or different?).",
    "sem correspondência confiável": "no reliable match",
    "Análise rápida: %s": "Quick analysis: %s",
    "Não encontrei uma correspondência confiável entre a dublagem e o filme.\n\nOpções (menu Sincronização):\n"
    " - 'Detectar usando outra faixa do arquivo' (ex.: a faixa em inglês da mesma fonte);\n"
    " - 'Detectar lendo os arquivos inteiros (lento)';\n - 'Detectar pelo vídeo';\n"
    " - ou arraste a faixa laranja na onda para alinhar na mão.":
        "Could not find a reliable match between the dub and the movie.\n\nOptions (Sync menu):\n"
        " - 'Detect using another track of the file' (e.g. the English track of the same source);\n"
        " - 'Detect by reading the whole files (slow)';\n - 'Detect by video';\n"
        " - or drag the orange track in the waveform to align it by hand.",
    "detectado: %s, confiança %s": "detected: %s, confidence %s",
    "o atraso muda %.2f s por hora (velocidades um pouco diferentes)":
        "the delay changes %.2f s per hour (slightly different speeds)",
    "A dublagem e o filme têm VELOCIDADES diferentes:\n%s.\n\nCorrigir a velocidade? Ao gerar o arquivo, SOMENTE "
    "a dublagem será convertida para FLAC (o vídeo não é tocado).\n\nAtraso depois da correção: %+d ms":
        "The dub and the movie have different SPEEDS:\n%s.\n\nCorrect the speed? When the file is made, ONLY the "
        "dub will be converted to FLAC (the video is not touched).\n\nDelay after the correction: %+d ms",
    "velocidade corrigida (x%.4f), confiança %s": "speed corrected (x%.4f), confidence %s",
    "velocidade DIFERENTE, confiança %s": "DIFFERENT speed, confidence %s",
    "de %s a %s: %+d ms": "from %s to %s: %+d ms",
    "As versões têm CORTES diferentes: o atraso muda ao longo do filme (tempos do filme).":
        "The versions have different CUTS: the delay changes along the movie (movie times).",
    "As versões têm CORTES diferentes: o atraso muda ao longo do filme.":
        "The versions have different CUTS: the delay changes along the movie.",
    "Um único atraso não serve para o filme inteiro (juntar trechos ainda não existe nesta versão).\n"
    "Usar o atraso do primeiro trecho (%+d ms)?":
        "A single delay won't work for the whole movie (joining sections is not available in this version yet).\n"
        "Use the delay of the first section (%+d ms)?",
    "CORTES diferentes - ver registro": "different CUTS - see the log",
    "Trechos com atrasos diferentes: %s": "Sections with different delays: %s",

    # ---- montagem e conferencia
    "Salvar como": "Save as",
    "O arquivo de saída não pode ser o próprio filme.": "The output file can't be the movie itself.",
    "Espaço livre no destino: %.1f GB. O filme tem %.1f GB.\nContinuar mesmo assim?":
        "Free space at the destination: %.1f GB. The movie is %.1f GB.\nContinue anyway?",
    "ARQUIVO PRONTO: %s": "FILE READY: %s",
    "Conferindo se cada dublagem tem som e está sincronizada (lê só 3 trechos curtos; o arquivo já está pronto, "
    "mesmo que você cancele esta conferência)...":
        "Checking that each dub has sound and is in sync (reads only 3 short excerpts; the file is already "
        "done, even if you cancel this check)...",
    "Pronto (%s): %s": "Done (%s): %s",
    "não deu para conferir (os trechos não puderam ser lidos a tempo)":
        "could not be checked (the excerpts could not be read in time)",
    "MUDA (sem som)": "SILENT (no sound)",
    "com som (sincronia não conferida: sem trecho parecido com a faixa de referência)":
        "has sound (sync not checked: no excerpt similar to the reference track)",
    "com som, mas FORA de sincronia em %+d ms": "has sound, but OUT of sync by %+d ms",
    "com som e sincronizada (diferença %+d ms)": "has sound and is in sync (difference %+d ms)",
    "SEM ÁUDIO por volta de %s (a dublagem acaba antes ou tem um buraco ali?)":
        "NO AUDIO around %s (does the dub end early or have a gap there?)",
    "Conferência - %s": "Check - %s",
    "Dublagem muda no arquivo gerado": "Silent dub in the generated file",
    "Estas dublagens saíram SEM SOM no arquivo gerado:\n%s\n\nTente gerar de novo com o outro motor (Opções > "
    "Motor de montagem > %s). Se continuar, relate o problema (Ajuda > Relatar um problema) com o conteúdo do "
    "Registro.\n\n%s":
        "These dubs came out WITHOUT SOUND in the generated file:\n%s\n\nTry making it again with the other engine "
        "(Options > Muxing engine > %s). If it persists, report the problem (Help > Report a problem) with the "
        "contents of the Log.\n\n%s",
    "Teste gerado:\n%s\n\nConferência automática:\n%s\n\nAbrir no player padrão para ouvir?":
        "Test made:\n%s\n\nAutomatic check:\n%s\n\nOpen it in the default player to listen?",
    "Arquivo final gerado (sem recodificar):\n%s\n\nConferência automática:\n%s\n\nPara conferir que vídeo, "
    "áudios e legendas originais continuam IDÊNTICOS, use Ferramentas > Verificar integridade.\n\nDica: para "
    "assistir, espere a leitura das ondas terminar (canto inferior direito) ou use Sincronização > Parar a "
    "leitura das ondas. Num HD lento, duas leituras ao mesmo tempo fazem o vídeo travar.":
        "Final file made (no re-encoding):\n%s\n\nAutomatic check:\n%s\n\nTo confirm that the original video, "
        "audio and subtitle tracks are still IDENTICAL, use Tools > Verify integrity.\n\nTip: before watching, "
        "wait for the waveform loading to finish (bottom right corner) or use Sync > Stop loading the "
        "waveforms. On a slow hard drive, two reads at the same time make the video stutter.",
    "Gerando o teste de 5 minutos": "Making the 5-minute test",
    "Gerando o arquivo final": "Making the final file",
    "Arquivo final a verificar": "Final file to verify",
    "ATENÇÃO: estes fluxos do filme original estão DIFERENTES no arquivo final:\n\n%s\n\nTente o outro motor de "
    "montagem (Opções) e confira de novo.":
        "WARNING: these streams of the original movie are DIFFERENT in the final file:\n\n%s\n\nTry the other "
        "muxing engine (Options) and check again.",
    "Todos os %d fluxos originais (vídeo, áudio, legendas) estão IDÊNTICOS no arquivo final.":
        "All %d original streams (video, audio, subtitles) are IDENTICAL in the final file.",
    "Verificando a integridade (lê os dois arquivos inteiros)": "Verifying integrity (reads both files entirely)",

    # ---- projeto, opcoes, ajuda
    "Abra um filme primeiro.": "Open a movie first.",
    "Salvar projeto": "Save project",
    "Projeto EternalDub (*.eternaldub)": "EternalDub project (*.eternaldub)",
    "Projeto salvo: %s": "Project saved: %s",
    "Abrir projeto": "Open project",
    "Projeto EternalDub (*.eternaldub *.dubsync)": "EternalDub project (*.eternaldub *.dubsync)",
    "Não consegui abrir o projeto": "Could not open the project",
    "Alguns arquivos de dublagem do projeto não foram encontrados e foram ignorados.":
        "Some dub files of the project were not found and were skipped.",
    "Motor de montagem: %s": "Muxing engine: %s",
    "Localizar %s": "Locate %s",
    "%d arquivo(s) de cache removido(s).": "%d cache file(s) removed.",
    "Para relatar um problema, abra um \"Issue\" na página do projeto e cole o conteúdo da aba Registro (e, se "
    "houver, o arquivo %s).\n\nAbrir a página agora?":
        "To report a problem, open an \"Issue\" on the project page and paste the contents of the Log tab (and, "
        "if it exists, the file %s).\n\nOpen the page now?",
    "Sobre o EternalDub": "About EternalDub",
    "Adiciona dublagens a releases de alta qualidade (BDRemux, WEB-DL...) <b>sem recodificar</b> o vídeo.":
        "Adds dubs to high-quality releases (BDRemux, WEB-DL...) <b>without re-encoding</b> the video.",
    "1) Abra o filme  2) adicione as dublagens  3) <i>Detectar atraso</i> (ou arraste a faixa laranja na onda)  "
    "4) <i>Gerar teste</i> e confira  5) <i>Gerar arquivo final</i>.":
        "1) Open the movie  2) add the dubs  3) <i>Detect delay</i> (or drag the orange track in the waveform)  "
        "4) <i>Make test</i> and check it  5) <i>Make final file</i>.",
    "Se a dublagem tiver velocidade diferente (ex.: PAL), o programa avisa e corrige só a dublagem. Se as versões "
    "tiverem cortes diferentes, ele mostra os trechos.":
        "If the dub has a different speed (e.g. PAL), the program warns you and corrects only the dub. If the "
        "versions have different cuts, it shows the sections.",
    "Créditos": "Credits",
    "Criação, testes e direção do projeto: %s": "Creation, testing and project direction: %s",
    "Código escrito com auxílio de IA (Claude, da Anthropic).": "Code written with AI assistance (Claude, by Anthropic).",
    "Usa: FFmpeg, MKVToolNix (mkvmerge), Qt for Python (PySide6) e NumPy.":
        "Uses: FFmpeg, MKVToolNix (mkvmerge), Qt for Python (PySide6) and NumPy.",
    "Colaboradores: veja CREDITS.md e a página do projeto.": "Contributors: see CREDITS.md and the project page.",
    "Software livre e de código aberto (licença %s).": "Free and open-source software (%s license).",
    "Há uma tarefa em andamento. Cancelar e sair?": "A task is running. Cancel it and exit?",
    "arquivos de versões diferentes": "files from different versions",
    "Os arquivos do EternalDub nesta pasta não combinam:\n%s\n\nPasta: %s\n\nComo resolver: extraia o EternalDub "
    "numa pasta NOVA e vazia, ou apague os arquivos antigos desta pasta (inclusive cópias com (1), (2) no nome, e "
    "os antigos dubsync_*.py).\nTodos estes precisam ser da versão %s: %s.":
        "The EternalDub files in this folder don't match:\n%s\n\nFolder: %s\n\nHow to fix it: extract EternalDub "
        "into a NEW, empty folder, or delete the old files from this folder (including copies with (1), (2) in the "
        "name, and the old dubsync_*.py).\nAll of these must be version %s: %s.",
    "Ocorreu um erro inesperado.": "An unexpected error occurred.",
    "Copie o texto dos detalhes e relate o problema na página do projeto:\n%s":
        "Copy the details text and report the problem on the project page:\n%s",

    # ---- nucleo (EternalDub_core.py)
    "detectar_atraso.py (versão %s) e EternalDub_core.py (versão %s) não combinam.\nArquivo encontrado: %s":
        "detectar_atraso.py (version %s) and EternalDub_core.py (version %s) don't match.\nFile found: %s",
    "ffprobe não encontrado. Instale o FFmpeg (ou indique o caminho em Opções).":
        "ffprobe not found. Install FFmpeg (or set its path in Options).",
    "Não consegui abrir o arquivo:\n%s\n%s": "Could not open the file:\n%s\n%s",
    "Faixa de áudio inexistente.": "Audio track does not exist.",
    "Aviso: a faixa da dublagem termina em %s, mas o filme vai até %s (dublagem incompleta ou de versão cortada?).":
        "Warning: the dub track ends at %s, but the movie runs until %s (incomplete dub, or from a cut version?).",
    "A análise rápida não foi suficiente (%s). Lendo os arquivos inteiros (em UHD pode levar vários minutos; o "
    "resultado fica guardado)...":
        "The quick analysis was not enough (%s). Reading the whole files (with UHD this can take several minutes; "
        "the result is cached)...",
    "Comparando as duas faixas inteiras...": "Comparing both full tracks...",
    "Lendo o vídeo do filme (UHD pode levar muito tempo)...": "Reading the movie's video (UHD can take a long time)...",
    "Lendo o vídeo da dublagem...": "Reading the dub's video...",
    "O programa terminou com erro (código %s):\n%s\n\n%s": "The program ended with an error (code %s):\n%s\n\n%s",
    "Adicione pelo menos uma dublagem.": "Add at least one dub.",
    "Arquivo da dublagem não encontrado:\n%s": "Dub file not found:\n%s",
    "A mesma faixa foi adicionada duas vezes: %s (faixa %d)": "The same track was added twice: %s (track %d)",
    "Só uma dublagem pode ser a faixa padrão.": "Only one dub can be the default track.",
    "Dublagem %d: corrigindo a velocidade (só esta dublagem vira FLAC)...":
        "Dub %d: correcting the speed (only this dub becomes FLAC)...",
    "Mantenha pelo menos uma faixa de vídeo do filme.": "Keep at least one video track from the movie.",
    "Dublagem %d: cortando o começo da dublagem (cópia exata, sem recodificar)...":
        "Dub %d: trimming the start of the dub (exact copy, no re-encoding)...",
    "O mkvmerge não conseguiu ler:\n%s\n%s": "mkvmerge could not read:\n%s\n%s",
    "O mkvmerge não achou a faixa de áudio %d em %s": "mkvmerge could not find audio track %d in %s",
    "mkvmerge não encontrado. Escolha o FFmpeg ou indique o caminho em Opções.":
        "mkvmerge not found. Choose FFmpeg or set its path in Options.",
    "Montando o arquivo (só copia os fluxos, sem recodificar)...": "Muxing the file (just copies the streams, no re-encoding)...",
    "O arquivo final não foi criado.": "The final file was not created.",
    "Calculando o hash do filme original (lê o arquivo inteiro)...":
        "Computing the hash of the original movie (reads the whole file)...",
    "Calculando o hash do arquivo final...": "Computing the hash of the final file...",
    "Conferindo as dublagens no arquivo gerado (%d de %d, em %s)...":
        "Checking the dubs in the generated file (%d of %d, at %s)...",
    "   não consegui ler este trecho (%s); pulando": "   could not read this excerpt (%s); skipping",
    "   (este trecho demorou %.0f s para ler: disco lento)": "   (this excerpt took %.0f s to read: slow disk)",

    # ---- detector (detectar_atraso.py)
    "mesma velocidade": "same speed",
    "dublagem 4,27% mais rápida que o filme (fonte PAL 25 fps vs 23,976 fps)":
        "dub 4.27% faster than the movie (PAL source, 25 fps vs 23.976 fps)",
    "dublagem 4,10% mais lenta que o filme (fonte 23,976 fps vs 25 fps)":
        "dub 4.10% slower than the movie (23.976 fps source vs 25 fps)",
    "dublagem 4,17% mais rápida que o filme (25 fps vs 24 fps)": "dub 4.17% faster than the movie (25 fps vs 24 fps)",
    "dublagem 4,00% mais lenta que o filme (24 fps vs 25 fps)": "dub 4.00% slower than the movie (24 fps vs 25 fps)",
    "dublagem 0,10% mais rápida que o filme (24 fps vs 23,976 fps)":
        "dub 0.10% faster than the movie (24 fps vs 23.976 fps)",
    "dublagem 0,10% mais lenta que o filme (23,976 fps vs 24 fps)":
        "dub 0.10% slower than the movie (23.976 fps vs 24 fps)",
    "FFmpeg não encontrado. Instale o FFmpeg e tente de novo.": "FFmpeg not found. Install FFmpeg and try again.",
    "passou de %d s": "took longer than %d s",
    "o FFmpeg falhou (código %s)": "FFmpeg failed (code %s)",
    "ERRO: ffprobe não encontrado. Instale o FFmpeg e tente de novo.":
        "ERROR: ffprobe not found. Install FFmpeg and try again.",
    "ERRO: não consegui abrir: %s": "ERROR: could not open: %s",
    "áudio curto demais para analisar": "audio too short to analyze",
    "arquivo curto demais para a análise rápida": "file too short for the quick analysis",
    "   (o trecho do filme em %s veio com só %.0f s de áudio; pulando)":
        "   (the movie excerpt at %s had only %.0f s of audio; skipping)",
    "   (a dublagem em %s veio com só %.0f s de áudio; pulando)":
        "   (the dub at %s had only %.0f s of audio; skipping)",
    "Análise rápida: procurando 1 minuto do filme (em %s) na dublagem...":
        "Quick analysis: looking for 1 minute of the movie (at %s) in the dub...",
    "   achou: atraso %s, velocidade x%.4f (pontuação %.0f)": "   found: delay %s, speed x%.4f (score %.0f)",
    "   não bateu ali (melhor pontuação %.0f)": "   no match there (best score %.0f)",
    "não encontrei o trecho do filme na dublagem (tentei em %s)":
        "could not find the movie excerpt in the dub (tried at %s)",
    "   (a faixa da dublagem só cobre o filme até %s; os pontos de verificação ficam até ali)":
        "   (the dub track only covers the movie up to %s; the checkpoints stay within that range)",
    "Ponto de verificação %d de %d (%s do filme)...": "Checkpoint %d of %d (%s into the movie)...",
    "   ponto %d: atraso %s (pontuação %.0f)": "   checkpoint %d: delay %s (score %.0f)",
    "   ponto %d: não achei a dublagem perto de onde deveria estar":
        "   checkpoint %d: could not find the dub near where it should be",
    "poucos trechos bateram (%d de %d)": "too few excerpts matched (%d of %d)",
    "=== RESULTADO (método: %s, análise %s) ===": "=== RESULT (method: %s, %s analysis) ===",
    "Leu só %s do filme e %s da dublagem (trechos espalhados).":
        "Read only %s of the movie and %s of the dub (spread-out excerpts).",
    "Trechos confiáveis: %d de %d  (pontuação mediana: %.1f)": "Reliable excerpts: %d of %d  (median score: %.1f)",
    "Velocidade: igual à do filme. Não precisa corrigir.": "Speed: same as the movie. No correction needed.",
    "ATRASO SUGERIDO: %s   (confiança %s)": "SUGGESTED DELAY: %s   (confidence %s)",
    "ATENÇÃO: %s.": "WARNING: %s.",
    "ATENÇÃO: o atraso vai mudando ao longo do filme (%.2f s por hora): as duas versões têm velocidades um pouco "
    "diferentes.":
        "WARNING: the delay keeps changing along the movie (%.2f s per hour): the two versions have slightly "
        "different speeds.",
    "Só o atraso NÃO resolve. Antes, corrija a velocidade da dublagem (sem perder qualidade, em FLAC):":
        "A delay alone will NOT fix it. First correct the dub's speed (losslessly, to FLAC):",
    "Depois use o arquivo corrigido com o atraso: %s   (confiança %s)":
        "Then use the corrected file with the delay: %s   (confidence %s)",
    "ATENÇÃO: o atraso muda de repente: as versões têm CORTES diferentes.":
        "WARNING: the delay changes suddenly: the versions have different CUTS.",
    "tempo do filme": "movie time",
    "tempo da dublagem": "dub time",
    "   por volta de %s até %s (%s): atraso %s": "   around %s to %s (%s): delay %s",
    "Um único atraso não serve para o filme inteiro. A ferramenta ainda não junta os pedaços sozinha; por "
    "enquanto, o atraso do primeiro trecho é: %s":
        "A single delay won't work for the whole movie. The tool doesn't join the sections by itself yet; for "
        "now, the delay of the first section is: %s",
    "Não encontrei uma correspondência confiável entre os dois arquivos.":
        "Could not find a reliable match between the two files.",
    "Melhor palpite (NÃO confie): %s": "Best guess (do NOT trust it): %s",
    "Descobre o atraso de uma dublagem em relação ao filme.": "Finds the delay of a dub relative to the movie.",
    "faixa de áudio do filme usada como referência (número, ou 'auto' = a em inglês)":
        "movie audio track used as the reference (number, or 'auto' = the English one)",
    "faixa de áudio da dublagem (padrão 0)": "dub audio track (default 0)",
    "maior atraso procurado, em segundos": "largest delay searched, in seconds",
    "tamanho dos trechos de verificação (s)": "size of the checking excerpts (s)",
    "diferença aceita entre trechos (ms)": "accepted difference between excerpts (ms)",
    "lê os arquivos inteiros (lento em UHD); o padrão é a análise rápida por trechos":
        "reads the whole files (slow with UHD); the default is the quick analysis by excerpts",
    "relatório vai para a tela de erro; só linhas CHAVE=valor no resultado":
        "report goes to stderr; only KEY=value lines in the output",
    "idioma das mensagens (padrão: o do sistema)": "message language (default: the system's)",
    "Aviso: falta faixa de áudio em um dos arquivos; pulando o método de áudio.":
        "Warning: one of the files has no audio track; skipping the audio method.",
    "A análise rápida não foi suficiente (%s).": "The quick analysis was not enough (%s).",
    "Lendo o áudio INTEIRO do filme (faixa %d) e da dublagem (faixa %d); em UHD isso pode levar vários minutos...":
        "Reading the ENTIRE audio of the movie (track %d) and of the dub (track %d); with UHD this can take "
        "several minutes...",
    "Comparando...": "Comparing...",
    "O áudio não foi conclusivo; tentando pelos CORTES DE CENA do vídeo (pode levar vários minutos)...":
        "The audio was inconclusive; trying the video's SCENE CUTS (can take several minutes)...",
    "Lendo o vídeo dos dois arquivos (pode levar vários minutos)...":
        "Reading the video of both files (can take several minutes)...",
    "ERRO: os dois arquivos precisam ter vídeo para usar --metodo video.":
        "ERROR: both files must have video to use --metodo video.",
    "A dublagem não tem vídeo para comparar os cortes de cena.": "The dub has no video to compare scene cuts.",
    "ERRO: não foi possível analisar com os arquivos fornecidos.": "ERROR: could not analyze the given files.",
    "ERRO: %s": "ERROR: %s",
    "DUBLAGEM": "DUB",
    "DUBLAGEM_corrigida.flac": "DUB_corrected.flac",
}

TRADUCOES = {"en": EN}
