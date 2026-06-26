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

## Nota sobre custo

A estimativa usa as constantes `PRICE_PER_1M_*` no script (preço de referência da
saída de imagem do Gemini 2.5 Flash Image). Confira a tabela de preços oficial
atual do Google para valores exatos de faturamento.
