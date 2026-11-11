import os
import sys

import cohere
from dotenv import load_dotenv

load_dotenv(os.path.join(os.getcwd(), ".env"))
api_key = os.getenv("COHERE_API_KEY")
if not api_key:
    sys.exit("COHERE_API_KEY .env içinde yok")
print(f"COHERE_API_KEY bulundu (uzunluk={len(api_key)})")

model = sys.argv[1] if len(sys.argv) > 1 else "rerank-v5.0-pro"
# SENTETIK: gerçek yönetmelik metni değil
query = "Staj başvurusu için hangi belgeler gerekir?"
documents = [
    "Sınav tarihleri akademik takvimde ilan edilir.",
    "Staj başvurusu için başvuru formu ve sigorta evrakları teslim edilir.",
    "Kütüphane hafta içi 09:00-18:00 arasında açıktır.",
]

co = cohere.ClientV2(api_key=api_key)
try:
    response = co.rerank(model=model, query=query, documents=documents, top_n=3)
except Exception as e:  # noqa: BLE001 - betik her hatayı raporlamalı
    sys.exit(f"rerank HATA ({model}): {type(e).__name__}")

best = response.results[0]
score = f"{best.relevance_score:.3f}"
print(f"rerank OK ({model}): en üstteki belge indeksi={best.index}, skor={score}")
print("Beklenen indeks: 1")
