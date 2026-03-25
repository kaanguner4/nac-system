# Video Okuma Metni — NAC Sistemi
### Tahmini süre: 15–20 dakika
### Notlar: [...] = ekranda gösterilecek şey | (PAUSE) = kısa dur | **BOLD** = vurgulanacak kelime

---

## BÖLÜM 1 — Açılış ve Giriş (≈ 1 dk)

Merhaba. Bu videoda S3M Security staj değerlendirme ödevi kapsamında geliştirdiğim **Network Access Control** sistemini anlatacağım.

Sistem; RADIUS protokolü üzerine kurulu, FreeRADIUS, FastAPI, PostgreSQL ve Redis bileşenlerinden oluşuyor. Tüm altyapı Docker Compose ile tek komutla ayağa kaldırılabiliyor.

Videoyu şu sırayla ilerleteceğim: önce mimari diyagram, ardından Docker Compose yapısı, sonra canlı auth testleri, accounting ve dashboard gösterimi, son olarak kod incelemesi ve aldığım tasarım kararları.

---

## BÖLÜM 2 — Mimari Diyagram (≈ 2.5 dk)

[Ekranda mimari diyagram açık]

Sistemi üç katman olarak düşünebiliriz.

**Birinci katman — erişim katmanı.** Bir NAS — yani ağ anahtarı veya bir test aracı — kimlik doğrulama yapmak istediğinde RADIUS protokolü üzerinden, UDP port 1812'ye Access-Request paketi gönderir. Accounting için ise port 1813 kullanılır.

**İkinci katman — FreeRADIUS.** Bu paketleri dinleyen FreeRADIUS, her karar için doğrudan veritabanına bakmak yerine **rlm_rest modülü** aracılığıyla FastAPI'ye HTTP isteği gönderir. Yani FreeRADIUS burada bir delege gibi davranıyor — asıl iş mantığı Python tarafında.

(PAUSE)

**Üçüncü katman — veri.** FastAPI, kimlik doğrulama için PostgreSQL'e, aktif oturum sorguları için Redis'e başvurur. PostgreSQL kalıcı veri deposu, Redis ise hız gerektiren oturum cache'i ve rate-limiting için kullanılıyor.

Önemli bir nokta: FreeRADIUS ile FastAPI arasındaki bu ayrım, RADIUS protokolü bilmeden policy mantığını düz Python'da yazabilmeme imkân tanıdı. RADIUS tarafı sabit kalırken iş kuralları FastAPI'de kolayca değiştirilebilir.

---

## BÖLÜM 3 — Docker Compose Yapısı (≈ 2 dk)

[Ekranda docker-compose.yml açık]

`docker-compose.yml` dosyasına bakıyorum.

Dört servis tanımlı: `postgres`, `redis`, `api`, `freeradius`. Hepsinin ortak noktası `nac_network` bridge ağında haberleşmeleri. Dışarıya sadece üç port açık: FastAPI için 8000, RADIUS auth için 1812 ve accounting için 1813.

[`healthcheck` bloğuna kaydır]

Her servis için `healthcheck` tanımlı. Bu kritik çünkü `depends_on: condition: service_healthy` kullandım. FreeRADIUS başlamadan önce FastAPI'nin gerçekten hazır olduğunu bekliyor. PostgreSQL'in hazır olmadığı durumda FastAPI hata vermemesi için aynı mekanizma postgres → api bağımlılığında da var.

[`.env.example` aç]

Gizli bilgiler — şifreler ve API key — `.env` dosyasında tutuluyor ve bu dosya `.gitignore`'a eklenmiş durumda. Repoya commit edilmiyor.

[`docker compose ps` çalıştır]

```
docker compose ps
```

Dört servis de healthy durumda görülüyor.

---

## BÖLÜM 4 — Authentication: PAP Testi (≈ 2.5 dk)

[Terminal açık]

**PAP authentication** akışını `radtest` ile gösteriyorum.

```
docker exec nac_freeradius sh -lc \
  'radtest admin01 admin123 127.0.0.1 0 "$RADIUS_SHARED_SECRET"'
```

[Çıktı bekle]

`Access-Accept` aldık. Ve `Tunnel-Private-Group-Id = "10"` döndü — bu admin grubunun VLAN'ı.

Şimdi employee01 ile deneyelim:

```
docker exec nac_freeradius sh -lc \
  'radtest employee01 employee123 127.0.0.1 0 "$RADIUS_SHARED_SECRET"'
```

Burada VLAN 20 dönüyor. guest01 için VLAN 30 olacak.

(PAUSE)

Yanlış şifre ile ne oluyor?

```
docker exec nac_freeradius sh -lc \
  'radtest admin01 yanlis 127.0.0.1 0 "$RADIUS_SHARED_SECRET"'
```

`Access-Reject` ve `Reply-Message = "Access denied"`. Bu yanıt FreeRADIUS'un `post-auth REJECT` bloğundan geliyor.

[FastAPI log ekrana gel veya curl ile göster]

Şifre doğrulamasının nerede yapıldığını göstermek için curl ile `/auth` endpoint'ini çağırıyorum:

```
curl -s -X POST http://localhost:8000/auth \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_SECRET_KEY" \
  -d '{"username":"admin01","password":"yanlis"}' | python3 -m json.tool
```

`result: reject`, `reason: wrong_password` dönüyor. Bu yanıt FastAPI `/auth` endpoint'inden geliyor — FreeRADIUS bunu alıyor ve Access-Reject'e dönüştürüyor.

---

## BÖLÜM 5 — Authentication: MAB Testi (≈ 2 dk)

[Terminal]

**MAC Authentication Bypass** — 802.1X desteklemeyen cihazlar için. Yazıcılar, IP telefonlar gibi düşün.

MAB'da kullanıcı adı ve şifre yerine cihazın MAC adresi gönderiliyor. `radclient` ile gösteriyorum çünkü `radtest` özel attribute gönderemez:

```
docker exec nac_freeradius sh -lc '
  printf "User-Name = \"aa:bb:cc:dd:ee:ff\"\n
User-Password = \"aa:bb:cc:dd:ee:ff\"\n
Calling-Station-Id = \"aa:bb:cc:dd:ee:ff\"\n
NAS-IP-Address = 127.0.0.1\n" \
  | radclient -x 127.0.0.1 auth "$RADIUS_SHARED_SECRET"'
```

`Access-Accept` ve VLAN 20 döndü. Bu cihaz veritabanında kayıtlı ve employee grubunda.

Şimdi kayıtlı olmayan bir MAC deneyelim:

```
docker exec nac_freeradius sh -lc '
  printf "User-Name = \"de:ad:be:ef:00:01\"\n
User-Password = \"de:ad:be:ef:00:01\"\n
Calling-Station-Id = \"de:ad:be:ef:00:01\"\n
NAS-IP-Address = 127.0.0.1\n" \
  | radclient -x 127.0.0.1 auth "$RADIUS_SHARED_SECRET"'
```

`Access-Reject`. Bilinmeyen MAC adresi için varsayılan politika red.

(PAUSE)

MAB tespiti FastAPI'de nasıl yapılıyor? `password == calling_station_id` koşuluna bakıyorum. Eğer bu iki değer eşitse istek MAB olarak değerlendiriliyor ve veritabanında `Device-MAC` attribute'ü karşılaştırılıyor. Bu sayede tek bir `/auth` endpoint'i hem PAP hem MAB kararlarını veriyor.

---

## BÖLÜM 6 — Accounting Testi (≈ 2 dk)

[Terminal]

RADIUS accounting, oturum boyunca üç paketten oluşur: **Start**, **Interim-Update** ve **Stop**.

Start paketi:

```
docker exec nac_freeradius sh -lc '
  printf "Acct-Status-Type = Start\nUser-Name = \"guest01\"\n
Acct-Session-Id = \"demo-sess-01\"\nNAS-IP-Address = 10.0.0.20\n
Calling-Station-Id = \"cc:cc:cc:cc:cc:cc\"\nFramed-IP-Address = 192.168.1.30\n
Acct-Session-Time = 0\nAcct-Input-Octets = 0\nAcct-Output-Octets = 0\n" \
  | radclient -x 127.0.0.1:1813 acct "$RADIUS_SHARED_SECRET"'
```

`Accounting-Response` aldık. Şimdi aktif oturumlara bakıyorum:

```
curl -s http://localhost:8000/sessions/active \
  -H "X-API-Key: $API_SECRET_KEY" | python3 -m json.tool
```

`demo-sess-01` session_id'si aktif oturumlarda görünüyor.

Stop paketi:

```
docker exec nac_freeradius sh -lc '
  printf "Acct-Status-Type = Stop\nUser-Name = \"guest01\"\n
Acct-Session-Id = \"demo-sess-01\"\nNAS-IP-Address = 10.0.0.20\n
Acct-Session-Time = 180\nAcct-Input-Octets = 1024\nAcct-Output-Octets = 2048\n" \
  | radclient -x 127.0.0.1:1813 acct "$RADIUS_SHARED_SECRET"'
```

Tekrar `/sessions/active` çağırınca `demo-sess-01` artık görünmüyor — Redis cache'ten silindi.

---

## BÖLÜM 7 — Dashboard Simülasyonu (≈ 3 dk)

[Tarayıcı: http://localhost:8000/dashboard]

Dashboard'u açıyorum. Boot animasyonu çalışıyor — bu sırada sisteme bağlanmaya çalışıyor.

[Login ekranı geldi]

Login ekranında hızlı giriş butonları var: admin, employee, guest ve MAB. Bunlar test kullanıcılarının bilgilerini otomatik dolduruyor.

**Admin ile giriş:**

[Admin butonuna tık, login]

Handshake animasyonu — FreeRADIUS akışını görselleştiriyor: Access-Request, Authorize, Authenticate, Accounting-Start adımları sırayla gösteriliyor.

[Dashboard ekranı geldi]

Admin panelinde tüm kullanıcılar görünüyor: admin01, employee01, guest01 ve MAB cihazı. Aktif oturum sayısı, bloklu kullanıcılar, VLAN politika haritası mevcut.

[Sağ tarafta RADIUS attribute tablosu]

Sağda bu kullanıcının sahip olduğu RADIUS attribute'ları görünüyor: `Tunnel-Type = VLAN (13)`, `Tunnel-Medium-Type = IEEE-802 (6)`, `Tunnel-Private-Group-Id = 10`.

[Admin shell'e kaydır]

Admin olarak yeni kullanıcı oluşturabiliyorum. Yeni bir PAP kullanıcısı ekliyorum:

[username: testuser, group: employee, password: test123, Oluştur]

Kullanıcı listesine eklendi. Şimdi bu kullanıcı ile radtest yapabilirim.

(PAUSE)

**Employee ile giriş yapıyorum:**

[Logout → employee login]

Employee girişinde sadece kendi oturumunu görüyor, diğer kullanıcıları değil. Bu `_filter_overview_for_viewer` fonksiyonundan kaynaklanıyor — admin olmayan kullanıcılara sadece kendi verisi filtrelenerek döndürülüyor.

---

## BÖLÜM 8 — Kod İncelemesi (≈ 3.5 dk)

### 8.1 FreeRADIUS Konfigürasyonu

[Editörde `freeradius/sites-enabled/default` açık]

`sites-enabled/default` dosyasına bakıyorum. Üç önemli blok var.

`authorize` bloğunda önce `filter_username` çalışır, sonra REST çağrısı yapılır. Bu çağrı `/authorize` endpoint'ine gider ve VLAN attribute'larını alır. `if (&User-Password)` koşuluyla `Auth-Type := PAP` set edilir — bu satır kritik çünkü FreeRADIUS'a "bu isteği PAP olarak doğrula" demiş oluyor.

`authenticate` bloğunda `Auth-Type PAP` altında REST çağrısı `/auth`'a gider. Şifre doğrulama kararı buradan alınıyor.

[`mods-enabled/rest` aç]

REST modülünde her endpoint için hangi JSON gövdesinin gönderileceği tanımlı. Accounting için `Acct-Status-Type`, `Acct-Session-Id`, `Acct-Session-Time`, input/output octets gibi tüm önemli attribute'lar JSON olarak iletiliyor.

### 8.2 FastAPI — `/auth` Endpoint'i

[Editörde `routes/auth.py` açık]

`authenticate` fonksiyonuna bakıyorum. Beş adım var:

1. Redis rate-limit kontrolü — `check_rate_limit(username)`.
2. MAB tespiti — `password == calling_station_id and calling_station_id != ""`.
3. `get_user(username)` — PostgreSQL'den `Password-Hash` veya `Device-MAC` attribute'unu çek.
4. MAB ise MAC karşılaştırması, değilse `bcrypt.checkpw`.
5. Başarılıysa `reset_failed_attempts`, başarısızsa `increment_failed_attempts`.

Buradaki tasarım kararı şu: MAB ve PAP kararları aynı endpoint'ten verildiği için FreeRADIUS konfigürasyonu sade kalıyor, yeni bir auth metodu eklemek istesem sadece Python tarafını değiştirmem yeterli.

### 8.3 PostgreSQL — `insert_accounting`

[`db/postgres.py` — `insert_accounting` fonksiyonu]

`ON CONFLICT (acctuniqueid)` ile upsert yapılıyor. `acctuniqueid` FreeRADIUS'un ürettiği benzersiz oturum kimliği.

`acctstoptime` için `CASE WHEN acctstatustype = 'Stop' THEN NOW() ELSE radacct.acctstoptime END` ifadesine dikkat çekmek istiyorum. Başlangıçta burada `ELSE NULL` yazıyordu — bu ciddi bir bug'dı. Bir Interim-Update paketi geldiğinde oturumun stop zamanını NULL'a sıfırlıyordu ve oturum tekrar "aktif" görünüyordu. `radacct.acctstoptime` ile mevcut değer korunarak düzeltildi.

### 8.4 Redis — Rate Limiting ve SCAN

[`db/redis.py`]

`_scan_keys` yardımcı fonksiyonuna bakıyorum. Başlangıçta `r.keys("session:*")` kullanıyordum. Redis'te `KEYS` komutu O(N) blocking bir komuttur — tüm key alanını tarar ve Redis'i başka isteklere kapattığı için prodüksiyonda ciddi gecikmelere yol açar. `scan_iter` ise iterator tabanlı çalışır, büyük key setlerinde bile Redis'i bloklamaz.

---

## BÖLÜM 9 — Zorluklar ve Çözümler (≈ 1.5 dk)

Bu projede karşılaştığım üç önemli zorluktan bahsetmek istiyorum.

**Birinci zorluk — FreeRADIUS iç akışını anlamak.** `authorize` ve `authenticate` adımlarının ne zaman çalıştığını, `Auth-Type`'ın nasıl set edildiğini anlamak başlangıçta kafa karıştırıcıydı. FreeRADIUS'u `radiusd -X` debug moduyla çalıştırarak her adımda hangi modülün devreye girdiğini incelemek çok yardımcı oldu.

**İkinci zorluk — employee01 hash sorunu.** `init.sql`'deki bcrypt hash'in yanlış üretilmiş olduğunu, yani veritabanındaki hash'in `employee123` şifresine karşılık gelmediğini fark ettim. Bunu `bcrypt.checkpw` ile doğrulayarak tespit ettim ve hash'i yeniden üretip hem veritabanını güncelledim hem de `init.sql`'i düzelttim.

**Üçüncü zorluk — `acctstoptime` bug'ı.** Daha önce anlattığım SQL bug'ı. İlk başta fark etmek zor oldu çünkü normal akışta (Start → Interim → Stop sırasıyla) ortaya çıkmıyordu. Kenar senaryoları düşünürken tespit ettim.

---

## BÖLÜM 10 — Kapanış (≈ 30 sn)

Smoke testini çalıştırarak bitirmek istiyorum:

```
sh tests/smoke_radius.sh
```

7/7 test geçti.

Bu proje RADIUS protokolü, AAA mimarisi, FreeRADIUS konfigürasyonu, async Python geliştirme ve Docker ile çoklu servis yönetimi konularında pratik deneyim kazanmamı sağladı. İzlediğiniz için teşekkürler.

---

## Ekstra — Sık Sorulabilecek Sorular (Hazırlık için)

**S: Neden rlm_sql yerine rlm_rest kullandın?**
C: `rlm_sql` ile FreeRADIUS doğrudan veritabanına bağlanır. Bu çalışır ama tüm iş mantığı SQL sorgularına ve FreeRADIUS konfigürasyonuna gömülü kalır. `rlm_rest` ile policy mantığı FastAPI'de Python'da yazıldığı için test edilmesi, değiştirilmesi ve genişletilmesi çok daha kolay.

**S: Redis neden sadece cache değil de rate limiting için de kullandın?**
C: Redis'in `TTL` desteği rate limiting için idealdir. `fail:{username}` key'ini 5 dakika TTL ile set ediyorum — 5 dakika geçince otomatik sıfırlanıyor. `blocked:{username}` key'ini 15 dakika TTL ile set ediyorum — blok süresi dolunca key silinip kullanıcı otomatik açılıyor. Ayrı bir scheduler'a gerek yok.

**S: bcrypt cost=12 neden seçildi?**
C: bcrypt cost factor ikiye katlandıkça hesaplama süresi de iki katına çıkar. Cost=10 yaklaşık 100ms, cost=12 yaklaşık 400ms sürer. Bu değer, meşru bir kullanıcı için fark edilmez düzeyde iken brute-force saldırılarını önemli ölçüde yavaşlatır.

**S: `acctuniqueid` boş gelirse ne olur?**
C: FreeRADIUS bazı durumlarda `Acct-Unique-Session-Id`'yi boş gönderebilir. `accounting.py`'de `effective_unique_id = req.unique_id or req.session_id` satırıyla fallback olarak `Acct-Session-Id` kullanılıyor.
