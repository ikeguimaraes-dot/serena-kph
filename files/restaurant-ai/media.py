"""
Mídia inbound: download do Twilio + upload para Supabase Storage.

Bucket privado (entrada): serena-midia-entrada  → fotos/docs que clientes mandam
Bucket público  (saída) : serena-midia-saida    → reservado para ETAPA 3 (envio da IA)

Best-effort: toda função pode levantar exceção — o caller decide se loga e ignora.
"""
import os, mimetypes
import httpx
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
BUCKET_ENTRADA = "serena-midia-entrada"
BUCKET_SAIDA  = "serena-midia-saida"


def get_public_url(storage_path: str) -> str:
    """Monta URL pública de objeto no bucket de saída."""
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET_SAIDA}/{storage_path}"


def _service_key() -> str:
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL não configurada")
    k = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not k:
        raise RuntimeError("SUPABASE_SERVICE_KEY não configurada — adicionar no Railway")
    return k


async def download_twilio_media(url: str) -> tuple[bytes, str]:
    """Baixa mídia do Twilio com Basic Auth. Retorna (bytes, content_type)."""
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, auth=(sid, token), timeout=30, follow_redirects=True)
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
        return resp.content, ct


async def upload_private(
    data: bytes,
    content_type: str,
    restaurant_id: str,
    user_phone: str,
) -> str:
    """Upload para bucket privado. Retorna URL de storage (não URL pública)."""
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    ext = mimetypes.guess_extension(content_type) or ""
    safe_phone = user_phone.lstrip("+").replace(" ", "")
    path = f"{restaurant_id}/{safe_phone}/{ts}{ext}"
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET_ENTRADA}/{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            upload_url,
            content=data,
            headers={
                "Authorization": f"Bearer {_service_key()}",
                "Content-Type": content_type,
                "x-upsert": "false",
            },
            timeout=30,
        )
        resp.raise_for_status()
    return f"{SUPABASE_URL}/storage/v1/object/{BUCKET_ENTRADA}/{path}"


async def get_signed_url(storage_url: str, expires_in: int = 3600) -> str:
    """Gera URL assinada para objeto do bucket privado (uso pelo painel/closer)."""
    path = storage_url.split(f"/storage/v1/object/{BUCKET_ENTRADA}/", 1)[-1]
    sign_url = f"{SUPABASE_URL}/storage/v1/object/sign/{BUCKET_ENTRADA}/{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            sign_url,
            json={"expiresIn": expires_in},
            headers={"Authorization": f"Bearer {_service_key()}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    signed = data.get("signedURL") or data.get("signedUrl", "")
    if signed.startswith("/"):
        return f"{SUPABASE_URL}{signed}"
    return signed


def describe_media(content_type: str) -> str:
    """Gera descrição legível para injetar no contexto do agente."""
    if content_type.startswith("image/"):
        return "[Imagem recebida]"
    if content_type == "application/pdf":
        return "[Documento PDF recebido]"
    if content_type.startswith("audio/"):
        return "[Áudio recebido]"
    if content_type.startswith("video/"):
        return "[Vídeo recebido]"
    return f"[Arquivo recebido: {content_type}]"
