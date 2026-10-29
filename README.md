# Ragnarok 0.1

Leitor de textos em voz alta, **local, só CPU, uso pessoal**. Escrito do zero (não usa código do VoiceStudio).
Nenhum texto sai do computador; a internet é usada só na instalação (pacotes e modelos).

**Configuração inicial recomendada para avaliação:** voz `alex-pt` (Kokoro / `pm_alex`, PT-BR), velocidade `0.95` e saída WAV. A interface abre com essa voz e formato selecionados. Música e efeitos não são aplicados.

## Instalar (Windows 11)

1. Instale o Python 3.12 (64 bits) se ainda não tiver: `winget install -e --id Python.Python.3.12`
2. Extraia o zip numa pasta **sem espaços ou acentos no caminho** (ex.: `C:\Ragnarok`).
3. Duplo clique em `install.bat` (ou: `powershell -ExecutionPolicy Bypass -File .\install.ps1`).
   Cria a pasta `.venv`, instala as dependências, baixa Kokoro (necessário para Alex) e roda um diagnóstico.
   O Supertonic, usado por vozes opcionais, pode ser instalado separadamente com `ragnarok models`.
   Reserve ~1,5 GB livres; o tamanho exato varia entre versões do Python e do Windows.

Linux/macOS: `./install.sh`.

## Usar

```
ragnarok.bat                      abre a interface web em http://127.0.0.1:8765
ragnarok.bat voices               lista as vozes
ragnarok.bat say "Olá, mundo" --voice alex-pt --speed 0.95 --out ola.wav
ragnarok.bat models --kokoro         instala só o engine usado por Alex
ragnarok.bat say --file texto.txt --voice sabio-pt --speed 0.95 --out texto.wav
ragnarok.bat book ensaio.md --voice alex-pt --out ensaio.m4b --title "Meu ensaio" --author "Autor"
ragnarok.bat doctor [--full]      diagnóstico da instalação
```
(no Linux: `./run.sh ...`; também há `run.ps1`.)

**Vozes** (arquivo `config/voices.json`): `michael-en` (maduro, EN), `onyx-en` (grave, EN), `sabio-en` (EN),
`alex-pt` (maduro, PT-BR), `sabio-pt` (PT-BR), `dora-pt` (feminina, PT-BR), `heart-en` (feminina, EN).
`--speed` é um multiplicador sobre a velocidade base da voz (padrão 0.95; a velocidade efetiva de Alex começa em 0.95×).

**Livros** (`book`): cada cabeçalho Markdown do nível mais alto do arquivo (`#`) vira um capítulo (títulos mais fundos
viram subtítulos lidos no texto). O título do capítulo é lido em voz alta (use `--no-titles` para não ler).
Texto sem cabeçalhos vira um capítulo só. O texto é dividido em frases/blocos de até ~220 caracteres, com pausas
por pontuação (`.` 0,4 s, `!?` 0,45 s, `…` 0,7 s, fim de parágrafo 0,8 s, título 1,2 s, 2 s entre capítulos).
Saída `.m4b` ou `.mp3` com marcadores de capítulo. **Se interromper (Ctrl+C, queda de luz), rode o mesmo comando
de novo: os blocos já gerados são reaproveitados** (ficam em `data\work\`).

**Interface web**: quatro etapas — importar capítulo, gerar e escutar, aprovar capítulo, exportar audiobook. A aprovação preserva cópias do texto original e do áudio, com hashes de integridade e as configurações da geração. Áudios aprovados não podem ser apagados nem reprocessados; uma correção editorial entra como uma nova geração. Correções de pronúncia opcionais (`termo=leitura`) alteram apenas o texto enviado à síntese. A exportação seleciona e ordena capítulos aprovados, cria M4B com título, autor e marcadores e não roda a síntese novamente. Escuta só em 127.0.0.1 e rejeita Host/Origin de fora.

**API compatível com OpenAI**: `POST http://127.0.0.1:8765/v1/audio/speech` com
`{"model":"tts-1","input":"texto","voice":"alex-pt","response_format":"mp3","speed":1.0}`
(`mp3`, `wav`, `opus`, `aac`, `flac`, `pcm`). Nomes de voz da OpenAI (`alloy`, `nova`...) usam a voz padrão
(`michael-en`). Limite de 20 000 caracteres por pedido; para textos maiores use a fila (`/api/jobs`).
Um trabalho por vez: pedidos esperam a vez enquanto um livro está sendo gerado.

## Limitações

- Só vozes prontas; **sem clonagem de voz**. Piper não foi incluído nesta versão (previsto como opcional).
- Um engine carregado por vez (a troca Kokoro <-> Supertonic descarrega o anterior); um trabalho por vez.
- Números, siglas e abreviações são lidos como o modelo entende (sem normalização própria): confira nomes e números.
- O Supertonic não é bit-a-bit determinístico: após retomar, o áudio é equivalente, mas não idêntico amostra a amostra.
- Kokoro usa **sempre fp32** (o int8 deu áudio anômalo com `pm_alex`). Blocos com duração suspeita são regenerados
  uma vez e contados como "anomalias" no resumo.
- Voz "sábio" = timbre grave e fala mais lenta nos modelos prontos; não é sotaque nem estilo "mestre".
- PT-BR do Supertonic: o modelo declara "Portuguese" (`pt`); a variante brasileira não está confirmada.
- Textos longos são processados em blocos; a RAM de pico medida fica no resumo do CLI e no topo da interface.

## Licenças (verificadas em 27/10/2026)

| Componente | Licença |
|---|---|
| Ragnarok (este código) | uso pessoal do autor; sem licença de redistribuição definida |
| Kokoro-82M (pesos) | Apache-2.0 (card do modelo) |
| kokoro-onnx, espeakng-loader | MIT |
| **espeak-ng** (biblioteca embutida no `espeakng-loader`, fonética do PT-BR) e **phonemizer** | **GPL-3.0** (GitHub). Usar no próprio computador é livre; se você **distribuir** o programa junto com essas bibliotecas, a GPL se aplica |
| Supertonic (SDK) | MIT |
| Supertonic-3 (pesos) | **OpenRAIL-M** (BigScience Open RAIL-M: permite uso, mas com restrições de uso; leia `LICENSE` no repositório `Supertone/supertonic-3`) |
| onnxruntime | MIT |
| FastAPI, numpy, uvicorn, python-multipart, soundfile | MIT, BSD-3-Clause, BSD-3-Clause, Apache-2.0, BSD-3-Clause |
| imageio-ffmpeg | BSD-2-Clause; o binário ffmpeg que ele traz é GPL (verificado no build Linux: `--enable-gpl`; o do Windows não verifiquei) |

Os modelos não vêm no zip: o instalador baixa os do Kokoro (GitHub `thewh1teagle/kokoro-onnx`, com SHA-256 fixado
na primeira baixada, não cruzado com fonte oficial) e do Supertonic (Hugging Face `Supertone/supertonic-3`).

## Pastas

`ragnarok/` código · `config/voices.json` vozes · `exemplos/` ensaios de teste · `tests/` testes de texto ·
`models/`, `data/`, `.venv/` criados na instalação/uso (não vão no zip). Variáveis: `RAGNAROK_DATA`, `RAGNAROK_MODELS`, `RAGNAROK_FFMPEG`.
