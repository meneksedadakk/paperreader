# CLAUDE.md — paperreader (Optik Sınav Okuyucu)

Detaylı plan için bkz. [PLAN.md](PLAN.md). Bu dosya kalıcı bağlamdır.

## Proje özeti
Web tabanlı optik sınav okuyucu. İki rol var:
- **Öğretmen**: sınav oluşturur (ad + o sınava özel cevap anahtarı; her soru için doğru şık, ders ve konu). Tüm öğrencilerin sonuçlarını canlı bir listede görür.
- **Öğrenci**: sınavı seçer, doldurduğu turuncu-beyaz optiğin fotoğrafını yükler. Yalnızca kendi D/Y/B/Net ve eksik konu analizini görür.

## Ortam kısıtları
- Windows 11, PowerShell 5.1 (`&&` yok, `;` kullan).
- **Python 3.13 var, Node.js yok.** Frontend build aracı kullanma. Jinja2 + vanilla JS + CDN (Chart.js, Pico/Bootstrap).
- **PostgreSQL kurulu değil.** DB olarak **SQLite** (`instance/paperreader.db`) + SQLAlchemy kullan. Bağlantı `DATABASE_URL` env değişkeninden okunur, varsayılan sqlite. Ham `sqlite3` çağrısı yazma, her şey ORM üzerinden gitsin.
- Proje OneDrive altında ve yolda Türkçe karakter (`Masaüstü`) var. Dosya yollarında `pathlib` kullan. OpenCV'de `cv2.imread` yerine `cv2.imdecode(np.fromfile(path, np.uint8), ...)` kullan (Windows'ta Unicode yol sorunu).

## Stack
Flask, Flask-Login, Flask-SQLAlchemy, opencv-python-headless, numpy, pillow, pytest.

## Seed kullanıcılar (değiştirme)
- Öğretmen: `admin` / `admin`
- Öğrenciler: `ogr1`/`ogr1` … `ogr10`/`ogr10`
Şifreler `werkzeug.security.generate_password_hash` ile saklanır. Seed idempotent olmalı.

## Sınav formatı: yalnızca TYT
- Her sınav TYT'dir: 120 soru, A–E. Yapı `app/tyt.py` içinde sabit. Sınav başına soru/şık sayısı ayarı **yok**.
- Türkçe 1–40 · Sosyal 41–60 (Tarih 41–45, Coğrafya 46–50, Felsefe 51–55, Din 56–60) · Temel Mat 61–100 · Fen 101–120 (Fizik 101–107, Kimya 108–114, Biyoloji 115–120).
- DB'de soru no global (1–120). Arayüzde test içi numara gösterilir. Ders `answer_keys`'te saklanmaz, soru numarasından türetilir.
- Tek OMR şablonu: `omr/templates/tyt_120.json`.
- Din Kültürü **ek soru alanı yok** (kullanıcı tercihi). Kitapçık türü okunmaz.

## Referans optik form
- [docs/reference/tyt_optik_meb_sakarya.pdf](docs/reference/tyt_optik_meb_sakarya.pdf): MEB Sakarya ÖDM TYT formu. Şablonun kaynağı bu dosya, ölçüler PLAN.md §7.1'de.
- Anahtar geometri (pt, A4): siyah çerçeve x 44.36–416.13, y 288.13–779.82. Balon çapı 9.59, adım 12 (yatay ve dikey). 1. satır y = 299.90. A-merkezi x = 68.36 / 164.32 / 260.28 / 356.24. Şablonda çerçeveye göre normalize saklanır.
- Kalın siyah çerçeve perspektif düzeltmede ana referanstır. Baskı magenta, sistemin ürettiği kopya turuncu. İkisi de R kanalında kaybolur.

## Alan kuralları
- Net = Doğru − Yanlış / `exam.wrong_penalty`. Katsayıyı öğretmen **elle ve zorunlu** girer, varsayılan değer yok (ipucu: TYT için 4). 0 ise yanlış götürmez.
- Net; 4 test, alt dersler ve toplam için hesaplanır.
- Çift işaret = yanlış. Boş = işaretsiz. İptal soru (`correct_option` NULL) = herkese doğru.
- Eksik konu: konu başarısı < %50 (`WEAK_TOPIC_THRESHOLD`).
- Ders ve konu özetleri DB'de ayrı saklanmaz, `submission_answers` + `answer_keys` + `tyt.py` üzerinden hesaplanır. Anahtar değişince tüm gönderimler yeniden puanlanır.

## Cevap anahtarı: yalnızca elle giriş
- Öğretmen 120 sorunun **tamamını** elle girer (A–E veya İptal). Eksik varsa kayıt reddedilir; hem JS'te hem sunucuda doğrulanır.
- CSV veya optik fotoğrafından anahtar okuma **yok**.
- Konu alanı opsiyonel (`app/tyt_topics.py` listesi + serbest metin). Boş konu analizde "Belirtilmemiş" olarak geçer.
- Sınav taslak (`is_active=False`) oluşur, öğretmen yayınlayınca öğrencilere açılır.

## Tek yükleme kuralı
- Öğrenci her sınava **bir kez** kesin gönderim yapar (`submissions` üzerinde `UNIQUE(exam_id, student_id)`, ikinci POST → 409).
- Akış: yükleme → OMR → `pending_uploads` taslağı → önizleme (yalnızca şüpheli sorular düzeltilebilir) → "Onayla ve Gönder" → `submissions`.
- Hak yalnızca onayla tükenir. Okunamayan fotoğraf ve onaylanmamış taslak hak harcamaz, taslak yeni yüklemeyle üzerine yazılır.
- Yalnızca öğretmen bir gönderimi "Sıfırla" ile silip yeniden yüklemeye açabilir.

## Güvenlik
- Her route `role_required` ile korunur.
- Öğrenci uçlarında veri **her zaman** `current_user.id` ile filtrelenir. URL'den gelen öğrenci id'sine güvenme.
- Yüklenen dosyalar: yalnızca görsel MIME, boyut limiti (10 MB), `secure_filename` + uuid ile adlandırma, `uploads/` dışında sunma.

## OMR notları
- Turuncu baskıyı yok etmek için **kırmızı kanal** kullanılır: turuncu R'de açık görünür, kalem izi koyu kalır.
- Hat: EXIF düzelt → köşe/dörtgen bul → perspektif warp (kanonik boyut) → R kanal + eşik → şablon JSON'daki balon koordinatlarında doluluk oranı → işaret, boş, çift işaret ve güven skoru.
- Şablon `omr/templates/tyt_120.json`, koordinatlar kanonik (warp sonrası) uzayda.
- Düşük güvenli sorular öğrenciye önizlemede onaylatılır.
- OMR mantığı `omr/` altında Flask'tan bağımsız saf modül olmalı, CLI/pytest ile tek başına test edilebilsin.

## Komutlar
```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
flask --app app seed      # kullanıcıları ekle (idempotent; uygulama ilk açılışta da otomatik seed eder)
python run.py             # http://127.0.0.1:5000  (veya: flask --app app run --debug)
python -m pytest          # tüm testler (~1 dk)
python -m omr.geometry    # omr/templates/tyt_120.json'u ölçülerden yeniden üretir
```

## Proje durumu (kod yazıldı, tüm PLAN.md aşamaları tamam)
- Yapı: `app/` (Flask: `auth.py`, `teacher/`, `student/`, `api.py`, `files.py`, `services/{grading,submissions,report}.py`, `tyt.py`, `tyt_topics.py`), `omr/` (`geometry.py`, `preprocess.py`, `reader.py`, `form_generator.py`, `templates/tyt_120.json`), `tests/`.
- Testler: `test_omr*.py` (sentetik ve gerçek MEB formu üzerinde), `test_grading.py`, `test_tyt.py`, `test_submissions.py`, `test_auth.py`, `test_teacher.py`, `test_student_flow.py`. Uçtan uca akış gerçek fotoğraf üretip yükleyerek test edilir (`tests/helpers.py::to_photo`).
- Testlerde `create_app({...})` ile geçici DB/upload/instance dizini ve hızlı parola hash'i (`PASSWORD_HASH_METHOD`) verilir; CSRF açık kalır, `tests/conftest.py::Browser` token'ı ekler.
- Tuzaklar: (1) Jinja'da `d.values`/`d.items` gibi anahtar adları dict metoduna çözülür, şablona giden dict'lerde bu adları kullanma. (2) CSRF kontrolünde boş token ile boş oturum eşleşmemeli (düzeltildi, testli). (3) OMR yön tespiti baskılı numaralara değil, Sosyal/Fen bloklarının 21–40. satır boşluğuna bakar. Dolu balonlara bakan bir ipucu kullanma. (4) Çerçeve adayı kenarının koyu olup olmadığı kontrol edilir, aksi halde A4 sayfa kenarı çerçeve sanılır.
- JS (`answer_key_grid.js`, `live_table.js`) birim testli değil; başsız Edge (`--dump-dom`) ile üretilen sayfalarda çalıştığı doğrulandı.

## Kodlama tercihleri
- Arayüz metinleri Türkçe, kod (değişken/fonksiyon adları) İngilizce.
- Puanlama (`app/services/grading.py`) saf fonksiyonlarla yazılır ve birim testleri olur.
- `instance/`, `uploads/`, `.venv/` git'e girmez.
