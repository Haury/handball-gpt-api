import json
import os
from fastapi import FastAPI
from pydantic import BaseModel
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = FastAPI()

# Google Sheet ID deines Strafenkatalogs
SHEET_ID = "1v4TyRW0mS-EWnjrGbR49UtNK7Jp5X0ycB9pXVtVMAu0"

# Environment Variable enthält den kompletten JSON-Key
SERVICE_ACCOUNT_ENV = os.environ.get("GOOGLE_SERVICE_ACCOUNT")

if not SERVICE_ACCOUNT_ENV:
    raise Exception("Environment variable GOOGLE_SERVICE_ACCOUNT is missing.")

SERVICE_ACCOUNT_INFO = json.loads(SERVICE_ACCOUNT_ENV)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

class Entry(BaseModel):
    date: str
    name: str
    vergehen: str
    kosten: str | None = ""
    kosten_manuell: str | None = ""
    anmerkung: str | None = ""

def make_sheet_client():
    creds = service_account.Credentials.from_service_account_info(
        SERVICE_ACCOUNT_INFO,
        scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=creds)
    return service

@app.post("/add-entry")
def add_entry(entry: Entry):
    values = [[
        entry.date,
        entry.name,
        entry.vergehen,
        entry.kosten or "",
        entry.kosten_manuell or "",
        "",
        entry.anmerkung or ""
    ]]

    service = make_sheet_client()
    sheets = service.spreadsheets()

    sheets.values().append(
        spreadsheetId=SHEET_ID,
        range="Einträge!A:G",
        valueInputOption="USER_ENTERED",
        body={"values": values}
    ).execute()

    return {"status": "ok", "appended": values}
