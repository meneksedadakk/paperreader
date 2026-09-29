# Optik Sınav Okuyucu — Uygulama Planı

> **Durum:** Aşama 1–7 uygulandı ve test edildi (262 test). Aşama 8 (kalibrasyon ekranı) opsiyonel olduğu için yapılmadı.
> Plandan sapmalar: `openpyxl` gereksiz olduğu için bağımlılıklardan çıkarıldı. Yön tespiti (180°/90°) Sosyal/Fen bloklarının
> boş 21–40. satır bölgesine göre yapılıyor. Çerçeve adayı, kenarının koyu olmasıyla doğrulanıyor.
> Çalıştırma ve tuzaklar için bkz. CLAUDE.md.

## 1. Amaç
Tüm sınavlar **TYT** formatındadır: 120 soru, A–E şıkları. Öğretmen bir sınav oluşturur ve cevap anahtarını **elle** girer. Öğrenci sınavı seçip doldurduğu turuncu-beyaz TYT optiğinin fotoğrafını **bir kez** yükler. Sistem formu okur, cevap anahtarıyla karşılaştırır ve şunları çıkarır:
- test ve ders bazında doğru / yanlış / boş / net,
- konu bazında eksikler.

Öğretmen tüm öğrencileri anlık güncellenen bir listede görür. Öğrenci yalnızca kendi sonuçlarını görür.

## 2. Teknoloji Seçimi
| Katman | Seçim | Gerekçe |
|---|---|---|
| Backend | **Python 3.13 + Flask** | Makinede Python var, Node yok. Flask, oturum tabanlı iki rollü panel için yeterince basit. |
| Veritabanı | **SQLite** (`instance/paperreader.db`) + **SQLAlchemy** | PostgreSQL kurulu değil. Dosya tabanlı ve kurulum gerektirmeyen gerçek bir DB. SQLAlchemy sayesinde ileride tek satırlık `DATABASE_URL` değişikliğiyle Postgres'e geçilebilir. |
| Kimlik doğrulama | **Flask-Login** + `werkzeug.security` (parola hash) | Rol bazlı erişim (`teacher` / `student`). |
| Optik okuma (OMR) | **OpenCV (opencv-python-headless) + NumPy** | Perspektif düzeltme, eşikleme, balon doluluk ölçümü. |
| Arayüz | Jinja2 şablonları + vanilla JS + hazır CSS (Pico.css veya Bootstrap CDN) | Build adımı yok, Node gerekmiyor. |
| "Anlık" güncelleme | JS ile 5 sn'de bir JSON **polling** (`/api/teacher/exams/<id>/results`) | 10 öğrenci için yeterli ve en az riskli yöntem. SSE/WebSocket gerekmiyor. |
| Grafik | Chart.js (CDN) | Ders netleri ve konu başarı grafikleri. |

## 3. Kullanıcılar (seed)
| Rol | Kullanıcı adı | Şifre |
|---|---|---|
| Öğretmen | `admin` | `admin` |
| Öğrenci | `ogr1` … `ogr10` | `ogr1` … `ogr10` (kullanıcı adıyla aynı) |

Şifreler DB'de hash'li saklanır. Seed işlemi `flask --app app seed` komutuyla ya da ilk açılışta DB boşsa otomatik yapılır.

## 4. TYT Yapısı (sabit, kodda tanımlı)
Her sınav aynı 120 soruluk yapıdadır. Yapı `app/tyt.py` içinde sabit olarak tutulur. Sınav başına ayar gerekmez.

| Test | Ders | Soru (test içi) | Global soru no |
|---|---|---|---|
| Türkçe | Türkçe | 1–40 | 1–40 |
| Sosyal Bilimler | Tarih | 1–5 | 41–45 |
|  | Coğrafya | 6–10 | 46–50 |
|  | Felsefe | 11–15 | 51–55 |
|  | Din Kültürü | 16–20 | 56–60 |
| Temel Matematik | Matematik (Geometri dahil) | 1–40 | 61–100 |
| Fen Bilimleri | Fizik | 1–7 | 101–107 |
|  | Kimya | 8–14 | 108–114 |
|  | Biyoloji | 15–20 | 115–120 |

- DB'de soru numarası **global** (1–120) tutulur. Arayüzde "Türkçe 12", "Fen 9" gibi test içi numarayla gösterilir.
- Ders bilgisi soru numarasından otomatik türetilir. Öğretmen dersi girmez, yalnızca cevabı ve konuyu girer.
- Matematik içinde geometri ayrımı istenirse konu alanıyla yapılır; ayrı bir ders olarak tutulmaz.
- **Din Kültürü "ek soru" alanı yok.** Referans formda (Bölüm 7) bu bölüm bulunmuyor, kullanıcı tercihi de bu yönde. Sosyal testi her zaman 20 soru, 56–60 her zaman Din Kültürü.
- Referans formda "Kitapçık Türü" başlığı var ama işaretlenecek balon yok. Kitapçık türü okunmaz, tek kitapçık varsayılır.

## 5. Veri Modeli (SQLite)
```
users
  id PK, username UNIQUE, password_hash, full_name, role ('teacher'|'student'), created_at

exams
  id PK, name, description, created_by FK users, created_at,
  wrong_penalty REAL NOT NULL  -- öğretmen her sınavda elle girer (zorunlu; 0 = yanlış götürmez)
  is_active BOOL               -- öğrenci listesinde görünür mü / yükleme açık mı

answer_keys                      -- her sınav için tam 120 satır
  id PK, exam_id FK, question_no (1..120),
  correct_option ('A'..'E' | NULL = iptal soru),
  topic (konu, örn. 'Üslü Sayılar')
  UNIQUE(exam_id, question_no)
  -- ders (subject) kolonu yok, app/tyt.py'den question_no ile türetilir

submissions                      -- öğrencinin bir sınava tek ve kesin gönderimi
  id PK, exam_id FK, student_id FK, image_path, debug_image_path,
  correct, wrong, blank, net, submitted_at
  UNIQUE(exam_id, student_id)   -- ikinci gönderim DB seviyesinde de engellenir

submission_answers
  id PK, submission_id FK, question_no, marked_option (NULL = boş, '*' = çift işaret),
  confidence REAL, edited_by_student BOOL, is_correct BOOL

pending_uploads                  -- okunmuş ama henüz onaylanmamış taslak (onayla silinir)
  id PK, exam_id FK, student_id FK, image_path, debug_image_path,
  omr_result JSON, created_at
  UNIQUE(exam_id, student_id)
```
Ders ve konu özetleri ayrı tabloda tutulmaz. `submission_answers` ⋈ `answer_keys` + `tyt.py` üzerinden hesaplanır, tek kaynak olsun diye.

## 6. Net ve Analiz Kuralları
- **Net** = Doğru − Yanlış / `wrong_penalty`. Katsayıyı öğretmen sınav oluştururken **elle ve zorunlu olarak** girer (TYT için 4 önerilir, alanın ipucu metninde yazar ama önceden doldurulmaz). `0` girilirse Net = Doğru.
- Net, 4 test (Türkçe, Sosyal, Temel Mat, Fen), alt dersler (Tarih, Coğrafya, Felsefe, Din, Fizik, Kimya, Biyoloji) ve toplam için ayrı ayrı hesaplanır.
- **Boş**: hiç işaret yok. **Çift işaret**: yanlış sayılır.
- **İptal soru** (`correct_option = NULL`): herkese doğru sayılır.
- **Konu başarısı** = konudaki doğru / konudaki soru sayısı. Başarısı **%50'nin altındaki** konular "eksik konu" olarak işaretlenir (`WEAK_TOPIC_THRESHOLD` config'de).
- Sınıf geneli: konu bazında sınıf ortalaması. Öğretmen, sınıfın genelinde zayıf olan konuları görür.

## 7. Referans Form ve Optik Okuma (OMR) Hattı — `omr/`

### 7.1 Referans form (internetten)
- Kaynak: MEB Sakarya Ölçme Değerlendirme Merkezi, "TYT Optik Cevap Formu — Kazanım Değerlendirme Sınavı":
  https://sakaryaodm.meb.gov.tr/meb_iys_dosyalar/2020_02/18112015_Lise_Optik_Formu.pdf
- Yerel kopya: [docs/reference/tyt_optik_meb_sakarya.pdf](docs/reference/tyt_optik_meb_sakarya.pdf) (+ `.png` önizleme).
- A4 dikey, tek sayfa. Baskı rengi **magenta/pembe** (RGB ≈ 0.93, 0.00, 0.55). Turuncu versiyonu bulunamadı. Aynı yöntem ikisinde de çalışır, çünkü turuncu ve pembe mürekkebin ikisi de kırmızı kanalda açık görünür.
- Yerleşim: 4 sütun (Türkçe 40, Sosyal 20, Temel Mat 40, Fen 20), her satırda A–E, hepsi **kalın siyah bir çerçeve** içinde. Ek soru, kitapçık balonu ya da öğrenci no balonu yok. Öğrenci kimliği zaten oturumdan bilindiği için gerekmiyor.

**PDF vektörlerinden ölçülen geometri (pt, A4 = 595.28 × 841.89):**
| Öğe | Değer |
|---|---|
| Siyah çerçeve (çizgi merkezi) | x 44.36 → 416.13, y 288.13 → 779.82 (371.8 × 491.7), çizgi kalınlığı 2.83 |
| Balon çapı | 9.59 |
| Şıklar arası (A→B…) yatay adım | 12.0 |
| Sorular arası dikey adım | 12.0 (40. satır y = 767.7) |
| 1. soru satırı merkezi y | 299.90 |
| A şıkkı merkezi x — Türkçe / Sosyal / Temel Mat / Fen | 68.36 / 164.32 / 260.28 / 356.24 (bloklar arası ≈ 95.96) |

Şablonda bu değerler **çerçeveye göre normalize** saklanır: (x − 44.36) / 371.77, (y − 288.13) / 491.69. Böylece çerçeve bulunduktan sonra her çözünürlükte doğrudan kullanılabilir. `omr/templates/tyt_120.json` bu tablodan üretilir.

### 7.2 Okuma hattı
Temel fikir: form baskısı turuncu/pembe, kurşun kalem izi koyu gri/siyah. **Kırmızı kanalda baskı neredeyse beyaz görünür**, kalem izi ve siyah çerçeve ise koyu kalır. Kırmızı kanalla eşikleme, baskıyı silip yalnızca işaretleri bırakır.

1. **Ön işleme**: EXIF yönünü düzelt, uzun kenarı ~2000 px'e indir.
2. **Çerçeveyi bulma**: referans formdaki kalın **siyah dikdörtgen çerçeve** en güvenilir işarettir. Gri/R kanalında eşikleme → konturlar → alanı en büyük 4 köşeli kontur (`approxPolyDP`) alınır, en/boy oranı ≈ 0.756 ile doğrulanır. Bulunamazsa hata verilir ("Formun tamamı görünecek şekilde, düz zeminde tekrar çekin"). Bu hata **yükleme hakkını tüketmez**.
3. **Perspektif düzeltme**: çerçeve köşeleri `getPerspectiveTransform` ile kanonik boyuta (örn. 1116 × 1476 px ≈ 3 px/pt) warp edilir.
4. **Kanal ayırma + eşik**: R kanalı → Gaussian blur → adaptif / Otsu eşik (ters). Sonuçta işaretler beyaz, geri kalanı siyah olur. Çerçeve çizgisi balon bölgelerine girmediği için sorun çıkarmaz.
5. **Şablon ile balon konumları**: tek şablon, `omr/templates/tyt_120.json` (Bölüm 7.1'deki normalize değerler: 4 blok, blok başı A-merkezi, adımlar, balon yarıçapı, test içi soru sayısı).
6. **Doluluk ölçümü**: her balonun dairesel maskesindeki beyaz piksel oranı hesaplanır.
   - En yüksek oran ≥ `FILL_THRESHOLD` (≈0.45) ve ikinciden belirgin yüksekse işaretli sayılır.
   - İki balon eşiğin üzerindeyse çift işaret (`*`), hiçbiri değilse boş.
   - En yüksek ile ikinci arasındaki fark küçükse `confidence` düşer ve soru "şüpheli" işaretlenir.
7. **Çıktı**: `{question_no: (option|None|'*', confidence)}` ve hata ayıklama için balonları renklendirilmiş overlay görseli (`uploads/debug/`).

**Önizleme / onay adımı**: okunan cevaplar `pending_uploads` tablosuna taslak olarak yazılır ve öğrenciye 4 test halinde gösterilir. Şüpheli sorular sarıyla vurgulanır. Öğrenci yalnızca şüpheli soruları düzeltebilir. Önizlemede "Bu gönderim kesindir, bir daha yükleme yapamazsınız" uyarısı çıkar. **"Onayla ve Gönder"** denince taslak `submissions`'a taşınır ve puanlanır. Düzeltilen sorular `edited_by_student` ile işaretlenir, öğretmen görebilir.

**Form kaynağı**:
- **Birincil**: referans MEB formu (7.1) ve onunla birebir aynı ölçülerde, sistemin ürettiği **turuncu-beyaz** yazdırılabilir kopya (`omr/form_generator.py` → `/forms/tyt_120.pdf`). Öğretmen bunu yazdırıp dağıtır. Renk dışında geometri aynı olduğu için tek şablon iki formu da okur.
- **Opsiyonel**: farklı bir TYT optiği kullanılırsa **kalibrasyon ekranı** ile yeni şablon üretilir. Öğretmen boş formun fotoğrafında her test bloğunun ilk ve son balonuna tıklar, JSON otomatik oluşur.

**Test verisi**: referans PDF'ten render edilen görüntünün üzerine programla işaretler basılır (bilinen cevaplar), sonra döndürme, perspektif, gölge ve bulanıklık eklenerek sentetik test fotoğrafları üretilir (`tests/fixtures/`). Ardından birkaç gerçek çıktı + telefon fotoğrafı ile doğrulanır.

## 8. Tek Yükleme Kuralı
- Öğrenci her sınava **yalnızca bir kez** kesin gönderim yapabilir. Kural hem uygulamada hem DB'de (`UNIQUE(exam_id, student_id)`) uygulanır.
- Hak **yalnızca "Onayla ve Gönder" ile tükenir**. Okunamayan fotoğraf (köşe bulunamadı, bulanık vb.) ya da onaylanmadan terk edilen taslak hak harcamaz. Öğrenci onaya kadar fotoğrafı yeniden çekip yükleyebilir; yeni yükleme eski taslağın üzerine yazar.
- Gönderimden sonra öğrenci panelinde sınav "Gönderildi" olarak kilitlenir ve yükleme butonu gizlenir. Sunucu tarafı da ikinci POST'u reddeder (409).
- **Öğretmen istisnası**: öğretmen, öğrenci detay sayfasından bir gönderimi **"Sıfırla"** diyebilir (onay pop-up'ı ile). Gönderim silinir ve öğrenci tekrar yükleyebilir. Hatalı okuma durumları için gerekli.

## 9. Cevap Anahtarı Girişi (öğretmen, elle ve zorunlu)
Sınav oluşturma tek bir formda yapılır:
1. **Sınav adı** (zorunlu), açıklama (opsiyonel).
2. **Yanlış katsayısı** (zorunlu, sayı, ≥ 0; ipucu: "TYT için 4").
3. **Cevap anahtarı ızgarası**: 120 soru, 4 test sekmesinde (Türkçe 40 / Sosyal 20 / Temel Mat 40 / Fen 20). Her satırda test içi soru no, otomatik ders etiketi, **A B C D E İptal** radyo butonları ve konu alanı bulunur.
   - **Her sorunun cevabı zorunlu.** 120 sorunun tamamı seçilmeden kaydet butonu pasif kalır. Eksik sorular kırmızıyla vurgulanır, sekme başlıklarında "38/40" gibi sayaç gösterilir. Sunucu tarafında da 120 sorunun tamamı doğrulanır.
   - Klavyeyle hızlı giriş: soru satırında A–E tuşuna basınca şık seçilir ve bir sonraki soruya geçilir.
   - **Konu** alanı: ders bazında önceden tanımlı TYT konu listesinden seçilir (`app/tyt_topics.py`), serbest metin de yazılabilir. "Soru 1–5 → Paragraf" gibi toplu aralık atama yapılabilir. Konu boş bırakılabilir ama boş olanlar konu analizine "Belirtilmemiş" olarak girer.
4. Kaydet. Sınav önce `is_active = False` kaydedilir, öğretmen "Yayınla" deyince öğrencilere açılır.

CSV veya optikten anahtar okuma **yapılmaz**, anahtar yalnızca elle girilir.

Anahtar yayından sonra düzenlenirse (ör. hatalı cevap, iptal soru) o sınavın mevcut tüm gönderimleri **yeniden puanlanır**. Öğrencinin ham işaretleri saklı olduğu için görsel tekrar işlenmez.

## 10. Sayfalar ve API
### Ortak
- `GET/POST /login`, `POST /logout`. Rol kontrolü `@role_required('teacher'|'student')` dekoratörüyle yapılır.

### Öğretmen paneli (`/teacher`)
- `/teacher` — sınav listesi (ad, tarih, durum taslak/yayında, gönderen öğrenci sayısı / 10, ortalama net).
- `/teacher/exams/new`, `/teacher/exams/<id>/edit` — sınav bilgisi, yanlış katsayısı ve 120 soruluk anahtar ızgarası.
- `/teacher/exams/<id>` — **canlı sonuç tablosu**. Sütunlar: öğrenci, durum (göndermedi / gönderdi), Türkçe / Sosyal / Temel Mat / Fen için D-Y-B-Net, toplam net, sıra. Tablo sıralanabilir, 5 sn'de bir yenilenir. Altında sınıf geneli konu başarı grafiği ve "en çok yanlış yapılan sorular" listesi.
- `/teacher/exams/<id>/students/<sid>` — öğrencinin soru soru cevapları, yüklenen fotoğraf, debug overlay, öğrencinin düzelttiği sorular, eksik konular, **"Gönderimi Sıfırla"** butonu.
- `/teacher/students` — öğrenci listesi ve öğrencinin tüm sınavlardaki net gelişimi.
- `GET /api/teacher/exams/<id>/results` — polling için JSON.

### Öğrenci paneli (`/student`)
- `/student` — yayındaki sınavlar ("Yüklenmedi" / "Gönderildi" rozetiyle) ve geçmiş sonuç özetleri.
- `/student/exams/<id>/upload` — fotoğraf yükleme (mobilde `accept="image/*" capture="environment"` ile doğrudan kamera). Yalnızca gönderim yoksa erişilebilir.
- `/student/exams/<id>/review` — taslak önizleme, şüpheli soruları düzeltme, "Onayla ve Gönder".
- `/student/exams/<id>/result` — 4 test ve alt dersler için D/Y/B/Net kartları, soru soru tablo (doğru yeşil, yanlış kırmızı, boş gri), **eksik konular** listesi, konu başarı grafiği.
- Öğrenci başka öğrencinin verisine erişemez. Tüm sorgular `current_user.id` ile filtrelenir, URL'deki id'ye güvenilmez.

## 11. Klasör Yapısı
```
paperreader/
  app/
    __init__.py          # create_app, config, extension init
    models.py            # SQLAlchemy modelleri
    tyt.py               # TYT yapısı: testler, dersler, soru aralıkları, numara dönüşümleri
    tyt_topics.py        # ders bazında önceden tanımlı konu listeleri
    auth.py              # login/logout, role_required
    teacher/routes.py
    student/routes.py
    api.py               # JSON uçları (polling)
    services/
      grading.py         # puanlama, net, konu analizi (saf fonksiyonlar)
      submissions.py     # taslak → kesin gönderim, tek yükleme kuralı, sıfırlama
    templates/ (base.html, login.html, teacher/*, student/*)
    static/ (css, js/live_table.js, js/answer_key_grid.js, js/charts.js)
  omr/
    reader.py            # read_sheet(image_path, template) -> sonuç
    preprocess.py        # köşe bulma, warp, R-kanal eşikleme
    templates/tyt_120.json
    form_generator.py    # yazdırılabilir turuncu-beyaz TYT formu üretimi
  instance/paperreader.db   # (git'e girmez)
  uploads/                  # öğrenci fotoğrafları + debug (git'e girmez)
  tests/ (test_grading.py, test_tyt.py, test_submissions.py, test_omr.py + tests/fixtures/*.jpg)
  seed.py
  requirements.txt
  run.py
```

## 12. Uygulama Aşamaları
1. **İskelet**: venv, `requirements.txt` (flask, flask-login, flask-sqlalchemy, opencv-python-headless, numpy, pillow, pytest), app factory, modeller, seed (admin + ogr1..10), login ve rol yönlendirmesi.
2. **TYT yapısı ve anahtar girişi**: `tyt.py`, `tyt_topics.py`, 120 soruluk zorunlu elle giriş ızgarası (istemci ve sunucu doğrulaması), taslak/yayın durumu.
3. **Puanlama servisi**: `grading.py` (test, ders, toplam net ve konu analizi) ve birim testleri. OMR'den bağımsız, elle verilen cevaplarla test edilir.
4. **OMR**: referans ölçülerden `tyt_120.json`, turuncu-beyaz yazdırılabilir TYT formu, `preprocess` + `reader`, debug overlay. Önce referans PDF'ten sentetik fixture'larla, sonra gerçek fotoğraflarla (farklı ışık/açı) testler.
5. **Öğrenci akışı**: sınav seçimi → yükleme → taslak önizleme/düzeltme → onay (tek yükleme kilidi) → sonuç ve eksik konular.
6. **Öğretmen canlı paneli**: polling'li sonuç tablosu, öğrenci detayı, gönderim sıfırlama, sınıf konu grafiği.
7. **Cila**: anahtar düzenlenince yeniden puanlama, sonuçları CSV/Excel dışa aktarma, hata mesajları, mobil uyumluluk.
8. (Opsiyonel) Farklı optikler için şablon kalibrasyon ekranı.

## 13. Riskler ve Önlemler
| Risk | Önlem |
|---|---|
| Sınıfta referanstan farklı bir TYT optiği kullanılması | Referans MEB formu ve aynı ölçülerde üretilen turuncu kopya standart kabul edilir. Farklı form gelirse kalibrasyon ekranı (aşama 8). |
| Çerçevenin fotoğrafta kısmen görünmemesi | Çekim ipucu ("4 köşe görünsün") ve net hata mesajı. Hak tüketmez. |
| Kötü ışık, gölge, eğik çekim | Adaptif eşik, perspektif düzeltme, köşe bulunamazsa net hata mesajı. Okunamayan fotoğraf hak tüketmez. |
| Tek yükleme hakkının yanlış okumayla harcanması | Onay öncesi önizleme ve şüpheli soru düzeltme, öğretmenin "Sıfırla" yetkisi. |
| 120 soruluk elle girişte hata | Sekme bazlı sayaçlar, eksik soru vurgusu, klavye kısayolları, kaydetmeden önce özet ekranı (test başına cevap dağılımı). |
| Öğrencinin başkasının verisini görmesi | Tüm öğrenci sorgularını sunucu tarafında `current_user` ile filtrele. |
| SQLite eşzamanlı yazma | 10 kullanıcı için sorun değil. WAL modu açılır. |

## 14. Kararlar (kullanıcı ile netleşti)
- Tüm sınavlar TYT, 120 soru, A–E.
- Yanlış katsayısı ve cevap anahtarı öğretmen tarafından elle ve zorunlu girilir.
- Öğrenci sınav başına tek kesin gönderim yapar.
- Optik şablonu internetten bulunan MEB TYT formuna göre (Bölüm 7.1). Din Kültürü ek soru alanı yok.
