# Optik Sınav Okuyucu

Öğrencinin doldurduğu **TYT optik formunun fotoğrafını** okuyup cevap anahtarıyla karşılaştıran, test/ders/konu bazında doğru-yanlış-net analizi çıkaran web uygulaması. Öğretmen ve öğrenci için ayrı paneller vardır.

## Özellikler

**Öğretmen**
- Sınav oluşturur: ad, yanlış katsayısı ve 120 soruluk cevap anahtarı (elle, hepsi zorunlu; iptal soru desteği).
- Sınavı yayınlar; öğrenciler sonuçları yükledikçe **canlı güncellenen** tabloda net, ders ve sıralama görünür.
- Sınıf genelinde eksik konuları ve en çok yanlış yapılan soruları görür; sonuçları CSV indirir.
- Anahtar düzeltilirse tüm sonuçlar otomatik yeniden hesaplanır. Hatalı bir gönderimi sıfırlayabilir.

**Öğrenci**
- Sınavı seçer, optik formun fotoğrafını yükler, sistemin okuduğu cevapları kontrol eder ve onaylar.
- Her sınava **yalnızca bir kez** kesin gönderim yapabilir (uygulamada ve veritabanında zorunlu).
- Test, ders ve konu bazında D/Y/B/Net ile eksik konu analizini görür. Yalnızca kendi verisine erişebilir.

## Optik okuma (OMR)

OpenCV ile yazıldı, Flask'tan bağımsız `omr/` paketindedir.

1. Formun kalın siyah çerçevesi bulunur, perspektif düzeltilir (eğik/gölgeli çekimler sorun olmaz).
2. Turuncu/pembe baskı **kırmızı kanalda silinir**, yalnızca kurşun kalem izi kalır.
3. Her balonun doluluk oranı ölçülür; boş, tek işaret ve çift işaret ayrılır, her soru için güven skoru üretilir.
4. Emin olunamayan sorular öğrenciye onay ekranında sarı gösterilir.
5. Fotoğraf 90°/180° ters çekilse bile yön otomatik bulunur.

Şablon, MEB'in yayımladığı TYT optik formunun PDF'inden ölçülmüştür (`docs/reference/`).

## Teknoloji

Python 3.13 · Flask · Flask-Login · SQLAlchemy (SQLite) · OpenCV · NumPy · Pillow · pytest. Ön yüz: Jinja2 + vanilla JS (derleme adımı yok).

## Kurulum

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

Uygulama http://127.0.0.1:5000 adresinde açılır. İlk çalıştırmada veritabanı ve demo hesaplar otomatik oluşur.

### Demo hesaplar

Giriş sayfasında önce **Öğretmen** veya **Öğrenci** seçilir.

| Rol | Kullanıcı adı | Şifre |
|---|---|---|
| Öğretmen | `admin` | `admin` |
| Öğrenci | `ogr1` … `ogr10` | kullanıcı adıyla aynı (`ogr1`, `ogr2`, …) |

> Bunlar yalnızca yerelde deneme içindir. Gerçek bir ortamda şifreler değiştirilmelidir.

### Denemek için

1. Öğretmen olarak girin, **Yeni sınav** ile anahtarı girip **Yayınla**'ya basın.
2. Giriş yaptıktan sonra http://127.0.0.1:5000/forms/tyt_120.pdf adresinden boş optik formu indirip yazdırın, kurşun kalemle doldurun ve fotoğrafını çekin (formun siyah çerçevesinin 4 köşesi görünmeli).
3. Öğrenci olarak girip fotoğrafı yükleyin, okunan cevapları onaylayın.

## Testler

```powershell
python -m pytest
```

275 test: OMR (sentetik fotoğraflar ve gerçek MEB formu üzerinde; eğiklik, gölge, ters çevirme, çift işaret), puanlama, kimlik doğrulama/yetkilendirme (CSRF dahil), sınav yönetimi ve uçtan uca öğrenci akışı.

## Proje yapısı

```
app/     Flask uygulaması (rotalar, modeller, servisler, şablonlar)
omr/     Optik okuma: çerçeve bulma, perspektif düzeltme, balon ölçümü, form üretimi
tests/   pytest testleri
docs/    Referans TYT optik formu
```

Ayrıntılı tasarım kararları için [PLAN.md](PLAN.md), geliştirici notları için [CLAUDE.md](CLAUDE.md) dosyasına bakın.
