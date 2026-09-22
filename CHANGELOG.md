# Changelog

## Unreleased

- `quality-first` ve deneysel `balanced` trajectory profilleri.
- Luna-first çalışma; dispatch, Git diff, yeni dosya ve verifier kanıtından seçici Sol
  escalation.
- Açık process/verifier/no-diff hatasında gereksiz Jev çağrısını atlama.
- Güçlü düzeltme turuna sınırlı stderr, verifier çıktısı, changed-files ve reason-code
  aktarımı.
- Hassas path'leri receipt'ten çıkaran, secret/destructive değişiklikte fail-closed
  progress gate.
- Generated cache ve binary non-source artefaktlarını scope/diff evidence'ından çıkarma.
- Tur başına replay edilebilir progress/evidence-gate/review-called receipt'i.
- Resmî SWE-bench adaptöründe `balanced-trajectory` deney kolu ve trajectory ölçümleri.
- İlk iki-görev resmî test: final 2/2 resolved, fakat doğru Luna patch'lerinde 2/2
  gereksiz Sol escalation; judge kalibrasyonu sonraki darboğaz olarak kaydedildi.

## v0.0.1 — 2026-09-22

İlk dondurulmuş benchmark referansı.

- Jev prompt router, Luna/Sol OpenRouter worker'ları ve resmî LiveCodeBench checker'ı.
- 100 dev + 100 kilitli testte V0.01 quality-first politikası.
- Birleşik sonuç: router ve always-Sol 193/200; router maliyeti %12,90 daha düşük.
- Maliyet, provider usage, latency, hata receipt'i ve paired kalite raporlaması.
- Yerel Codex dispatch, Git evidence, Jev code judge ve resmî coding benchmark adaptörleri.
- Bilinen sınır: held-out router süresi always-Sol'dan daha yüksek; repository düzeyi
  trajectory-aware kazanç henüz ölçülmedi.
