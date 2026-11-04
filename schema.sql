-- NeuroTrack AI SQLite schema
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assessments (
    assessment_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    assessment_version TEXT,
    assessment_date TEXT NOT NULL,
    total_correct INTEGER NOT NULL,
    total_questions INTEGER NOT NULL,
    percentage REAL NOT NULL,
    domain_scores TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_assessments_user_date
    ON assessments(user_id, assessment_date DESC);

CREATE TABLE IF NOT EXISTS assessment_responses (
    response_id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    answer TEXT NOT NULL,
    FOREIGN KEY (assessment_id) REFERENCES assessments(assessment_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_responses_assessment
    ON assessment_responses(assessment_id);

-- Reserved for future, genuine model integration only.
-- No predictions are generated or inserted by database.py.
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id TEXT,
    model_version TEXT NOT NULL,
    predicted_class TEXT NOT NULL,
    confidence_score REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (assessment_id) REFERENCES assessments(assessment_id) ON DELETE SET NULL
);
