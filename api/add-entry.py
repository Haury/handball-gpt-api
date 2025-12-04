import json
import os
from fastapi import FastAPI
from pydantic import BaseModel
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = FastAPI()

SHEET_ID = "1v4TyRW0mS-EWnjrGbR49UtNK7Jp5X0ycB9pXVtVMAu0"

# Service Account aus Umgebungsvariable laden
SERVICE_ACCOUNT_ENV = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
if not SERVICE_ACCOUNT_ENV:
    raise Exception("Environment variable GOOGLE_SERVICE_ACCOUNT is missing.")

SERVICE_ACCOUNT_INFO = json.loads(SERVICE_ACCOUNT_ENV)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


# -----------------------------
# Hilfsfunktion: Sheets-Client
# -----------------------------
def make_sheet_client():
    creds = service_account.Credentials.from_service_account_info(
        SERVICE_ACCOUNT_INFO,
        scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


# -----------------------------
# Datenmodell für /add-entry
# -----------------------------
class Entry(BaseModel):
    date: str
    name: str
    vergehen: str
    kosten: str | None = ""
    kosten_manuell: str | None = ""
    anmerkung: str | None = ""


# -----------------------------
# Strafen aus Google Sheet holen
# -----------------------------
def load_strafen():
    service = make_sheet_client()
    sheet = service.spreadsheets()

    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range="Strafen!A:B"
    ).execute()

    values = result.get("values", [])
    strafen = {}

    # Überspring Header
    for row in values[1:]:
        if len(row) >= 2:
            key = row[0].strip()
            value = row[1].strip()
            strafen[key] = value

    return strafen


@app.post("/add-entry")
def add_entry(entry: Entry):
    # 1) Strafen laden
    strafen = load_strafen()

    # ------------------------------------------------------------
    # 2) Kosten bestimmen (Variante 1 – D immer Auto-Mapping)
    # ------------------------------------------------------------
    kosten = ""           # Spalte D (automatisch)
    kosten_manuell = ""   # Spalte E (manuell)
    kosten_final = ""     # Spalte F

    # ---------- A) AUTOMATISCHE STRAFE (SPALTE D) ----------
    if entry.vergehen in strafen:
        mapped_value = strafen[entry.vergehen].strip()

        # Geldwert erkennen (z. B. "3,00 €")
        if "€" in mapped_value or "," in mapped_value:
            kosten = mapped_value

        # Text wie "Kiste"
        elif "kiste" in mapped_value.lower():
            kosten = ""             # D bleibt leer
            kosten_final = "Kiste"  # Default für später

        else:
            # sonstige Texte
            kosten = ""
            kosten_final = mapped_value
    else:
        kosten = ""


    # ---------- B) MANUELLE ANGABEN (SPALTE E) ----------
    if entry.kosten_manuell:
        man = entry.kosten_manuell.strip()

        # Normalisiere alle Kisten-Schreibweisen
        if "kiste" in man.lower():
            kosten_manuell = "Kiste"
        else:
            kosten_manuell = man


    # ---------- C) FINALWERT F BERECHNEN ----------
    if kosten_manuell:
        # Manuell sticht automatisch
        kosten_final = kosten_manuell
    else:
        # Manuell nicht gesetzt → Auto-Wert
        if kosten_final == "" and kosten != "":
            kosten_final = kosten

        # Falls weder auto noch manuell → 0 €
        if kosten_final == "":
            kosten_final = "0,00 €"


    # ---------- D) ZEILE SCHREIBEN ----------
    values = [[
        entry.date,
        entry.name,
        entry.vergehen,
        kosten,
        kosten_manuell,
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
        "written": values,
        "kosten": kosten,
        "kosten_manuell": kosten_manuell,
        "kosten_final": kosten_final
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
    spieler = [row[0] for row in values[1:] if row]

    return spieler
