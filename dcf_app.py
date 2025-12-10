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
st.set_page_config(page_title="DCF Valuation Pro (Community Edition)", layout="wide")

# --- FUNCTIE: DATA COLLECTIE (MINING) ---
def save_analysis_to_hq(bedrijf, ticker, waarde, upside, json_data):
    try:
        # Verbinding maken met jouw privé sheet
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("DCF_Bibliotheek").sheet1
        
        # De rij samenstellen: Leesbaar deel + De volledige JSON dump
        row = [
            str(datetime.date.today()),  # A: Datum
            str(bedrijf),                # B: Bedrijf
            f"€ {waarde:.2f}",           # C: Waarde
            str(ticker),                 # D: Ticker
            f"{upside:.1%}",             # E: Upside
            str(json_data)               # F: DE VOLLEDIGE DATA VOOR JOU
        ]
        
        sheet.append_row(row)
        return True
    except Exception as e:
        return str(e)

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
    "bedrijfsnaam": "Bedrijf X", "ticker": "", "projectie_jaren": 10, "basis_omzet": 100.0, 
    "ebit_marge": 20.0, "tax_rate": 25.0, "invested_cap": 100.0, "shares": 10.0,
    "target_sales_to_cap": 1.0, "revenue_growth": 5.0, "wacc": 9.0, "debt": 20.0, "cash": 5.0, 
    "margin_safety": 30, "term_growth": 2.0, "term_roic": 15.0,
    "dyn_groei_start": 3, "dyn_groei_delta": -1.0, "dyn_marge_start": 3, "dyn_marge_delta": 0.0,
    "dyn_tax_start": 5, "dyn_tax_delta": 0.0, "dyn_s2c_start": 5, "dyn_s2c_delta": 0.0
}
for key, val in defaults.items():
    if key not in st.session_state: st.session_state[key] = val

# --- SIDEBAR: BESTANDEN (ALLEEN LADEN, OPSLAAN GAAT NU ONLINE) ---
st.sidebar.title("📁 Load Data")
uploaded_file = st.sidebar.file_uploader("Heb je een .json bestand?", type=["json"])
if uploaded_file is not None:
    if st.sidebar.button("⚠️ Laad bestand"):
        try:
            data = json.load(uploaded_file)
            for key, value in data.items(): st.session_state[key] = value
            st.sidebar.success("Geladen!"); st.rerun()
        except Exception as e: st.sidebar.error(f"Fout: {e}")
st.sidebar.markdown("---")

# --- SIDEBAR INPUTS ---
st.sidebar.header("1. Bedrijf")
bedrijfsnaam = st.sidebar.text_input("Naam", key="bedrijfsnaam")
ticker_symbol = st.sidebar.text_input("Ticker (Yahoo)", key="ticker")
analyse_datum = st.sidebar.date_input("Datum", datetime.date.today())

huidige_koers = 0.0
if ticker_symbol:
    try:
        stock = yf.Ticker(ticker_symbol)
        history = stock.history(period="1d")
        if not history.empty:
            huidige_koers = history['Close'].iloc[-1]
            st.sidebar.success(f"Koers: {huidige_koers:.2f}")
    except: pass

st.sidebar.header("2. Projectie")
projectie_jaren = st.sidebar.slider("Jaren", 5, 30, key="projectie_jaren")
omzet_groei = st.sidebar.number_input("Groei %", step=0.1, key="revenue_growth") / 100
with st.sidebar.expander("Dynamische Groei"):
    dyn_groei_start = st.number_input("Startjaar", min_value=1, key="dyn_groei_start")
    dyn_groei_delta = st.number_input("Correctie %", step=0.1, key="dyn_groei_delta") / 100

st.sidebar.header("3. Marges & Start")
basis_omzet = st.sidebar.number_input("Omzet", key="basis_omzet")
basis_ebit_marge = st.sidebar.number_input("EBIT Marge %", step=0.5, key="ebit_marge") / 100
with st.sidebar.expander("Dynamische Marge"):
    dyn_marge_start = st.number_input("Startjaar", min_value=1, key="dyn_marge_start")
    dyn_marge_delta = st.number_input("Correctie %", step=0.1, key="dyn_marge_delta") / 100
invest_kapitaal_basis = st.sidebar.number_input("Geïnv. Kapitaal", key="invested_cap")
aantal_aandelen = st.sidebar.number_input("Aandelen", key="shares")

st.sidebar.header("4. Efficiëntie")
sales_to_cap_target = st.sidebar.number_input("Sales-to-Cap", 0.1, 20.0, step=0.01, format="%.2f", key="target_sales_to_cap")
with st.sidebar.expander("Dynamische Efficiëntie"):
    dyn_s2c_start = st.number_input("Startjaar", min_value=1, key="dyn_s2c_start")
    dyn_s2c_delta = st.number_input("Correctie", step=0.01, format="%.2f", key="dyn_s2c_delta")

st.sidebar.header("5. Tax & WACC")
belastingtarief = st.sidebar.number_input("Belasting %", step=1.0, key="tax_rate") / 100
with st.sidebar.expander("Dynamische Tax"):
    dyn_tax_start = st.number_input("Startjaar", min_value=1, key="dyn_tax_start")
    dyn_tax_delta = st.number_input("Correctie %", step=0.1, key="dyn_tax_delta") / 100
wacc = st.sidebar.number_input("WACC %", step=0.1, key="wacc") / 100

st.sidebar.header("6. Financiën")
schulden = st.sidebar.number_input("Schuld", key="debt")
kasmiddelen = st.sidebar.number_input("Cash", key="cash")
veiligheidsmarge = st.sidebar.slider("Veiligheidsmarge %", 0, 50, key="margin_safety") / 100

st.sidebar.header("7. Terminal")
terminal_growth = st.sidebar.number_input("Term. Groei %", step=0.1, key="term_growth") / 100
terminal_roic = st.sidebar.number_input("Term. ROIC %", step=0.5, key="term_roic") / 100

# --- BEREKENING ---
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

# --- DASHBOARD ---
st.title("📊 DCF Valuation Tool (Community Edition)")
st.info("Deze tool is gratis te gebruiken. Door je analyse op te slaan, draag je bij aan de publieke database.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Intrinsieke Waarde", f"€ {val_per_share:,.2f}")
c2.metric(f"Na Marge ({int(veiligheidsmarge*100)}%)", f"€ {val_marge:,.2f}")
c3.metric("Actuele Koers", f"{huidige_koers:.2f}" if huidige_koers>0 else "N/A")
c4.metric("Potentieel", f"{upside:.1%}" if huidige_koers>0 else "N/A", delta_color="normal" if upside>0 else "inverse")

st.divider()
tab1, tab2, tab3 = st.tabs(["📉 Grafieken", "📋 Data", "💾 Deel & Download"])

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
    st.write("### 1. Download voor jezelf (PDF)")
    pdf_in = {k: st.session_state[k] for k in defaults.keys() if "dyn_" not in k}
    pdf_res = {"Waarde per aandeel": f"EUR {val_per_share:,.2f}", "Potentieel": f"{upside:.1%}" if huidige_koers > 0 else "N/A"}
    pdf_d = create_pdf(bedrijfsnaam, analyse_datum, pdf_in, pdf_res, df)
    st.download_button("📄 Download PDF Rapport", pdf_d, file_name=f"Report_{bedrijfsnaam}.pdf", mime="application/pdf")
    
    st.divider()
    
    st.write("### 2. Deel Analyse met de Community")
    st.write("Door hieronder te klikken, wordt jouw analyse opgeslagen in de centrale database. Jij kunt deze zelf ook weer opvragen door de JSON op te slaan.")
    
    if st.button("🚀 Voeg toe aan DCF Database"):
        # We maken een JSON string van de HELE sessie state
        full_json_dump = json.dumps({k: st.session_state[k] for k in defaults.keys()})
        
        res = save_analysis_to_hq(bedrijfsnaam, ticker_symbol, val_per_share, upside, full_json_dump)
        
        if res is True: 
            st.success("Bedankt! Jouw analyse is veilig opgeslagen.")
            st.balloons()
            # Optioneel: Bied de JSON ook direct als download aan voor de gebruiker zelf
            st.download_button("📥 Download jouw .json (voor eigen gebruik)", full_json_dump, file_name=f"{bedrijfsnaam}_data.json", mime="application/json")
        else: 
            st.error(f"Er ging iets mis: {res}")
