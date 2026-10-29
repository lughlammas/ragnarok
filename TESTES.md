# Ragnarok 0.1 - relatório de testes (27/10/2026)

**Onde foi testado:** na box (Linux, Python 3.13.5, Intel Xeon 8 vCPU, 16 GB RAM visíveis). **NADA foi testado no Windows**
(a máquina do Gui é i5-12450H, 7,7 GB RAM; os tempos abaixo NÃO são dela). O pip estava com cache na box; o download dos
modelos foi real (Kokoro 354 MB do GitHub, Supertonic ~370 MB do Hugging Face).

Definições: **RTF = tempo de parede total ÷ duração do áudio** (inclui carregar o modelo, juntar os blocos e codificar).
**RAM pico = pico do processo** (`ru_maxrss`), inclui Python, bibliotecas e modelo.

## 1. Instalação limpa a partir do zip
`ragnarok-0.1.zip` extraído em pasta vazia -> `./install.sh` (venv + pip + modelos + doctor): **16,8 s**, "TUDO OK".
Disco: modelos 0,72 GB + `.venv` 0,31 GB. Testes de texto: 9/9 ok (`python -m unittest discover -s tests`).
`install.ps1` / `run.ps1`: apenas **análise de sintaxe** com o parser do PowerShell 7 (0 erros) e execução das funções
auxiliares (`Get-PythonExe`, `Run`) no PowerShell 7 do Linux. **Não executado no Windows nem no PowerShell 5.1.**

## 2. Livro .m4b com 3 capítulos (CLI `book`)
| Texto | Voz | Palavras | Caracteres | Blocos | Áudio | Tempo total | RTF | RAM pico |
|---|---|---|---|---|---|---|---|---|
| ensaio_pt.md | alex-pt (Kokoro) | 544 | 3008 | 32 | 200,0 s (3:20) | 25,2 s (2ª execução, pacote limpo: 26,7 s) | 0,126 (0,133) | 680 MB (678) |
| ensaio_en.md | michael-en (Kokoro) | 563 | 3048 | 32 | 217,9 s (3:38) | 28,9 s (pacote limpo: 35,2 s) | 0,133 (0,162) | 695 MB (694) |
| ensaio_pt.md | sabio-pt (Supertonic) | 544 | 3008 | 32 | 304,8 s (5:05) | 41,9 s | 0,138 | 551 MB |
| ensaio_en.md (`say --file`, 1 capítulo) | onyx-en (Kokoro) | 563 | 3048 | 32 | 216,0 s | 28,1 s | 0,130 | 687 MB |
| ensaio_en.md (`say --file`, 1 capítulo) | sabio-en (Supertonic) | 563 | 3048 | 32 | 270,8 s | 37,5 s | 0,139 | 553 MB |
| ensaio_en.md (`say --file`; voz PT lendo inglês) | dora-pt (Kokoro) | 563 | 3048 | 32 | 196,4 s | 23,8 s | 0,121 | 693 MB |

(As 3 últimas linhas usaram `say --file`, sem capítulos. A da dora-pt foi só teste de velocidade: o texto é inglês, então o áudio não é uma leitura válida.)
Verificado com ffprobe no `ensaio_pt.m4b`: AAC 24 kHz mono, ~66 kb/s, **3 capítulos** ("Sobre o tempo", "Sobre o silêncio",
"Sobre a espera"), título e autor nos metadados, duração 199,97 s. O `ensaio_en.m4b` também tem 3 capítulos (On Time /
On Silence / On Waiting) e o upload pela API gerou os mesmos.
Os ensaios têm ~550 palavras (pedido: ~600).

## 3. Retomada
- **Kokoro, `kill -9` aos ~11 s:** 15 de 32 blocos em disco. Reexecutar o mesmo comando: *gerados 17, reaproveitados 15*,
  15,1 s (contra 23,7 s do zero). O áudio decodificado final tem **MD5 idêntico** ao de uma execução sem interrupção.
- **Kokoro, Ctrl+C (SIGINT) no pacote limpo:** saída 130 com aviso para rodar de novo; 12 blocos em disco; retomada gerou 20,
  reaproveitou 12 (17,1 s); **MD5 do áudio idêntico** (23f5e5bd...) ao da execução sem interrupção.
- **Supertonic, `kill -9`:** 12 blocos reaproveitados, 20 gerados; mesma duração (304,783 s), mas **MD5 diferente**:
  o Supertonic não é determinístico (a mesma frase gerada duas vezes tem o mesmo tamanho e amostras diferentes; o Kokoro é idêntico).
- **Servidor:** `kill -9` do servidor com um livro a meio: ao reiniciar o trabalho aparece como `interrupted`; `POST /api/jobs/{id}/retry`
  retomou (16 blocos reaproveitados, 14,3 s) e terminou `done`.
- **Trava anti-duplicidade:** um 2º processo tentando gerar o mesmo livro (mesma voz/velocidade) enquanto o 1º roda foi recusado com
  mensagem clara. (Antes da trava, um teste mal feito deixou dois processos escrevendo na mesma pasta: foi o que motivou a trava.)
- **Cancelar** um trabalho em execução via `DELETE /api/jobs/{id}`: status `cancelled` em ~4 s (parou entre blocos, 8/32).

## 4. Interface web e API (curl + navegador headless Chrome via Playwright)
- `GET /` 200 (7,5 KB, sem nenhuma URL externa no HTML; **0 requisições externas** medidas no navegador); `/api/voices`, `/api/status` ok.
- Fluxo no navegador real (Chrome headless): carregou as 7 vozes, ajustou velocidade (0,90x), clicou **Gerar**
  (texto de 122 caracteres, alex-pt): player e botão Baixar apareceram em 3,4 s ("pronto 0:09, RTF 0,25, RAM pico 568 MB");
  upload de `.md` pelo campo de arquivo gerou o livro .m4b com barra de progresso ("3/32 · ~0:31") e terminou
  ("pronto 3:53, 3 cap., RAM pico 825 MB"); **Apagar** removeu a linha. Capturas: `/tmp/pkgtest/out/ui_*.png` (só na box).
  Erros de JS: nenhum. Havia um 404 de `/favicon.ico` (corrigido depois com resposta 204; ver nota ao fim).
- `POST /api/jobs` (texto -> mp3/wav), `POST /api/jobs/upload` (.md -> m4b, 3 capítulos conferidos com ffprobe), download com
  `Content-Disposition`, histórico persistido em `data/history.json` e restaurado após reiniciar.
- Segurança: Host falso -> 400; Origin falsa em POST -> 403; upload de `.pdf` -> 400; servidor escuta só em `127.0.0.1:8765`.
- **`POST /v1/audio/speech`** (pacote final): mp3, wav, opus, aac, flac e pcm -> 200 com o tipo MIME correto;
  duração decodificada ~3,4 s para o texto de teste; voz inválida / input vazio / formato inválido -> 400; nomes OpenAI (`alloy`)
  usam a voz padrão. Cliente oficial `openai` (Python) com `base_url=http://127.0.0.1:8765/v1`: `audio.speech.create` gravou um mp3 de
  5,8 s em 1,7 s; `models.list()` devolveu `ragnarok`.
- Um pedido `/v1` feito durante um livro em geração **esperou a vez** (19,6 s) e respondeu 200.
- Tempos `/v1` (frase de 1 linha, depois do modelo carregado): ~0,25-0,33 s para wav/opus/flac/aac/pcm; o 1º pedido, com carga do modelo, 1,5 s.

## 5. Memória (um engine por vez)
Sequência no mesmo processo (RSS atual): base 27 MB -> Kokoro 527 MB -> Supertonic 521 MB -> Kokoro 580 MB -> Supertonic 527 MB ->
Kokoro 539 MB -> após `unload` 422 MB. Não acumula ao alternar engines. O pico do **servidor** depois de várias gerações foi maior que o do CLI
(825 MB num caso, contra ~695 MB do CLI no mesmo texto); não investiguei a causa.
Projeção (inferência, NÃO medida): com picos de 0,55-0,83 GB cabe folgado nos 7,7 GB do Gui; a velocidade na i5-12450H pode diferir bastante da do Xeon.

## 6. O que NÃO foi testado
- Windows 11 e PowerShell do Windows: a instalação, `ragnarok.bat doctor`, Kokoro/Alex, WAV e medições foram executados em 29/10/2026; detalhes na seção 9. A trava `msvcrt` foi exercitada pela aprovação da geração, mas concorrência entre processos não foi repetida.
- Pico de RAM e velocidade na i5-12450H com 7,7 GB; Python 3.11/3.12 (testado só 3.13.5); livros longos (horas) e textos muito grandes (>3 MB).
- Piper (não incluído nesta versão). Qualidade/naturalidade do áudio (não consigo ouvir).
- Playback de `.m4b` dentro do navegador (a interface oferece só "Baixar" para m4b).

## 7. Riscos de instalação no Windows
1. Python: precisa 3.11-3.13 de 64 bits (o `kokoro-onnx 0.6.1` declara `<3.14`); o alias da Microsoft Store pode atrapalhar (o script prefere o `py` launcher).
2. `onnxruntime` pede o runtime Visual C++ 2015-2022 x64 (o instalador só avisa).
3. `espeakng-loader` (DLL do espeak-ng embutida) e `phonemizer` no Windows: não verificado.
4. `imageio-ffmpeg` baixa/usa o binário ffmpeg dele; o do Windows não foi inspecionado (codecs mp3/aac/opus assumidos; no Linux conferidos).
5. Antivírus/Defender pode atrasar ou bloquear a 1ª execução do ffmpeg; caminho com espaços/acentos pode dar erro (recomendo `C:\Ragnarok`).
6. Download do Supertonic exige internet e o Hugging Face (sem login); hash SHA-256 do Kokoro foi fixado na 1ª baixada, sem fonte oficial para cruzar.
7. Porta 8765 ocupada: use `ragnarok.bat web --port 8800`.

**Nota:** depois destes testes foram feitas duas mudanças pequenas: a trava de processo (testada, seção 3) e o `/favicon.ico` (204); esta
última foi reverificada só com unit tests e `curl` do favicon (seção 8).

## 8. Reverificação final do pacote
Zip final extraído em pasta nova e instalado do zero (`install.sh`: "TUDO OK"); 9/9 testes de texto; `GET /favicon.ico` -> 204;
`POST /v1/audio/speech` (alex-pt, mp3) -> 200, 15,9 KB; livro `michael-en` -> `.m4b` com 3 capítulos conferidos com ffprobe, 217,9 s de áudio,
35,4 s no total (RTF 0,162), RAM pico 694 MB. (A mesma tarefa levou 28,9 s numa execução anterior: a box tem carga variável, então
espere variação de ~20% nos tempos.) A trava de processo, a retomada e a interface no navegador foram testadas no zip anterior a
estas duas mudanças pequenas (favicon/204 e trava), sem outra mudança de código depois.

## 9. Windows 11 — Alex/Kokoro e fluxo editorial (29/10/2026)

Ambiente desta execução: Windows 11, Python 3.12.10 64 bits, Kokoro ONNX 0.6.1, ONNX Runtime 1.31.1, CPU.

- `install.ps1`: instalação concluída; Kokoro (325,5 MB + 28,2 MB) conferido pelos hashes fixados; diagnóstico terminou em `TUDO OK`. O Supertonic não foi baixado.
- `ragnarok.bat doctor`: `TUDO OK`; ffmpeg do `imageio-ffmpeg` reconhecido.
- Texto integral de calibração `exemplos/amostra_calibracao_alex_ptbr.txt`, voz `alex-pt` / `pm_alex`, PT-BR, 0,95, WAV: 724 caracteres, 13 blocos, 56,86 s, 27,9 s de execução (RTF 0,490), pico 538 MB, zero anomalias. WAV PCM 16-bit, 24 kHz, mono, 2.729.516 bytes; sem amostras não finitas nem clipping detectado.
- Trecho adicional de pronúncia enviado ao Alex com “zazen”, “aquietamento”, “transmutação”, “integração” e pergunta: WAV de 7,6 s, 1 bloco, 6,2 s, pico 552 MB, zero anomalias. A pronúncia foi exercitada no sintetizador; a avaliação auditiva final pertence ao autor.
- Fluxo de aprovação: áudio e texto copiados à área protegida, hashes registrados e exclusão recusada. Exportação M4B reutilizou WAVs, verificou duração (3,38 s no trecho curto de 2,7 s, incluindo priming AAC) e ordem/metadados; nenhuma chamada ao sintetizador ocorreu na exportação.
- `python -m unittest discover -s tests`: 9/9 passaram. Sintaxe JavaScript da interface verificada com `node --check`.
- O instalador foi corrigido para direcionar temporários do Windows a `data/tmp`; sem isso, `ensurepip` e o phonemizer podem falhar em ambientes que bloqueiam `%TEMP%` do sistema.

Ainda não foi feita avaliação auditiva subjetiva nem teste visual em navegador do fluxo web. A compatibilidade do arquivo e as métricas foram verificadas localmente.

## 10. Sábio PT — avaliação inicial no Windows (29/10/2026)

Ambiente: Windows 11, Python 3.12.10 64 bits, Supertonic-3 / voz M5, CPU; `ragnarok models` baixou o modelo, e `ragnarok doctor` terminou em `TUDO OK` com Supertonic como engine obrigatório.

- Amostra integral de calibração (mesmo texto usado na comparação Alex), `sabio-pt`, velocidade efetiva 0,85×: 724 caracteres, 13 blocos, 86,19 s de áudio, 44,0 s de processamento (RTF 0,511), pico 510 MB e zero anomalias. WAV mono 44,1 kHz; pico digital 0,453, sem clipping.
- Trecho adicional com “zazen”, “aquietamento”, “transmutação”, “integração” e pergunta: 14,42 s, 2 blocos, 8,2 s de processamento, pico 506 MB e zero anomalias.
- Estimativa acústica exploratória por autocorrelação: F0 mediana aproximada de 90 Hz para Sábio e 134 Hz para Alex. Isso indica frequência fundamental mais baixa no trecho e não comprova timbre percebido, naturalidade, emoção ou sotaque.
- O Supertonic recebe o idioma `pt`; essa configuração não identifica explicitamente a variante brasileira. A confirmação de pronúncia e prosódia brasileiras ainda depende de escuta. As gravações estão entregues para comparação; nenhuma alternativa foi escolhida sem essa avaliação.
