-- RADIUS kullanıcı bilgileri 
-- Her satır bir kullanıcı + attribute seti içerir
CREATE TABLE IF NOT EXISTS radcheck (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(64) NOT NULL DEFAULT '',
    attribute   VARCHAR(64) NOT NULL DEFAULT '',
    op          CHAR(2) NOT NULL DEFAULT '==',
    value       VARCHAR(255) NOT NULL DEFAULT ''
);


-- Kullanıcıya dönecek RADIUS attribute'ları
-- ÖRN: VLAN, session timeout, vs.
CREATE TABLE IF NOT EXISTS radreply (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(64) NOT NULL DEFAULT '',
    attribute   VARCHAR(64) NOT NULL DEFAULT '',
    op          CHAR(2) NOT NULL DEFAULT '==',
    value       VARCHAR(255) NOT NULL DEFAULT ''
);

CREATE INDEX idx_radreply_username ON radreply (username);


-- Kullanıcı -> grup ilişkisi 
-- (örneğin: "network-admins" grubu)
CREATE TABLE IF NOT EXISTS radusergroup (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(64) NOT NULL DEFAULT '',
    groupname   VARCHAR(64) NOT NULL DEFAULT '',
    priority    INTEGER     NOT NULL DEFAULT 1
);

CREATE INDEX idx_radusergroup_username ON radusergroup (username);


-- Grup bazlı RADIUS attribute'ları 
-- (örneğin: "network-admins" grubuna özel VLAN10 ataması)
CREATE TABLE IF NOT EXISTS radgroupreply (
    id          SERIAL PRIMARY KEY,
    groupname   VARCHAR(64) NOT NULL DEFAULT '',
    attribute   VARCHAR(64) NOT NULL DEFAULT '',
    op          CHAR(2) NOT NULL DEFAULT '==',
    value       VARCHAR(255) NOT NULL DEFAULT ''
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

CREATE INDEX idx_radacct_username ON radacct (username);
CREATE INDEX idx_radacct_acctsessionid ON radacct (acctsessionid);
CREATE INDEX idx_radacct_acctstarttime ON radacct (acctstarttime);


-- NAS (Network Access Server) bilgileri / Hangi switch/AP sisteme bağlanabilir
CREATE TABLE IF NOT EXISTS nas (
    id          SERIAL PRIMARY KEY,
    nasname     VARCHAR(128) NOT NULL,
    shortname   VARCHAR(32)  DEFAULT NULL,
    type        VARCHAR(30)  DEFAULT 'other',
    ports       INTEGER      DEFAULT NULL,
    secret      VARCHAR(60)  NOT NULL DEFAULT 'secret',
    description VARCHAR(200) DEFAULT NULL
);








-- TEST DATA


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


-- TEST KULLANICILAR
-- NOT: Şifreler ilerleyen adımda hash'lenecek, şimdilik plaintext — sadece test amaçlı
INSERT INTO radcheck (username, attribute, op, value) VALUES
    ('admin01',   'Cleartext-Password', ':=', 'admin123'),
    ('employee01','Cleartext-Password', ':=', 'emp123'),
    ('guest01',   'Cleartext-Password', ':=', 'guest123');


-- Kullanıcı-grup ilişkisi
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
