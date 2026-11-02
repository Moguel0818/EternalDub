# Novidades / Changelog

## 1.3

**Português**

- **Organização do arquivo final.** A aba **Filme** virou **Arquivo final**: mostra todas as faixas que podem ir para o MKV (as do filme, as dublagens e as legendas adicionadas), já na ordem em que vão ficar. Marque o que entra, mude a ordem com **Subir/Descer** (vídeos, áudios e legendas ficam cada um no seu grupo) e escolha o áudio e a legenda **padrão** (a que toca ou aparece sozinha).
- **Marcar tudo / Desmarcar tudo** para as faixas do filme (o vídeo nunca sai).
- **Padrão BDRemux PT-BR**, aplicado sozinho ao abrir o filme e ao adicionar dublagens ou legendas: 1) áudio PT-BR (as dublagens adicionadas e as faixas PT-BR do filme), 2) a faixa principal do idioma original (sem comentários nem audiodescrição), 3) legendas PT-BR: a completa e depois a forçada. Uma legenda externa PT-BR substitui a do filme do mesmo tipo (uma completa externa tira a completa do filme, mas a forçada do filme continua, porque traduz placas e falas em outro idioma enquanto se ouve a dublagem). O primeiro áudio é o padrão e nenhuma legenda aparece sozinha (as forçadas continuam forçadas). O resto do filme fica desmarcado, no fim da lista. Se você mudar algo à mão, o padrão não é reaplicado; o botão **Aplicar o padrão BDRemux PT-BR** volta a ele. Dá para escolher o **idioma original** quando a detecção errar, e desligar a organização automática. Na interface em outros idiomas ela começa desligada.
- **Legendas externas**, adicionadas como as dublagens (botão, Ctrl+L ou arrastando para a janela): `.srt`, `.ass`, `.ssa`, `.vtt`, `.sup`, `.idx/.sub`, `.mks` ou faixas de legenda de outro MKV/MP4. Cada uma tem nome, idioma, atraso (positivo ou negativo) e marca de forçada. O idioma é tirado do nome do arquivo (`Filme.pt-BR.srt`). Legenda tirada do mesmo arquivo de uma dublagem já vem com o atraso dela. Textos em Windows-1252 (ANSI) ou UTF-16 são convertidos para UTF-8 (os acentos ficam certos); legendas de MP4 (`mov_text`) viram SRT. O arquivo original da legenda nunca é alterado.
- **Gerar sem dublagem:** dá para usar o EternalDub só para reorganizar um filme (por exemplo, deixar só o áudio PT-BR que ele já tem, o original e as legendas PT-BR). O arquivo sugerido termina em `_remux`.
- Antes de gerar, a aba Registro lista as faixas do arquivo final na ordem, com as marcas de cada uma.
- **Verificar integridade** acha cada faixa original pelo hash em qualquer posição (a ordem pode ter mudado).
- Projetos guardam a organização e as legendas (versão 5 do projeto). Projetos antigos continuam abrindo.
- Corrigido: a prévia podia mandar meio quadro de áudio para a placa de som.

**English**

- **Final file layout.** The **Movie** tab became **Final file**: it lists every track that can go into the MKV (the movie's own, the dubs and the added subtitles), already in the order they will have. Tick what goes in, change the order with **Up/Down** (videos, audios and subtitles each stay in their own group) and choose the **default** audio and subtitle (the one that plays or shows by itself).
- **Check all / Uncheck all** for the movie's tracks (the video never leaves).
- **PT-BR BDRemux layout**, applied automatically when you open the movie and when you add dubs or subtitles: 1) PT-BR audio (the added dubs and the movie's PT-BR tracks), 2) the main track in the original language (no commentary or audio description), 3) PT-BR subtitles: the full one, then the forced one. An external PT-BR subtitle replaces the movie's of the same kind (an external full subtitle takes out the movie's full one, but the movie's forced one stays, because it translates signs and lines in other languages while you listen to the dub). The first audio is the default and no subtitle turns on by itself (forced ones stay forced). The rest of the movie is unticked, at the end of the list. Once you change something by hand the layout is not applied again; the **Apply the PT-BR BDRemux layout** button brings it back. You can pick the **original language** when detection gets it wrong, and turn the automatic layout off. With the interface in other languages it starts off.
- **External subtitles**, added like dubs (button, Ctrl+L or drag and drop): `.srt`, `.ass`, `.ssa`, `.vtt`, `.sup`, `.idx/.sub`, `.mks` or subtitle tracks from another MKV/MP4. Each one has a name, language, delay (positive or negative) and forced flag. The language is taken from the file name (`Movie.pt-BR.srt`). A subtitle taken from the same file as a dub starts with that dub's delay. Windows-1252 (ANSI) or UTF-16 text is converted to UTF-8 (accents come out right); MP4 subtitles (`mov_text`) become SRT. The original subtitle file is never changed.
- **Make a file without a dub:** EternalDub can just reorganize a movie (for example, keep only its PT-BR audio, the original audio and the PT-BR subtitles). The suggested file name ends in `_remux`.
- Before muxing, the Log lists the tracks of the final file in order, with each one's flags.
- **Verify integrity** finds every original track by hash in any position (the order may have changed).
- Projects store the layout and the subtitles (project version 5). Old projects still open.
- Fixed: the preview could send half an audio frame to the sound card.

## 1.2

**Português**

- **Edição manual das emendas.** Na sincronia trecho por trecho, cada emenda é uma linha vermelha na onda: arraste-a, mova com as setas (10 ms; Shift 100 ms; Ctrl 1 ms), digite o tempo e a quantia exatos na nova aba **Emendas**, crie emendas (botão direito na onda) ou remova as falsas. Ctrl+arrastar desliza só um trecho; Ctrl+Shift+arrastar, este e os seguintes. Mover uma emenda nunca muda o alinhamento de nenhum trecho.
- **Som na emenda.** A aba Emendas diz se cada emenda cai numa *pausa*, em *som baixo* ou em *SOM ALTO* (fala ou música); o **ímã** encaixa a emenda numa pausa da dublagem ao arrastar, e **Achar pausa** (Ctrl+P) procura a melhor posição por perto. Assim nenhuma fala é cortada sem querer.
- **Desfazer / Refazer** (Ctrl+Z / Ctrl+Y) para o atraso, as emendas, os resultados da detecção e do mapa.
- **Ouvir dentro do programa.** F8 toca a dublagem já sincronizada (atraso, velocidade e emendas), o filme ou os dois misturados, a partir da linha azul (clique na régua). F9 toca 3 s antes e depois da emenda escolhida. A prévia usa o mesmo montador do arquivo final, então o que se ouve é o que vai para o arquivo. A leitura das ondas pausa enquanto você ouve.
- **Programa independente para Windows** (sem precisar de Python): `EternalDub.spec`, `Gerar_EXE.bat` e um fluxo do GitHub (Actions) que gera o `.exe` e o testa sozinho (`--autoteste`). O FFmpeg é procurado ao lado do `EternalDub.exe`, no PATH e nas pastas do winget.
- **Mais idiomas:** espanhol, francês, italiano e alemão, além de português e inglês. Os idiomas agora são arquivos `.json` em `idiomas/`: traduzir não exige programar, e o idioma novo aparece sozinho no menu. O idioma do sistema é escolhido automaticamente quando há tradução.
- **Testes automáticos** (`tests/`): editor de emendas (inclusive com milhares de edições aleatórias), prévia comparada com a saída real, traduções e janela principal.
- Removido o motor de montagem alternativo: a montagem é sempre feita pelo FFmpeg (cópia sem recodificar). Projetos antigos continuam abrindo.
- A montagem trecho por trecho foi reorganizada numa classe reutilizável (`MontadorPedacos`); o FLAC gerado é idêntico ao da 1.1 (conferido byte a byte).
- Todas as chamadas a programas externos agora têm entrada padrão fechada (necessário para o programa sem janela de console).

**English**

- **Manual splice editing.** In section-by-section sync, every splice is a red line on the waveform: drag it, nudge it with the arrow keys (10 ms; Shift 100 ms; Ctrl 1 ms), type its exact time and amount in the new **Splices** tab, add splices (right-click the waveform) or remove false ones. Ctrl+drag slides only one section; Ctrl+Shift+drag, that one and the following ones. Moving a splice never changes the alignment of any section.
- **Sound at the splice.** The Splices tab tells you whether each splice falls in a *pause*, in *low sound* or in *LOUD SOUND* (speech or music); the **magnet** snaps a splice into a pause of the dub while you drag, and **Find pause** (Ctrl+P) looks for the best nearby position. No line is cut by accident.
- **Undo / Redo** (Ctrl+Z / Ctrl+Y) for the delay, the splices and the results of detection and of the section map.
- **Listen inside the program.** F8 plays the dub already synced (delay, speed and splices), the movie, or both mixed, from the blue line (click the ruler). F9 plays 3 s before and after the selected splice. The preview uses the same assembler as the final file, so what you hear is what goes into the file. Waveform reading pauses while you listen.
- **Standalone Windows program** (no Python needed): `EternalDub.spec`, `Gerar_EXE.bat` and a GitHub (Actions) workflow that builds the `.exe` and tests it by itself (`--autoteste`). FFmpeg is looked up next to `EternalDub.exe`, in the PATH and in winget's folders.
- **More languages:** Spanish, French, Italian and German, besides Portuguese and English. Languages are now `.json` files in `idiomas/`: translating needs no programming, and a new language shows up in the menu by itself. The system language is picked automatically when a translation exists.
- **Automated tests** (`tests/`): the splice editor (including thousands of random edits), the preview compared with the real output, the translations and the main window.
- The alternative muxing engine was removed: muxing is always done by FFmpeg (copy without re-encoding). Old projects still open.
- Section-by-section assembly was moved into a reusable class (`MontadorPedacos`); the FLAC it produces is identical to 1.1's (checked byte by byte).
- Every call to an external program now has its standard input closed (needed by the program without a console window).

## 1.1

**Português**

- **Corrigido: trechos mudos no arquivo final** (ex.: 3:36–3:43 em Mad Monster Party, no VLC, no MPC e no Jellyfin). Quando a faixa de legenda do filme fica um tempo sem fala, o FFmpeg (do 4.4 ao 9) parava de ler a dublagem até a próxima legenda, e o áudio desse intervalo ia parar muito mais adiante dentro do arquivo (até minutos). O som estava lá, mas os players chegavam no vídeo antes de ler o áudio e tocavam silêncio. Agora as legendas entram por uma leitura separada e o áudio fica colado ao vídeo. **Arquivos já gerados precisam ser gerados de novo.**
- A conferência automática também mede o entrelaçamento: avisa se o áudio de alguma dublagem ficou gravado longe do vídeo dentro do arquivo.
- **Sincronia trecho por trecho.** Quando as versões têm cortes diferentes (ou a dublagem foi remontada por quem a publicou), o atraso muda ao longo do filme e um atraso único deixava parte das falas fora do lugar. Agora o EternalDub mede o atraso a cada segundo, acha cada mudança e monta a dublagem pedaço por pedaço: silêncio onde falta um pedaço na dublagem e remoção, de preferência numa pausa, do que não existe no filme. Aparece sozinho quando a detecção avisa de cortes diferentes, e também em **Sincronização ▸ Sincronizar trecho por trecho** (Ctrl+M).
- A onda mostra a dublagem já no lugar, com as emendas em vermelho. A aba Registro lista cada emenda.
- Ao recusar a sincronia por trechos, o atraso único usado é o do trecho mais longo, e não mais o do primeiro.
- Correção de velocidade: a dublagem agora é decodificada na mesma linha do tempo da análise. Fontes com atraso embutido (áudio começando depois do vídeo no arquivo) não perdem mais esse atraso.
- FLAC da dublagem processada em 24 bits para fontes com perdas (antes 16 bits).
- Linha de comando: `detectar_atraso.py ... --mapa` mostra o mapa por trechos.

**English**

- **Fixed: silent stretches in the final file** (e.g. 3:36–3:43 in Mad Monster Party, in VLC, MPC and Jellyfin). When the movie's subtitle track goes a while without a line, FFmpeg (from 4.4 to 9) stopped reading the dub until the next subtitle, so the audio of that gap ended up written much further ahead in the file (up to minutes). The sound was there, but players reached the video before reading the audio and played silence. Subtitles now come in through a separate read and the audio stays next to its video. **Files already made need to be made again.**
- The automatic check also measures interleaving: it warns if a dub's audio was written far away from the video inside the file.
- **Section-by-section sync.** When the versions have different cuts (or the dub was re-edited by whoever uploaded it), the delay changes along the movie, and a single delay left part of the lines out of place. EternalDub now measures the delay at every second, finds each change and assembles the dub piece by piece: silence where the dub is missing a piece, and removal (preferably in a pause) of what doesn't exist in the movie. It is offered automatically when detection reports different cuts, and is also in **Sync ▸ Sync section by section** (Ctrl+M).
- The waveform shows the dub already in place, with the splices in red. The Log lists every splice.
- When you decline section sync, the single delay used is the one from the longest section, no longer the first one.
- Speed correction: the dub is now decoded on the same timeline as the analysis. Sources with a built-in delay (audio starting after the video in the file) no longer lose it.
- Processed dub FLAC is 24-bit for lossy sources (it was 16-bit).
- Command line: `detectar_atraso.py ... --mapa` prints the section map.

## 1.0

Primeira versão pública. / First public release.
