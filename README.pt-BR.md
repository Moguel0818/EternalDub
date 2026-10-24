# EternalDub

> Ferramenta open-source para adicionar faixas de áudio dubladas a releases de vídeo de alta qualidade (**BDRemux, WEB-DL, BDRip**) **sem recodificar nada**. O vídeo fica idêntico bit a bit; a dublagem é sincronizada automaticamente.

🇺🇸 **[Read in English](README.md)**

---

## Por que este projeto existe?

Sou arquivista, e **preservação de mídias e integridade de arquivos são princípios que levo muito a sério.**

Com o tempo, percebi um problema recorrente: muitas dublagens clássicas só circulam junto de vídeos de baixa qualidade (rips ruins de DVD/BD, recodificações pesadas). Por isso, vários filmes parecem bem mais velhos do que são. Já existem releases com imagem muito melhor (BDRemux, scans de 35 mm), mas sem a dublagem.

Colocar uma dublagem numa release melhor costuma exigir vários programas: um para medir o atraso, outro para ajustar, outro para juntar os arquivos e um player para conferir o resultado. O EternalDub faz tudo isso numa única janela.

Criei o EternalDub também por um motivo pessoal: **meu irmão tem dislexia**, e ler legendas rápidas em filmes estrangeiros é exaustivo para ele. Uma boa imagem e a dublagem certa ajudam muita gente com dificuldade de leitura.

A dublagem brasileira (e a cultura de dublagem no mundo todo) é um verdadeiro tesouro que merece o melhor tratamento. Você não deveria precisar sacrificar a qualidade da imagem para assistir a um filme no seu idioma.

---

## Recursos

- **Sem perdas.** As faixas de vídeo, áudio e legenda do filme são copiadas, nunca recodificadas. Uma verificação por hash embutida prova que são idênticas no arquivo final.
- **Detecção automática de atraso.** O EternalDub compara a música e os efeitos sonoros da dublagem com o áudio original do filme (correlação cruzada), então funciona mesmo com vozes diferentes. Ele lê só trechos curtos do filme, o que o mantém rápido mesmo com remuxes UHD grandes.
- **Diferença de velocidade.** Detecta diferenças como PAL (25 fps) contra cinema (23,976 fps) e se oferece para corrigir. Só a dublagem é convertida (para FLAC, sem perdas); o vídeo nunca é tocado.
- **Cortes diferentes.** Quando as versões têm cortes diferentes, ele avisa e mostra onde o atraso muda.
- **Visualização das ondas sonoras** no estilo do Subtitle Edit. Arraste a dublagem para ajustar o atraso na mão, ou use os botões de ±10/100/1000 ms.
- **Várias dublagens de uma vez,** de um ou vários arquivos, cada uma com nome, idioma e marcação de padrão próprios.
- **Escolha de faixas.** Você decide quais faixas de áudio e legenda do próprio filme vão para o arquivo final.
- **Teste e conferência automática.** Gera primeiro um arquivo de teste de 5 minutos. Depois de juntar tudo, confere se cada dublagem tem som e está sincronizada dentro do arquivo final.
- **Tudo num lugar só.** Detecção, ajuste manual, junção e verificação acontecem numa única janela.
- **Idiomas da interface:** português (Brasil) e inglês.

---

## Requisitos

| O quê | Observações |
|---|---|
| **Windows 10/11** | Testado. Linux/macOS devem funcionar rodando `EternalDub_gui.py` diretamente, mas ainda não foi testado. |
| **Python 3.10+** | Em [python.org](https://www.python.org/downloads/). Marque **"Add python.exe to PATH"** durante a instalação. Recomendado 3.12 ou 3.13. |
| **FFmpeg** | `ffmpeg` e `ffprobe` no PATH. No Windows: `winget install Gyan.FFmpeg` |
| **numpy, PySide6** | Instalados automaticamente pelo `Iniciar_EternalDub.bat` na primeira execução (ou `pip install -r requirements.txt`). |

---

## Instalação

**Opção A: baixar (mais fácil)**
1. Clique em **Code ▸ Download ZIP** nesta página (ou baixe em **Releases**).
2. Extraia numa pasta nova.
3. Dê dois cliques em **`Iniciar_EternalDub.bat`**.

**Opção B: git**
```bash
git clone https://github.com/Moguel0818/EternalDub.git
cd EternalDub
pip install -r requirements.txt
python EternalDub_gui.py
```

A interface abre no idioma do seu sistema (português ou inglês). Dá para trocar em **Opções ▸ Idioma / Language**.

---

## Como usar

1. **Abrir filme.** Escolha a release de alta qualidade, ou arraste para a janela.
2. **Adicionar dublagem.** Escolha o(s) arquivo(s) com a dublagem: um MKV/MP4 com vídeo, ou só áudio (MP3, AC3, E-AC3, DTS, FLAC, WAV…). Se o arquivo tiver várias faixas de áudio, marque as que são dublagens.
3. **Detectar atraso (F5).** O resultado aparece na lista e na aba **Log**.
   - *Dica:* se o arquivo da dublagem também tiver a faixa no idioma original (por exemplo, inglês), use **Sincronizar ▸ Detectar usando outra faixa do arquivo** com essa faixa. É mais confiável e aplica o resultado a todas as dublagens daquele arquivo.
4. **Confira as ondas sonoras.** O filme aparece em verde e a dublagem em laranja. Faça o ajuste fino arrastando a onda laranja ou pelos botões.
5. **Escolha as faixas do filme que ficam** na aba **Filme** (por exemplo, desmarque faixas de áudio ou legendas que você não quer).
6. **Gerar teste (5 min)** e ouça no seu player.
7. **Gerar arquivo final.** A conferência automática roda no fim.
8. *(Opcional)* **Ferramentas ▸ Verificar integridade** prova que o vídeo, o áudio e as legendas originais são idênticos bit a bit.

Os projetos podem ser salvos (`.eternaldub`) e reabertos depois.

---

## Como funciona (técnico)

- **A análise** usa uma cópia leve do áudio (mono, 8 kHz), só para medir, nunca gravada na saída. Envelopes de energia por banda do espectro são correlacionados com FFT. Várias razões de velocidade são testadas (PAL, 24 ↔ 23,976). A análise rápida lê cerca de 1 minuto mais quatro trechos de 40 segundos do filme e procura cada um numa janela maior da dublagem.
- **A junção** usa o FFmpeg com `-c copy` e `-itsoffset` para o atraso. Atrasos negativos são aplicados com um corte da dublagem, só por cópia.
- **Cache:** as ondas sonoras ficam em `~/.eternaldub/cache`, então um filme é lido por inteiro só uma vez. Dá para limpar em **Ferramentas**.
- **Arquivos:** `EternalDub_gui.py` (interface), `EternalDub_core.py` (leitura, detecção, junção, conferências), `detectar_atraso.py` (detecção de atraso, também usável pela linha de comando), `EternalDub_i18n.py` (traduções).

Exemplo de linha de comando:
```bash
python detectar_atraso.py FILME.mkv DUBLAGEM.mkv --faixa-dub 1 --idioma pt
```

---

## Limitações

- **Cortes diferentes entre versões** são detectados e mostrados, mas juntar trechos com atrasos diferentes (pontos de ancoragem) **ainda não foi implementado**. O teste de 5 minutos cobre só o começo, então, se o log mostrar atrasos variando, confira também as cenas mais adiante.
- A detecção depende de música e efeitos sonoros em comum nas duas versões. Se a dublagem tiver trilha sonora regravada, use o alinhamento manual ou **Detectar pelo vídeo**.
- Em discos lentos (por exemplo, HD externo em USB 2.0), ler um remux UHD demora. Salvar o arquivo final em outro disco ajuda bastante.

## Roteiro

- Pontos de ancoragem: atrasos diferentes por trecho, para versões com cortes diferentes
- Reprodução de áudio dentro do programa
- `.exe` independente (sem precisar de Python)
- Mais idiomas de interface

---

## Como contribuir

Issues e pull requests são bem-vindos, principalmente de quem tem experiência com áudio/DSP, FFmpeg ou interface desktop.

- **Bugs:** abra uma [Issue](https://github.com/Moguel0818/EternalDub/issues) e cole o conteúdo da aba **Log** (mais o `~/.eternaldub/erro.log`, se existir).
- **Traduções:** veja `EternalDub_i18n.py`. Copie o dicionário `EN` e traduza os valores.
- Todo mundo que ajudar é creditado em [CREDITS.md](CREDITS.md) e na janela **Sobre** do programa.

## Transparência

O código foi escrito com ajuda de IA (Claude, da Anthropic). O projeto foi idealizado, dirigido e testado pelo autor com arquivos reais. Revisão de desenvolvedores experientes é muito bem-vinda.

## Aviso legal

O EternalDub não inclui, baixa nem distribui nenhuma mídia. Use apenas com arquivos que você tem o direito de usar.

## Licença

[MIT](LICENSE). O EternalDub chama o FFmpeg como programa externo e usa PySide6 e NumPy como bibliotecas; nenhum deles está incluído aqui, e cada um mantém a própria licença.
