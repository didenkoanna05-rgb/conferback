-- Схема бази даних ConferBack (SQLite)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT    NOT NULL UNIQUE,
    full_name     TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1
);

-- Одна людина може мати кілька ролей (табл. 3.1)
CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role    TEXT    NOT NULL CHECK (role IN ('head', 'marketer', 'manager', 'rep')),
    PRIMARY KEY (user_id, role)
);

-- Довідники, які розширюються без зміни коду (ДВ-10)
CREATE TABLE IF NOT EXISTS cost_categories (
    id        INTEGER PRIMARY KEY,
    name      TEXT    NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS criteria (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    hint        TEXT,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    city        TEXT,
    address     TEXT,
    start_date  DATE    NOT NULL,
    end_date    DATE    NOT NULL,
    goal        TEXT,
    has_booth   INTEGER NOT NULL DEFAULT 1,
    currency    TEXT    NOT NULL DEFAULT 'USD',
    close_rate  REAL    CHECK (close_rate IS NULL OR (close_rate >= 0 AND close_rate <= 1)),
    avg_deal    REAL    CHECK (avg_deal IS NULL OR avg_deal >= 0),
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (end_date >= start_date)
);

CREATE TABLE IF NOT EXISTS cost_items (
    id          INTEGER PRIMARY KEY,
    event_id    INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES cost_categories(id),
    description TEXT,
    -- Планова сума вноситься до поїздки, фактична — коли з'являються чеки
    planned     REAL    NOT NULL DEFAULT 0 CHECK (planned >= 0),
    actual      REAL    CHECK (actual IS NULL OR actual >= 0)
);

CREATE TABLE IF NOT EXISTS event_scores (
    event_id     INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    criterion_id INTEGER NOT NULL REFERENCES criteria(id) ON DELETE CASCADE,
    score        INTEGER NOT NULL CHECK (score BETWEEN 0 AND 5),
    PRIMARY KEY (event_id, criterion_id)
);

CREATE TABLE IF NOT EXISTS targets (
    id           INTEGER PRIMARY KEY,
    event_id     INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    full_name    TEXT    NOT NULL,
    company      TEXT    NOT NULL,
    position     TEXT,
    email        TEXT,
    phone        TEXT,
    linkedin_url TEXT,
    channel      TEXT    NOT NULL DEFAULT 'linkedin'
                 CHECK (channel IN ('linkedin', 'email', 'event_app', 'messenger', 'phone', 'in_person')),
    priority     INTEGER NOT NULL DEFAULT 2 CHECK (priority BETWEEN 1 AND 3),
    source       TEXT    NOT NULL DEFAULT 'manual'
                 CHECK (source IN ('event_site', 'event_app', 'linkedin', 'own_base', 'manual', 'import')),
    status       TEXT    NOT NULL DEFAULT 'candidate'
                 CHECK (status IN ('candidate', 'contacted', 'replied', 'meeting', 'met', 'not_interested', 'no_reply')),
    owner_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    contacted_at DATE,
    meeting_at   DATETIME,
    meeting_place TEXT,
    note         TEXT
);

CREATE TABLE IF NOT EXISTS leads (
    id          INTEGER PRIMARY KEY,
    event_id    INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    target_id   INTEGER REFERENCES targets(id) ON DELETE SET NULL,
    full_name   TEXT    NOT NULL,
    company     TEXT,
    position    TEXT,
    email       TEXT,
    phone       TEXT,
    linkedin_url TEXT,
    channel     TEXT    CHECK (channel IS NULL OR channel IN ('linkedin', 'email', 'event_app', 'messenger', 'phone', 'in_person')),
    -- 0: з людиною не зустрілися, але її взяли в роботу після події з цільового списку
    met         INTEGER NOT NULL DEFAULT 1,
    -- Звідки лід, якщо його імпортували або внесли вручну (NULL — записано під час розмови)
    source      TEXT,
    icp_fit     INTEGER CHECK (icp_fit IS NULL OR icp_fit BETWEEN 1 AND 3),
    intent      INTEGER CHECK (intent IS NULL OR intent BETWEEN 1 AND 3),
    need_topic  TEXT,
    details     TEXT,
    next_step   TEXT,
    owner_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    due_date    DATE,
    captured_at DATETIME NOT NULL,
    captured_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    status      TEXT    NOT NULL DEFAULT 'new'
                CHECK (status IN ('new', 'in_progress', 'won', 'closed', 'no_action')),
    client_uid  TEXT    UNIQUE
);

CREATE TABLE IF NOT EXISTS followups (
    id       INTEGER PRIMARY KEY,
    lead_id  INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    channel  TEXT    NOT NULL CHECK (channel IN ('linkedin', 'email', 'event_app', 'messenger', 'phone', 'in_person')),
    done_on  DATE    NOT NULL,
    result   TEXT    NOT NULL CHECK (result IN ('no_answer', 'talking', 'meeting_set', 'agreement', 'refused')),
    note     TEXT,
    user_id  INTEGER REFERENCES users(id) ON DELETE SET NULL
);

-- Зв'язок «лід — угода» 0..1, тому lead_id унікальний
CREATE TABLE IF NOT EXISTS deals (
    id           INTEGER PRIMARY KEY,
    lead_id      INTEGER NOT NULL UNIQUE REFERENCES leads(id) ON DELETE CASCADE,
    amount       REAL    NOT NULL CHECK (amount >= 0),
    stage        TEXT    NOT NULL CHECK (stage IN ('negotiation', 'proposal', 'won', 'lost')),
    revenue_type TEXT    NOT NULL CHECK (revenue_type IN ('new', 'accelerated')),
    close_date   DATE
);

CREATE INDEX IF NOT EXISTS idx_cost_items_event ON cost_items(event_id);
CREATE INDEX IF NOT EXISTS idx_targets_event    ON targets(event_id);
CREATE INDEX IF NOT EXISTS idx_leads_event      ON leads(event_id);
CREATE INDEX IF NOT EXISTS idx_leads_due        ON leads(status, due_date);
CREATE INDEX IF NOT EXISTS idx_followups_lead   ON followups(lead_id);
