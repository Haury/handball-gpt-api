import json
import os
from fastapi import FastAPI, Query
from pydantic import BaseModel
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = FastAPI()

SHEET_ID = "1v4TyRW0mS-EWnjrGbR49UtNK7Jp5X0ycB9pXVtVMAu0"

# Service Account laden
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


# -----------------------------
# POST /add-entry
# -----------------------------
class Entry(BaseModel):
    date: str
    name: str
    vergehen: str
    kosten: str | None = ""
    kosten_manuell: str | None = ""
    anmerkung: str | None = ""


def load_strafen():
    service = make_sheet_client()
    sheet = service.spreadsheets()

    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range="Strafen!A:B"
    ).execute()

    values = result.get("values", [])
    strafen = {}

    for row in values[1:]:
        if len(row) >= 2:
            key = row[0].strip()
            value = row[1].strip()
            strafen[key] = value
    return strafen


@app.post("/add-entry")
def add_entry(entry: Entry):
    strafen = load_strafen()

    # Kostenlogik
    if entry.kosten_manuell:
        man = entry.kosten_manuell.strip()
        kosten_final = "Kiste" if "kiste" in man.lower() else man
    else:
        kosten_final = ""
        if entry.vergehen in strafen:
            value = strafen[entry.vergehen].strip()
            if "kiste" in value.lower():
                kosten_final = "Kiste"
            elif "€" in value or "," in value:
                kosten_final = value
            else:
                kosten_final = value
        elif entry.kosten:
            kosten_final = "Kiste" if "kiste" in entry.kosten.lower() else entry.kosten
        if kosten_final == "":
            kosten_final = "0,00 €"

    values = [[
        entry.date,
        entry.name,
        entry.vergehen,
        entry.kosten or "",
        entry.kosten_manuell or "",
        kosten_final,
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

    return {
        "status": "ok",
        "kosten_final": kosten_final,
        "appended": values
    }


# -----------------------------
# GET /get-strafen
# -----------------------------
@app.get("/get-strafen")
def get_strafen():
    return load_strafen()


# -----------------------------
# GET /get-spieler
# -----------------------------
@app.get("/get-spieler")
def get_spieler():
    service = make_sheet_client()
    sheet = service.spreadsheets()

    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range="Spielerliste!A:A"
    ).execute()

    values = result.get("values", [])
    return [row[0] for row in values[1:] if row]


# -----------------------------
# GET /get-eintraege
# -----------------------------
@app.get("/get-eintraege")
def get_eintraege(name: str = Query(...)):
    service = make_sheet_client()
    sheets = service.spreadsheets()

    result = sheets.values().get(
        spreadsheetId=SHEET_ID,
        range="Einträge!A:G"
    ).execute()

    rows = result.get("values", [])
    header = rows[0]
    entries = []

    for row in rows[1:]:
        row_dict = {header[i]: row[i] if i < len(row) else "" for i in range(len(header))}
        if row_dict.get("Name", "").lower() == name.lower():
            entries.append(row_dict)

    return {"eintraege": entries}


# -----------------------------
# GET /get-saldo
# -----------------------------
@app.get("/get-saldo")
def get_saldo(name: str = Query(...)):
    service = make_sheet_client()
    sheet = service.spreadsheets()

    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range="Einträge!A:G"
    ).execute()

    rows = result.get("values", [])
    if not rows:
        return {"error": "Keine Daten gefunden."}

    header = rows[0]

    geld_saldo = 0.0
    kisten_plus = 0      # Vergehen = Bezahlt
    kisten_minus = 0     # Vergehen ≠ Bezahlt

    for row in rows[1:]:
        row_dict = {header[i]: row[i] if i < len(row) else "" for i in range(len(header))}

        # Name matchen (case insensitive)
        if row_dict.get("Name", "").strip().lower() != name.strip().lower():
            continue

        vergehen = row_dict.get("Vergehen", "").strip().lower()
        kosten = row_dict.get("Kosten Final", "").strip().lower()

        # ------------------------------
        # 1. KISTEN-LOGIK (exakt wie Excel)
        # ------------------------------
        if kosten == "kiste":

            if vergehen == "bezahlt":
                kisten_plus += 1
            else:
                kisten_minus += 1

            continue  # nicht bei Geldsaldo addieren

        # ------------------------------
        # 2. GELD-LOGIK
        # ------------------------------
        if "€" in kosten:
            wert = kosten.replace("€", "").replace(",", ".").strip()
            try:
                geld_saldo += float(wert)
            except:
                pass

    # Ergebnis wie in Excel
    kisten_saldo = kisten_minus - kisten_plus

    return {
        "geld_saldo": geld_saldo,
        "kisten_saldo": kisten_saldo,
        "kisten_minus": kisten_minus,
        "kisten_plus": kisten_plus
    }
