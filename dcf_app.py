import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
from fpdf import FPDF
import datetime
import json

# --- CONFIGURATIE ---
st.set_page_config(page_title="DCF Valuation Pro", layout="wide")

# --- FUNCTIES ---

def create_pdf(bedrijf, datum, inputs, resultaten, df_projectie):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"Waarderingsrapport: {bedrijf}", ln=True, align='C')
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(0, 10, f"Datum analyse: {datum}", ln=True, align='C')
    pdf.ln(10)
    
    # Sectie 1: Resultaten
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "1. Waarderingsresultaten", ln=True)
    pdf.set_font("Arial", '', 10)
    for key, value in resultaten.items():
        pdf.cell(100, 8, f"{key}", border=0)
        pdf.cell(50, 8, f"{value}", border=0, ln=True)
    pdf.ln(5)

    # Sectie 2: Inputs
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "2. Gebruikte Parameters & Dynamiek", ln=True)
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

    # Sectie 3: Tabel
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "3. Projectie (Details)", ln=True)
    pdf.set_font("Arial", 'B', 7) 
    
    headers = ["Jaar", "Groei%", "Omzet", "EBIT%", "EBIT", "FCFF", "PV FCFF"]
    col_widths = [15, 15, 25, 15, 25, 25, 25]
    
    for i, head in enumerate(headers):
        pdf.cell(col_widths[i], 8, head, border=1)
    pdf.ln()
    
    pdf.set_font("Arial", '', 7)
    for index, row in df_projectie.iterrows():
        vals = [
            str(int(row['Jaar'])),
            f"{row['Gebruikte Groei']*100:.1f}%",
            f"{row['Omzet']:.1f}",
            f"{row['Gebruikte Marge']*100:.1f}%",
            f"{row['EBIT']:.1f}",
            f"{row['FCFF']:.1f}",
            f"{row['PV FCFF']:.1f}"
        ]
        for i, val in enumerate(vals):
            pdf.cell(col_widths[i], 8, val, border=1)
        pdf.ln()

    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- INITIALISATIE SESSION STATE ---
defaults = {
    "bedrijfsnaam": "Mijn Bedrijf", "ticker": "AAPL",
    "projectie_jaren": 10, "basis_omzet": 100.0, "ebit_marge": 20.0,
    "tax_rate": 25.0, "invested_cap": 100.0, "shares": 10.0,
    "target_sales_to_cap": 1.0, 
    "revenue_growth": 5.0, "wacc": 9.0,
    "debt": 20.0, "cash": 5.0, "margin_safety": 30,
    "term_growth": 2.0, "term_roic": 15.0,
    "dyn_groei_start": 3, "dyn_groei_delta": -1.0,
    "dyn_marge_start": 3, "dyn_marge_delta": 0.0,
    "dyn_tax_start": 5, "dyn_tax_delta": 0.0,
    "dyn_s2c_start": 5, "dyn_s2c_delta": 0.0
}

for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- SIDEBAR: OPSLAAN & LADEN ---
st.sidebar.title("📁 Bestandsbeheer")
uploaded_file = st.sidebar.file_uploader("📂 Selecteer bestand (.json)", type=["json"])

if uploaded_file is not None:
    if st.sidebar.button("⚠️ Laad data uit bestand"):
        try:
            data = json.load(uploaded_file)
            for key, value in data.items():
                st.session_state[key] = value
            st.sidebar.success("Instellingen geladen!")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Fout bij laden: {e}")

st.sidebar.markdown("---")

# --- SIDEBAR: INPUTS ---
st.sidebar.header("1. Bedrijfsgegevens")
bedrijfsnaam = st.sidebar.text_input("Bedrijfsnaam", key="bedrijfsnaam")
ticker_symbol = st.sidebar.text_input("Ticker Symbool", key="ticker")
analyse_datum = st.sidebar.date_input("Datum Analyse", datetime.date.today())

huidige_koers = 0.0
if ticker_symbol:
    try:
        stock = yf.Ticker(ticker_symbol)
        history = stock.history(period="1d")
        if not history.empty:
            huidige_koers = history['Close'].iloc[-1]
            st.sidebar.success(f"Koers: {huidige_koers:.2f}")
    except:
        pass

st.sidebar.header("2. Projectie & Groei")
projectie_jaren = st.sidebar.slider("Aantal jaren", 5, 30, key="projectie_jaren")
omzet_groei = st.sidebar.number_input("Basis Omzetgroei (%)", step=0.1, key="revenue_growth") / 100

with st.sidebar.expander("⚡️ Dynamische Groei Aanpassing"):
    st.write("Pas de groei aan vanaf een bepaald jaar.")
    dyn_groei_start = st.number_input("Startjaar correctie (Groei)", min_value=1, max_value=30, step=1, key="dyn_groei_start")
    dyn_groei_delta = st.number_input("Correctie (%)", step=0.1, key="dyn_groei_delta") / 100

st.sidebar.header("3. Startwaarden & Marges")
basis_omzet = st.sidebar.number_input("Omzet (mln)", key="basis_omzet")
basis_ebit_marge = st.sidebar.number_input("Basis EBIT Marge (%)", step=0.5, key="ebit_marge") / 100

with st.sidebar.expander("⚡️ Dynamische Marge Aanpassing"):
    dyn_marge_start = st.number_input("Startjaar correctie (Marge)", min_value=1, max_value=30, step=1, key="dyn_marge_start")
    dyn_marge_delta = st.number_input("Correctie Marge (%)", step=0.1, key="dyn_marge_delta") / 100

invest_kapitaal_basis = st.sidebar.number_input("Geïnvesteerd Kapitaal", key="invested_cap")
aantal_aandelen = st.sidebar.number_input("Aantal Aandelen (mln)", key="shares")

st.sidebar.header("4. Investeringsbeleid (Efficiëntie)")
huidige_ratio_berekend = basis_omzet / invest_kapitaal_basis if invest_kapitaal_basis > 0 else 1.0
st.sidebar.caption(f"Huidige Ratio (Jaar 0): {huidige_ratio_berekend:.2f}")

sales_to_cap_target = st.sidebar.number_input(
    "Basis Sales-to-Capital Ratio", 
    min_value=0.1, 
    max_value=20.0, 
    step=0.01,           
    format="%.2f",       
    key="target_sales_to_cap"
)

with st.sidebar.expander("⚡️ Dynamische Efficiëntie Aanpassing"):
    dyn_s2c_start = st.number_input("Startjaar correctie (S2C)", min_value=1, max_value=30, step=1, key="dyn_s2c_start")
    dyn_s2c_delta = st.number_input("Correctie Ratio (+/-)", step=0.01, format="%.2f", key="dyn_s2c_delta")

st.sidebar.header("5. Belasting & WACC")
belastingtarief = st.sidebar.number_input("Basis Belasting (%)", step=1.0, key="tax_rate") / 100

with st.sidebar.expander("⚡️ Dynamische Belasting Aanpassing"):
    dyn_tax_start = st.number_input("Startjaar correctie (Tax)", min_value=1, max_value=30, step=1, key="dyn_tax_start")
    dyn_tax_delta = st.number_input("Correctie Tax (%)", step=0.1, key="dyn_tax_delta") / 100

wacc = st.sidebar.number_input("WACC (%)", step=0.1, key="wacc") / 100

st.sidebar.header("6. Financiële Positie")
schulden = st.sidebar.number_input("Schulden", key="debt")
kasmiddelen = st.sidebar.number_input("Kasmiddelen", key="cash")
veiligheidsmarge = st.sidebar.slider("Veiligheidsmarge (%)", 0, 50, key="margin_safety") / 100

st.sidebar.header("7. Terminal Value")
terminal_growth = st.sidebar.number_input("Eeuwige Groei (%)", step=0.1, key="term_growth") / 100
terminal_roic = st.sidebar.number_input("Eeuwige ROIC (%)", step=0.5, key="term_roic") / 100

# --- KNOP VOOR OPSLAAN ---
st.sidebar.markdown("---")
export_data = {key: st.session_state[key] for key in defaults.keys()}
json_string = json.dumps(export_data, indent=4)
st.sidebar.download_button("💾 Sla instellingen op", json_string, file_name=f"config_{bedrijfsnaam}.json", mime="application/json")

# --- BEREKENINGEN ---
jaren = range(1, projectie_jaren + 1)
data = []
huidige_omzet = basis_omzet
huidig_kapitaal = invest_kapitaal_basis
discount_factors = []

for jaar in jaren:
    # 1. Bepaal de dynamische variabelen
    actuele_groei = omzet_groei
    if jaar >= dyn_groei_start:
        actuele_groei += dyn_groei_delta
        
    actuele_marge = basis_ebit_marge
    if jaar >= dyn_marge_start:
        actuele_marge += dyn_marge_delta
        
    actuele_tax = belastingtarief
    if jaar >= dyn_tax_start:
        actuele_tax += dyn_tax_delta
        
    actuele_s2c = sales_to_cap_target
    if jaar >= dyn_s2c_start:
        actuele_s2c += dyn_s2c_delta

    # 2. Bereken
    huidige_omzet = huidige_omzet * (1 + actuele_groei)
    ebit = huidige_omzet * actuele_marge
    nopat = ebit * (1 - actuele_tax)
    
    vereist_kapitaal = huidige_omzet / actuele_s2c
    groei_investeringen = vereist_kapitaal - huidig_kapitaal
    huidig_kapitaal = vereist_kapitaal
    
    fcff = nopat - groei_investeringen
    discount_factor = 1 / ((1 + wacc) ** jaar)
    pv_fcff = fcff * discount_factor
    discount_factors.append(discount_factor)
    
    data.append({
        "Jaar": jaar, 
        "Omzet": huidige_omzet, 
        "Gebruikte Groei": actuele_groei,
        "Gebruikte Marge": actuele_marge,
        "EBIT": ebit, 
        "NOPAT": nopat, 
        "Investering": groei_investeringen, 
        "FCFF": fcff, 
        "PV FCFF": pv_fcff
    })

df = pd.DataFrame(data)

# Terminal Value
last_nopat = data[-1]["NOPAT"]
terminal_nopat = last_nopat * (1 + terminal_growth)
reinv_rate = terminal_growth / terminal_roic if terminal_roic > 0 else 0
terminal_fcff = terminal_nopat * (1 - reinv_rate)
terminal_value = terminal_fcff / (wacc - terminal_growth)
pv_terminal = terminal_value * discount_factors[-1]

waarde_expliciet = df["PV FCFF"].sum()
waarde_perpetueel = pv_terminal
ondernemingswaarde = waarde_expliciet + waarde_perpetueel
aandeelhouderswaarde = ondernemingswaarde - schulden + kasmiddelen
waarde_per_aandeel = aandeelhouderswaarde / aantal_aandelen
waarde_met_marge = waarde_per_aandeel * (1 - veiligheidsmarge)

# Upside
upside = 0.0
if huidige_koers > 0:
    upside = (waarde_per_aandeel - huidige_koers) / huidige_koers

# --- HOOFDSCHERM ---
st.title("📊 DCF Valuation Pro")
st.subheader(f"Analyse: {bedrijfsnaam}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Intrinsieke Waarde", f"€ {waarde_per_aandeel:,.2f}")
c2.metric(f"Na Marge ({int(veiligheidsmarge*100)}%)", f"€ {waarde_met_marge:,.2f}")
if huidige_koers > 0:
    c3.metric("Actuele Koers", f"{huidige_koers:.2f}")
    c4.metric("Potentieel", f"{upside:.1%}", delta_color="normal" if upside > 0 else "inverse")

st.divider()

tab1, tab2, tab3 = st.tabs(["📉 Grafieken", "📋 Detail Data", "📄 Rapport"])

with tab1:
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        fig_water = go.Figure(go.Waterfall(
            name = "Waardering", orientation = "v",
            measure = ["relative", "relative", "total", "relative", "relative", "total"],
            x = ["Expliciet", "Terminal", "EV", "Schuld", "Cash", "Equity"],
            y = [waarde_expliciet, waarde_perpetueel, ondernemingswaarde, -schulden, kasmiddelen, aandeelhouderswaarde],
            connector = {"line":{"color":"rgb(63, 63, 63)"}},
            decreasing = {"marker":{"color":"#EF553B"}}, increasing = {"marker":{"color":"#00CC96"}}, totals = {"marker":{"color":"#636EFA"}}
        ))
        fig_water.update_layout(title="Waardebrug", height=400)
        st.plotly_chart(fig_water, use_container_width=True)
    with col_g2:
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Bar(x=df["Jaar"], y=df["FCFF"], name="FCFF", marker_color='rgba(55, 83, 109, 0.7)'))
        fig_trend.add_trace(go.Scatter(
            x=df["Jaar"], y=df["Gebruikte Marge"], name="EBIT Marge %", 
            yaxis="y2", mode="lines+markers", line=dict(color='firebrick', width=2)
        ))
        fig_trend.update_layout(
            title="Kasstroom & Marge Verloop", 
            height=400,
            yaxis=dict(title="Kasstroom (€ mln)"),
            yaxis2=dict(title="EBIT Marge", overlaying="y", side="right", tickformat=".0%"),
            legend=dict(x=0, y=1.1, orientation="h")
        )
        st.plotly_chart(fig_trend, use_container_width=True)

with tab2:
    st.write("De tabel toont de **daadwerkelijk gebruikte** percentages per jaar.")
    format_dict = {
        "Omzet": "{:,.1f}", "EBIT": "{:,.1f}", "NOPAT": "{:,.1f}", 
        "Investering": "{:,.1f}", "FCFF": "{:,.1f}", "PV FCFF": "{:,.1f}",
        "Gebruikte Groei": "{:.1%}", "Gebruikte Marge": "{:.1%}"
    }
    st.dataframe(df.style.format(format_dict))

with tab3:
    st.write("Genereer een PDF rapport met alle dynamische scenario's.")
    pdf_inputs = {k: st.session_state[k] for k in defaults.keys() if "dyn_" not in k}
    pdf_inputs["--- SCENARIO ---"] = ""
    pdf_inputs[f"Groei vanaf jaar {st.session_state['dyn_groei_start']}"] = f"{st.session_state['dyn_groei_delta']*100:+.1f}%"
    pdf_inputs[f"Marge vanaf jaar {st.session_state['dyn_marge_start']}"] = f"{st.session_state['dyn_marge_delta']*100:+.1f}%"
    
    pdf_results = {
        "Waarde per aandeel": f"EUR {waarde_per_aandeel:,.2f}",
        "Potentieel": f"{upside:.1%}" if huidige_koers > 0 else "N/A"
    }
    pdf_data = create_pdf(bedrijfsnaam, analyse_datum, pdf_inputs, pdf_results, df)
    st.download_button("📄 Download PDF", pdf_data, file_name=f"Report_{bedrijfsnaam}.pdf", mime="application/pdf")
