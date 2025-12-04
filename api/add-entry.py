from fastapi import FastAPI
from pydantic import BaseModel
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = FastAPI()

SHEET_ID = "1v4TyRW0mS-EWnjrGbR49UtNK7Jp5X0ycB9pXVtVMAu0"
SERVICE_ACCOUNT_FILE = "service_account.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

class Entry(BaseModel):
    date: str
    name: str
    vergehen: str
    kosten: str | None = ""
    kosten_manuell: str | None = ""
    anmerkung: str | None = ""

def make_sheet_client():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds)

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
    sheet = service.spreadsheets()

    sheet.values().append(
        spreadsheetId=SHEET_ID,
        range="Einträge!A:G",
        valueInputOption="USER_ENTERED",
        body={"values": values}
    ).execute()

    return {"status": "ok", "appended": values}
