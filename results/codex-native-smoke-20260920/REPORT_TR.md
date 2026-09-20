# Codex-native dispatcher smoke testi

Tarih: 2026-09-20

Aynı salt-okunur görev, yerel `codex exec --json` ve mevcut Codex oturum kimliği üzerinden Luna ve Sol'e gönderildi. Görev yalnız README içindeki belirli bir başlığı doğruladı; kalite benchmarkı değil, dispatcher ve receipt ölçümünün entegrasyon testidir.

| Model | Sonuç | Duvar saati | Input | Cached input | Output | Reasoning output |
|---|---|---:|---:|---:|---:|---:|
| `gpt-5.6-luna` medium | `ROUTER_SMOKE_OK` | 12.65 s | 30,817 | 24,064 | 140 | 21 |
| `gpt-5.6-sol` high | `ROUTER_SMOKE_OK` | 15.87 s | 52,699 | 43,136 | 265 | 75 |

İki model de doğru cevap verdi. Bu tek ve kolay görevde Luna yaklaşık 3.22 saniye daha hızlıydı ve daha az token tüketti. Tek örnek olduğundan genellenebilir kalite veya hız üstünlüğü çıkarılamaz.

Bu koşular OpenRouter chat-completions çağrısı değildir. Yerel Codex CLI, kullanıcının mevcut Codex oturumu/kullanım hakkıyla çalıştı; bu nedenle API USD maliyeti hesaplanmadı. Jev de bu iki forced-baseline smoke çağrısında kullanılmadı.

Codex başlangıcında kullanıcının bazı MCP/plugin bağlantılarından uyarılar geldi, fakat iki işlem de `returncode=0` ile tamamlandı. Ham stderr; yerel yapılandırma ayrıntıları içerebildiği için açık kaynak artefaktına eklenmedi.
