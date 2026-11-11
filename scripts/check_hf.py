import os
import sys

from dotenv import load_dotenv
from huggingface_hub import HfApi, hf_hub_download

load_dotenv(os.path.join(os.getcwd(), ".env"))
token = os.getenv("HF_TOKEN")
if not token:
    sys.exit("HF_TOKEN .env içinde yok")
print(f"HF_TOKEN bulundu (uzunluk={len(token)}, önek={token[:3]})")

api = HfApi(token=token)
print("Kullanıcı:", api.whoami()["name"])

repo = sys.argv[1] if len(sys.argv) > 1 else None
checks = {
    "açık model (bge-m3)": lambda: hf_hub_download("BAAI/bge-m3", "config.json", token=token),
    "gated model (EmbeddingGemma)": lambda: hf_hub_download(
        "google/embeddinggemma-300m", "config.json", token=token
    ),
}
if repo:
    repo_id: str = repo
    checks["özel dataset okuma"] = lambda: api.dataset_info(repo_id)
    if "--write" in sys.argv:
        checks["özel dataset yazma"] = lambda: api.upload_file(
            path_or_fileobj=b'{"ping": 1}',
            path_in_repo="healthcheck.json",
            repo_id=repo_id,
            repo_type="dataset",
        )

for name, fn in checks.items():
    try:
        fn()
    except Exception as e:  # noqa: BLE001 - betik her hatayı raporlamalı
        print("HATA:", name, "->", type(e).__name__)
    else:
        print("OK  :", name)
