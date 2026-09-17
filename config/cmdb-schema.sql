CREATE TABLE IF NOT EXISTS assets (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hostname TEXT NOT NULL UNIQUE,
    asset_type TEXT NOT NULL,
    environment TEXT NOT NULL,
    status TEXT NOT NULL,
    manufacturer TEXT,
    model TEXT,
    serial_number TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS network_endpoints (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_id BIGINT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    ip_address INET NOT NULL,
    dns_name TEXT,
    network_role TEXT,
    UNIQUE (asset_id, ip_address)
);

CREATE TABLE IF NOT EXISTS operating_systems (
    asset_id BIGINT PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
    os_name TEXT NOT NULL,
    os_version TEXT NOT NULL,
    kernel_version TEXT,
    architecture TEXT,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS owners (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    department TEXT NOT NULL,
    name TEXT NOT NULL,
    contact TEXT,
    UNIQUE (department, name)
);

CREATE TABLE IF NOT EXISTS asset_owners (
    asset_id BIGINT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    owner_id BIGINT NOT NULL REFERENCES owners(id) ON DELETE RESTRICT,
    responsibility_type TEXT NOT NULL,
    PRIMARY KEY (asset_id, owner_id, responsibility_type)
);

CREATE TABLE IF NOT EXISTS business_services (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_name TEXT NOT NULL UNIQUE,
    criticality TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS asset_business_services (
    asset_id BIGINT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    service_id BIGINT NOT NULL REFERENCES business_services(id) ON DELETE RESTRICT,
    PRIMARY KEY (asset_id, service_id)
);

CREATE TABLE IF NOT EXISTS account_inventory (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username TEXT NOT NULL,
    account_type TEXT NOT NULL,
    status TEXT NOT NULL,
    UNIQUE (username, account_type)
);

CREATE TABLE IF NOT EXISTS asset_accounts (
    asset_id BIGINT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    account_id BIGINT NOT NULL REFERENCES account_inventory(id) ON DELETE RESTRICT,
    privilege_level TEXT NOT NULL,
    PRIMARY KEY (asset_id, account_id)
);

CREATE TABLE IF NOT EXISTS security_audits (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_id BIGINT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    policy_id TEXT NOT NULL,
    result TEXT NOT NULL,
    findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS config_values (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_id BIGINT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    config_name TEXT NOT NULL,
    config_value TEXT NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

REVOKE ALL ON SCHEMA public FROM PUBLIC;
