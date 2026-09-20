# 2.375 resmi görevde Jev yönlendirme sonucu

Bu koşu dört kilitli resmi setin tamamında yalnızca yönlendirmeyi ölçer. Görev
metinleri Jev/OpenRouter'a gönderildi; işçi model cevapları bu tabloda sayılmaz.
Codex çözümleri ve resmi evaluator sonuçları ayrı raporlanır.

| Set | Görev | Luna | Terra | Sol | Astra | Jev maliyeti |
|---|---:|---:|---:|---:|---:|---:|
| LiveCodeBench release_v6 | 1.055 | 734 | 186 | 135 | 0 | $0,057841 |
| SWE-bench Verified | 500 | 76 | 334 | 38 | 52 | $0,027945 |
| SWE-bench Pro public | 731 | 20 | 264 | 344 | 103 | $0,033956 |
| Terminal-Bench 2 | 89 | 18 | 13 | 51 | 7 | $0,003961 |
| **Toplam** | **2.375** | **848** | **797** | **568** | **162** | **$0,123703** |

Toplam dağılım yaklaşık Luna `%35,7`, Terra `%33,6`, Sol `%23,9` ve Astra
`%6,8` oldu. Ortalama yönlendirme gecikmesi `480,54 ms`, medyan `455,22 ms`,
p95 `676,02 ms` idi. 2.375 çağrının hiçbirinde ağ/provider fallback'i olmadı.

## Bulduğumuz önemli sorun

İlk LiveCodeBench koşusunda kelime tabanlı kritik-domain kuralı, restoran
problemindeki “payment” ve interaktif algoritmadaki “secretly” kelimelerini gerçek
ödeme/secret riski sandı ve iki görevi gereksiz yere Astra'ya çıkardı. İzole algoritma
görevlerinde bu kural kapatıldı ve 1.055 görevin tamamı yeniden yönlendirildi.

Aynı 1.055 görevde iki bağımsız Jev koşusunun nihai tier anlaşması `%88,15`, ham
Jev seçimi anlaşması `%90,43` oldu. Yani router tamamen kararlı değil; özellikle
Luna/Terra ve Terra/Sol sınırındaki görevler koşular arasında değişebiliyor. Bu,
kalibrasyon gerektiren gerçek bir eksikliktir ve başarı sonucu gibi gizlenmemelidir.

Bu rapor “2.375 görev doğru çözüldü” anlamına gelmez. Yalnızca 2.375 geçerli,
oracle-sız yönlendirme kararı üretildiğini gösterir. Çözüm kalitesi yalnızca resmi
test harness'larının sonuçlarıyla ölçülür.
