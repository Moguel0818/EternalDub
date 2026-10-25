# Novidades / Changelog

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
- A interface não recomenda mais instalar o MKVToolNix.

**English**

- **Fixed: silent stretches in the final file** (e.g. 3:36–3:43 in Mad Monster Party, in VLC, MPC and Jellyfin). When the movie's subtitle track goes a while without a line, FFmpeg (from 4.4 to 9) stopped reading the dub until the next subtitle, so the audio of that gap ended up written much further ahead in the file (up to minutes). The sound was there, but players reached the video before reading the audio and played silence. Subtitles now come in through a separate read and the audio stays next to its video. **Files already made need to be made again.**
- The automatic check also measures interleaving: it warns if a dub's audio was written far away from the video inside the file.
- **Section-by-section sync.** When the versions have different cuts (or the dub was re-edited by whoever uploaded it), the delay changes along the movie, and a single delay left part of the lines out of place. EternalDub now measures the delay at every second, finds each change and assembles the dub piece by piece: silence where the dub is missing a piece, and removal (preferably in a pause) of what doesn't exist in the movie. It is offered automatically when detection reports different cuts, and is also in **Sync ▸ Sync section by section** (Ctrl+M).
- The waveform shows the dub already in place, with the splices in red. The Log lists every splice.
- When you decline section sync, the single delay used is the one from the longest section, no longer the first one.
- Speed correction: the dub is now decoded on the same timeline as the analysis. Sources with a built-in delay (audio starting after the video in the file) no longer lose it.
- Processed dub FLAC is 24-bit for lossy sources (it was 16-bit).
- Command line: `detectar_atraso.py ... --mapa` prints the section map.
- The interface no longer recommends installing MKVToolNix.

## 1.0

Primeira versão pública. / First public release.
