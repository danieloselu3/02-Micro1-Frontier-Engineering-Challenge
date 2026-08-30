-- Payer reference data, the workflow audit trail, and the policy corpus.
-- Loaded automatically on first `docker compose up`.

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------- membership

CREATE TABLE plans (
    plan_id                     TEXT PRIMARY KEY,
    name                        TEXT NOT NULL,
    waiting_period_days         INT  NOT NULL DEFAULT 0,
    preexisting_exclusion_months INT NOT NULL DEFAULT 0,
    requires_in_network         BOOLEAN NOT NULL DEFAULT FALSE,
    covered_states              TEXT[] NOT NULL DEFAULT '{}',
    excluded_categories         TEXT[] NOT NULL DEFAULT '{}',
    coverage_document_id        TEXT
);

CREATE TABLE members (
    member_id            TEXT PRIMARY KEY,
    first_name           TEXT NOT NULL,
    last_name            TEXT NOT NULL,
    date_of_birth        DATE NOT NULL,
    sex                  TEXT NOT NULL,
    plan_id              TEXT NOT NULL REFERENCES plans(plan_id),
    group_id             TEXT NOT NULL,
    status               TEXT NOT NULL,
    effective_date       DATE NOT NULL,
    termination_date     DATE,
    premium_paid_through DATE,
    state                TEXT NOT NULL,
    enrolled_at          DATE NOT NULL
);
CREATE INDEX ON members (lower(last_name), lower(first_name));

CREATE TABLE accumulators (
    member_id       TEXT NOT NULL REFERENCES members(member_id),
    plan_year       INT  NOT NULL,
    category        TEXT NOT NULL,
    limit_amount    NUMERIC(12,2) NOT NULL,
    consumed_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (member_id, plan_year, category)
);

-- ------------------------------------------------------------------ network

CREATE TABLE providers (
    npi                     TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    specialty               TEXT NOT NULL,
    network_tier            TEXT NOT NULL,
    license_state           TEXT NOT NULL,
    license_expiry          DATE NOT NULL,
    contract_start          DATE NOT NULL,
    contract_end            DATE,
    sanctioned              BOOLEAN NOT NULL DEFAULT FALSE,
    credentialed_procedures TEXT[] NOT NULL DEFAULT '{}'
);

-- ----------------------------------------------------------------- clinical

CREATE TABLE procedures (
    code                 TEXT PRIMARY KEY,
    description          TEXT NOT NULL,
    category             TEXT NOT NULL,
    requires_preauth     BOOLEAN NOT NULL,
    unit_cost            NUMERIC(12,2) NOT NULL,
    always_review        BOOLEAN NOT NULL DEFAULT FALSE,
    sex_restriction      TEXT,
    age_min              INT,
    age_max              INT,
    policy_document_id   TEXT
);

CREATE TABLE diagnoses (
    code        TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

-- Which diagnoses plausibly justify which procedure. R9 reads this.
CREATE TABLE code_pairs (
    procedure_code TEXT NOT NULL REFERENCES procedures(code),
    diagnosis_code TEXT NOT NULL REFERENCES diagnoses(code),
    PRIMARY KEY (procedure_code, diagnosis_code)
);

-- ------------------------------------------------------------------ history

CREATE TABLE prior_authorizations (
    auth_id        TEXT PRIMARY KEY,
    member_id      TEXT NOT NULL REFERENCES members(member_id),
    provider_npi   TEXT NOT NULL REFERENCES providers(npi),
    procedure_code TEXT NOT NULL REFERENCES procedures(code),
    valid_from     DATE NOT NULL,
    valid_to       DATE NOT NULL,
    status         TEXT NOT NULL,
    units_approved INT  NOT NULL DEFAULT 1
);
CREATE INDEX ON prior_authorizations (member_id, procedure_code);

-- ----------------------------------------------------------------- identity

CREATE TABLE reviewers (
    reviewer_id    TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    role           TEXT NOT NULL,
    credentials    TEXT NOT NULL,
    license_number TEXT NOT NULL
);

-- ----------------------------------------------------------------- workflow

CREATE TABLE submissions (
    submission_id TEXT PRIMARY KEY,
    channel       TEXT NOT NULL,
    received_at   TIMESTAMPTZ NOT NULL,
    document_uri  TEXT NOT NULL,
    degradation   TEXT NOT NULL DEFAULT 'clean',
    case_id       TEXT
);

CREATE TABLE determinations (
    determination_id      TEXT PRIMARY KEY,
    submission_id         TEXT NOT NULL REFERENCES submissions(submission_id),
    verdict               TEXT NOT NULL,
    governing_rule        TEXT NOT NULL,
    reason                TEXT NOT NULL,
    approved_units        INT,
    approved_amount       NUMERIC(12,2),
    missing_information   TEXT[] NOT NULL DEFAULT '{}',
    payload               JSONB NOT NULL,
    auto_released         BOOLEAN NOT NULL DEFAULT FALSE,
    requires_human_review BOOLEAN NOT NULL DEFAULT TRUE,
    model_cost_usd        NUMERIC(10,6) NOT NULL DEFAULT 0,
    elapsed_seconds       REAL NOT NULL DEFAULT 0,
    created_at            TIMESTAMPTZ NOT NULL
);
CREATE INDEX ON determinations (requires_human_review, created_at);

-- Who signed. Nothing is issued without a row here, and the row is both the
-- audit trail and the signature block printed on the determination letter.
CREATE TABLE review_actions (
    action_id         TEXT PRIMARY KEY,
    determination_id  TEXT NOT NULL REFERENCES determinations(determination_id),
    reviewer_id       TEXT NOT NULL REFERENCES reviewers(reviewer_id),
    decision          TEXT NOT NULL,
    final_verdict     TEXT NOT NULL,
    reason            TEXT NOT NULL,
    field_corrections JSONB NOT NULL DEFAULT '{}',
    seconds_spent     REAL NOT NULL DEFAULT 0,
    acted_at          TIMESTAMPTZ NOT NULL
);

-- ------------------------------------------------------------------- corpus

CREATE TABLE policy_documents (
    document_id TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    doc_type    TEXT NOT NULL,   -- medical_policy | coverage_certificate | guideline
    version     TEXT NOT NULL,
    body        TEXT NOT NULL
);

-- Chunked on criterion boundaries, never token counts, so every retrieved
-- clause is a complete quotable rule.
CREATE TABLE policy_chunks (
    clause_id   TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES policy_documents(document_id),
    ordinal     INT  NOT NULL,
    text        TEXT NOT NULL,
    embedding   vector(1024)
);
CREATE INDEX ON policy_chunks (document_id, ordinal);
