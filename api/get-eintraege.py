import json
import os
from fastapi import FastAPI, Query
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = FastAPI()

SHEET_ID = "1v4TyRW0mS-EWnjrGbR49UtNK7Jp5X0ycB9pXVtVMAu0"

SERVICE_ACCOUNT_ENV = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
if not SERVICE_ACCOUNT_ENV:
    raise Exception("Environment variable GOOGLE_SERVICE_ACCOUNT is missing.")

SERVICE_ACCOUNT_INFO = json.loads(SERVICE_ACCOUNT_ENV)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def make_sheet_client():
    creds = service_account.Credentials.from_service_account_info(
        SERVICE_ACCOUNT_INFO,
        scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


@app.get("/get-eintraege")
def get_eintraege(name: str = Query(..., description="Spielername exakt wie im Sheet")):
    service = make_sheet_client()
    sheet = service.spreadsheets()

    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range="Einträge!A:G"
    ).execute()

    rows = result.get("values", [])

    # Header lesen
    header = rows[0]
    entries = []

    for row in rows[1:]:
        row_dict = {header[i]: row[i] if i < len(row) else "" for i in range(len(header))}

        if row_dict.get("Name", "").strip().lower() == name.strip().lower():
            entries.append(row_dict)

    return {"eintraege": entries}
