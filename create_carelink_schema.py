import os

import psycopg
from dotenv import load_dotenv


SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS carelink;

CREATE TABLE IF NOT EXISTS carelink.app_user (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    timezone_name TEXT,
    UNIQUE (first_name, last_name)
);

CREATE TABLE IF NOT EXISTS carelink.device (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES carelink.app_user(id) ON DELETE CASCADE,
    manufacturer TEXT,
    model_number TEXT,
    hardware_revision TEXT,
    firmware_revision TEXT,
    serial_number TEXT NOT NULL UNIQUE,
    system_id TEXT
);

CREATE TABLE IF NOT EXISTS carelink.insulin_reservoir (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES carelink.app_user(id) ON DELETE CASCADE,
    device_id BIGINT NOT NULL REFERENCES carelink.device(id) ON DELETE CASCADE,
    measured_at TIMESTAMPTZ NOT NULL,
    reservoir_units NUMERIC,
    reservoir_percent NUMERIC,
    UNIQUE (device_id, measured_at)
);

CREATE TABLE IF NOT EXISTS carelink.active_insulin (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES carelink.app_user(id) ON DELETE CASCADE,
    measured_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC,
    UNIQUE (user_id, measured_at)
);

CREATE TABLE IF NOT EXISTS carelink.cgm_reading (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES carelink.app_user(id) ON DELETE CASCADE,
    reading_time TIMESTAMPTZ NOT NULL,
    glucose_value NUMERIC,
    sensor_state TEXT,
    trend TEXT,
    UNIQUE (user_id, reading_time)
);

CREATE TABLE IF NOT EXISTS carelink.bolus_data (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES carelink.app_user(id) ON DELETE CASCADE,
    event_time TIMESTAMPTZ NOT NULL,
    insulin_type TEXT,
    programmed_amount NUMERIC,
    delivered_amount NUMERIC,
    activation_type TEXT,
    completed BOOLEAN,
    bolus_type TEXT,
    UNIQUE (user_id, event_time)
);

CREATE TABLE IF NOT EXISTS carelink.basal_data (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES carelink.app_user(id) ON DELETE CASCADE,
    event_time TIMESTAMPTZ NOT NULL,
    delivered_amount NUMERIC,
    max_basal_rate NUMERIC,
    UNIQUE (user_id, event_time)
);
"""


def create_schema(conn):
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)


def main():
    load_dotenv()

    connection_options = {
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT"),
        "dbname": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
    }

    with psycopg.connect(**connection_options) as conn:
        create_schema(conn)

    print("CareLink database schema is ready.")


if __name__ == "__main__":
    main()