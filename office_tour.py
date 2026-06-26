#!/usr/bin/env python3
"""
Gera um VÍDEO-TOUR do andar corporativo a partir das salas já tratadas com
virtual staging (salaX_staged.jpg).

Para cada sala, usa o modelo de vídeo Veo (mesma API/chave do Gemini) em modo
image-to-video, criando um clipe curto com um movimento de câmera cinematográfico
que PRESERVA o ambiente da imagem (só "passeia" por ele). Depois concatena todos
os clipes num único arquivo office_tour.mp4.

Fluxo:
    imagem com staging  --Veo image-to-video-->  salaX_clip.mp4
    [sala5_clip, sala6_clip, sala8_clip]  --ffmpeg concat-->  office_tour.mp4

Uso:
    export GEMINI_API_KEY="sua-chave"
    python3 office_tour.py [diretorio_das_fotos]

Dependências:
    pip install google-genai Pillow imageio-ffmpeg
(o ffmpeg vem do pacote imageio-ffmpeg; não precisa instalar ffmpeg no sistema)

Observações importantes sobre o Veo:
    - A geração é uma operação assíncrona (long-running). O script faz polling.
    - Cada chamada gera um clipe de poucos segundos (5-8s, depende do modelo).
    - person_generation pode ser restrito por região/política; ajuste se necessário.
"""

import os
import sys
import glob
import time
import subprocess

DEFAULT_PHOTOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fotos")

# Modelo de vídeo. Alternativas comuns: "veo-3.0-fast-generate-001",
# "veo-2.0-generate-001". Veo 3 também gera áudio.
VIDEO_MODEL = os.environ.get("VEO_MODEL", "veo-3.0-generate-001")

# Movimento de câmera padrão. Sempre "passeia" pelo ambiente existente.
DEFAULT_MOTION = (
    "Slow cinematic dolly/pan through this modern corporate office space, smooth "
    "steady gimbal motion, gently revealing the furniture and the people working."
)

# Ajuste fino do movimento por tipo de sala (palavra-chave no nome do arquivo).
MOTION_HINTS = {
    "boardroom": "Slow cinematic pan across this executive boardroom, revealing "
                 "the meeting table and the executives in a meeting.",
    "meeting": "Slow cinematic pan across this meeting room, revealing the "
               "conference table and people in discussion.",
    "open": "Slow cinematic dolly forward through this open-plan workspace, "
            "revealing the desks and people working.",
    "private": "Slow cinematic dolly into this private office, revealing the "
               "desk and the person working.",
}

MOTION_SUFFIX = (
    " Keep the existing architecture, walls, windows and the view through the "
    "windows unchanged. Photorealistic, consistent lighting. No text overlays."
)


def motion_for(stem):
    low = stem.lower()
    for kw, m in MOTION_HINTS.items():
        if kw in low:
            return m
    return DEFAULT_MOTION


def discover_staged(photos_dir):
    """Prefere os *_staged.jpg; se não houver nenhum, usa as imagens originais."""
    staged = sorted(glob.glob(os.path.join(photos_dir, "*_staged.jpg")))
    if staged:
        return staged
    out = []
    for ext in ("jpg", "jpeg", "png", "webp"):
        for p in glob.glob(os.path.join(photos_dir, f"*.{ext}")):
            low = os.path.basename(p).lower()
            if "_clip" in low:
                continue
            out.append(p)
    return sorted(set(out))

POLL_SECONDS = 10
POLL_TIMEOUT = 600  # 10 min por clipe


def ffmpeg_exe():
    """ffmpeg do sistema, ou o portátil do pacote imageio-ffmpeg."""
    from shutil import which
    if which("ffmpeg"):
        return "ffmpeg"
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def generate_clip(client, types, src_image_path, out_path, prompt):
    """Gera um clipe image-to-video com o Veo e salva em out_path."""
    with open(src_image_path, "rb") as f:
        img_bytes = f.read()
    mime = "image/png" if src_image_path.lower().endswith(".png") else "image/jpeg"

    operation = client.models.generate_videos(
        model=VIDEO_MODEL,
        prompt=prompt,
        image=types.Image(image_bytes=img_bytes, mime_type=mime),
        config=types.GenerateVideosConfig(
            aspect_ratio="16:9",
            number_of_videos=1,
        ),
    )

    # Polling da operação assíncrona.
    waited = 0
    while not operation.done:
        if waited >= POLL_TIMEOUT:
            raise TimeoutError(f"Veo não concluiu em {POLL_TIMEOUT}s.")
        time.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
        operation = client.operations.get(operation)
        print(f"    ... gerando vídeo ({waited}s)")

    response = getattr(operation, "response", None) or getattr(operation, "result", None)
    videos = getattr(response, "generated_videos", None) if response else None
    if not videos:
        raise RuntimeError(f"Operação sem vídeo. error={getattr(operation,'error',None)}")

    video = videos[0].video
    # Garante os bytes localmente e salva.
    client.files.download(file=video)
    video.save(out_path)
    size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
    print(f"    [ok] clipe salvo: {out_path} ({size} bytes)")
    return out_path


def concat_clips(ff, clip_paths, out_path):
    """Concatena os clipes num único mp4 via ffmpeg (concat demuxer)."""
    list_file = out_path + ".concat.txt"
    with open(list_file, "w") as f:
        for p in clip_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")
    cmd = [
        ff, "-y", "-f", "concat", "-safe", "0", "-i", list_file,
        "-c", "copy", out_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Fallback: re-encode (caso os clipes tenham parâmetros diferentes)
        cmd = [
            ff, "-y", "-f", "concat", "-safe", "0", "-i", list_file,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", out_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        os.remove(list_file)
    except OSError:
        pass
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg concat falhou:\n{proc.stderr[-800:]}")
    return out_path


def main():
    photos_dir = (
        sys.argv[1] if len(sys.argv) > 1
        else os.environ.get("PHOTOS_DIR", DEFAULT_PHOTOS_DIR)
    )
    if not os.path.isdir(photos_dir):
        print(f"ERRO: diretório das fotos não encontrado: {photos_dir}", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERRO: defina a variável de ambiente GEMINI_API_KEY.", file=sys.stderr)
        sys.exit(1)

    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        print(f"ERRO de dependência: {e}\nInstale: pip install google-genai Pillow imageio-ffmpeg",
              file=sys.stderr)
        sys.exit(1)

    ff = ffmpeg_exe()
    if not ff:
        print("AVISO: ffmpeg indisponível — os clipes serão gerados, mas não "
              "serão concatenados no tour final.", file=sys.stderr)

    sources = discover_staged(photos_dir)
    if not sources:
        print(f"Nenhuma imagem encontrada em {photos_dir} (rode antes o "
              f"virtual_staging.py para gerar os *_staged.jpg).", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    print(f"Diretório: {photos_dir}\nModelo de vídeo: {VIDEO_MODEL}\n"
          f"Clipes a gerar: {len(sources)}\n")

    clips, fail = [], 0
    for src in sources:
        stem = os.path.splitext(os.path.basename(src))[0].replace("_staged", "")
        print(f"== {stem} ==")
        out_clip = os.path.join(photos_dir, f"{stem}_clip.mp4")
        prompt = motion_for(stem) + MOTION_SUFFIX
        print(f"    [origem] {src}")
        try:
            generate_clip(client, types, src, out_clip, prompt)
            clips.append(out_clip)
        except Exception as e:  # noqa: BLE001
            print(f"    [ERRO] falha no clipe de {room}: {type(e).__name__}: {e}")
            fail += 1
        print()

    # Monta o tour final
    if clips and ff:
        tour_path = os.path.join(photos_dir, "office_tour.mp4")
        try:
            concat_clips(ff, clips, tour_path)
            print(f"TOUR PRONTO: {tour_path} (a partir de {len(clips)} clipe(s))")
        except Exception as e:  # noqa: BLE001
            print(f"[ERRO] não foi possível concatenar o tour: {e}")
            print(f"Clipes individuais disponíveis: {clips}")
            fail += 1
    elif clips:
        print(f"Clipes gerados (sem concatenar, ffmpeg ausente): {clips}")
    else:
        print("Nenhum clipe gerado.")

    sys.exit(0 if fail == 0 and clips else 2)


if __name__ == "__main__":
    main()
