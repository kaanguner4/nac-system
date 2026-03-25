# NAC Sistemi Teknik Rapor Taslağı

Not: Bu dosya örnek taslaktır. Teslim etmeden önce kendi cümlelerin, kendi gözlemlerin ve kendi değerlendirmelerinle yeniden yazman gerekir. PDF'teki yapay zeka tespit uyarısı nedeniyle bu metni birebir teslim etmek doğru yaklaşım olmaz.

## 1. Giriş

Bu projenin amacı, RADIUS tabanlı temel bir Network Access Control (NAC) sistemi kurmak ve kimlik doğrulama, yetkilendirme ve accounting bileşenlerini çalışan bir bütün halinde göstermektir. NAC sistemleri gerçek dünyada ağa bağlanan kullanıcıların ve cihazların kim olduğunu, hangi ağa erişebileceğini ve bağlantı süresince ne kadar trafik ürettiğini kontrol etmek için kullanılır.

Bu proje kapsamında FreeRADIUS, FastAPI, PostgreSQL ve Redis kullanan çok servisli bir mimari kurulmuştur. FreeRADIUS RADIUS paketlerini kabul eden ana AAA bileşeni olarak çalışırken, FastAPI policy engine katmanı kimlik doğrulama ve yetkilendirme kararlarını üretmektedir. PostgreSQL kalıcı veri katmanını, Redis ise aktif oturum önbelleği ve rate limiting mekanizmasını sağlamaktadır. Tüm sistem Docker Compose üzerinden orkestre edilmiştir.

Bu çalışma ile hedeflenen temel noktalar şunlardır:

- RADIUS tabanlı AAA akışını uçtan uca göstermek
- PAP ve MAB senaryolarını desteklemek
- Kullanıcıyı gruba göre VLAN'a atamak
- Accounting verilerini saklamak ve aktif oturumları hızlı sorgulamak
- Servisleri container tabanlı ve tekrar çalıştırılabilir bir yapıda sunmak

## 2. Mimari Tasarım

Sistemin genel mimarisi dört ana bileşenden oluşmaktadır:

- FreeRADIUS: Authentication, Authorization ve Accounting paketlerini karşılayan RADIUS sunucusu
- FastAPI API: Policy engine, kullanıcı ve oturum mantığının yazıldığı uygulama katmanı
- PostgreSQL: Kullanıcı, grup, VLAN ve accounting kayıtlarının tutulduğu kalıcı veri katmanı
- Redis: Başarısız giriş denemeleri için rate limiting ve aktif session cache katmanı

Veri akışı özetle şu şekildedir:

1. NAS, switch ya da test istemcisi FreeRADIUS'a Access-Request veya Accounting-Request gönderir.
2. FreeRADIUS, `rlm_rest` modülü ile bu isteği FastAPI'ye iletir.
3. FastAPI gerekli kullanıcıyı PostgreSQL'den okur, rate limit bilgisini Redis'ten kontrol eder ve karar üretir.
4. Authorization aşamasında ilgili kullanıcı grubuna göre VLAN attribute'ları dönülür.
5. Accounting paketleri işlendiğinde oturum hem PostgreSQL'e yazılır hem de aktif oturum bilgisi Redis'te tutulur.

Bu mimari ayrımı sayesinde RADIUS sunucusu ile iş mantığı birbirinden ayrılmıştır. Böylece FreeRADIUS yalnızca AAA taşıma katmanı olarak kalırken, politika mantığı Python tarafında daha okunabilir ve genişletilebilir şekilde yönetilmiştir.

## 3. Uygulama Detayları

### 3.1 Docker Compose Altyapısı

Tüm servisler tek bir `docker-compose.yml` dosyasında tanımlanmıştır. Her servis için healthcheck eklenmiş, servisler arası bağımlılıklar tanımlanmış ve veritabanı ile Redis için kalıcı volume kullanılmıştır. Ayrıca servisler arası trafik için ayrılmış bir Docker network kullanılmıştır.

Kullanılan temel image'lar:

- `freeradius/freeradius-server:latest-3.2`
- `postgres:18-alpine`
- `redis:8-alpine`
- `python:3.13-slim`

Bu yapı sayesinde sistem tek komutla ayağa kalkabilmekte ve yeniden üretilebilir bir ortam sunmaktadır.

### 3.2 Authentication

Projede iki authentication yöntemi desteklenmiştir:

#### PAP

PAP senaryosunda kullanıcı adı ve şifre FastAPI'ye iletilir. Kullanıcı bilgisi PostgreSQL `radcheck` tablosundan okunur. Şifreler düz metin olarak tutulmaz; bcrypt hash kullanılır. Doğrulama sırasında girilen parola hash ile karşılaştırılır.

Başarısız girişlerde Redis tabanlı rate limiting çalışır. Aynı kullanıcı için belirli sayıda hatalı deneme sonrası kullanıcı geçici olarak bloklanır. Bu yaklaşım brute-force denemelerini zorlaştırır.

#### MAB

MAB senaryosunda cihazın MAC adresi kullanıcı adı ve kimlik olarak kullanılır. Bu yöntem özellikle 802.1X desteklemeyen yazıcı, IP telefon veya IoT cihazları gibi uçlar için anlamlıdır. Sistemde bilinen MAC adresleri PostgreSQL'de tutulur ve doğrulama `Calling-Station-Id` ile yapılır. Bilinmeyen MAC adresleri için politika olarak reddetme uygulanmıştır.

Bu iki yöntemin birlikte bulunması, ödevde belirtilen minimum gereksinimin üzerine çıkmakta ve bonus puan beklentisini de karşılamaktadır.

### 3.3 Authorization

Başarılı authentication sonrasında kullanıcı grubu belirlenir. Bu gruplar `admin`, `employee` ve `guest` olarak modellenmiştir. VLAN atamaları `radgroupreply` tablosundaki grup bazlı attribute'lar üzerinden yönetilir. Dönülen temel attribute'lar şunlardır:

- `Tunnel-Type`
- `Tunnel-Medium-Type`
- `Tunnel-Private-Group-Id`

Bu tasarım ile kullanıcı doğrudan kendi grubuna ait erişim segmentine yerleştirilir. Örnek olarak:

- admin -> VLAN 10
- employee -> VLAN 20
- guest -> VLAN 30

Yetkilendirme kararlarının FastAPI tarafında üretilmesi, sistemin ileride ACL, zaman bazlı erişim, cihaz tipi bazlı politika gibi ek kurallarla genişletilmesini kolaylaştırır.

### 3.4 Accounting

Accounting tarafında `Start`, `Interim-Update` ve `Stop` paketleri işlenmektedir. Her oturum için aşağıdaki veriler toplanmaktadır:

- kullanıcı adı
- NAS IP bilgisi
- Calling-Station-ID
- Framed IP
- oturum süresi
- input/output octet bilgisi
- başlangıç, güncelleme ve bitiş zamanları

Bu veriler PostgreSQL'deki `radacct` benzeri tabloya yazılır. Aynı anda aktif session bilgisi Redis'e cache'lenir. Bu sayede `/sessions/active` gibi endpoint'ler daha hızlı cevap verebilir.

Accounting mimarisi, gerçek hayatta audit, kapasite planlama, güvenlik takibi ve olay inceleme süreçleri için önemlidir. Bu projede accounting yalnızca kaydetme amacıyla değil, dashboard üzerinden de görünür hale getirilmiştir.

### 3.5 FastAPI Policy Engine

FastAPI tarafı FreeRADIUS ile `rlm_rest` üzerinden haberleşmektedir. Temel endpoint'ler şunlardır:

- `POST /auth`
- `POST /authorize`
- `POST /accounting`
- `GET /users`
- `GET /sessions/active`

Ek olarak proje kapsamında dashboard desteği de eklenmiştir. Dashboard sayesinde aktif kullanıcılar, session bilgileri, grup politikaları ve accounting geçmişi görsel olarak izlenebilmektedir. Bu kısım ödevde zorunlu olmamakla birlikte, sistemin anlaşılmasını kolaylaştıran değerli bir bonus özelliktir.

### 3.6 Test ve Doğrulama

Sistemin doğrulanmasında üç farklı yaklaşım kullanılmıştır:

- `curl` ile FastAPI endpoint testleri
- `radtest` ile PAP authentication testi
- `radclient` ile MAB ve accounting testleri

Ayrıca unit testler ve smoke test scripti ile sistem davranışı tekrar üretilebilir şekilde doğrulanmıştır. Bu yaklaşım, sadece "çalışıyor" demekten daha ileri giderek, sistemin belirli senaryolarda beklenen sonucu verdiğini göstermektedir.

## 4. Güvenlik Değerlendirmesi

Projede uygulanan temel güvenlik önlemleri şunlardır:

- Şifrelerin bcrypt ile hash'lenmesi
- API endpoint'lerinde `X-API-Key` zorunluluğu
- Redis tabanlı rate limiting
- Dashboard oturumlarının sunucu tarafı aktif session kontrolü ile doğrulanması
- Secret bilgilerin `.env` dosyasında tutulması ve git'e eklenmemesi
- Docker servislerinde iç ağ ayrımı ve healthcheck kullanımı

Buna rağmen gerçek dünya bakış açısıyla bazı potansiyel riskler de vardır:

- Bu proje eğitim amaçlı olduğundan yüksek erişilebilirlik, merkezi log yönetimi ve SIEM entegrasyonu gibi kurumsal ihtiyaçlar henüz yoktur.
- NAS envanteri ve istemci doğrulaması daha katı ağ politikalarıyla genişletilebilir.
- Dashboard tarafı için ek olarak rol tabanlı daha ayrıntılı erişim kontrolleri ve ayrıntılı denetim logları eklenebilir.
- Üretim ortamında TLS sonlandırma, secret rotation ve yedekleme stratejileri de düşünülmelidir.

Bu nedenle proje, ödev kapsamını karşılayan sağlam bir temel sunsa da gerçek üretim ortamına geçmeden önce ilave güvenlik ve operasyonel iyileştirmeler gerektirir.

## 5. Gerçek Dünya Uygulamaları

### 5.1 Kurumsal Ağ Güvenliği

Kurumsal yapılarda çalışan cihazları, misafir kullanıcılar ve yönetim sistemleri aynı ağ segmentinde tutulduğunda saldırı yüzeyi ciddi biçimde büyür. NAC sistemleri burada kullanıcıyı ya da cihazı kimliğine göre farklı VLAN'lara yerleştirerek yatay hareket riskini azaltır. Bu proje de admin, employee ve guest ayrımı ile buna benzer bir segmentasyon mantığını göstermektedir.

### 5.2 Eğitim Kurumları

Üniversite veya okul ağlarında öğrenciler, akademisyenler ve idari personel için farklı politikalar tanımlanabilir. Öğrenciler daha kısıtlı internet erişimi alırken, idari personel iç kaynaklara erişebilir. Bu projedeki grup bazlı authorization yapısı böyle bir senaryoya doğrudan uyarlanabilir.

### 5.3 Sağlık Sektörü

Hastane ortamlarında doktor terminalleri, hemşire istasyonları, tıbbi cihazlar ve misafir ağları birbirinden ayrılmalıdır. Özellikle 802.1X desteklemeyen cihazlar için MAB desteği kritik hale gelir. Bu projede MAB desteğinin bulunması, sağlık sektöründeki cihaz tabanlı erişim kontrolü yaklaşımına da örnek oluşturmaktadır.

## 6. Sonuç ve Öğrenilenler

Bu proje, RADIUS tabanlı temel bir NAC sisteminin modern ve modüler araçlarla nasıl kurulabileceğini göstermiştir. FreeRADIUS'ın güçlü AAA altyapısı, FastAPI'nin okunabilir iş mantığı, PostgreSQL'in kalıcı kayıt yeteneği ve Redis'in düşük gecikmeli cache yapısı birlikte kullanılarak anlaşılır ve test edilebilir bir çözüm ortaya çıkarılmıştır.

Bu çalışma sırasında öğrenilen en önemli noktalar şunlardır:

- RADIUS akışında authentication, authorization ve accounting birbirinden ayrı düşünülmelidir.
- Policy mantığını uygulama katmanına taşımak, FreeRADIUS tarafını sade tutar ve geliştirmeyi kolaylaştırır.
- Docker Compose, çok servisli güvenlik projelerinde tekrar üretilebilirlik açısından büyük avantaj sağlar.
- Gerçek değeri olan bir güvenlik sistemi yalnızca erişim vermemeli, erişim kararını gerekçelendirebilmeli ve oturum boyunca iz bırakmalıdır.

Genel olarak bakıldığında proje, ödev kapsamındaki teknik gereksinimleri karşılayan ve üstüne dashboard ile test kapsamı gibi bonus değerler ekleyen bir çalışma haline gelmiştir.

## 7. Kaynaklar

- RFC 2865 - Remote Authentication Dial In User Service (RADIUS)
- RFC 2866 - RADIUS Accounting
- FreeRADIUS resmi dokümantasyonu
- FastAPI resmi dokümantasyonu
- PostgreSQL resmi dokümantasyonu
- Redis resmi dokümantasyonu
- Proje içerisindeki `README.md`, test senaryoları ve konfigürasyon dosyaları
