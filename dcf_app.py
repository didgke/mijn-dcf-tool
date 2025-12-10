import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
from fpdf import FPDF
import datetime
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURATIE ---
st.set_page_config(page_title="DCF Valuation Pro", layout="wide")

# --- FUNCTIE: SILENT SAVE (Geen meldingen, gewoon opslaan) ---
def silent_save_to_hq(bedrijf, ticker, waarde, upside, json_data):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("DCF_Bibliotheek").sheet1
        
        row = [
            str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")), # Datum + Tijd
            str(bedrijf),
            f"€ {waarde:.2f}",
            str(ticker),
            f"{upside:.1%}",
            str(json_data) # De volledige JSON dump voor jouw bibliotheek
        ]
        sheet.append_row(row)
        return True
    except:
        return False # Als het mislukt, negeren we het (zodat de user geen fout ziet)

# --- PDF FUNCTIE ---
def create_pdf(bedrijf, datum, inputs, resultaten, df_projectie):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"Waarderingsrapport: {bedrijf}", ln=True, align='C')
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(0, 10, f"Datum analyse: {datum}", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "1. Resultaten", ln=True)
    pdf.set_font("Arial", '', 10)
    for k, v in resultaten.items():
        pdf.cell(100, 8, f"{k}", 0); pdf.cell(50, 8, f"{v}", 0, 1)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "2. Parameters", ln=True)
    pdf.set_font("Arial", '', 9)
    keys = list(inputs.keys())
    half = len(keys) // 2
    for i in range(half + 1): 
        if i < len(keys):
            k1, v1 = keys[i], inputs[keys[i]]
            pdf.cell(90, 6, f"{k1}: {v1}", border=0)
        if i + half < len(keys):
            k2, v2 = keys[i+half], inputs[keys[i+half]]
            pdf.cell(90, 6, f"{k2}: {v2}", border=0)
        pdf.ln()
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "3. Projectie", ln=True)
    pdf.set_font("Arial", 'B', 7) 
    headers = ["Jaar", "Groei%", "Omzet", "EBIT%", "EBIT", "FCFF", "PV FCFF"]
    col_widths = [15, 15, 25, 15, 25, 25, 25]
    for i, head in enumerate(headers): pdf.cell(col_widths[i], 8, head, border=1)
    pdf.ln()
    pdf.set_font("Arial", '', 7)
    for index, row in df_projectie.iterrows():
        vals = [
            str(int(row['Jaar'])), f"{row['Gebruikte Groei']*100:.1f}%", f"{row['Omzet']:.1f}",
            f"{row['Gebruikte Marge']*100:.1f}%", f"{row['EBIT']:.1f}", f"{row['FCFF']:.1f}", f"{row['PV FCFF']:.1f}"
        ]
        for i, val in enumerate(vals): pdf.cell(col_widths[i], 8, val, border=1)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- INITIALISATIE ---
defaults = {
    "bedrijfsnaam": "Naamloos Bedrijf", "ticker": "", "projectie_jaren": 10, "basis_omzet": 100.0, 
    "ebit_marge": 20.0, "tax_rate": 25.0, "invested_cap": 100.0, "shares": 10.0,
    "target_sales_to_cap": 1.0, "revenue_growth": 5.0, "wacc": 9.0, "debt": 20.0, "cash": 5.0, 
    "margin_safety": 30, "term_growth": 2.0, "term_roic": 15.0,
    "dyn_groei_start": 3, "dyn_groei_delta": -1.0, "dyn_marge_start": 3, "dyn_marge_delta": 0.0,
    "dyn_tax_start": 5, "dyn_tax_delta": 0.0, "dyn_s2c_start": 5, "dyn_s2c_delta": 0.0
}
for key, val in defaults.items():
    if key not in st.session_state: st.session_state[key] = val

# --- SIDEBAR: START FORMULIER ---
st.sidebar.title("Instellingen")

# We gebruiken een FORMULIER. De app draait pas als je op Submit klikt.
with st.sidebar.form(key='dcf_form'):
    
    st.header("1. Bedrijf")
    # We laden waarden uit session_state zodat ze blijven staan na herladen
    bedrijfsnaam = st.text_input("Naam", value=st.session_state['bedrijfsnaam'])
    ticker_symbol = st.text_input("Ticker (Yahoo)", value=st.session_state['ticker'])
    analyse_datum = st.date_input("Datum", datetime.date.today())

    st.header("2. Projectie")
    projectie_jaren = st.slider("Jaren", 5, 30, value=st.session_state['projectie_jaren'])
    omzet_groei = st.number_input("Basis Groei %", step=0.1, value=st.session_state['revenue_growth']) / 100
    with st.expander("Dynamische Groei"):
        dyn_groei_start = st.number_input("Startjaar", min_value=1, value=st.session_state['dyn_groei_start'])
        dyn_groei_delta = st.number_input("Correctie %", step=0.1, value=st.session_state['dyn_groei_delta']) / 100

    st.header("3. Marges")
    basis_omzet = st.number_input("Basis Omzet", value=st.session_state['basis_omzet'])
    basis_ebit_marge = st.number_input("Basis Marge %", step=0.5, value=st.session_state['ebit_marge']) / 100
    with st.expander("Dynamische Marge"):
        dyn_marge_start = st.number_input("Startjaar (Marge)", min_value=1, value=st.session_state['dyn_marge_start'])
        dyn_marge_delta = st.number_input("Correctie Marge %", step=0.1, value=st.session_state['dyn_marge_delta']) / 100
    
    invest_kapitaal_basis = st.number_input("Geïnv. Kapitaal", value=st.session_state['invested_cap'])
    aantal_aandelen = st.number_input("Aandelen", value=st.session_state['shares'])

    st.header("4. Efficiëntie")
    sales_to_cap_target = st.number_input("S2C Ratio", 0.1, 20.0, step=0.01, format="%.2f", value=st.session_state['target_sales_to_cap'])
    with st.expander("Dynamische Efficiëntie"):
        dyn_s2c_start = st.number_input("Startjaar (S2C)", min_value=1, value=st.session_state['dyn_s2c_start'])
        dyn_s2c_delta = st.number_input("Correctie S2C", step=0.01, format="%.2f", value=st.session_state['dyn_s2c_delta'])

    st.header("5. Tax & WACC")
    belastingtarief = st.number_input("Belasting %", step=1.0, value=st.session_state['tax_rate']) / 100
    with st.expander("Dynamische Tax"):
        dyn_tax_start = st.number_input("Startjaar (Tax)", min_value=1, value=st.session_state['dyn_tax_start'])
        dyn_tax_delta = st.number_input("Correctie Tax %", step=0.1, value=st.session_state['dyn_tax_delta']) / 100
    wacc = st.number_input("WACC %", step=0.1, value=st.session_state['wacc']) / 100

    st.header("6. Financiën")
    schulden = st.number_input("Schuld", value=st.session_state['debt'])
    kasmiddelen = st.number_input("Cash", value=st.session_state['cash'])
    veiligheidsmarge = st.slider("Veiligheidsmarge %", 0, 50, value=st.session_state['margin_safety']) / 100

    st.header("7. Terminal")
    terminal_growth = st.number_input("Term. Groei %", step=0.1, value=st.session_state['term_growth']) / 100
    terminal_roic = st.number_input("Term. ROIC %", step=0.5, value=st.session_state['term_roic']) / 100
    
    st.markdown("---")
    # DE GROTE KNOP: DIT IS DE TRIGGER VOOR BEREKENEN EN OPSLAAN
    submit_button = st.form_submit_button("🔄 Bereken & Update Model")

# --- DATA VERWERKING ---
# We updaten de session state met de waarden uit het formulier
if submit_button:
    st.session_state['bedrijfsnaam'] = bedrijfsnaam
    st.session_state['ticker'] = ticker_symbol
    st.session_state['basis_omzet'] = basis_omzet
    # ... (en zo voort voor alle variabelen, maar Streamlit doet dit deels zelf bij forms)

# Koers ophalen (buiten formulier voor snelheid bij opstarten, of binnen formulier)
huidige_koers = 0.0
if ticker_symbol:
    try:
        stock = yf.Ticker(ticker_symbol)
        history = stock.history(period="1d")
        if not history.empty:
            huidige_koers = history['Close'].iloc[-1]
    except: pass

# --- BEREKENING (Draait alleen als submit geklikt is of bij eerste load) ---
jaren = range(1, projectie_jaren + 1)
data, discount_factors = [], []
huidige_omzet, huidig_kapitaal = basis_omzet, invest_kapitaal_basis

for jaar in jaren:
    actuele_groei = omzet_groei + (dyn_groei_delta if jaar >= dyn_groei_start else 0)
    actuele_marge = basis_ebit_marge + (dyn_marge_delta if jaar >= dyn_marge_start else 0)
    actuele_tax = belastingtarief + (dyn_tax_delta if jaar >= dyn_tax_start else 0)
    actuele_s2c = sales_to_cap_target + (dyn_s2c_delta if jaar >= dyn_s2c_start else 0)

    huidige_omzet *= (1 + actuele_groei)
    ebit = huidige_omzet * actuele_marge
    nopat = ebit * (1 - actuele_tax)
    req_cap = huidige_omzet / actuele_s2c
    inv = req_cap - huidig_kapitaal
    huidig_kapitaal = req_cap
    fcff = nopat - inv
    dfactor = 1 / ((1 + wacc) ** jaar)
    discount_factors.append(dfactor)
    data.append({"Jaar": jaar, "Omzet": huidige_omzet, "Gebruikte Groei": actuele_groei, "Gebruikte Marge": actuele_marge, "EBIT": ebit, "NOPAT": nopat, "Investering": inv, "FCFF": fcff, "PV FCFF": fcff * dfactor})

df = pd.DataFrame(data)
last_nopat = data[-1]["NOPAT"]
term_nop = last_nopat * (1 + terminal_growth)
reinv = terminal_growth / terminal_roic if terminal_roic > 0 else 0
term_fcff = term_nop * (1 - reinv)
term_val = term_fcff / (wacc - terminal_growth)
pv_term = term_val * discount_factors[-1]

waarde_expl = df["PV FCFF"].sum()
onderneming = waarde_expl + pv_term
equity = onderneming - schulden + kasmiddelen
val_per_share = equity / aantal_aandelen
val_marge = val_per_share * (1 - veiligheidsmarge)
upside = (val_per_share - huidige_koers) / huidige_koers if huidige_koers > 0 else 0

# --- AUTOMATISCH OPSLAAN (ALLEN BIJ DRUK OP KNOP) ---
if submit_button:
    # We bereiden de JSON voor
    full_json_dump = json.dumps({
        "bedrijfsnaam": bedrijfsnaam, "ticker": ticker_symbol, "projectie_jaren": projectie_jaren,
        "basis_omzet": basis_omzet, "ebit_marge": basis_ebit_marge * 100, # save as percentage number
        "wacc": wacc * 100,
        # ... Je kunt hier alles toevoegen wat je wilt terugladen
    })
    
    # We slaan op in de achtergrond
    silent_save_to_hq(bedrijfsnaam, ticker_symbol, val_per_share, upside, full_json_dump)
    # Geen melding aan de gebruiker, gebeurt "silent"

# --- DASHBOARD ---
st.title("📊 DCF Valuation Tool (Community Edition)")
st.caption("Alle berekeningen worden uitgevoerd zodra je op 'Bereken & Update' klikt.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Intrinsieke Waarde", f"€ {val_per_share:,.2f}")
c2.metric(f"Na Marge ({int(veiligheidsmarge*100)}%)", f"€ {val_marge:,.2f}")
c3.metric("Actuele Koers", f"{huidige_koers:.2f}" if huidige_koers>0 else "N/A")
c4.metric("Potentieel", f"{upside:.1%}" if huidige_koers>0 else "N/A", delta_color="normal" if upside>0 else "inverse")

st.divider()
tab1, tab2, tab3 = st.tabs(["📉 Grafieken", "📋 Data", "💾 Download"])

with tab1:
    cg1, cg2 = st.columns(2)
    with cg1:
        fig_w = go.Figure(go.Waterfall(name="Waardering", orientation="v", measure=["relative", "relative", "total", "relative", "relative", "total"], x=["Expliciet", "Terminal", "EV", "Schuld", "Cash", "Equity"], y=[waarde_expl, pv_term, onderneming, -schulden, kasmiddelen, equity], connector={"line":{"color":"rgb(63, 63, 63)"}}, decreasing={"marker":{"color":"#EF553B"}}, increasing={"marker":{"color":"#00CC96"}}, totals={"marker":{"color":"#636EFA"}}))
        fig_w.update_layout(title="Waardebrug", height=400)
        st.plotly_chart(fig_w, use_container_width=True)
    with cg2:
        fig_t = go.Figure()
        fig_t.add_trace(go.Bar(x=df["Jaar"], y=df["FCFF"], name="FCFF", marker_color='rgba(55, 83, 109, 0.7)'))
        fig_t.add_trace(go.Scatter(x=df["Jaar"], y=df["Gebruikte Marge"], name="EBIT Marge %", yaxis="y2", mode="lines+markers", line=dict(color='firebrick', width=2)))
        fig_t.update_layout(title="Kasstroom & Marge", height=400, yaxis2=dict(overlaying="y", side="right", tickformat=".0%"), legend=dict(x=0, y=1.1, orientation="h"))
        st.plotly_chart(fig_t, use_container_width=True)

with tab2:
    st.dataframe(df.style.format({"Omzet": "{:,.1f}", "EBIT": "{:,.1f}", "FCFF": "{:,.1f}", "Gebruikte Groei": "{:.1%}", "Gebruikte Marge": "{:.1%}"}))

with tab3:
    st.write("### Download PDF Rapport")
    pdf_in = {k: st.session_state[k] for k in defaults.keys() if "dyn_" not in k}
    pdf_res = {"Waarde per aandeel": f"EUR {val_per_share:,.2f}", "Potentieel": f"{upside:.1%}" if huidige_koers > 0 else "N/A"}
    pdf_d = create_pdf(bedrijfsnaam, analyse_datum, pdf_in, pdf_res, df)
    st.download_button("📄 Download PDF", pdf_d, file_name=f"Report_{bedrijfsnaam}.pdf", mime="application/pdf")
    
    st.write("### Load Data")
    uploaded_file = st.file_uploader("Heb je een .json bestand van een vorige sessie?", type=["json"])
    if uploaded_file is not None:
        if st.button("Laad Instellingen"):
            data = json.load(uploaded_file)
            for key, value in data.items(): st.session_state[key] = value
            st.success("Geladen! Klik nu links op 'Bereken & Update'.")
