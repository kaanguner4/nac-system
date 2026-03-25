FROM freeradius/freeradius-server:latest-3.2

# Kendi config dosyalarımızı varsayılanların üstüne kopyala
# Bu sayede pap, preprocess, always vs. varsayılan modüller korunur
COPY clients.conf /etc/freeradius/3.0/clients.conf
COPY mods-enabled/rest /etc/freeradius/3.0/mods-enabled/rest
COPY sites-enabled/default /etc/freeradius/3.0/sites-enabled/default

COPY mods-enabled/rest /etc/freeradius/3.0/mods-available/rest
