# NAC Projesi Video Akışı ve Okuma Metni

Not: Bu dosya örnek video planı ve konuşma metnidir. Bunu birebir ezberlemek yerine kendi doğal tonuna göre uyarlaman çok daha iyi olur. Videoda koda hakimiyet önemli olduğu için, her bölümde neyi neden yaptığını gerçekten anlayarak anlatman gerekir.

## Hedef Süre

Toplam hedef süre: 16-19 dakika

Önerilen dağılım:

1. Giriş ve proje amacı - 1:00
2. Mimari şema anlatımı - 2:00
3. Docker Compose ve servis yapısı - 2:00
4. Dashboard simülasyonu üzerinden genel akış - 2:30
5. PAP authentication canlı demo - 2:00
6. MAB canlı demo - 2:00
7. Authorization ve VLAN mantığı - 1:30
8. Accounting ve aktif session takibi - 2:00
9. Code review bölümü - 3:30
10. Güvenlik değerlendirmesi, zorluklar ve kapanış - 1:30

## Videoda Açık Tutulabilecek Pencereler

- Terminal
- Tarayıcıda dashboard (`http://localhost:8000/dashboard`)
- Editörde proje dosyaları
- Gerekirse mimariyi göstermek için README içindeki yapı veya kendi çizdiğin basit diyagram

## Önerilen Görsel Akış

Videoda şu sırayı kullanmak temiz olur:

1. İlk 1-2 dakikada mimari şema
2. Sonra `docker compose ps` ile servislerin ayakta olduğunu göster
3. Dashboard'u açıp görsel şema üzerinden veri akışını anlat
4. Terminale dönüp auth, authorize ve accounting demolarını yap
5. Son bölümde editöre geçip kısa ama güçlü bir code review yap

## Demo Öncesi Hazırlık Checklist

Videoya başlamadan önce bunları hazır tut:

- `docker compose up -d` çalışmış olsun
- `docker compose ps` tüm servisleri healthy göstersin
- Dashboard tarayıcıda açık olsun
- Kullanacağın test komutları kolay erişilebilir olsun
- Gerekirse `tests/smoke_radius.sh` dosyasını referans için açık tut

## Kullanılabilecek Komutlar

### Sağlık kontrolü

```bash
docker compose ps
curl http://localhost:8000/health
```

### PAP auth

```bash
docker exec nac_freeradius sh -lc \
  'radtest admin01 admin123 127.0.0.1 0 "$RADIUS_SHARED_SECRET"'
```

### MAB auth

```bash
docker exec nac_freeradius sh -lc \
  'printf "User-Name = \"aa:bb:cc:dd:ee:ff\"\nUser-Password = \"aa:bb:cc:dd:ee:ff\"\nCalling-Station-Id = \"aa:bb:cc:dd:ee:ff\"\nNAS-IP-Address = 127.0.0.1\n" | radclient -x 127.0.0.1 auth "$RADIUS_SHARED_SECRET"'
```

### Accounting

```bash
curl -X POST http://localhost:8000/accounting \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <API_SECRET_KEY>" \
  -d '{
    "status_type": "Start",
    "session_id": "video-sess-01",
    "username": "guest01"
  }'
```

```bash
curl -H "X-API-Key: <API_SECRET_KEY>" http://localhost:8000/sessions/active
```

## Ayrıntılı Video Akışı ve Okuma Metni

## 1. Açılış - 1 Dakika

### Ekranda

- Proje klasörü
- Kısa başlık

### Okuma Metni

"Merhaba, bu videoda staj değerlendirme ödevi kapsamında geliştirdiğim Network Access Control yani NAC sistemini anlatacağım. Projede FreeRADIUS, FastAPI, PostgreSQL ve Redis kullanarak temel AAA yani authentication, authorization ve accounting bileşenlerini çalışan bir yapı haline getirdim. Ayrıca sistemi Docker Compose ile orkestre ettim ve dashboard ile görsel olarak da izlenebilir hale getirdim."

## 2. Mimari Şema Anlatımı - 2 Dakika

### Ekranda

- Dashboard'un üst kısmındaki ağ şeması
- Gerekirse README veya kendi çizdiğin mimari diyagram

### Vurgu Noktaları

- Client veya NAS -> FreeRADIUS
- FreeRADIUS -> FastAPI policy engine
- FastAPI -> PostgreSQL ve Redis
- Sonuç -> Access-Accept / Reject / Accounting kaydı

### Okuma Metni

"Önce mimariyi göstermek istiyorum. Burada istemci ya da NAS cihazı önce FreeRADIUS'a istek gönderiyor. FreeRADIUS benim AAA taşıma katmanım. Ancak doğrulama ve politika kararlarını doğrudan burada yazmak yerine `rlm_rest` üzerinden FastAPI uygulamasına delege ettim. FastAPI tarafı kullanıcıyı PostgreSQL'den okuyor, rate limit ve aktif oturum bilgisini Redis'ten kontrol ediyor ve sonrasında gerekli kararı FreeRADIUS'a döndürüyor. Authorization aşamasında kullanıcı grubu bazlı VLAN bilgileri yine bu katmanda dönülüyor. Accounting tarafında da oturum başlangıcı, güncellenmesi ve bitişi hem veritabanına yazılıyor hem de Redis cache tarafında tutuluyor."

## 3. Docker Compose ve Servis Yapısı - 2 Dakika

### Ekranda

- `docker compose ps`
- `docker-compose.yml`

### Anlatılacak Noktalar

- 4 servis
- healthcheck
- volume
- dedicated network
- `.env` kullanımı

### Okuma Metni

"Burada Docker Compose yapısını görebiliriz. Sistemde dört servis var: FreeRADIUS, FastAPI API, PostgreSQL ve Redis. Her servis için healthcheck tanımladım. PostgreSQL ve Redis tarafında volume kullanarak kalıcılık sağladım. Servisler aynı Docker ağı üzerinde haberleşiyor. Secret bilgileri doğrudan dosyaya gömmek yerine `.env` ile yönetiyorum. Bu yapı sayesinde proje tek komutla ayağa kalkabiliyor ve tekrar üretilebilir bir ortam sunuyor."

## 4. Dashboard Simülasyonu Üzerinden Genel Akış - 2.5 Dakika

### Ekranda

- Dashboard login ekranı
- Dashboard içindeki ağ görselleştirmesi
- Kullanıcı, VLAN, packet log, active sessions bölümleri

### Anlatılacak Noktalar

- Dashboard zorunlu değil ama sistemi anlatmayı kolaylaştırıyor
- Kullanıcı rolü, VLAN, packet log, accounting görünürlüğü
- Admin görünümünde users ve sessions takibi

### Okuma Metni

"Bu bölümde dashboard'u gösteriyorum. Bu arayüz ödev için zorunlu değildi ama sistemi görsel olarak anlatmayı çok kolaylaştırdığı için ekledim. Burada kullanıcı giriş ekranı, ardından oturum açıldığında atanan VLAN, RADIUS attribute'ları, packet log ve aktif session detayları görülebiliyor. Admin görünümünde ayrıca kullanıcı listesi, aktif oturumlar ve grup politikaları da yer alıyor. Videoda özellikle bu ağ şemasını kullanarak istemci, switch, VLAN ve AAA core ilişkisini açıklamak daha anlaşılır bir demo sağlıyor."

## 5. PAP Authentication Canlı Demo - 2 Dakika

### Ekranda

- Terminal
- `radtest` çıktısı
- Gerekirse `/auth` ve `/authorize` için `curl`

### Okuma Metni

"Şimdi PAP authentication akışını gösteriyorum. `radtest` ile `admin01` kullanıcısını doğru şifreyle doğruluyorum. Burada Access-Accept döndüğünü görüyoruz. Bu sırada FreeRADIUS isteği alıyor, FastAPI `/auth` endpoint'ine gidiyor, kullanıcıyı PostgreSQL'den kontrol ediyor ve bcrypt hash ile doğrulama yapıyor. Eğer kullanıcı adı ya da parola yanlış olursa sistem reject dönüyor ve başarısız deneme Redis tarafında sayılıyor."

### Ek Cümle

"İstersem aynı akışı FastAPI tarafında `curl` ile doğrudan da test edebiliyorum. Bu da RADIUS katmanı ile uygulama katmanını ayrı ayrı doğrulamayı kolaylaştırıyor."

## 6. MAB Canlı Demo - 2 Dakika

### Ekranda

- `radclient` komutu
- Access-Accept veya Access-Reject çıktısı

### Okuma Metni

"Şimdi MAB yani MAC Authentication Bypass senaryosunu gösteriyorum. Bu senaryo 802.1X desteklemeyen cihazlar için önemli. Burada kayıtlı MAC adresini `Calling-Station-Id` ile gönderiyorum ve sistem bunu kabul ediyor. Bilinmeyen bir MAC adresi gönderdiğimde ise Access-Reject alıyorum. Bu sayede sisteme tanımlı olmayan cihazların ağa erişmesi engellenmiş oluyor."

## 7. Authorization ve VLAN Mantığı - 1.5 Dakika

### Ekranda

- `/authorize` çıktısı
- Dashboard üzerindeki VLAN alanı
- Gerekirse veritabanı grupları

### Okuma Metni

"Authentication başarılı olduktan sonra authorization aşamasına geçiyoruz. Burada kullanıcı grubu belirleniyor ve buna göre VLAN bilgisi dönülüyor. Örneğin admin kullanıcılar VLAN 10'a, employee kullanıcılar VLAN 20'ye, guest kullanıcılar VLAN 30'a yönlendiriliyor. Bu atama `Tunnel-Type`, `Tunnel-Medium-Type` ve `Tunnel-Private-Group-Id` attribute'ları ile yapılıyor. Bu yaklaşım gerçek dünyadaki ağ segmentasyonu mantığını küçük ölçekte modellemiş oluyor."

## 8. Accounting ve Aktif Session Takibi - 2 Dakika

### Ekranda

- `radclient` accounting Start/Interim/Stop
- `/sessions/active`
- Dashboard session görünümü

### Okuma Metni

"Şimdi accounting tarafını gösteriyorum. Burada Start, Interim-Update ve Stop paketleri işleniyor. Oturum başladığında kayıt veritabanına yazılıyor ve aktif session bilgisi Redis'e alınıyor. Interim-Update ile oturum süresi ve trafik bilgileri güncelleniyor. Stop geldiğinde oturum kapanıyor. Dashboard ve `/sessions/active` endpoint'i sayesinde aktif bağlantıları hızlı şekilde gözlemleyebiliyoruz. Bu bölüm özellikle audit ve kullanım takibi açısından önemli."

## 9. Code Review Bölümü - 3.5 Dakika

### Ekranda

- Editör içinde ilgili dosyalar

### Dosya Sırası

1. `docker-compose.yml`
2. `freeradius/sites-enabled/default`
3. `freeradius/mods-enabled/rest`
4. `api/app/routes/auth.py`
5. `api/app/routes/accounting.py`
6. `api/app/routes/users.py`
7. `api/app/security.py`
8. `api/app/routes/dashboard_api.py`

### Okuma Metni

"Bu bölümde kısa bir code review yapacağım. Buradaki amacım sadece dosya göstermek değil, neden bu yapıyı seçtiğimi açıklamak."

"İlk olarak `docker-compose.yml` dosyasında servislerin orkestrasyonunu görüyoruz. Burada bağımlılıklar, portlar, environment değişkenleri ve healthcheck tanımları var. Bu dosya projenin altyapı omurgasını oluşturuyor."

"İkinci olarak FreeRADIUS tarafına bakıyorum. `sites-enabled/default` içinde authorize, authenticate ve accounting akışını ayrıştırdım. `mods-enabled/rest` ile FreeRADIUS'tan FastAPI'ye hangi verilerin gönderileceğini net şekilde tanımladım. Böylece FreeRADIUS karar motoru olmaktan çok istekleri taşıyan katman haline geldi."

"FastAPI tarafında `auth.py` dosyası authentication mantığını içeriyor. Burada PAP ve MAB desteği birlikte ele alınıyor. Aynı dosyada rate limiting ile entegrasyon bulunuyor."

"`accounting.py` dosyasında Start, Interim-Update ve Stop paketleri işleniyor. Bu dosyanın kritik noktası oturumu hem veritabanına yazması hem de Redis cache'i güncellemesi."

"`users.py` içinde kullanıcıların durumu, aktif session sayıları ve son accounting bilgileri bir araya getiriliyor. Bu kısım dashboard ve izleme ekranı için önemli."

"`security.py` dosyasında API key koruması ve dashboard session doğrulaması var. Burada özellikle logout sonrası eski session cookie'lerinin yeniden kullanılamaması için sunucu tarafı session kontrolü ekledim."

"Son olarak `dashboard_api.py` dosyasında dashboard için login, overview, pulse, logout ve user creation akışları bulunuyor. Bu katman demo ve yönetim deneyimini iyileştiriyor."

### Kısa Kapanış Cümlesi

"Bu code review'de özellikle şunu göstermek istedim: her dosya tek başına değil, AAA akışının bir parçası olarak tasarlandı."

## 10. Güvenlik Değerlendirmesi, Zorluklar ve Kapanış - 1.5 Dakika

### Ekranda

- README
- Dashboard veya terminal

### Okuma Metni

"Projede temel güvenlik önlemleri olarak bcrypt hash, API key koruması, Redis tabanlı rate limiting ve sunucu tarafı dashboard session doğrulaması kullandım. Geliştirme sırasında en dikkat ettiğim konu, FreeRADIUS ile uygulama mantığını temiz biçimde ayırmak oldu. Ayrıca accounting ile aktif session cache'i tutarlı hale getirmek de önemli bir konuydu."

"Karşılaştığım temel zorluklar, RADIUS attribute'larının doğru taşınması, accounting akışının Start, Interim ve Stop boyunca tutarlı kalması ve dashboard tarafında session güvenliğinin doğru yönetilmesiydi. Bunları testler ve smoke senaryoları ile doğruladım."

"Özetle bu projede temel NAC bileşenlerini çalışan, test edilebilir ve genişletilebilir bir yapı halinde kurdum. İzlediğiniz için teşekkür ederim."

## Video İçin Son Tavsiyeler

- Videoda çok hızlı konuşma; özellikle mimari ve code review kısmında yavaşla
- Komutları önceden hazır tut, yazarken zaman kaybetme
- Hata alırsan panik yapma; sistemin nasıl çalıştığını anlattığın sürece bu da hakimiyet göstergesidir
- Dashboard görselini sadece gösterme, veri akışını onun üzerinden anlat
- Code review kısmında ezber cümle kurma; "neden böyle yaptım" yaklaşımıyla konuş

## İstersen Kısa Versiyon

Eğer video uzarsa şunları kısaltabilirsin:

- Dashboard kısmını 2.5 dakikadan 1.5 dakikaya indir
- Code review kısmında dosya sayısını azalt ama `docker-compose.yml`, `auth.py`, `accounting.py`, `security.py` dosyalarını mutlaka göster
- MAB ve PAP demolarında yalnızca bir başarılı, bir başarısız örnek göster
