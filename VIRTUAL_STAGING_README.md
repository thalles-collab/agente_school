# Virtual Staging — salas vazias (Gemini 2.5 Flash Image / Nano Banana)

Script que popula salas vazias de um escritório real com mobília corporativa e
algumas pessoas trabalhando, **preservando a arquitetura** (paredes, janelas,
piso, pé-direito e vista pela janela). Não inventa um ambiente novo.

## Instalação

```bash
pip install -r requirements.txt
```

## Uso

```bash
export GEMINI_API_KEY="sua-chave-do-google-ai-studio"

# diretório com as fotos sala5.jpg, sala6.jpg, sala8.jpg
python3 virtual_staging.py /caminho/das/fotos
```

O diretório também pode ser passado via `PHOTOS_DIR`. Se nada for informado,
usa o padrão `DEFAULT_PHOTOS_DIR` definido no script.

## O que faz

- Para cada sala (`sala5`, `sala6`, `sala8`) procura a foto de origem
  (`.jpg/.jpeg/.png/.webp`), ignorando arquivos já gerados `*_staged.*`.
- Chama `gemini-2.5-flash-image` com a **imagem original + um prompt de edição**
  (prompt base em inglês adaptado por sala em `ROOM_HINTS`).
- Salva o resultado como `sala5_staged.jpg`, `sala6_staged.jpg`, `sala8_staged.jpg`.
- Trata erros **por sala** (uma falha não interrompe as demais) e imprime
  **uso de tokens + estimativa de custo** a partir do `usage_metadata` da API.

## Personalização

- `BASE_PROMPT`: instrução comum (preservação da estrutura + adicionar mobília/pessoas).
- `ROOM_HINTS`: ajuste fino por sala (ex.: sala de reunião, área colaborativa).
- `ROOMS`: lista de salas a processar.

## Vídeo-tour (office_tour.py)

Depois de gerar as imagens com staging, `office_tour.py` cria um **vídeo-tour**
do andar: para cada `salaX_staged.jpg` usa o modelo **Veo** (mesma API/chave) em
modo image-to-video, gerando um clipe curto com movimento de câmera que apenas
"passeia" pelo ambiente (sem alterar a arquitetura), e concatena tudo num único
`office_tour.mp4`.

```bash
export GEMINI_API_KEY="sua-chave"
python3 office_tour.py /caminho/das/fotos
```

- Modelo configurável via `VEO_MODEL` (padrão `veo-3.0-generate-001`; o Veo 3
  também gera áudio). Alternativas: `veo-3.0-fast-generate-001`, `veo-2.0-generate-001`.
- A geração do Veo é assíncrona (o script faz polling) e cada clipe tem poucos
  segundos (5–8s). Saídas: `salaX_clip.mp4` + o tour final `office_tour.mp4`.
- A concatenação usa o ffmpeg do pacote `imageio-ffmpeg` (não precisa instalar
  ffmpeg no sistema). Se o ffmpeg faltar, os clipes individuais ainda são gerados.
- `person_generation` no Veo pode ter restrições por região/política — ajuste no
  script se a API recusar gerar pessoas.

## Nota sobre custo

A estimativa usa as constantes `PRICE_PER_1M_*` no script (preço de referência da
saída de imagem do Gemini 2.5 Flash Image). Confira a tabela de preços oficial
atual do Google para valores exatos de faturamento.
