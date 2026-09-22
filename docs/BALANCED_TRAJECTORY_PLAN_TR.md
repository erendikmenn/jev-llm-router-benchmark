# Balanced trajectory router — uygulama ve benchmark planı

Durum: ilk çalışan iskelet ve fixture doğrulaması tamam; canlı held-out ölçüm bekliyor

Tarih: 2026-09-22

## Uygulama durumu

- [x] V0.01 baseline ve `v0.0.1` etiketi donduruldu.
- [x] `ProgressSnapshot`, deterministik evidence gate ve hassas-path fail-closed davranışı eklendi.
- [x] CLI'da `quality-first` ve `balanced` profil seçimi eklendi.
- [x] Balanced profilde Luna verifier/no-diff/dispatch hatasından doğrudan Sol'a geçiş eklendi.
- [x] Hata ve progress özeti güçlü düzeltme promptuna eklendi.
- [x] Accept, verifier failure, spinning, untracked file, high-stakes ve destructive yollar fixture testlerinde doğrulandı.
- [x] Tek gerçek Codex + Jev smoke'unda Luna-only kabul yolu doğrulandı; generated-file evidence gürültüsü bulunup düzeltildi.
- [ ] Mevcut gerçek receipt'ler için shadow/replay skorlayıcı.
- [ ] Dev'de dondurulmuş balanced eşikleri ve yeni paired held-out kampanya.
- [ ] SWE-bench/Terminal-Bench repository düzeyi kalite-maliyet raporu.

## Hedef

Yeni politika görevin zorluğunu yalnız ilk prompttan tahmin etmeye çalışmayacak. Düşük
riskli kod görevinde Luna önce bir gerçek çalışma turu yapacak; sistem oluşan diff'i,
değişen dosyaları, test/lint/typecheck sonuçlarını, process hatasını ve modelin son
çıktısını görecek. Sol yalnız bu kanıtlarda sorun varsa devreye girecek.

```text
görev
  │
  ├─ kritik hard guard ───────────────────────────────> Sol / Astra
  │
  └─ Luna çalışma turu
        │
        ├─ process başarısız / hiç diff yok / verifier kaldı
        │       └─ gereksiz Jev çağrısını atla ───────> Sol düzeltme turu
        │
        └─ makul bir değişiklik + verifier geçti
                └─ Jev: task + diff + code + evidence
                      ├─ accept ──────────────────────> tamamla
                      ├─ revise / escalate ───────────> Sol düzeltme turu
                      └─ block ───────────────────────> durdur / insan incelemesi
```

Bu, “Luna doğru yaparsa Sol'a hiç gitme; yanlış veya eksik yaparsa Sol yalnız mevcut
sorunu düzeltsin” fikrinin yürütülebilir karşılığıdır.

## Profiller

| Özellik | `quality-first` | `balanced` |
|---|---|---|
| İlk model | Dondurulmuş task-router/hard guard seçimi | Hard guard yoksa Luna |
| Task öncesi Jev | Evet | Yalnız hard-risk/route kartı gerekiyorsa; normal görevde şart değil |
| Luna çalışma turu | Router Luna seçerse | Varsayılan olarak bir tam tur |
| Açık process/verifier hatasında Jev | Tanı için çağrılabilir | Çağrılmaz; kanıt doğrudan Sol'a gider |
| Luna sonrası semantik review | Evet | Yalnız değişiklik tamamlanabilir görünüyorsa evet |
| `revise` kararı | Aynı role bir düzeltme hakkı verilebilir | Sol'a yükselt |
| Ana amaç | Kalite kaybını en aza indir | En fazla 2 yp kalite kaybıyla %30–40 maliyet azaltmak |
| Varsayılan olma koşulu | V0.01 baseline | Yeni, kilitli benchmark kapılarını geçmek |

V0.01 davranışı `quality-first` olarak korunur. `balanced`, sonuç görmeden aynı sürümün
yerine geçirilmez.

## Her turda tutulacak kanıt

### Worker receipt'i

- model ve reasoning effort;
- process return code ve duvar saati;
- input/cached/output token sayıları;
- son agent mesajı;
- stderr ve hata satırı sayısı.

### Git ilerleme snapshot'ı

- değişen dosyalar;
- diff SHA-256 parmak izi;
- eklenen/silinen satır sayısı;
- diff boyutu;
- auth, payment, migration, secret veya destructive risk flag'leri;
- önceki turla aynı diff olup olmadığı.

### Verifier kanıtı

- çalıştırılan komut;
- return code, süre, stdout/stderr sonu;
- geçen/kalan komut sayısı;
- önceki turla aynı hata imzasının tekrar edip etmediği;
- testin agent tarafından bu turda yazılmış olmasının bağımsız kanıt sayılmadığı işareti.

### Jev review paketi

Jev yalnız temizlenmiş ve boyutu sınırlanmış görev, kabul kriteri, diff, ilgili kod ve
yukarıdaki receipt özetini görür. `.env`, credential/key dosyaları ve bilinen secret
biçimleri mevcut evidence katmanında dışlanır veya redakte edilir.

## Deterministik karar sırası

LLM kararı açık makine kanıtını geçersiz kılamaz. Sıra şöyledir:

1. Secret exposure veya destructive değişiklik varsa `block`.
2. Auth/payment/migration/security boundary varsa ucuz model kullanılmadan güçlü role git.
3. Worker process başarısızsa `escalate`.
4. Kod görevi başarılı process ile bittiği hâlde diff yoksa `escalate`.
5. Yapılandırılmış verifier kaldıysa `escalate`.
6. Aynı diff veya aynı hata tekrarlanıyorsa `spinning` say ve `escalate`.
7. Ancak bu kapılar geçerse Jev semantik yeterlilik ve regresyon riski hakkında karar versin.
8. Jev hatası, parse hatası, düşük güven veya review bütçe aşımı fail-safe olarak güçlü role gitsin.

Balanced profilinde Luna'dan sonra `revise` de bir sorun sinyalidir ve Sol'a yükselir.
Sol mevcut çalışma ağacını, görev/kabul kriterlerini, kalan verifier stderr'ini ve Jev
reason code'larını alır; geçerli Luna değişikliklerini silmesi istenmez.

## Durum makinesi

| Durum | Olay | Sonraki durum |
|---|---|---|
| `route` | kritik/high-stakes hard guard | `strong_work` |
| `route` | normal görev | `cheap_work` |
| `cheap_work` | dispatch/no-diff/verifier sorunu | `strong_work` |
| `cheap_work` | makul ilerleme | `semantic_review` |
| `semantic_review` | accept | `accepted` |
| `semantic_review` | revise/escalate/provider error | `strong_work` |
| `semantic_review` | block | `blocked` |
| `strong_work` | verifier + review accept | `accepted` |
| `strong_work` | tekrar başarısız, tur/tier var | `frontier_work` |
| `strong_work` | limit veya frontier bitti | `needs_human_review` |

Her geçiş receipt'e `reason_codes` ile yazılır. Yalnız son model değil, Luna'nın ne
yaptığı, neden kabul edilmediği ve Sol'un neyi düzelttiği sonradan replay edilebilir.

## Hız ve maliyet beklentisi

Balanced profil otomatik olarak daha hızlı değildir:

- başarılı görev: `Luna + yerel verifier + Jev`;
- yükselen görev: `Luna + verifier + Sol + verifier + Jev`.

İkinci yol always-Sol'dan doğal olarak daha yavaştır. Ortalama hız ancak Luna'da biten
görev oranı yüksekse ve task öncesi router/Jev çağrısı atlanırsa iyileşebilir. Bu nedenle
raporda worker süresi, verifier süresi, Jev süresi ve toplam p50/p95 ayrı gösterilir.
Maliyet de çağrı sayısından değil gerçek token/provider cost toplamından hesaplanır.

## Uygulama sırası

1. `v0.0.1` quality-first sonucunu README, changelog ve Git tag ile dondur.
2. Her tur için `ProgressSnapshot` ve gerekçe kodlu evidence gate ekle.
3. CLI'a `--profile quality-first|balanced` ekle; dry-run seçilecek ilk rolü göstersin.
4. Balanced profilde hard guard yoksa Luna ile başla; açık failure'da Jev'yi atlayıp Sol'a geç.
5. Luna receipt, verifier hatası ve Jev reason code'larını Sol düzeltme promptuna ekle.
6. Fixture replay testleriyle accept, no-diff, test failure, judge revise, critical block ve
   repeated failure yollarını deterministik doğrula.
7. Gerçek API harcamadan mevcut receipt'lerde shadow/replay raporu üret.
8. Eşikleri yalnız dev'de dondur; yeni paired held-out kampanyayı sonra çalıştır.

## Benchmark kolları

- always-Luna;
- always-Sol;
- V0.01 `quality-first` prompt router;
- `balanced` trajectory router;
- matched-random (aynı Sol oranı);
- oracle karşı-olgusu.

LiveCodeBench hızlı algoritmik kontrol içindir. Ürün iddiası için en az bir repository
benchmarkı gerekir: SWE-bench Verified/audit edilmiş Pro alt kümesi ve Terminal-Bench 2.
Router eşiği test split'i görülmeden dondurulur; aynı görevde bütün kolların sonucu
eşleştirilir.

## Başarı kapısı

Balanced profil ancak kilitli sette aşağıdaki koşulların tamamını sağlarsa varsayılan
adayı olur:

| Metrik | Kapı |
|---|---:|
| Resolved/pass@1 kaybı vs always-Sol | en fazla 2 yüzde puan |
| Gerçek/API-equivalent maliyet tasarrufu | en az %30 |
| Çözülen görev başına maliyet iyileşmesi | en az 1,5× |
| Kritik güvenlik/veri kaybı false-accept | 0 |
| p50 toplam süre | Sol'dan en fazla %10 kötü |
| Matched-random'a göre paired kalite farkı | pozitif; güven aralığı raporlanmış |
| Provider/parse hatası | sessiz accept yok; %100 fail-safe |

Kapılar geçilmezse V0.01 quality-first varsayılan kalır. Daha düşük maliyet uğruna
başarısız sonuç “başarı” diye sunulmaz.

## Tamamlanma tanımı

Bu yaklaşım yalnız kodu yazıldığında bitmiş sayılmaz. Tamamlanma için profil seçimi,
kanıt receipt'leri, replay testleri, dondurulmuş dev politikası, yeni held-out paired
koşu ve README'de V0.01 ile yan yana dürüst sonuç tablosu gerekir.

Araştırma dayanağı ve karşılaştırmalı ölçümler:
[`../exa-results/router-cascade-landscape-2026-09-22.md`](../exa-results/router-cascade-landscape-2026-09-22.md).
