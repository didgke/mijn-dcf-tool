import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from fpdf import FPDF
import datetime
import json
import os
import csv

# --- CONFIGURATION ---
st.set_page_config(page_title="DCF Valuation Pro", layout="wide")

# --- FUNCTION: LOCAL SAVE (CSV) ---
def save_to_local_csv(company, ticker, value, upside, json_data):
    try:
        file_name = "dcf_history.csv"
        file_exists = os.path.isfile(file_name)
        
        row = [
            str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            str(company),
            f"{value:.2f}",
            str(ticker),
            f"{upside:.1%}",
            str(json_data)
        ]
        
        with open(file_name, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Timestamp", "Company", "Value", "Ticker", "Upside", "Settings_JSON"])
            writer.writerow(row)
        return True
    except Exception as e:
        print(f"Save error: {e}")
        return False

# --- FUNCTION: PDF GENERATION ---
def create_pdf(company, date, inputs, results, df_projectie):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"Valuation Report: {company}", ln=True, align='C')
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(0, 10, f"Analysis Date: {date}", ln=True, align='C')
    pdf.ln(10)
    
    # Results Section
    pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "1. Valuation Results", ln=True); pdf.set_font("Arial", '', 10)
    for k, v in results.items(): pdf.cell(100, 8, f"{k}", 0); pdf.cell(50, 8, f"{v}", 0, 1)
    pdf.ln(5)
    
    # Parameters Section
    pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "2. Key Assumptions", ln=True); pdf.set_font("Arial", '', 9)
    for k, v in inputs.items():
        if "dyn_" not in k: 
            pdf.cell(90, 6, f"{k}: {v}", border=0); pdf.ln()
    pdf.ln(5)
    
    # Projection Table
    pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, "3. Projections", ln=True); pdf.set_font("Arial", 'B', 7)
    headers = ["Year", "Rev", "EBIT", "NOPAT", "Inv.Cap", "Gr.Inv", "FCFF"]
    col_widths = [10, 25, 20, 20, 25, 20, 20]
    for i, h in enumerate(headers): pdf.cell(col_widths[i], 8, h, 1)
    pdf.ln(); pdf.set_font("Arial", '', 7)
    
    for index, row in df_projectie.iterrows():
        vals = [
            str(int(row['Year'])), 
            f"{row['Revenue']:.1f}", 
            f"{row['EBIT']:.1f}",
            f"{row['NOPAT']:.1f}",
            f"{row['Invested Capital']:.1f}", 
            f"{row['Investment']:.1f}",       
            f"{row['FCFF']:.1f}"
        ]
        for i, val in enumerate(vals): pdf.cell(col_widths[i], 8, val, border=1)
        pdf.ln()
    
    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- INITIALIZE SESSION STATE ---
defaults = {
    "bedrijfsnaam": "Zoetis", "ticker": "ZTS", "projectie_jaren": 10, "basis_omzet": 9256.0, 
    "ebit_marge": 40.3, "tax_rate": 20.3, "invested_cap": 9792.0, "shares": 443.2,
    "target_sales_to_cap": 0.95, "initial_investment": 312.0, 
    "revenue_growth": 5.0, "wacc": 8.9, "debt": 7273.0, "cash": 1899.0, 
    "margin_safety": 0, "term_growth": 4.1, "term_roic": 15.0, "current_price": 0.0,
    "dyn_groei_start": 10, "dyn_groei_delta": -0.9, "dyn_marge_start": 3, "dyn_marge_delta": 0.0,
    "dyn_tax_start": 5, "dyn_tax_delta": 0.0, "dyn_s2c_start": 5, "dyn_s2c_delta": 0.0
}
for key, val in defaults.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 1. LOAD FILE (Top of Sidebar) ---
st.sidebar.title("Settings")
uploaded_file = st.sidebar.file_uploader("📂 Load previous analysis (.json)", type=["json"])

if uploaded_file is not None:
    if st.sidebar.button("⚠️ Apply Settings"):
        try:
            data = json.load(uploaded_file)
            for key, value in data.items():
                st.session_state[key] = value
            st.sidebar.success("Loaded! Settings applied below.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

st.sidebar.markdown("---")

# --- 2. INPUT FORM ---
with st.sidebar.form(key='dcf_form'):
    
    st.header("1. Company Profile")
    bedrijfsnaam = st.text_input("Company Name", value=st.session_state['bedrijfsnaam'])
    ticker_symbol = st.text_input("Ticker (Optional)", value=st.session_state['ticker'])
    huidige_koers_input = st.number_input("Current Share Price (€)", value=float(st.session_state['current_price']), step=0.5)
    analyse_datum = st.date_input("Analysis Date", datetime.date.today())

    st.header("2. Projection & Growth")
    projectie_jaren = st.slider("Projection Years", 5, 30, value=int(st.session_state['projectie_jaren']))
    omzet_groei = st.number_input("Base Growth Rate (%)", step=0.1, value=float(st.session_state['revenue_growth'])) / 100
    with st.expander("⚡️ Dynamic Growth Adjustment"):
        dyn_groei_start = st.number_input("Start Year", min_value=1, value=int(st.session_state['dyn_groei_start']))
        dyn_groei_delta = st.number_input("Correction (%)", step=0.1, value=float(st.session_state['dyn_groei_delta'])) / 100

    st.header("3. Margins & Base")
    basis_omzet = st.number_input("Base Revenue (Year 0)", value=float(st.session_state['basis_omzet']))
    basis_ebit_marge = st.number_input("Base EBIT Margin (%)", step=0.1, value=float(st.session_state['ebit_marge'])) / 100
    with st.expander("⚡️ Dynamic Margin Adjustment"):
        dyn_marge_start = st.number_input("Start Year (Margin)", min_value=1, value=int(st.session_state['dyn_marge_start']))
        dyn_marge_delta = st.number_input("Correction Margin (%)", step=0.1, value=float(st.session_state['dyn_marge_delta'])) / 100
    
    invest_kapitaal_basis = st.number_input("Invested Capital (Year 0)", value=float(st.session_state['invested_cap']))
    aantal_aandelen = st.number_input("Shares Outstanding (mln)", value=float(st.session_state['shares']))

    st.header("4. Efficiency & Investment")
    st.info("Invested Capital Year 1 = Inv.Cap Year 0 + Initial Investment Year 0.")
    # Aangepast label om duidelijk te maken dat dit bij Jaar 0 hoort
    initial_investment_input = st.number_input("Initial Growth Investment (Year 0)", value=float(st.session_state['initial_investment']))
    
    sales_to_cap_target = st.number_input("Sales-to-Capital Ratio (Year 2+)", 0.1, 20.0, step=0.01, format="%.2f", value=float(st.session_state['target_sales_to_cap']))
    with st.expander("⚡️ Dynamic Efficiency"):
        dyn_s2c_start = st.number_input("Start Year (S2C)", min_value=1, value=int(st.session_state['dyn_s2c_start']))
        dyn_s2c_delta = st.number_input("Correction S2C", step=0.01, format="%.2f", value=float(st.session_state['dyn_s2c_delta']))

    st.header("5. Tax & WACC")
    belastingtarief = st.number_input("Tax Rate (%)", step=0.1, value=float(st.session_state['tax_rate'])) / 100
    with st.expander("⚡️ Dynamic Tax"):
        dyn_tax_start = st.number_input("Start Year (Tax)", min_value=1, value=int(st.session_state['dyn_tax_start']))
        dyn_tax_delta = st.number_input("Correction Tax (%)", step=0.1, value=float(st.session_state['dyn_tax_delta'])) / 100
    wacc = st.number_input("WACC (%)", step=0.1, value=float(st.session_state['wacc'])) / 100

    st.header("6. Financial Position")
    schulden = st.number_input("Total Debt", value=float(st.session_state['debt']))
    kasmiddelen = st.number_input("Cash & Equivalents", value=float(st.session_state['cash']))
    
    veiligheidsmarge = st.slider("Margin of Safety (%)", 0, 50, value=int(st.session_state['margin_safety']), step=1) / 100

    st.header("7. Terminal Value")
    terminal_growth = st.number_input("Terminal Growth (%)", step=0.1, value=float(st.session_state['term_growth'])) / 100
    terminal_roic = st.number_input("Terminal ROIC (%)", step=0.5, value=float(st.session_state['term_roic'])) / 100
    
    st.markdown("---")
    # SUBMIT BUTTON
    submit_button = st.form_submit_button("🔄 Calculate & Update Model")

# --- CALCULATION LOGIC ---
val_per_share = 0.0
val_marge = 0.0
upside = 0.0
df = pd.DataFrame()
waarde_expl = 0
pv_term = 0
onderneming = 0
equity = 0

if submit_button:
    # --- 1. UPDATE SESSION STATE ---
    st.session_state['bedrijfsnaam'] = bedrijfsnaam
    st.session_state['ticker'] = ticker_symbol
    st.session_state['current_price'] = huidige_koers_input
    st.session_state['projectie_jaren'] = projectie_jaren
    st.session_state['basis_omzet'] = basis_omzet
    st.session_state['invested_cap'] = invest_kapitaal_basis
    st.session_state['shares'] = aantal_aandelen
    st.session_state['initial_investment'] = initial_investment_input
    st.session_state['target_sales_to_cap'] = sales_to_cap_target
    st.session_state['debt'] = schulden
    st.session_state['cash'] = kasmiddelen
    st.session_state['revenue_growth'] = omzet_groei * 100
    st.session_state['ebit_marge'] = basis_ebit_marge * 100
    st.session_state['tax_rate'] = belastingtarief * 100
    st.session_state['wacc'] = wacc * 100
    st.session_state['margin_safety'] = veiligheidsmarge * 100
    st.session_state['term_growth'] = terminal_growth * 100
    st.session_state['term_roic'] = terminal_roic * 100
    st.session_state['dyn_groei_start'] = dyn_groei_start
    st.session_state['dyn_groei_delta'] = dyn_groei_delta * 100
    st.session_state['dyn_marge_start'] = dyn_marge_start
    st.session_state['dyn_marge_delta'] = dyn_marge_delta * 100
    st.session_state['dyn_tax_start'] = dyn_tax_start
    st.session_state['dyn_tax_delta'] = dyn_tax_delta * 100
    st.session_state['dyn_s2c_start'] = dyn_s2c_start
    st.session_state['dyn_s2c_delta'] = dyn_s2c_delta
    
    huidige_koers = huidige_koers_input

    # --- 2. PERFORM DCF (UPDATED LOGIC) ---
    jaren = range(1, projectie_jaren + 1)
    data, discount_factors = [], []
    
    # SETUP JAAR 0 WAARDEN
    huidige_omzet = basis_omzet
    # Kapitaal Jaar 1 is gebaseerd op Start Kapitaal + Investering in Jaar 0
    huidig_kapitaal = invest_kapitaal_basis + initial_investment_input

    for jaar in jaren:
        # Bepaal groeipercentages en inputs voor DIT jaar
        groei_percentage_nu = omzet_groei + (dyn_groei_delta if jaar >= dyn_groei_start else 0)
        
        # Bepaal groeipercentages voor VOLGEND jaar (voor investeringsberekening)
        if jaar < projectie_jaren:
            groei_percentage_volgend = omzet_groei + (dyn_groei_delta if (jaar + 1) >= dyn_groei_start else 0)
        else:
            # Voor het laatste jaar gebruiken we de terminal growth om de volgende omzet in te schatten
            groei_percentage_volgend = terminal_growth

        actuele_marge = basis_ebit_marge + (dyn_marge_delta if jaar >= dyn_marge_start else 0)
        actuele_tax = belastingtarief + (dyn_tax_delta if jaar >= dyn_tax_start else 0)
        actuele_s2c = sales_to_cap_target + (dyn_s2c_delta if jaar >= dyn_s2c_start else 0)

        # 1. Omzet stap
        omzet_dit_jaar = huidige_omzet * (1 + groei_percentage_nu)
        
        # 2. Winst stap
        ebit = omzet_dit_jaar * actuele_marge
        nopat = ebit * (1 - actuele_tax)
        
        # 3. Investering stap (FORWARD LOOKING)
        # "Groeiinvestering vanaf jaar 1 bereken je door de jaar omzet van jaar 1 af te trekken van jaar 2"
        omzet_volgend_jaar = omzet_dit_jaar * (1 + groei_percentage_volgend)
        delta_omzet = omzet_volgend_jaar - omzet_dit_jaar
        
        if actuele_s2c != 0:
            inv = delta_omzet / actuele_s2c
        else:
            inv = 0
        
        # 4. Cashflow stap
        fcff = nopat - inv
        dfactor = 1 / ((1 + wacc) ** jaar)
        discount_factors.append(dfactor)
        
        data.append({
            "Year": jaar, 
            "Revenue": omzet_dit_jaar, 
            "EBIT": ebit, 
            "NOPAT": nopat, 
            # Huidig kapitaal is wat we aan het begin van het jaar hadden (vorige cap + vorige inv)
            "Invested Capital": huidig_kapitaal, 
            "Investment": inv,
            "FCFF": fcff, 
            "PV FCFF": fcff * dfactor
        })

        # Update variabelen voor volgende loop
        # Het kapitaal voor volgend jaar = kapitaal dit jaar + investering dit jaar
        huidig_kapitaal += inv
        huidige_omzet = omzet_dit_jaar

    df = pd.DataFrame(data)
    
    # Terminal Value
    if not df.empty:
        last_nopat = data[-1]["NOPAT"]
        term_nop = last_nopat * (1 + terminal_growth)
        
        # Voor TV gebruiken we vaak return on new invested capital (RONIC/ROIC)
        reinv_rate = terminal_growth / terminal_roic if terminal_roic > 0 else 0
        term_fcff = term_nop * (1 - reinv_rate)
        
        term_val = term_fcff / (wacc - terminal_growth)
        pv_term = term_val * discount_factors[-1]

        waarde_expl = df["PV FCFF"].sum()
        onderneming = waarde_expl + pv_term
        equity = onderneming - schulden + kasmiddelen
        val_per_share = equity / aantal_aandelen
        val_marge = val_per_share * (1 - veiligheidsmarge)
        upside = (val_per_share - huidige_koers) / huidige_koers if huidige_koers > 0 else 0

        # Save results
        full_json_dump = json.dumps({k: st.session_state[k] for k in defaults.keys()}, indent=4)
        save_to_local_csv(bedrijfsnaam, ticker_symbol, val_per_share, upside, full_json_dump)

else:
    huidige_koers = st.session_state['current_price']

# --- DASHBOARD UI ---
st.title("📊 DCF Valuation Pro (Offline)")

if df.empty:
    st.info("👈 Enter company details on the left and click **'Calculate & Update Model'** to see the valuation.")
    st.stop()

# Row 1: Per Share Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Intrinsic Value", f"€ {val_per_share:,.2f}")
c2.metric(f"After Margin ({int(veiligheidsmarge*100)}%)", f"€ {val_marge:,.2f}")
c3.metric("Current Price (Input)", f"{huidige_koers:.2f}" if huidige_koers>0 else "N/A")
c4.metric("Upside Potential", f"{upside:.1%}" if huidige_koers>0 else "N/A", delta_color="normal" if upside>0 else "inverse")

# Row 2: Firm Value Metrics
st.caption("Enterprise Value Components")
ce1, ce2, ce3 = st.columns(3)
ce1.metric("PV Projected Cash Flow", f"€ {waarde_expl:,.1f}")
ce2.metric("PV Terminal Value", f"€ {pv_term:,.1f}")
ce3.metric("Enterprise Value (Sum)", f"€ {onderneming:,.1f}")

st.divider()
tab1, tab2, tab3 = st.tabs(["📉 Charts", "📋 Data (Compare with Excel)", "💾 Download"])

with tab1:
    cg1, cg2 = st.columns(2)
    with cg1:
        fig_w = go.Figure(go.Waterfall(
            name="Valuation", orientation="v", 
            measure=["relative", "relative", "total", "relative", "relative", "total"], 
            x=["Explicit Period", "Terminal Value", "Enterprise Value", "Debt", "Cash", "Equity Value"], 
            y=[waarde_expl, pv_term, onderneming, -schulden, kasmiddelen, equity], 
            connector={"line":{"color":"rgb(63, 63, 63)"}}, 
            decreasing={"marker":{"color":"#EF553B"}}, increasing={"marker":{"color":"#00CC96"}}, totals={"marker":{"color":"#636EFA"}}
        ))
        fig_w.update_layout(title="Valuation Bridge", height=400)
        st.plotly_chart(fig_w, use_container_width=True)
    with cg2:
        fig_t = go.Figure()
        fig_t.add_trace(go.Bar(x=df["Year"], y=df["FCFF"], name="FCFF", marker_color='rgba(55, 83, 109, 0.7)'))
        fig_t.add_trace(go.Bar(x=df["Year"], y=df["Investment"], name="Growth Investment", marker_color='rgba(239, 85, 59, 0.7)'))
        fig_t.add_trace(go.Scatter(x=df["Year"], y=df["Invested Capital"], name="Tot. Invested Capital", yaxis="y2", mode="lines+markers", line=dict(color='firebrick', width=2)))
        fig_t.update_layout(title="Cash Flow vs Investment", height=400, yaxis2=dict(overlaying="y", side="right", title="Total Capital"), legend=dict(x=0, y=1.1, orientation="h"))
        st.plotly_chart(fig_t, use_container_width=True)

with tab2:
    st.write("Calculations: Inv.Capital Year N = Inv.Capital Year N-1 + Investment Year N-1. Investment is based on Future Growth (Sales N+1 - Sales N).")
    
    display_cols = ["Year", "Revenue", "EBIT", "NOPAT", "Invested Capital", "Investment", "FCFF", "PV FCFF"]
    format_dict = {
        "Revenue": "{:,.1f}", "EBIT": "{:,.1f}", "NOPAT": "{:,.1f}",
        "Invested Capital": "{:,.1f}", "Investment": "{:,.1f}", 
        "FCFF": "{:,.1f}", "PV FCFF": "{:,.1f}"
    }
    st.dataframe(df[display_cols].style.format(format_dict))

with tab3:
    st.write("### PDF Report")
    # PDF gebruikt de opgeslagen sessie waarden
    pdf_in = {k: st.session_state[k] for k in defaults.keys() if "dyn_" not in k}
    pdf_res = {"Value per share": f"EUR {val_per_share:,.2f}", "Upside": f"{upside:.1%}" if huidige_koers > 0 else "N/A"}
    
    pdf_d = create_pdf(bedrijfsnaam, analyse_datum, pdf_in, pdf_res, df)
    st.download_button("📄 Download PDF Report", pdf_d, file_name=f"Report_{bedrijfsnaam}.pdf", mime="application/pdf")
    
    st.write("### Save for later")
    json_out = json.dumps({k: st.session_state[k] for k in defaults.keys()}, indent=4)
    st.download_button("📥 Download Analysis (.json)", json_out, file_name=f"{bedrijfsnaam}_settings.json", mime="application/json")
