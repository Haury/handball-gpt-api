import json
import os
from fastapi import FastAPI
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = FastAPI()

SHEET_ID = "1v4TyRW0mS-EWnjrGbR49UtNK7Jp5X0ycB9pXVtVMAu0"

SERVICE_ACCOUNT_INFO = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Hilfsfunktion
def make_sheet_client():
    creds = service_account.Credentials.from_service_account_info(
        SERVICE_ACCOUNT_INFO, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


@app.get("/get-saldo")
def get_saldo(name: str):
    service = make_sheet_client()
    sheet = service.spreadsheets()

    # ganze Tabelle laden
    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range="Einträge!A:G"
    ).execute()

    rows = result.get("values", [])
    if not rows:
        return {"saldo": 0, "kisten": 0, "eintraege": []}

    header = rows[0]
    data = rows[1:]

    # in Dicte umwandeln
    entries = []
    for row in data:
        entry = {}
        for i, value in enumerate(row):
            entry[header[i]] = value
        entries.append(entry)

    # Filter auf Spieler
    name_lower = name.lower()
    filtered = [e for e in entries if e.get("Name", "").lower() == name_lower]

    # Summen berechnen
    saldo_euro = 0.0
    kisten = 0

    for e in filtered:
        val = e.get("Kosten Final", "").strip().lower()

        if "kiste" in val:
            kisten += 1
            continue

        # geldwerte rausfiltern
        if "€" in val:
            num = val.replace("€", "").replace(".", "").replace(",", ".").strip()
            try:
                saldo_euro += float(num)
            except:
                pass

    return {
        "name": name,
        "saldo_euro": round(saldo_euro, 2),
        "kisten": kisten,
        "eintraege": filtered
    }
