-- RADIUS kullanıcı kimlik bilgileri
-- Her satır bir kullanıcı + attribute çifti
CREATE TABLE IF NOT EXISTS radcheck (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(64) NOT NULL DEFAULT '',
    attribute   VARCHAR(64) NOT NULL DEFAULT '',
    op          CHAR(2)     NOT NULL DEFAULT '==',
    value       VARCHAR(253) NOT NULL DEFAULT ''
);

CREATE INDEX idx_radcheck_username ON radcheck (username);


-- Kullanıcıya dönecek RADIUS attribute'ları
-- Örn: VLAN, Session-Timeout
CREATE TABLE IF NOT EXISTS radreply (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(64) NOT NULL DEFAULT '',
    attribute   VARCHAR(64) NOT NULL DEFAULT '',
    op          CHAR(2)     NOT NULL DEFAULT '=',
    value       VARCHAR(253) NOT NULL DEFAULT ''
);

CREATE INDEX idx_radreply_username ON radreply (username);


-- Kullanıcı → Grup ilişkisi
CREATE TABLE IF NOT EXISTS radusergroup (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(64) NOT NULL DEFAULT '',
    groupname   VARCHAR(64) NOT NULL DEFAULT '',
    priority    INTEGER     NOT NULL DEFAULT 1
);

CREATE INDEX idx_radusergroup_username ON radusergroup (username);


-- Grup bazlı RADIUS attribute'ları
-- Örn: admin grubuna VLAN 10 ata
CREATE TABLE IF NOT EXISTS radgroupreply (
    id          SERIAL PRIMARY KEY,
    groupname   VARCHAR(64) NOT NULL DEFAULT '',
    attribute   VARCHAR(64) NOT NULL DEFAULT '',
    op          CHAR(2)     NOT NULL DEFAULT '=',
    value       VARCHAR(253) NOT NULL DEFAULT ''
);

CREATE INDEX idx_radgroupreply_groupname ON radgroupreply (groupname);


-- Accounting kayıtları
-- Her oturum için bir satır
CREATE TABLE IF NOT EXISTS radacct (
    radacctid           BIGSERIAL PRIMARY KEY,
    acctsessionid       VARCHAR(64)  NOT NULL DEFAULT '',
    acctuniqueid        VARCHAR(32)  NOT NULL DEFAULT '',
    username            VARCHAR(64)  NOT NULL DEFAULT '',
    nasipaddress        VARCHAR(15)  NOT NULL DEFAULT '',
    nasportid           VARCHAR(15)  DEFAULT NULL,
    nasporttype         VARCHAR(32)  DEFAULT NULL,
    acctstarttime       TIMESTAMPTZ  DEFAULT NULL,
    acctupdatetime      TIMESTAMPTZ  DEFAULT NULL,
    acctstoptime        TIMESTAMPTZ  DEFAULT NULL,
    acctinterval        INTEGER      DEFAULT NULL,
    acctsessiontime     INTEGER      DEFAULT NULL,
    acctinputoctets     BIGINT       DEFAULT 0,
    acctoutputoctets    BIGINT       DEFAULT 0,
    calledstationid     VARCHAR(50)  NOT NULL DEFAULT '',
    callingstationid    VARCHAR(50)  NOT NULL DEFAULT '',
    acctterminatecause  VARCHAR(32)  NOT NULL DEFAULT '',
    acctstatustype      VARCHAR(25)  DEFAULT NULL,
    framedipaddress     VARCHAR(15)  DEFAULT NULL,
    acctstartdelay      INTEGER      DEFAULT NULL
);

CREATE INDEX idx_radacct_username      ON radacct (username);
CREATE INDEX idx_radacct_acctsessionid ON radacct (acctsessionid);
CREATE INDEX idx_radacct_acctstarttime ON radacct (acctstarttime);
CREATE UNIQUE INDEX idx_radacct_acctuniqueid ON radacct (acctuniqueid);

-- NAS (Network Access Server) tanımları
-- Hangi switch/AP sisteme bağlanabilir
CREATE TABLE IF NOT EXISTS nas (
    id          SERIAL PRIMARY KEY,
    nasname     VARCHAR(128) NOT NULL,
    shortname   VARCHAR(32)  DEFAULT NULL,
    type        VARCHAR(30)  DEFAULT 'other',
    ports       INTEGER      DEFAULT NULL,
    secret      VARCHAR(60)  NOT NULL DEFAULT 'secret',
    description VARCHAR(200) DEFAULT NULL
);




-- TEST VERİLERİ

-- Gruplar ve VLAN atamaları
INSERT INTO radgroupreply (groupname, attribute, op, value) VALUES
    ('admin',    'Tunnel-Type',             ':=', '13'),
    ('admin',    'Tunnel-Medium-Type',      ':=', '6'),
    ('admin',    'Tunnel-Private-Group-Id', ':=', '10'),
    ('employee', 'Tunnel-Type',             ':=', '13'),
    ('employee', 'Tunnel-Medium-Type',      ':=', '6'),
    ('employee', 'Tunnel-Private-Group-Id', ':=', '20'),
    ('guest',    'Tunnel-Type',             ':=', '13'),
    ('guest',    'Tunnel-Medium-Type',      ':=', '6'),
    ('guest',    'Tunnel-Private-Group-Id', ':=', '30');


-- Test kullanıcıları
-- NOT: Şifreler ilerleyen adımda hash'lenecek, şimdilik plaintext — sadece test amaçlı
INSERT INTO radcheck (username, attribute, op, value) VALUES
    ('admin01',    'Cleartext-Password', ':=', '$2b$12$x1HaTP3nOMhMsZur.X5Vv.nCev084dXAvcNPqbnxgiDKoj9Qc0fEa'),
    ('employee01', 'Cleartext-Password', ':=', '$2b$12$.0QK6HXf41x1O.jA8ESfjeDTtP7yrhaSKoBZimAkRT74hiiCjfUZG'),
    ('guest01',    'Cleartext-Password', ':=', '$2b$12$WUd3tljzZGFxpH3lHEbH6u0.jQp//A0ekkdnhsMzrdtlqCSz7tFUG');


-- Kullanıcıları gruplara bağla
INSERT INTO radusergroup (username, groupname, priority) VALUES
    ('admin01',    'admin',    1),
    ('employee01', 'employee', 1),
    ('guest01',    'guest',    1);


-- Test NAS tanımı (docker ortamı için)
INSERT INTO nas (nasname, shortname, secret, description) VALUES
    ('127.0.0.1', 'localhost', 'testing123', 'Local test NAS');


-- MAB test cihazları (MAC adresi tabanlı)
INSERT INTO radcheck (username, attribute, op, value) VALUES
    ('aa:bb:cc:dd:ee:ff', 'Cleartext-Password', ':=', 'aa:bb:cc:dd:ee:ff');

INSERT INTO radusergroup (username, groupname, priority) VALUES
    ('aa:bb:cc:dd:ee:ff', 'employee', 1);