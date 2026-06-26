#!/usr/bin/env python3
"""
Virtual staging de um andar corporativo usando a API do Google Gemini 2.5 Flash
Image (Nano Banana).

Direção (definida com o cliente):
  - PRESERVAR a estrutura real: paredes, janelas, teto, piso, colunas, divisórias
    de vidro e a vista pela janela.
  - RE-MOBILIAR: substituir os móveis existentes por mobília corporativa moderna
    adequada ao espaço.
  - ADICIONAR 2-3 profissionais trabalhando/em reunião de forma natural.
  - REMOVER marca-d'água/logo e textos sobrepostos presentes na foto.

O script descobre automaticamente todas as imagens do diretório (ignorando as
geradas *_staged.* e *_clip.*) e gera <nome>_staged.jpg para cada uma. O prompt
é adaptado por tipo de sala a partir de palavras-chave no nome do arquivo.

Uso:
    export GEMINI_API_KEY="sua-chave"
    python3 virtual_staging.py [diretorio_das_fotos]   # padrão: ./fotos
"""

import os
import sys
import glob

DEFAULT_PHOTOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fotos")

MODEL = "gemini-2.5-flash-image"

# Preço de referência da saída de imagem (estimativa de custo a partir do usage).
PRICE_PER_1M_OUTPUT_TOKENS = 30.0
PRICE_PER_1M_INPUT_TOKENS = 0.30

# Instrução comum a todas as salas.
BASE_PROMPT = (
    "Edit this real corporate office photo. Keep the exact room structure "
    "unchanged: walls, windows, ceiling, flooring, columns, glass partitions and "
    "the view through the windows. Replace the existing furniture with realistic, "
    "modern corporate furniture appropriate to the space, and add 2-3 "
    "professionals working naturally. Remove any watermark, logo or text overlay "
    "present in the image (especially the 'FI.' logo and any caption). "
    "Photorealistic, matching the existing lighting and perspective. Do not alter "
    "the architecture or the window view."
)

# Ajuste fino por tipo de sala, escolhido por palavra-chave no nome do arquivo.
TYPE_HINTS = {
    "boardroom": " Modern executive boardroom: refined long meeting table and "
                 "ergonomic chairs, a few executives in a meeting.",
    "meeting": " Modern meeting room: clean conference table and ergonomic chairs, "
               "2-3 professionals in discussion.",
    "conf": " Modern conference/training room: updated table and seating, people "
            "attending and presenting.",
    "auditorio": " Modern conference/training room with tiered seating, an "
                 "audience attending a presentation.",
    "open": " Modern open-plan workspace: sleek desks, ergonomic chairs, monitors "
            "and laptops, people working and collaborating.",
    "desks": " Modern open-plan workspace with people working at sleek desks.",
    "cubicles": " Modern open-plan workstations with low partitions and people "
                "working at their desks.",
    "private": " Modern private office: a contemporary desk setup with one or two "
               "people working.",
}


def hint_for(stem):
    low = stem.lower()
    for kw, hint in TYPE_HINTS.items():
        if kw in low:
            return hint
    return ""


def discover_images(photos_dir):
    """Todas as imagens do diretório, exceto as geradas (*_staged, *_clip)."""
    out = []
    for ext in ("jpg", "jpeg", "png", "webp"):
        out += glob.glob(os.path.join(photos_dir, f"*.{ext}"))
        out += glob.glob(os.path.join(photos_dir, f"*.{ext.upper()}"))
    res = []
    for p in sorted(set(out)):
        low = os.path.basename(p).lower()
        if "_staged" in low or "_clip" in low:
            continue
        res.append(p)
    return res


def report_usage(response):
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        print("    [uso] API não retornou usage_metadata.")
        return
    pt = getattr(usage, "prompt_token_count", 0) or 0
    ct = getattr(usage, "candidates_token_count", 0) or 0
    tt = getattr(usage, "total_token_count", 0) or 0
    est = pt / 1e6 * PRICE_PER_1M_INPUT_TOKENS + ct / 1e6 * PRICE_PER_1M_OUTPUT_TOKENS
    print(f"    [uso] entrada={pt} | saída={ct} | total={tt} tok | "
          f"custo estimado ~${est:.4f}")


def save_image_parts(response, out_path):
    candidates = getattr(response, "candidates", None)
    if not candidates:
        fb = getattr(response, "prompt_feedback", None)
        raise RuntimeError(f"Resposta sem candidates. prompt_feedback={fb}")
    saved = False
    for part in candidates[0].content.parts:
        if getattr(part, "text", None):
            print(f"    [modelo] {part.text.strip()[:200]}")
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "data", None):
            with open(out_path, "wb") as f:
                f.write(inline.data)
            print(f"    [ok] {out_path} ({len(inline.data)} bytes, {inline.mime_type})")
            saved = True
    if not saved:
        raise RuntimeError("Nenhuma imagem na resposta do modelo.")


def main():
    photos_dir = (
        sys.argv[1] if len(sys.argv) > 1
        else os.environ.get("PHOTOS_DIR", DEFAULT_PHOTOS_DIR)
    )
    if not os.path.isdir(photos_dir):
        print(f"ERRO: diretório não encontrado: {photos_dir}", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERRO: defina GEMINI_API_KEY.", file=sys.stderr)
        sys.exit(1)

    try:
        from google import genai
        from PIL import Image
    except ImportError as e:
        print(f"ERRO de dependência: {e}\nInstale: pip install google-genai Pillow",
              file=sys.stderr)
        sys.exit(1)

    images = discover_images(photos_dir)
    if not images:
        print(f"Nenhuma imagem encontrada em {photos_dir}.", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    print(f"Diretório: {photos_dir}\nModelo: {MODEL}\nImagens: {len(images)}\n")

    ok, fail = 0, 0
    for src in images:
        stem = os.path.splitext(os.path.basename(src))[0]
        print(f"== {stem} ==")
        out_path = os.path.join(photos_dir, f"{stem}_staged.jpg")
        prompt = BASE_PROMPT + hint_for(stem)
        try:
            image = Image.open(src)
            print(f"    [origem] {src} ({image.size[0]}x{image.size[1]})")
            response = client.models.generate_content(
                model=MODEL, contents=[prompt, image],
            )
            save_image_parts(response, out_path)
            report_usage(response)
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"    [ERRO] {stem}: {type(e).__name__}: {e}")
            fail += 1
        print()

    print(f"Concluído. Sucesso: {ok} | Falhas: {fail}")
    sys.exit(0 if ok and not fail else 2)


if __name__ == "__main__":
    main()
