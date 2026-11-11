import os
import sys

from dotenv import load_dotenv
from langfuse import get_client

load_dotenv(os.path.join(os.getcwd(), ".env"))

REQUIRED = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
missing = [k for k in REQUIRED if not os.getenv(k)]
if missing:
    sys.exit(f"Eksik değişken(ler): {', '.join(missing)}")

host = os.environ["LANGFUSE_HOST"].rstrip("/")
os.environ.setdefault("LANGFUSE_BASE_URL", host)  # yeni SDK bu adı okuyor
print("Host:", host)
public_prefix = os.environ["LANGFUSE_PUBLIC_KEY"][:6]
secret_prefix = os.environ["LANGFUSE_SECRET_KEY"][:6]
print("Anahtar önekleri:", public_prefix, secret_prefix)

langfuse = get_client()
try:
    ok = langfuse.auth_check()
except Exception as e:  # noqa: BLE001 - betik her hatayı raporlamalı
    sys.exit(f"auth_check HATA: {type(e).__name__}")
print("auth_check:", "OK" if ok else "BAŞARISIZ")

with langfuse.start_as_current_observation(as_type="span", name="setup-check") as span:
    span.update(
        input="SENTETIK: bağlantı testi sorusu",
        output="SENTETIK: bağlantı testi yanıtı",
    )
langfuse.flush()
print("Deneme trace'i gönderildi. Langfuse > Tracing sayfasında 'setup-check' ara.")
