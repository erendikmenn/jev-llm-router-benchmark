# Balanced trajectory — ilk fixture smoke

Tarih: 2026-09-22

## Sonuç

İlk çalışan iskelet başarılı: repository testlerinin 107/107'si geçti, paket wheel ve
sdist olarak üretildi. Yeni politikanın 11 testi profil seçimi, tracked/untracked/deleted
dosya ilerlemesi, verifier failure, spinning, high-stakes escalation, destructive block,
hassas path dışlama ve Luna→Sol düzeltme akışını kapsıyor.

İki CLI dry-run da beklendiği gibi çalıştı:

| Görev | Task-router çağrısı | İlk rol | Neden |
|---|---:|---|---|
| README cümlesi güncelle | hayır | Luna | `balanced_luna_first` |
| OAuth token validation değiştir | hayır | Astra | `critical_domain_to_astra` hard guard |

Fixture pipeline senaryosunda Luna yanlış içerik ürettiğinde yerel verifier kaldı.
Sistem Jev provider'ını çağırmadan `verifier_failed` reason code'uyla Sol'a geçti;
Sol doğru içeriği yazınca verifier ve Jev fixture review geçti ve iş kabul edildi.
Destructive migration senaryosu Jev çağrılmadan bloklandı.

## Ne anlama gelmiyor?

Bu bir model kalite benchmarkı değildir. Fixture worker/judge deterministiktir; Luna ve
Sol'a gerçek görev gönderilmedi, OpenRouter çağrısı yapılmadı ve harcama `$0` oldu.
Kanıtlanan şey akışın ve fail-safe kararların çalışmasıdır. V0.01'e göre kalite, maliyet
ve hız iyileşmesi ancak yeni paired held-out worker kampanyasından sonra söylenebilir.

Makine özeti: [`summary.json`](summary.json).
