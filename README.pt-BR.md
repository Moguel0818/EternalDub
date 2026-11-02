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
- **Cortes diferentes, sincronizados trecho por trecho.** Quando as versões têm cortes diferentes (ou a dublagem foi remontada por quem a publicou), o atraso muda ao longo do filme. O EternalDub mede o atraso a cada segundo, acha cada mudança e monta a dublagem pedaço por pedaço: onde falta um pedaço do filme na dublagem, entra silêncio; onde ela tem algo que não existe no filme, esse pedaço sai, de preferência numa pausa. Só a dublagem vira FLAC (sem perdas); o filme não é tocado.
- **Visualização das ondas sonoras** no estilo do Subtitle Edit. Arraste a dublagem para ajustar o atraso na mão, ou use os botões de ±10/100/1000 ms.
- **Edite as emendas à mão.** Na sincronia trecho por trecho, cada emenda é uma linha vermelha na onda: arraste-a, ajuste com as setas do teclado (10 ms; Shift 100 ms; Ctrl 1 ms), digite o tempo ou a quantia exatos, crie uma emenda em qualquer ponto (botão direito) ou remova uma falsa. Ctrl+arrastar desliza só um trecho. Um ímã encaixa as emendas nas pausas da dublagem, e a aba **Emendas** diz se cada uma cai numa pausa ou no meio de fala ou música, para nunca cortar uma fala sem querer. Tudo tem Desfazer/Refazer.
- **Ouça dentro do programa.** Aperte **F8** para ouvir a dublagem exatamente como ela vai ficar no arquivo (atraso, correção de velocidade e emendas aplicados), o áudio de referência do filme, ou os dois misturados (se a música e os efeitos combinam, a sincronia está certa). Clique na régua para escolher de onde começar; **F9** toca 3 segundos antes e depois da emenda escolhida. Sem precisar gerar um arquivo de teste.
- **Várias dublagens de uma vez,** de um ou vários arquivos, cada uma com nome, idioma e marcação de padrão próprios.
- **Organize o arquivo final.** A aba **Arquivo final** lista todas as faixas que podem ir para o MKV (as do próprio filme, as dublagens e as legendas adicionadas) na ordem em que vão ficar: marque o que entra (botões **Marcar tudo** / **Desmarcar tudo**), mude a ordem com **Subir/Descer** e escolha o áudio e a legenda padrão. Com a interface em português ela já começa no padrão BDRemux PT-BR: 1) áudio PT-BR, 2) áudio no idioma original, 3) legenda PT-BR. Também dá para só reorganizar um filme, sem nenhuma dublagem.
- **Adicione legendas** como adiciona dublagens: `.srt`, `.ass`, `.ssa`, `.vtt`, `.sup`, `.idx/.sub` ou uma faixa de legenda de outro MKV/MP4, cada uma com nome, idioma, atraso e marca de *forçada*. Legendas de texto em Windows-1252 (ANSI) ou UTF-16 são convertidas para UTF-8, para os acentos saírem certos.
- **Teste e conferência automática.** Gera primeiro um arquivo de teste de 5 minutos. Depois de juntar tudo, confere se cada dublagem tem som, está sincronizada e está bem entrelaçada com o vídeo dentro do arquivo final (áudio gravado longe do vídeo faz alguns players ficarem mudos).
- **Tudo num lugar só.** Detecção, ajuste manual, junção e verificação acontecem numa única janela.
- **Idiomas da interface:** português (Brasil), inglês, espanhol, francês, italiano e alemão. Cada idioma é um simples arquivo `.json` na pasta `idiomas/`, então qualquer pessoa pode acrescentar outro sem programar.
- **Funciona sem Python.** Há um programa independente para Windows (`EternalDub.exe`); veja Instalação.

---

## Requisitos

| O quê | Observações |
|---|---|
| **Windows 10/11** | Testado. Linux/macOS devem funcionar rodando `EternalDub_gui.py` diretamente, mas ainda não foi testado. |
| **FFmpeg** | `ffmpeg` e `ffprobe`: no PATH (no Windows: `winget install Gyan.FFmpeg`) **ou ao lado do `EternalDub.exe`** (ou do `EternalDub_gui.py`). O EternalDub também procura nas pastas onde o winget o instala. |
| **Python 3.10+** | Só para rodar pelo código-fonte (o programa independente não precisa). Em [python.org](https://www.python.org/downloads/); marque **"Add python.exe to PATH"**. Recomendado 3.12 ou 3.13. |
| **numpy, PySide6** | Só para rodar pelo código-fonte. Instalados automaticamente pelo `Iniciar_EternalDub.bat` na primeira execução (ou `pip install -r requirements.txt`). |

---

## Instalação

**Opção A: programa independente (sem precisar de Python)**
1. Na página de **Releases**, baixe o `EternalDub-Windows-pasta.zip` (ou o `EternalDub-Windows-um-arquivo.zip`, um único `.exe` que abre um pouco mais devagar).
2. Extraia e dê dois cliques em **`EternalDub.exe`**.
3. Confira se o FFmpeg está disponível (veja Requisitos).

> O programa não tem assinatura digital, então o Windows SmartScreen pode avisar na primeira vez: clique em **Mais informações ▸ Executar assim mesmo**.

**Opção B: baixar o código-fonte (precisa de Python)**
1. Clique em **Code ▸ Download ZIP** nesta página.
2. Extraia numa pasta nova.
3. Dê dois cliques em **`Iniciar_EternalDub.bat`**.

**Opção C: git**
```bash
git clone https://github.com/Moguel0818/EternalDub.git
cd EternalDub
pip install -r requirements.txt
python EternalDub_gui.py
```

A interface abre no idioma do seu sistema quando existe tradução (senão, em inglês). Dá para trocar em **Opções ▸ Idioma / Language**.

**Gerar o programa independente você mesmo**
- Com o Python instalado: dê dois cliques em **`Gerar_EXE.bat`** (o resultado fica em `dist\EternalDub\`).
- Sem instalar nada: no GitHub, vá em **Actions ▸ Gerar EternalDub.exe ▸ Run workflow**; em uns 5 minutos o zip aparece em **Artifacts**. Publicar uma tag de versão (por exemplo `v1.3`) também anexa os zips em **Releases**.

---

## Como usar

1. **Abrir filme.** Escolha a release de alta qualidade, ou arraste para a janela.
2. **Adicionar dublagem.** Escolha o(s) arquivo(s) com a dublagem: um MKV/MP4 com vídeo, ou só áudio (MP3, AC3, E-AC3, DTS, FLAC, WAV…). Se o arquivo tiver várias faixas de áudio, marque as que são dublagens.
3. **Detectar atraso (F5).** O resultado aparece na lista e na aba **Registro**.
   - *Dica:* se o arquivo da dublagem também tiver a faixa no idioma original (por exemplo, inglês), use **Sincronização ▸ Detectar usando outra faixa do arquivo** com essa faixa. É mais confiável e aplica o resultado a todas as dublagens daquele arquivo.
   - Se aparecer o aviso de **cortes diferentes**, escolha **Sincronizar trecho por trecho** (também em **Sincronização ▸ Sincronizar trecho por trecho**, Ctrl+M). A onda passa a mostrar a dublagem já no lugar, com cada emenda marcada em vermelho, e a aba Registro lista todas as emendas.
4. **Confira as ondas sonoras.** O filme aparece em verde e a dublagem em laranja. Faça o ajuste fino arrastando a onda laranja ou pelos botões.
   - **Ouvir:** clique na régua para pôr a linha azul de onde quer começar e aperte **F8** (de novo para parar). Escolha o que ouvir na barra de ferramentas: a dublagem já sincronizada, o filme, ou os dois juntos.
   - **Ajuste as emendas** (quando usou a sincronia trecho por trecho): arraste as linhas vermelhas, use as setas do teclado, ou escolha uma na aba **Emendas** (tempo, quantia, *Achar pausa*, *Ouvir (F9)*). Clique com o botão direito na onda para criar uma emenda ou remover uma errada. **Ctrl+Z / Ctrl+Y** desfazem e refazem.
5. **Organize o arquivo final** na aba **Arquivo final**: marque as faixas que entram, mude a ordem com **Subir/Descer**, escolha a faixa padrão e adicione legendas com **Adicionar legenda...** (Ctrl+L) ou arrastando arquivos `.srt` para a janela.
6. **Gerar teste (5 min)** e ouça no seu player.
7. **Gerar arquivo final.** A conferência automática roda no fim.
8. *(Opcional)* **Ferramentas ▸ Verificar integridade** prova que o vídeo, o áudio e as legendas originais são idênticos bit a bit.

Os projetos podem ser salvos (`.eternaldub`) e reabertos depois.

---

## Como funciona (técnico)

- **A análise** usa uma cópia leve do áudio (mono, 8 kHz), só para medir, nunca gravada na saída. Envelopes de energia por banda do espectro são correlacionados com FFT. Várias razões de velocidade são testadas (PAL, 24 ↔ 23,976). A análise rápida lê cerca de 1 minuto mais quatro trechos de 40 segundos do filme e procura cada um numa janela maior da dublagem.
- **A sincronia por trechos** mede o atraso a cada segundo (janelas de 6 s, até ±20 s em torno do atraso principal), escolhe o caminho mais provável com uma busca de Viterbi (o atraso só muda quando a evidência compensa, então trechos só de diálogo não criam emendas falsas), depois acha o ponto exato de cada mudança quadro a quadro (20 ms) e, entre pontos quase empatados, prefere uma pausa da dublagem. A dublagem é decodificada uma vez, na mesma linha do tempo da análise, emendada com cruzamentos de 8 ms (sem estalos) e gravada em FLAC (24 bits para fontes com perdas, 16 bits para fontes de 16 bits).
- **A junção** usa o FFmpeg com `-c copy` e `-itsoffset` para o atraso. Atrasos negativos são aplicados com um corte da dublagem, só por cópia. Dublagens com correção de velocidade ou sincronia por trechos entram como o FLAC descrito acima, já na linha do tempo do filme. As legendas do filme entram por uma segunda leitura do mesmo arquivo: sem isso, o FFmpeg para de ler a dublagem enquanto a legenda fica sem fala, e o áudio desse intervalo vai parar longe do vídeo dentro do arquivo.
- **Organização das faixas:** a ordem das opções `-map` é a ordem das faixas no MKV (vídeos, depois áudios, depois legendas). Cada faixa de áudio e de legenda recebe marcas explícitas (`-disposition`): exatamente um áudio padrão, no máximo uma legenda padrão, e as marcas do filme de *forçada*, *comentário*, *para surdos* e *audiodescrição* continuam; `-default_mode infer_no_subs` impede o MKV de ligar uma legenda sozinho. Legendas externas são entradas próprias: atraso positivo usa `-itsoffset`, negativo pula o começo da legenda (`-ss`). Legendas de MP4 (`mov_text`) viram SRT, a única mudança que o MKV exige. A verificação de integridade acha cada faixa original pelo hash, esteja onde estiver.
- **Edição das emendas** (`EternalDub_emendas.py`): o mapa por trechos é editado como uma lista de emendas (tempo, silêncio inserido, pedaço removido). Mover uma emenda nunca muda o alinhamento de nenhum trecho, só o ponto em que um alinhamento passa para o outro; a dublagem sempre anda para a frente no tempo e nenhum trecho fica menor que 50 ms. Uma emenda com quantia de cerca de 0 ms é removida (só deixaria um buraco de 16 ms no som). A conferência do *som na emenda* mede o nível da dublagem em volta do ponto de corte (o pedaço removido mais 50 ms de cada lado), e o ímã procura o ponto mais próximo em que esse nível é uma pausa. Um mapa que não foi editado é salvo exatamente como veio.
- **Prévia** (`EternalDub_audio.py`): usa o mesmo montador do arquivo final (mesmo atraso, mesma correção de velocidade, mesmos cruzamentos de 8 ms). O FFmpeg começa na linha azul (`-ss`) e blocos de 0,25 s tocam conforme são decodificados (mono, 48 kHz). Os testes automáticos comparam com a saída real: amostras idênticas sem correção de velocidade, e dentro de 1 ms com ela (o filtro `atempo` escolhe os próprios pontos de sobreposição).
- **Cache:** as ondas sonoras ficam em `~/.eternaldub/cache`, então um filme é lido por inteiro só uma vez. Dá para limpar em **Ferramentas**.
- **Arquivos:** `EternalDub_gui.py` (interface), `EternalDub_core.py` (leitura, detecção, junção, conferências), `EternalDub_emendas.py` (edição das emendas), `EternalDub_audio.py` (prévia), `detectar_atraso.py` (detecção de atraso, também usável pela linha de comando), `EternalDub_i18n.py` + `idiomas/*.json` (traduções), `EternalDub.spec` + `Gerar_EXE.bat` + `.github/workflows` (programa independente), `tests/` (testes automáticos).

Exemplo de linha de comando:
```bash
python detectar_atraso.py FILME.mkv DUBLAGEM.mkv --faixa-dub 1 --idioma pt
# mapa trecho por trecho (lê as duas faixas inteiras):
python detectar_atraso.py FILME.mkv DUBLAGEM.mp4 --mapa --idioma pt
```

---

## Limitações

- **A sincronia por trechos** depende de música e efeitos sonoros em comum nas duas versões. Em trechos longos só de diálogo, o ponto exato de uma mudança pode errar por alguns segundos (na dúvida, o programa mantém o atraso anterior em vez de chutar). O teste de 5 minutos cobre só o começo, então ouça no arquivo final algumas das emendas listadas na aba Registro.
- A detecção depende de música e efeitos sonoros em comum nas duas versões. Se a dublagem tiver trilha sonora regravada, use o alinhamento manual ou **Detectar pelo vídeo**.
- Em discos lentos (por exemplo, HD externo em USB 2.0), ler um remux UHD demora. Salvar o arquivo final em outro disco ajuda bastante.
- A prévia é em mono (o downmix do FFmpeg). Com correção de velocidade o tempo bate com o arquivo final em cerca de 1 ms, mas a forma de onda não é idêntica amostra por amostra.
- Enquanto você ouve, a leitura das ondas pausa (um disco, um trabalho de cada vez) e continua quando você para.
- O programa para Windows não tem assinatura digital e é gerado pelo fluxo automático do projeto: relate qualquer coisa estranha.

## Roteiro

- Prévia em estéreo / 5.1 (por enquanto é mono)
- `.exe` com assinatura digital e aviso de atualização
- Testes em Linux e macOS
- Mais idiomas de interface (mande o seu: é só um arquivo `.json`)

---

## Como contribuir

Issues e pull requests são bem-vindos, principalmente de quem tem experiência com áudio/DSP, FFmpeg ou interface desktop.

- **Bugs:** abra uma [Issue](https://github.com/Moguel0818/EternalDub/issues) e cole o conteúdo da aba **Registro** (mais o `~/.eternaldub/erro.log`, se existir).
- **Traduções:** copie `idiomas/en.json` para `idiomas/<código>.json` (por exemplo `fr.json`), troque `codigo`, `nome` e `tradutores` e traduza os valores. O idioma aparece sozinho em **Opções ▸ Idioma / Language**. Rode `python tests/test_idiomas.py` para ver o que falta ou está errado e abra um pull request.
- **Testes:** `python -m unittest discover -s tests -t .` (precisa do FFmpeg; os testes de interface rodam sem tela). Conferem o editor de emendas, a prévia contra a saída real, as traduções e a janela principal.
- Todo mundo que ajudar é creditado em [CREDITS.md](CREDITS.md) e na janela **Sobre** do programa.

## Transparência

O código foi escrito com ajuda de IA (Claude, da Anthropic). O projeto foi idealizado, dirigido e testado pelo autor com arquivos reais. Revisão de desenvolvedores experientes é muito bem-vinda.

## Aviso legal

O EternalDub não inclui, baixa nem distribui nenhuma mídia (nem o FFmpeg). Use apenas com arquivos que você tem o direito de usar.

## Licença

[MIT](LICENSE). O EternalDub chama o FFmpeg como programa externo e usa PySide6 e NumPy como bibliotecas; nenhum deles está incluído aqui, e cada um mantém a própria licença.
