import carelink_client2
import time
import json
import datetime
from dotenv import load_dotenv
import os
from pathlib import Path

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


clients = []
for user in users:
    client = carelink_client2.CareLinkClient(user)
    clients.append(client)

print("Clients created")
for client in clients:
    if client.init():
        client.printUserInfo()