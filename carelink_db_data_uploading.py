import carelink_client2
import time
import json
import datetime
from dotenv import load_dotenv
import os
from pathlib import Path
import psycopg
import requests


def parse_carelink_datetime(value, client_date_time):
    parsed = datetime.datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        return parsed

    reference = datetime.datetime.fromisoformat(client_date_time)
    if reference.tzinfo is None:
        raise ValueError("CareLink clientDateTime must include a timezone offset")

    return parsed.replace(tzinfo=reference.tzinfo)


def get_recent_data_with_retry(client, retries=3):
    for attempt in range(retries):
        try:
            return client.getRecentData()
        except requests.exceptions.RequestException as error:
            print(
                f"CareLink request failed (attempt {attempt + 1}/{retries}): {error}"
            )
            if attempt + 1 < retries:
                time.sleep(5 * (attempt + 1))

    return None


def get_or_create_user(conn, patient):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM carelink.app_user
            WHERE first_name = %s
              AND last_name = %s
            """,
            (
                patient["firstName"],
                patient["lastName"]
            )
        )
        row = cur.fetchone()
        if row:
            return row[0]

        cur.execute(
            """
            INSERT INTO carelink.app_user
            (
                first_name,
                last_name,
                timezone_name
            )
            VALUES (%s,%s,%s)
            RETURNING id
            """,
            (
                patient["firstName"],
                patient["lastName"],
                patient["clientTimeZoneName"]
            )
        )

        user_id = cur.fetchone()[0]
        conn.commit()

        return user_id


def get_or_create_device(conn, user_id, patient):

    device = patient["medicalDeviceInformation"]

    with conn.cursor() as cur:

        cur.execute(
            """
            SELECT id
            FROM carelink.device
            WHERE serial_number = %s
            """,
            (device["deviceSerialNumber"],)
        )

        row = cur.fetchone()

        if row:
            return row[0]

        cur.execute(
            """
            INSERT INTO carelink.device
            (
                user_id,
                manufacturer,
                model_number,
                hardware_revision,
                firmware_revision,
                serial_number,
                system_id
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                user_id,
                device["manufacturer"],
                device["modelNumber"],
                device["hardwareRevision"],
                device["firmwareRevision"],
                device["deviceSerialNumber"],
                device["systemId"]
            )
        )

        device_id = cur.fetchone()[0]
        conn.commit()

        return device_id

def insert_reservoir(conn, user_id, device_id, patient, client_date_time):

    with conn.cursor() as cur:

        cur.execute(
            """
            INSERT INTO carelink.insulin_reservoir
            (
                user_id,
                device_id,
                measured_at,
                reservoir_units,
                reservoir_percent
            )
            VALUES (%s,%s,%s,%s,%s)
            """,
            (
                user_id,
                device_id,
                parse_carelink_datetime(
                    patient["lastConduitDateTime"],
                    client_date_time
                ),
                patient["reservoirRemainingUnits"],
                patient["reservoirLevelPercent"]
            )
        )

    conn.commit()

def insert_active_insulin(conn, user_id, patient, client_date_time):

    active = patient.get("activeInsulin")

    if not active:
        return

    with conn.cursor() as cur:

        cur.execute(
            """
            INSERT INTO carelink.active_insulin
            (
                user_id,
                measured_at,
                amount
            )
            VALUES (%s,%s,%s)
            ON CONFLICT (user_id, measured_at)
            DO NOTHING
            """,
            (
                user_id,
                parse_carelink_datetime(active["datetime"], client_date_time),
                active["amount"]
            )
        )

    conn.commit()

def insert_cgm(conn, user_id, patient, client_date_time):

    sgs = patient.get("sgs", [])

    with conn.cursor() as cur:

        for sg in sgs:

            cur.execute(
                """
                INSERT INTO carelink.cgm_reading
                (
                    user_id,
                    reading_time,
                    glucose_value,
                    sensor_state,
                    trend
                )
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (user_id, reading_time)
                DO NOTHING
                """,
                (
                    user_id,
                    parse_carelink_datetime(sg["timestamp"], client_date_time),
                    sg["sg"],
                    sg["sensorState"],
                    None
                )
            )

    conn.commit()

def insert_delivery_data(conn, user_id, patient, client_date_time):

    with conn.cursor() as cur:

        for marker in patient.get("markers", []):
            values = marker.get("data", {}).get("dataValues", {})
            event_time = marker.get("timestamp")

            if not event_time:
                continue

            if marker.get("type") == "INSULIN":
                cur.execute(
                    """
                    INSERT INTO carelink.bolus_data
                    (
                        user_id,
                        event_time,
                        insulin_type,
                        programmed_amount,
                        delivered_amount,
                        activation_type,
                        completed,
                        bolus_type
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (user_id, event_time)
                    DO NOTHING
                    """,
                    (
                        user_id,
                        parse_carelink_datetime(event_time, client_date_time),
                        values.get("insulinType"),
                        values.get("programmedFastAmount"),
                        values.get("deliveredFastAmount"),
                        values.get("activationType"),
                        values.get("completed"),
                        values.get("bolusType")
                    )
                )

            elif marker.get("type") == "AUTO_BASAL_DELIVERY":
                cur.execute(
                    """
                    INSERT INTO carelink.basal_data
                    (
                        user_id,
                        event_time,
                        delivered_amount,
                        max_basal_rate
                    )
                    VALUES (%s,%s,%s,%s)
                    ON CONFLICT (user_id, event_time)
                    DO NOTHING
                    """,
                    (
                        user_id,
                        parse_carelink_datetime(event_time, client_date_time),
                        values.get("bolusAmount"),
                        values.get("maxAutoBasalRate")
                    )
                )

    conn.commit()

def import_carelink_response(conn, response):

    patient = response["patientData"]
    client_date_time = response["metadata"]["clientDateTime"]

    user_id = get_or_create_user(conn, patient)

    device_id = get_or_create_device(
        conn,
        user_id,
        patient
    )

    insert_reservoir(
        conn,
        user_id,
        device_id,
        patient,
        client_date_time
    )

    insert_active_insulin(
        conn,
        user_id,
        patient,
        client_date_time
    )

    insert_cgm(
        conn,
        user_id,
        patient,
        client_date_time
    )

    insert_delivery_data(
        conn,
        user_id,
        patient,
        client_date_time
    )

    return user_id, device_id

def save_current_data(conn, response):

    patient = response["patientData"]
    client_date_time = response["metadata"]["clientDateTime"]

    user_id = get_or_create_user(conn, patient)
    device_id = get_or_create_device(conn, user_id, patient)

    with conn.cursor() as cur:

        # reservoir
        cur.execute(
            """
            INSERT INTO carelink.insulin_reservoir
            (
                user_id,
                device_id,
                measured_at,
                reservoir_units,
                reservoir_percent
            )
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (device_id, measured_at)
            DO NOTHING
            """,
            (
                user_id,
                device_id,
                parse_carelink_datetime(
                    patient["lastConduitDateTime"],
                    client_date_time
                ),
                patient["reservoirRemainingUnits"],
                patient["reservoirLevelPercent"]
            )
        )

        # active insulin
        active = patient.get("activeInsulin")

        if active:
            cur.execute(
                """
                INSERT INTO carelink.active_insulin
                (
                    user_id,
                    measured_at,
                    amount
                )
                VALUES (%s,%s,%s)
                ON CONFLICT (user_id, measured_at)
                DO NOTHING
                """,
                (
                    user_id,
                    parse_carelink_datetime(active["datetime"], client_date_time),
                    active["amount"]
                )
            )

        # last SG only
        sg = patient.get("lastSG")

        if sg:
            cur.execute(
                """
                INSERT INTO carelink.cgm_reading
                (
                    user_id,
                    reading_time,
                    glucose_value,
                    sensor_state,
                    trend
                )
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (user_id, reading_time)
                DO NOTHING
                """,
                (
                    user_id,
                    parse_carelink_datetime(sg["timestamp"], client_date_time),
                    sg["sg"],
                    sg["sensorState"],
                    patient.get("lastSGTrend")
                )
            )

    conn.commit()

    insert_delivery_data(
        conn,
        user_id,
        patient,
        client_date_time
    )

load_dotenv()

db_host = os.getenv("DB_HOST")
db_port = os.getenv("DB_PORT")
db_name = os.getenv("DB_NAME")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")

USER_FILES = os.getenv("USER_FILES")

user_files_path = Path(USER_FILES)
users = []
for file in user_files_path.glob("*.json"):
    users.append(file)
print(users)

conn = psycopg.connect(
    host=db_host,
    port=db_port,
    dbname=db_name,
    user=db_user,
    password=db_password
)

with conn.cursor() as cur:
    cur.execute("SELECT NOW()")
    print(cur.fetchone())

clients = []
for user in users:
    client = carelink_client2.CareLinkClient(user)
    clients.append(client)

print("Clients created")
while True:
    for client in clients:
        if client.init():
            client.printUserInfo()
            recent_data = get_recent_data_with_retry(client)
            if recent_data is not None:
                save_current_data(conn, recent_data)
    time.sleep(30*5)