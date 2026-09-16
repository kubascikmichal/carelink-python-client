import os

import psycopg
from dotenv import load_dotenv

from create_carelink_schema import create_schema


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
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS carelink CASCADE")
        create_schema(conn)

    print("CareLink database schema was reset.")


if __name__ == "__main__":
    main()