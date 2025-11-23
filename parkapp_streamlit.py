import os
import json
from datetime import datetime
import streamlit as st
from openai import OpenAI

# Passwortschutz
PASSWORD = "Iobroker21"

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.title("🔒 Geschützte App")
    pwd = st.text_input("Passwort eingeben:", type="password")

    if pwd == PASSWORD:
        st.session_state["authenticated"] = True
        st.experimental_rerun()
    else:
        st.stop()

# -------------------------------------------------
# 1. Simulierter Zeitpunkt
# -------------------------------------------------
SIM_NOW = datetime(2025, 12, 15, 16, 0)


# -------------------------------------------------
# 2. Parkdaten laden & normalisieren
# -------------------------------------------------
def load_parkdata():
    with open("parkdata.json", "r") as f:
        return json.load(f)


parkdata_raw = load_parkdata()

# Kennzeichen normalisieren → Leerzeichen entfernen, groß schreiben
parkdata = {}
for plate, data in parkdata_raw.items():
    normalized_plate = plate.replace(" ", "").upper()
    parkdata[normalized_plate] = data

# -------------------------------------------------
# 3. OpenAI Client
# -------------------------------------------------
client = OpenAI(api_key=os.getenv("Park_AI_API"))


# -------------------------------------------------
# 4. Parkdauer & Kosten berechnen
# -------------------------------------------------
def calculate_parking_details(entry_time, exit_time, price_per_hour=1.20):
    fmt = "%Y-%m-%d %H:%M"
    entry = datetime.strptime(entry_time, fmt)

    # Fall A: Auto ist noch da → Ausfahrt in Zukunft oder None
    if exit_time is None:
        end_time = SIM_NOW
        exit_time_str = "Noch im Parkplatz"
    else:
        exit_dt = datetime.strptime(exit_time, fmt)
        if exit_dt > SIM_NOW:
            end_time = SIM_NOW
            exit_time_str = "Noch im Parkplatz"
        else:
            end_time = exit_dt
            exit_time_str = exit_time

    duration = end_time - entry
    hours = duration.total_seconds() / 3600
    price = round(hours * price_per_hour, 2)

    return {
        "duration_hours": round(hours, 2),
        "exit_time": exit_time_str,
        "price": price,
        "raw_duration": duration
    }


# -------------------------------------------------
# 5. KI-Antwort generieren
# -------------------------------------------------
def ask_ai(user_question, plate):
    vehicle_data = parkdata.get(plate)
    details = calculate_parking_details(vehicle_data["in"], vehicle_data["out"])

    # Parkdauer in h + min (immer bis SIM_NOW oder Ausfahrt, je nach Fall)
    total_minutes = int(details["raw_duration"].total_seconds() // 60)
    h = total_minutes // 60
    m = total_minutes % 60
    duration_str = f"{h}h {m}min"

    # Status bestimmen für KI
    out = vehicle_data["out"]
    entry_time = vehicle_data["in"][11:16]  # nur Uhrzeit

    if out is None:
        # Auto hat keine Ausfahrtszeit => steht um 16:00 Uhr noch da
        status = "da"
        out_info = ""
    else:
        out_dt = datetime.strptime(out, "%Y-%m-%d %H:%M")
        if out_dt <= SIM_NOW:
            # Auto ist vor oder genau um 16 Uhr ausgefahren
            status = "weg"
            out_info = f"Es ist um {out[11:16]} Uhr ausgefahren."
        else:
            # Auto fährt erst nach 16 Uhr aus => steht noch da
            status = "da"
            out_info = ""

    # Basisdaten für die KI (keine Logik mehr, nur Fakten!)
    facts = f"""
    Fahrzeug: {plate}
    Status um 16:00 Uhr: {status}
    Einfahrt: {entry_time} Uhr
    Parkdauer bis 16:00 Uhr: {duration_str}
    Parkplatz: {vehicle_data['parking_spot']}
    Preis: {details['price']} Euro
    {out_info}
    """

    # KI-Antwort
    response = client.responses.create(
        model="gpt-4o-mini",
        input=f"""
    Du bist der SmartPark KI-Assistent.

    Hier sind die Fakten zum Fahrzeug, alle berechnet auf den festen Zeitpunkt 15.12.2025 um 16:00 Uhr:

    {facts}

    Nutzerfrage:
    {user_question}

    Regeln:
    - Verwende ausschließlich die bereitgestellten Daten (Status, Einfahrt, ggf. Ausfahrt, Parkdauer, Preis).
    - Berechne nichts neu.
    - Wenn der Nutzer nach dem Parkpreis fragt → gib genau den Preis aus dem Systemtext zurück.
    - Der Preis DARF NICHT neu berechnet werden. Nutze IMMER den Wert "Preis: X Euro" aus den Fakten.
    - Nenne die Ausfahrtszeit nur, wenn das Auto zum simulierten Zeitpunkt bereits ausgefahren war.
    - Wenn die Ausfahrt in der Zukunft liegt → NICHT erwähnen.
    - Antworte professionell, kurz und maximal in 2–3 Sätzen.
    """
    )

    return response.output_text


# -------------------------------------------------
# 6. Streamlit UI
# -------------------------------------------------
st.title("🚗 SmartPark – KI Parksystem (Elias Maalouf)")
st.write("Einfaches Dashboard + KI-Fragen zum Parkplatzsystem.")
st.write("🕒 Angenommener Zeitpunkt: **15.12.2025 – 16:00 Uhr**")

# -------------------------------------------------
# Bereich: Kennzeichen-Abfrage
# -------------------------------------------------
st.subheader("🔍 Kennzeichen-Abfrage")

plate_input = st.text_input("Kennzeichen eingeben (z.B. EL1234):", key="plate")
plate = plate_input.replace(" ", "").upper()

# Schnell-Buttons für typische Fragen
st.write("📌 **Schnellfragen:**")

if "question" not in st.session_state:
    st.session_state["question"] = ""

col1, col2, col3 = st.columns(3)

if col1.button("Ist das Auto da?"):
    st.session_state["question"] = "Ist das Fahrzeug aktuell im Parkplatz?"

if col2.button("Seit wann steht es da?"):
    st.session_state["question"] = "Seit wann parkt dieses Fahrzeug hier?"

if col3.button("Parkpreis?"):
    st.session_state["question"] = "Wie hoch ist der bisherige Parkpreis?"

# Textfeld, das Session-State anzeigt
user_question = st.text_input("Frage an das Parksystem:", key="question")

# 🎯 KI-Antwort Button
st.write("---")
if st.button("🤖 Frag KI"):
    if plate not in parkdata:
        st.error("❌ Kennzeichen nicht gefunden.")
    else:
        data = parkdata[plate]
        details = calculate_parking_details(data["in"], data["out"])

        # Parkdaten anzeigen
        st.subheader("📄 Parkdaten")
        st.write(f"**Einfahrt:** {data['in']}")
        st.write(f"**Ausfahrt:** {details['exit_time']}")
        st.write(f"**Parkdauer (Std):** {details['duration_hours']}")
        st.write(f"**Preis:** {details['price']} €")
        st.write(f"**Parkplatz:** {data['parking_spot']}")
        st.write("---")

        # KI-Antwort
        st.subheader("🤖 KI-Antwort")

        with st.spinner("🔍 KI analysiert die Parkdaten..."):
            ai_answer = ask_ai(user_question, plate)

        st.success("Fertig!")
        st.write(ai_answer)

# -------------------------------------------------
# Bereich: Aktive Autos
# -------------------------------------------------
st.subheader("🚘 Aktive Autos (noch im Parkplatz)")

if st.button("Alle aktiven Autos anzeigen"):
    active = {k: v for k, v in parkdata.items() if v["out"] is None}

    if not active:
        st.info("Derzeit sind keine Fahrzeuge aktiv im Parkplatz.")
    else:
        for p, data in active.items():
            st.write(f"**{p}** – Parkplatz: {data['parking_spot']} – Einfahrt: {data['in']}")

# -------------------------------------------------
# Bereich: Autos von heute
# -------------------------------------------------
st.subheader("📅 Autos, die heute eingeparkt haben")

TODAY_SIM = "2025-12-15"

if st.button("Autos von heute anzeigen"):
    entries_today = {k: v for k, v in parkdata.items() if v["in"].startswith(TODAY_SIM)}

    if not entries_today:
        st.info("Keine Einfahrten am 15.12.2025 gefunden.")
    else:
        for plate, data in entries_today.items():
            st.write(f"**{plate}** – Einfahrt: {data['in']} – Parkplatz: {data['parking_spot']}")

# -------------------------------------------------
# Bereich: Längste Parkdauer
# -------------------------------------------------
st.subheader("⏳ Längste Parkdauer")

if st.button("Längste Parkdauer anzeigen"):
    durations = {plate: calculate_parking_details(v["in"], v["out"])["raw_duration"]
                 for plate, v in parkdata.items()}

    longest_plate = max(durations, key=durations.get)
    longest_data = parkdata[longest_plate]
    longest_details = calculate_parking_details(longest_data["in"], longest_data["out"])

    st.success(f"🚗 **Längste Parkdauer:** {longest_plate}")
    st.write(f"**Einfahrt:** {longest_data['in']}")
    st.write(f"**Ausfahrt:** {longest_details['exit_time']}")
    st.write(f"**Stunden:** {longest_details['duration_hours']}")
    st.write(f"**Parkplatz:** {longest_data['parking_spot']}")
