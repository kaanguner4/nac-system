# NAC Sistemi — Teknik Proje Raporu
### ⚠️ NOT: Bu dosya bir taslaktır. Kendi cümlelerinle ve kendi analizinle yeniden yazmalısın. Doğrudan teslim etme — AI tespit sistemi %25 üzerinde AI içeriği olan raporları eliyor.

---

## 1. Giriş

Bu proje, RADIUS protokolü (RFC 2865 ve RFC 2866) üzerine kurulu, tam AAA (Authentication, Authorization, Accounting) desteği sunan bir Network Access Control sistemidir. Amaç; kurumsal ağlara bağlanmak isteyen kullanıcıları ve cihazları merkezi olarak doğrulamak, her kullanıcıya ait grubu ve VLAN politikasını dinamik olarak belirlemek ve tüm oturum verilerini kayıt altına almaktır.

Geliştirme sürecinde dört farklı servis bir arada çalışacak şekilde tasarlandı: FreeRADIUS kimlik doğrulama sunucusu olarak görev yaparken, Python ile yazılan FastAPI uygulaması policy engine rolünü üstlendi. PostgreSQL kalıcı veri deposu olarak, Redis ise oturum önbelleği ve rate-limiting mekanizması olarak kullanıldı. Tüm bu bileşenler Docker Compose ile tek komutla ayağa kaldırılacak şekilde yapılandırıldı.

---

## 2. Mimari Tasarım

Sistemin genel mimarisi üç katmana ayrılmaktadır.

**Birinci katman — Erişim katmanı:** NAS (Network Access Server) ya da test araçları (radtest, radclient) RADIUS protokolü üzerinden FreeRADIUS'a kimlik doğrulama ve accounting istekleri gönderir. FreeRADIUS bu istekleri UDP port 1812 (auth) ve 1813 (accounting) üzerinden dinler.

**İkinci katman — Policy engine:** FreeRADIUS, `rlm_rest` modülü sayesinde her karar için FastAPI uygulamasına HTTP isteği gönderir. Kimlik doğrulama kararı `/auth` endpoint'inden, VLAN/policy ataması `/authorize` endpoint'inden, oturum kaydı ise `/accounting` endpoint'inden alınır. Bu yaklaşımın temel avantajı, FreeRADIUS'u soyut bir iletici olarak konumlandırması ve tüm iş mantığını Python tarafında yönetmeye imkân tanımasıdır.

**Üçüncü katman — Veri katmanı:** FastAPI, kimlik doğrulama sorguları için PostgreSQL'e, aktif oturum sorguları için Redis'e başvurur. PostgreSQL kalıcı ve güvenilir kayıt tutarken Redis hızlı erişim gerektiren oturum durumu için cache görevi görür.

```
NAS / radtest / radclient
        │  UDP 1812/1813
        ▼
  ┌──────────────┐
  │  FreeRADIUS  │  ──── rlm_rest (HTTP) ────▶  FastAPI :8000
  └──────────────┘                                  │        │
                                                    ▼        ▼
                                               PostgreSQL   Redis
```

**Veri akışı — PAP authentication örneği:**
1. NAS, kullanıcı adı ve şifre ile `Access-Request` gönderir.
2. FreeRADIUS `authorize` adımında `/authorize` çağırır → FastAPI VLAN attribute'larını döner.
3. FreeRADIUS `authenticate` adımında `/auth` çağırır → FastAPI bcrypt hash doğrulaması yapar.
4. Başarılı ise `Access-Accept` + `Tunnel-Private-Group-Id` cevabı NAS'a iletilir.
5. NAS `Accounting-Start` paketi gönderir → `/accounting` endpoint'i Redis ve PostgreSQL'e yazar.

---

## 3. Uygulama Detayları

### 3.1 FreeRADIUS Yapılandırması

FreeRADIUS üç konfigürasyon dosyasıyla özelleştirildi:

**`clients.conf`:** Hangi IP adreslerinden gelen RADIUS isteklerinin kabul edileceğini tanımlar. `localhost` ve Docker bridge ağı (`172.0.0.0/8`) için ayrı client tanımı yapılmıştır. Her iki client da `require_message_authenticator = yes` ile güvenlik seviyesi artırılmış haldedir.

**`mods-enabled/rest`:** `rlm_rest` modülü; authenticate, authorize ve accounting işlemleri için FastAPI'ye ne zaman, hangi endpoint'e, hangi JSON gövdesiyle istek atacağını tanımlar. Bağlantı havuzu 10 bağlantıya kadar çıkacak şekilde ayarlanmıştır.

**`sites-enabled/default`:** Sanal sunucu politikası. `authorize` adımında REST çağrısı yapılır ve VLAN attribute'ları alınır. `Auth-Type PAP` olarak belirlenerek `authenticate` adımında yine REST üzerinden şifre doğrulaması yaptırılır. `post-auth` adımında ise reddedilen bağlantılar için `Reply-Message = "Access denied"` yazılır.

### 3.2 FastAPI Policy Engine

Uygulama beş ana modüle ayrılmıştır:

**`routes/auth.py` — `/auth` ve `/authorize`:**
`/auth` endpoint'i gelen isteği önce Redis'te rate-limit kontrolünden geçirir. Ardından PostgreSQL'den kullanıcı kaydını çeker. MAB tespiti `password == calling_station_id` koşuluyla yapılır; eğer bu koşul sağlanıyorsa veritabanında `Device-MAC` attribute'ü karşılaştırılır, aksi halde bcrypt `checkpw` ile şifre doğrulanır. `/authorize` endpoint'i ise kullanıcının grubunu bularak o gruba ait VLAN attribute'larını `rlm_rest` formatında döner.

**`routes/accounting.py` — `/accounting`:**
`Start`, `Interim-Update` ve `Stop` paket türlerini işler. PostgreSQL'e `ON CONFLICT (acctuniqueid)` ile upsert yapar; bu sayede aynı oturuma ait tüm güncellemeler tek satır üzerinde tutulur. Redis cache'i `Start`/`Interim-Update`'te yazar, `Stop`'ta siler.

**`routes/users.py` — `/users` ve `/sessions/active`:**
`/users` endpoint'i PostgreSQL'deki tüm kullanıcıları Redis'teki blok durumu ve aktif oturum bilgisiyle birleştirerek döner. `/sessions/active` PostgreSQL'i kaynak-of-truth olarak kullanır; sadece `acctstoptime IS NULL` olan oturumları listeler. Redis'te olup DB'de olmayan oturumlar orphan olarak işaretlenir.

**`db/redis.py` — Rate Limiting:**
5 başarısız denemede `fail:{username}` sayacı `blocked:{username}` key'ine dönüşür. Blok süresi 15 dakikadır. `KEYS` komutu yerine `scan_iter` kullanılarak Redis'in blocklanması önlendi.

**`security.py` — API Key ve Session Yönetimi:**
FreeRADIUS'tan gelen tüm istekler `X-API-Key` header'ı ile doğrulanır; karşılaştırma `hmac.compare_digest` ile timing-safe şekilde yapılır. Dashboard oturumları için `API_SECRET_KEY:dashboard` türevi ile HMAC-SHA256 imzalı token üretilir ve `HttpOnly` cookie'de saklanır.

### 3.3 Veritabanı Şeması

| Tablo | İşlev |
|---|---|
| `radcheck` | bcrypt hash veya MAC adresi (attribute: `Password-Hash` / `Device-MAC`) |
| `radusergroup` | Kullanıcı → grup eşleşmesi |
| `radgroupreply` | Gruba ait RADIUS reply attribute'ları (Tunnel-Type, VLAN ID vb.) |
| `radreply` | Kullanıcıya özel reply attribute'lar |
| `radacct` | Accounting kayıtları; `acctuniqueid` üzerinde unique index |

`radacct` tablosundaki `INSERT ... ON CONFLICT DO UPDATE` ifadesinde `acctstoptime` için `ELSE radacct.acctstoptime` kullanılmıştır. Bu kritik detay sayesinde bir oturumun stop zamanı, sonradan gelen Interim-Update paketleriyle sıfırlanmaz.

### 3.4 Docker Compose Altyapısı

Dört servisin tamamı `nac_network` adlı bridge ağında izole şekilde haberleşmektedir. Dışarıya yalnızca `8000/TCP` (FastAPI), `1812/UDP` ve `1813/UDP` (RADIUS) açıktır. Her servis için `healthcheck` tanımlandı; servis bağımlılıkları `depends_on: condition: service_healthy` ile yönetildiğinden FreeRADIUS, FastAPI tamamen ayağa kalkmadan başlamaz.

---

## 4. Güvenlik Değerlendirmesi

### Alınan Önlemler

**Şifre saklama:** Kullanıcı şifrelerinin hiçbiri düz metin olarak saklanmaz. Tüm şifreler `bcrypt` ile `cost=12` ayarında hash'lenir. Bu değer, brute-force saldırılarını yavaşlatmak için bilinçli seçilmiştir.

**Rate limiting:** Aynı kullanıcı adından 5 dakika içinde 5 başarısız giriş denemesi yapıldığında hesap 15 dakika süreyle bloke edilir. Bu mekanizma Redis'te `fail:{username}` ve `blocked:{username}` key'leriyle tutulmakta ve her başarılı girişte sıfırlanmaktadır.

**API key doğrulama:** FreeRADIUS'tan FastAPI'ye gelen tüm istekler `X-API-Key` header'ı ile doğrulanır. Karşılaştırma `hmac.compare_digest` kullanılarak timing saldırılarına karşı güvenli hâle getirilmiştir.

**SQL injection önlemi:** PostgreSQL sorguları `asyncpg` kütüphanesi üzerinden parameterized (`$1`, `$2`, ...) formatta çalıştırılmaktadır.

**Session güvenliği:** Dashboard oturumları HMAC-SHA256 imzalı token ile yönetilir. Her token'a `exp` (expiration) alanı eklenerek 12 saatlik geçerlilik süresi kısıtlanmıştır. Cookie `HttpOnly` olarak işaretlenmiştir.

**Redis session doğrulaması:** Dashboard cookie'si geçerli olsa bile, Redis'te aktif oturum kaydı bulunamazsa istek 401 ile reddedilir. Bu sayede logout sonrasında eski cookie'ler geçersiz hâle gelir.

### Tespit Edilen ve Giderilen Riskler

| Risk | Çözüm |
|---|---|
| `KEYS` komutu Redis'i bloklar | `scan_iter` ile değiştirildi |
| `secure=True` cookie HTTP'de çalışmaz | `HTTPS_ENABLED` env değişkenine bağlandı |
| `acctstoptime` Interim-Update'te NULL'a düşüyordu | `ELSE radacct.acctstoptime` ile düzeltildi |
| employee01 hash yanlıştı | Yeniden üretilip güncellendi |

### Kalan Riskler

**API key dual-use:** `API_SECRET_KEY` hem RADIUS isteği doğrulaması hem de dashboard session imzalaması için kullanılmaktadır. İdealde bu iki amaca ayrı secret'lar atanmalıdır.

**HTTPS eksikliği:** FreeRADIUS ile FastAPI arasındaki HTTP trafiği Docker iç ağı üzerinden akar. Bu Docker bridge ağı dışarıya kapalı olduğundan kabul edilebilir bir risk olarak değerlendirilmiştir; ancak prodüksiyona alınacak bir sistemde TLS zorunludur.

**clients.conf geniş subnet:** Docker bridge ağının tamamı (`172.0.0.0/8`) tanımlanmıştır. Prodüksiyonda tam subnet belirlenmesi güvenliği artırır.

---

## 5. Gerçek Dünya Kullanım Alanları

### Kurumsal Ağ Güvenliği

Büyük ölçekli şirketlerde çalışanlar, ziyaretçiler ve yöneticiler aynı fiziksel ağ altyapısını kullanır; ancak her birinin farklı kaynaklara erişim yetkisi vardır. NAC sistemi bu senaryoda her kullanıcıyı kimliğine göre doğru VLAN'a yönlendirir. Örneğin muhasebe departmanı çalışanı VLAN 20'ye (kurumsal ağ) düşerken misafir VLAN 30'a (yalnızca internet erişimi) yönlendirilebilir. Bu proje tam olarak bu senaryoyu admin/employee/guest grupları ve VLAN 10/20/30 atamaları ile modellemektedir.

### Eğitim Kurumları

Üniversitelerde öğrenciler, öğretim görevlileri ve idari personel farklı ağ kaynaklarına ihtiyaç duyar. Öğrenciler yalnızca internet ve öğrenci bilgi sistemlerine erişebilirken, akademik personel araştırma sunucularına ve iç kaynaklara ulaşabilmelidir. MAB özelliği sayesinde baskı gibi cihazlar 802.1X desteklemese bile ağa güvenli şekilde dahil edilebilir.

---

## 6. Sonuç ve Öğrenilenler

Bu proje sürecinde en zorlu kısım FreeRADIUS ile FastAPI arasındaki `rlm_rest` entegrasyonuydu. FreeRADIUS'un iç akış sırasını (authorize → authenticate → accounting) ve her adımda hangi attribute'ların mevcut olduğunu anlamak, birçok deneme-yanılma sürecini gerektirdi.

MAB tespitini FreeRADIUS seviyesinde değil FastAPI içinde `password == calling_station_id` kontrolüyle yapmak, tek bir `/auth` endpoint'inin hem PAP hem MAB kararlarını vermesini sağladı. Bu tasarım kararı FreeRADIUS konfigürasyonunu sade tuttu.

Redis'in salt önbellek olarak değil, rate-limiting mekanizması olarak da kullanılması; `blocked:{username}` ve `fail:{username}` şeklinde namespace ayrımı yapılarak gerçekleştirildi. Bu pattern Redis'te yaygın bir yaklaşım olmasına karşın `KEYS` ile `SCAN` arasındaki farkı pratikte deneyimlemek — `KEYS`'in blocking bir O(N) komut olduğunu — öğretici oldu.

Geliştirme sürecinde PostgreSQL'deki `ON CONFLICT DO UPDATE` ifadesinde `acctstoptime` alanının `ELSE NULL` yazılmış olması, Stop kaydının ardından gelen paketlerin stop zamanını sıfırladığı ince bir bug'a yol açtı. `ELSE radacct.acctstoptime` ile var olan değer korunarak düzeltildi.

---

## 7. Kaynaklar

- RFC 2865 — Remote Authentication Dial In User Service (RADIUS): https://datatracker.ietf.org/doc/html/rfc2865
- RFC 2866 — RADIUS Accounting: https://datatracker.ietf.org/doc/html/rfc2866
- FreeRADIUS Documentation: https://www.freeradius.org/documentation/
- FreeRADIUS `rlm_rest` Module: https://github.com/FreeRADIUS/freeradius-server/tree/master/src/modules/rlm_rest
- FastAPI Documentation: https://fastapi.tiangolo.com/
- asyncpg Documentation: https://magicstack.github.io/asyncpg/
- Docker Compose Reference: https://docs.docker.com/compose/
- bcrypt Algorithm — Provos & Mazières (1999): https://www.usenix.org/legacy/events/usenix99/provos/provos.pdf
