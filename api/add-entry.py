import json
import os
from fastapi import FastAPI, Query
from pydantic import BaseModel
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime


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
    from datetime import datetime
    today = datetime.now().strftime("%d.%m.%Y")
    import re
    import difflib
    
    # ---------------------------------------
    # 1. Strafenliste laden
    # ---------------------------------------
    strafen = load_strafen()
    strafen_keys = list(strafen.keys())

    # gesamter Eingabetext für Sprach-Analysen
    raw_text = (
        (entry.vergehen or "") + " "
        + (entry.kosten_manuell or "") + " "
        + (entry.anmerkung or "")
    ).lower()


    # ---------------------------------------
    # 2. Kistenzahl aus Text extrahieren
    # ---------------------------------------
    def detect_kisten_count(text):
        # numerisch wie "2 Kisten"
        nums = re.findall(r"\b\d+\b", text)
        if nums:
            return int(nums[0])

        # textuelle Varianten
        mapping = {
            "eine": 1, "eins": 1,
            "zwei": 2, "drei": 3, "vier": 4,
            "fünf": 5, "sechs": 6, "sieben": 7,
            "acht": 8, "neun": 9, "zehn": 10
        }
        for word, val in mapping.items():
            if word in text:
                return val

        return 1


    # ---------------------------------------
    # 3. Erweiterte Sprach-Kiste-Logik
    # ---------------------------------------
    def looks_like_kisten_entry(entry, raw_text):
        t = raw_text

        # Fall A: jede Form von "2 Kisten", "3 Kiste", auch mit Semikolon
        if re.search(r"\b\d+\s*kiste", t):
            return True

        # Fall B: Wenn kosten_manuell "Kiste" enthält → immer Ausgleich
        if entry.kosten_manuell and "kiste" in entry.kosten_manuell.lower():
            return True

        # Fall C: klassische Erkennung "Kiste gebracht"
        if (
            "kiste" in t
            and ("gebracht" in t or "spend" in t or "mitgebracht" in t)
        ):
            return True

        return False


    is_sprach_kiste = looks_like_kisten_entry(entry, raw_text)
    sprach_kisten_count = detect_kisten_count(raw_text) if is_sprach_kiste else 1


    # ---------------------------------------
    # 4. Fuzzy-Matching (nur wenn keine Sprach-Kiste)
    # ---------------------------------------
    def match_vergehen(v):
        match = difflib.get_close_matches(v, strafen_keys, n=1, cutoff=0.5)
        return match[0] if match else v


    # ---------------------------------------
    # 5. FALL 1: Sprach-Kiste (Ausgleich)
    # ---------------------------------------
    if is_sprach_kiste:

        final_vergehen = "Bezahlt"
        kosten_manuell = "Kiste"
        kosten_final = "Kiste"

        all_rows = []
        for _ in range(sprach_kisten_count):
            row = [
                today,
                entry.name,
                final_vergehen,
                "",               # kosten
                kosten_manuell,   # "Kiste"
                kosten_final,     # "Kiste"
                entry.anmerkung or ""
            ]
            all_rows.append(row)

        # in Sheet schreiben
        service = make_sheet_client()
        sheets = service.spreadsheets()

        sheets.values().append(
            spreadsheetId=SHEET_ID,
            range="Einträge!A:G",
            valueInputOption="USER_ENTERED",
            body={"values": all_rows}
        ).execute()

        return {
            "status": "ok",
            "count": len(all_rows),
            "rows": all_rows,
            "info": "Sprach-Kiste erkannt (Ausgleich)"
        }


    # -------------------------------------------------------------------
    # 6. FALL 2: Normales Vergehen
    # -------------------------------------------------------------------

    final_vergehen = match_vergehen(entry.vergehen)


    # ---------------------------------------
    # 6a. Kostenlogik manuelle Eingabe
    # ---------------------------------------
    if entry.kosten_manuell:
        km = entry.kosten_manuell.strip()
        kosten = ""
        kosten_manuell = km
        kosten_final = km

    else:
        # ---------------------------------------
        # 6b. Aus Strafenliste ziehen
        # ---------------------------------------
        if final_vergehen in strafen:
            value = strafen[final_vergehen].strip()

            kosten = ""

            # STRAFEN-KISTE aus Katalog
            if value.lower() == "kiste":
                kosten_manuell = ""     # wichtig: nicht "Kiste"
                kosten_final = "Kiste"  # offene Kiste
            else:
                kosten_manuell = ""
                kosten_final = value

        else:
            # unbekanntes Vergehen → 0€
            kosten = ""
            kosten_manuell = ""
            kosten_final = "0,00 €"


    # ---------------------------------------
    # 7. Einzelnen Eintrag erzeugen
    # ---------------------------------------
    row = [
        today,
        entry.name,
        final_vergehen,
        kosten,
        kosten_manuell,
        kosten_final,
        entry.anmerkung or ""
    ]


    # ---------------------------------------
    # 8. Schreiben ins Sheet
    # ---------------------------------------
    service = make_sheet_client()
    sheets = service.spreadsheets()

    sheets.values().append(
        spreadsheetId=SHEET_ID,
        range="Einträge!A:G",
        valueInputOption="USER_ENTERED",
        body={"values": [row]}
    ).execute()

    return {
        "status": "ok",
        "count": 1,
        "rows": [row],
        "info": "Normales Vergehen"
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
    
@app.get("/essen-am-wochentag")
def essen_am_wochentag(tag: str):
    """
    Liefert den nächsten Termin (ab heute) für einen bestimmten Wochentag,
    z.B. /essen-am-wochentag?tag=donnerstag
    """
    service = make_sheet_client()
    sheet = service.spreadsheets()

    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range="Esse!A:B"
    ).execute()

    rows = result.get("values", [])[1:]  # ohne Header

    # gewünschten Wochentag normalisieren (z.B. "donnerstag")
    tag = tag.strip().lower()

    # map deutsche wochentage → Python weekday()
    wochentage = {
        "montag": 0,
        "dienstag": 1,
        "mittwoch": 2,
        "donnerstag": 3,
        "freitag": 4,
        "samstag": 5,
        "sonntag": 6
    }

    if tag not in wochentage:
        return {"error": f"Unbekannter Wochentag: {tag}"}

    gesuchter_index = wochentage[tag]
    heute = datetime.today()

    kandidaten = []

    for row in rows:
        if len(row) < 2:
            continue

        name = row[0].strip()
        datum_str = row[1].strip()

        try:
            datum = datetime.strptime(datum_str, "%d.%m.%Y")
        except:
            continue

        # nur zukünftige Termine berücksichtigen
        if datum.date() >= heute.date():
            if datum.weekday() == gesuchter_index:
                kandidaten.append((datum, name))

    if not kandidaten:
        return {"name": None, "datum": None}

    # nächstes Datum = frühestes Datum
    kandidaten.sort(key=lambda x: x[0])
    datum, name = kandidaten[0]

    return {
        "name": name,
        "datum": datum.strftime("%d.%m.%Y"),
        "wochentag": tag
    }

@app.get("/essen-fuer-spieler")
def essen_fuer_spieler(name: str):
    """
    Liefert den nächsten Essens-Termin für den angegebenen Spieler.
    Beispiel: /essen-fuer-spieler?name=Luis%20Schreiner
    """
    service = make_sheet_client()
    sheet = service.spreadsheets()

    result = sheet.values().get(
        spreadsheetId=SHEET_ID,
        range="Esse!A:B"
    ).execute()

    rows = result.get("values", [])[1:]  # ohne Header

    name_requested = name.strip().lower()
    heute = datetime.today()

    termine = []

    for row in rows:
        if len(row) < 2:
            continue

        name_sheet = row[0].strip().lower()
        datum_str = row[1].strip()

        if name_sheet != name_requested:
            continue

        try:
            datum = datetime.strptime(datum_str, "%d.%m.%Y")
        except:
            continue

        if datum.date() >= heute.date():
            termine.append(datum)

    if not termine:
        return {"name": name, "datum": None}

    termine.sort()
    naechster = termine[0]

    return {
        "name": name,
        "datum": naechster.strftime("%d.%m.%Y")
    }

