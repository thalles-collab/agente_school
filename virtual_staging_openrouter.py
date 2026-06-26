#!/usr/bin/env python3
"""
Virtual staging via OpenRouter (acesso ao modelo de imagem do Gemini por uma API
compatível com OpenAI), para quem tem uma chave `sk-or-...` em vez de uma chave
`AIza...` do Google.

IMPORTANTE: rode este script na SUA máquina. Em alguns ambientes gerenciados o
host openrouter.ai é bloqueado pela política de rede e o script não conecta.

Direção (a mesma do virtual_staging.py):
  - Preservar a estrutura real (paredes, janelas, teto, piso, vista da janela).
  - Re-mobiliar com mobília corporativa moderna.
  - Adicionar 2-3 profissionais trabalhando.
  - Remover marca-d'água/logo e textos sobrepostos.

Uso:
    export OPENROUTER_API_KEY="sk-or-..."
    python3 virtual_staging_openrouter.py [diretorio_das_fotos]   # padrão: ./fotos

Não precisa da google-genai aqui; usa apenas requests + Pillow.
"""

import os
import sys
import glob
import json
import base64

DEFAULT_PHOTOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fotos")
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# Modelo de imagem do Gemini no OpenRouter. Se este id não existir mais, liste os
# modelos em https://openrouter.ai/models e ajuste (procure por "flash-image").
MODEL = os.environ.get("OPENROUTER_IMAGE_MODEL", "google/gemini-2.5-flash-image")

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

TYPE_HINTS = {
    "boardroom": " Modern executive boardroom with executives in a meeting.",
    "meeting": " Modern meeting room with 2-3 professionals in discussion.",
    "conf": " Modern conference/training room with people attending.",
    "auditorio": " Modern conference/training room with tiered seating and an audience.",
    "open": " Modern open-plan workspace with people working at sleek desks.",
    "desks": " Modern open-plan workspace with people working at sleek desks.",
    "cubicles": " Modern open-plan workstations with people working.",
    "private": " Modern private office with one or two people working.",
}


def hint_for(stem):
    low = stem.lower()
    for kw, h in TYPE_HINTS.items():
        if kw in low:
            return h
    return ""


def discover_images(photos_dir):
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


def data_url(path):
    mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def extract_image_bytes(message):
    """OpenRouter devolve imagens em message['images'] como data URLs."""
    for img in message.get("images") or []:
        url = (img.get("image_url") or {}).get("url") or img.get("url")
        if url and url.startswith("data:") and "base64," in url:
            return base64.b64decode(url.split("base64,", 1)[1])
    # fallback: alguns modelos devolvem em content como lista de parts
    content = message.get("content")
    if isinstance(content, list):
        for part in content:
            url = (part.get("image_url") or {}).get("url", "") if isinstance(part, dict) else ""
            if url.startswith("data:") and "base64," in url:
                return base64.b64decode(url.split("base64,", 1)[1])
    return None


def main():
    photos_dir = (
        sys.argv[1] if len(sys.argv) > 1
        else os.environ.get("PHOTOS_DIR", DEFAULT_PHOTOS_DIR)
    )
    if not os.path.isdir(photos_dir):
        print(f"ERRO: diretório não encontrado: {photos_dir}", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERRO: defina OPENROUTER_API_KEY (sk-or-...).", file=sys.stderr)
        sys.exit(1)

    try:
        import requests
    except ImportError:
        print("ERRO: pip install requests", file=sys.stderr)
        sys.exit(1)

    images = discover_images(photos_dir)
    if not images:
        print(f"Nenhuma imagem em {photos_dir}.", file=sys.stderr)
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    print(f"Diretório: {photos_dir}\nModelo: {MODEL}\nImagens: {len(images)}\n")

    ok, fail = 0, 0
    for src in images:
        stem = os.path.splitext(os.path.basename(src))[0]
        print(f"== {stem} ==")
        out_path = os.path.join(photos_dir, f"{stem}_staged.jpg")
        prompt = BASE_PROMPT + hint_for(stem)
        payload = {
            "model": MODEL,
            "modalities": ["image", "text"],
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url(src)}},
                ],
            }],
        }
        try:
            resp = requests.post(ENDPOINT, headers=headers, json=payload, timeout=180)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            usage = data.get("usage")
            msg = data["choices"][0]["message"]
            img_bytes = extract_image_bytes(msg)
            if not img_bytes:
                txt = msg.get("content")
                raise RuntimeError(f"Resposta sem imagem. content={str(txt)[:200]}")
            with open(out_path, "wb") as f:
                f.write(img_bytes)
            print(f"    [ok] {out_path} ({len(img_bytes)} bytes)")
            if usage:
                print(f"    [uso] {json.dumps(usage)}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"    [ERRO] {stem}: {type(e).__name__}: {e}")
            fail += 1
        print()

    print(f"Concluído. Sucesso: {ok} | Falhas: {fail}")
    sys.exit(0 if ok and not fail else 2)


if __name__ == "__main__":
    main()
