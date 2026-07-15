CREATE TABLE IF NOT EXISTS office_escalations (
    id SERIAL PRIMARY KEY,
    customer_name VARCHAR(255) NOT NULL,
    contact_number VARCHAR(100) NOT NULL,
    domain VARCHAR(100),
    office_details TEXT,
    issue_encountering TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
