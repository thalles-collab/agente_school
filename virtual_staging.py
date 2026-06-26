#!/usr/bin/env python3
"""
Virtual staging de salas vazias de um escritório corporativo usando a API do
Google Gemini 2.5 Flash Image (Nano Banana).

O objetivo é POPULAR o ambiente real (mobília corporativa + algumas pessoas
trabalhando) PRESERVANDO a arquitetura: paredes, janelas, piso, pé-direito e a
vista pela janela. Não inventa um ambiente novo.

Uso:
    export GEMINI_API_KEY="sua-chave"
    python3 virtual_staging.py [diretorio_das_fotos]

O diretório das fotos pode vir (em ordem de prioridade):
    1. argumento de linha de comando
    2. variável de ambiente PHOTOS_DIR
    3. valor padrão abaixo (DEFAULT_PHOTOS_DIR)

Cada foto de entrada (ex.: sala5.jpg) gera uma saída sala5_staged.jpg no mesmo
diretório.
"""

import os
import sys
import glob
import mimetypes

DEFAULT_PHOTOS_DIR = "/caminho/das/fotos"

# Modelo de geração/edição de imagem (Nano Banana).
MODEL = "gemini-2.5-flash-image"

# Preço de referência da saída de imagem do Gemini 2.5 Flash Image.
# (cada imagem ~= 1290 tokens de saída; $30 / 1M tokens de saída => ~$0.039/imagem)
# Usado apenas para uma ESTIMATIVA de custo a partir do usage retornado pela API.
PRICE_PER_1M_OUTPUT_TOKENS = 30.0
PRICE_PER_1M_INPUT_TOKENS = 0.30  # texto/imagem de entrada (referência)

# Prompt base + adaptação por sala. A estrutura real é sempre preservada.
BASE_PROMPT = (
    "Edit this real office photo. Keep the exact room structure, walls, windows, "
    "ceiling, flooring and the view through the windows unchanged. Add realistic "
    "modern corporate furniture appropriate to the space and 2-3 professionals "
    "working naturally. Photorealistic, matching the existing lighting and "
    "perspective. Do not alter the architecture."
)

# Toque extra por sala (opcional). Mantém o prompt base e só acrescenta o tipo
# de uso desejado para cada ambiente. Ajuste à vontade.
ROOM_HINTS = {
    "sala5": (
        " This room should become an open collaborative workspace with a few "
        "desks, ergonomic chairs and laptops."
    ),
    "sala6": (
        " This room should become a meeting room with a central conference table, "
        "chairs and a few people in a discussion."
    ),
    "sala8": (
        " This room should become a focused work area with individual desks, "
        "monitors and people typing."
    ),
}

ROOMS = ["sala5", "sala6", "sala8"]


def find_source_image(photos_dir, room):
    """Encontra o arquivo de origem da sala (sala5.jpg, sala5.jpeg, sala5.png...),
    ignorando arquivos já gerados (*_staged.*)."""
    candidates = []
    for ext in ("jpg", "jpeg", "png", "webp", "JPG", "JPEG", "PNG", "WEBP"):
        candidates += glob.glob(os.path.join(photos_dir, f"{room}.{ext}"))
    # fallback: qualquer arquivo que comece com o nome da sala e não seja _staged
    if not candidates:
        for path in glob.glob(os.path.join(photos_dir, f"{room}*")):
            low = path.lower()
            if "_staged" in low:
                continue
            if low.rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "webp"):
                candidates.append(path)
    return candidates[0] if candidates else None


def report_usage(response):
    """Imprime tokens usados e uma estimativa de custo a partir do usage_metadata."""
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        print("    [uso] API não retornou usage_metadata.")
        return
    prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
    cand_tokens = getattr(usage, "candidates_token_count", 0) or 0
    total_tokens = getattr(usage, "total_token_count", 0) or 0
    est_cost = (
        prompt_tokens / 1_000_000 * PRICE_PER_1M_INPUT_TOKENS
        + cand_tokens / 1_000_000 * PRICE_PER_1M_OUTPUT_TOKENS
    )
    print(
        f"    [uso] entrada={prompt_tokens} tok | saída={cand_tokens} tok | "
        f"total={total_tokens} tok | custo estimado ~${est_cost:.4f}"
    )


def save_image_parts(response, out_path):
    """Percorre as parts da resposta, salva a primeira imagem e imprime textos."""
    candidates = getattr(response, "candidates", None)
    if not candidates:
        # Pode ter sido bloqueado por safety/prompt feedback.
        fb = getattr(response, "prompt_feedback", None)
        raise RuntimeError(f"Resposta sem candidates. prompt_feedback={fb}")

    saved = False
    for part in candidates[0].content.parts:
        # Texto explicativo eventual do modelo
        if getattr(part, "text", None):
            print(f"    [modelo] {part.text.strip()[:200]}")
        # Dados de imagem inline
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "data", None):
            ext = mimetypes.guess_extension(inline.mime_type or "image/jpeg") or ".jpg"
            # Forçamos .jpg conforme pedido, independente do mime retornado.
            with open(out_path, "wb") as f:
                f.write(inline.data)
            print(f"    [ok] imagem salva em {out_path} ({len(inline.data)} bytes, "
                  f"mime={inline.mime_type})")
            saved = True
    if not saved:
        raise RuntimeError("Nenhuma imagem encontrada na resposta do modelo.")


def main():
    # 1) Diretório das fotos
    photos_dir = (
        sys.argv[1] if len(sys.argv) > 1
        else os.environ.get("PHOTOS_DIR", DEFAULT_PHOTOS_DIR)
    )
    if not os.path.isdir(photos_dir):
        print(f"ERRO: diretório das fotos não encontrado: {photos_dir}", file=sys.stderr)
        print("Passe o caminho como argumento ou defina PHOTOS_DIR.", file=sys.stderr)
        sys.exit(1)

    # 2) Chave da API
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERRO: defina a variável de ambiente GEMINI_API_KEY.", file=sys.stderr)
        sys.exit(1)

    # Imports tardios para dar mensagens de erro claras caso a lib falte.
    try:
        from google import genai
        from PIL import Image
    except ImportError as e:
        print(f"ERRO de dependência: {e}\nInstale com: pip install google-genai Pillow",
              file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    print(f"Diretório das fotos: {photos_dir}")
    print(f"Modelo: {MODEL}\n")

    ok, fail = 0, 0
    for room in ROOMS:
        print(f"== {room} ==")
        src = find_source_image(photos_dir, room)
        if not src:
            print(f"    [pulado] foto de origem não encontrada para {room}.")
            fail += 1
            continue

        out_path = os.path.join(photos_dir, f"{room}_staged.jpg")
        prompt = BASE_PROMPT + ROOM_HINTS.get(room, "")

        try:
            image = Image.open(src)
            print(f"    [origem] {src} ({image.size[0]}x{image.size[1]})")
            response = client.models.generate_content(
                model=MODEL,
                contents=[prompt, image],
            )
            save_image_parts(response, out_path)
            report_usage(response)
            ok += 1
        except Exception as e:  # noqa: BLE001 - queremos continuar nas demais salas
            print(f"    [ERRO] falha ao processar {room}: {type(e).__name__}: {e}")
            fail += 1
        print()

    print(f"Concluído. Sucesso: {ok} | Falhas/puladas: {fail}")
    sys.exit(0 if fail == 0 else 2)


if __name__ == "__main__":
    main()
