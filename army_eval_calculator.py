import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import altair as alt
import math

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Army HR Executive Dashboard v8.5", page_icon="🦅", layout="wide")

# --- CONSTANTS & DICTIONARIES ---
NON_RATED_CODES = [
    "A - AWOL", "C - Confinement", "D - Dropped from rolls", 
    "E - Leave (30+ days)", "F - Under arrest", "I - In transit", 
    "M - Missing in Action", "P - Patient", "Q - Lack of rater qualification", 
    "R - Retirement/Resignation leave", "S - Student", "T - TDY", "W - Prisoner of War"
]

EVAL_TYPES = ["Annual", "Change of Rater", "Change of Duty", "Extended Annual", "Relief for Cause", "Complete the Record", "Academic"]
RANK_GROUPS = ["OER (< 50% Limit)", "NCOER (< 24% Limit)"]

FLAGGED_TERMS = [
    "pregnancy", "pregnant", "medical", "profile", "article 15", "court martial", "court-martial", 
    "religion", "race", "gender", "sexual orientation", "sharp", "eo complaint", "sympathy", 
    "marital status", "spouse", "husband", "wife"
]

# --- HELPER FUNCTIONS ---
def parse_date(date_str):
    if not date_str: return None
    try:
        return datetime.strptime(str(date_str).strip(), "%Y%m%d").date()
    except ValueError: return None

def check_overlaps(periods):
    if not periods: return False
    sorted_periods = sorted(periods, key=lambda x: x['start'])
    for i in range(1, len(sorted_periods)):
        if sorted_periods[i]['start'] <= sorted_periods[i-1]['end']: return True
    return False

def plot_timeline(from_date, thru_date, valid_periods):
    chart_data = [{"Task": "Base Rating Period", "Start": pd.to_datetime(from_date), "End": pd.to_datetime(thru_date), "Type": "Rated Time"}]
    for p in valid_periods:
        code_letter = p['code'].split(" - ")[0]
        chart_data.append({"Task": f"Non-Rated ({code_letter})", "Start": pd.to_datetime(p['start']), "End": pd.to_datetime(p['end']), "Type": "Non-Rated Time"})
    
    chart = alt.Chart(pd.DataFrame(chart_data)).mark_bar(size=30).encode(
        x=alt.X('Start', title='Date', axis=alt.Axis(format='%Y-%m-%d', labelAngle=-45)),
        x2='End',
        y=alt.Y('Task', sort=['Base Rating Period']),
        color=alt.Color('Type', scale=alt.Scale(domain=['Rated Time', 'Non-Rated Time'], range=['#2e7d32', '#d32f2f']), legend=None),
        tooltip=['Task', 'Start', 'End']
    ).properties(height=200).interactive()
    return chart

def calculate_profile_health(total, mqs, limit_type):
    limit = 0.499 if limit_type == "OER (< 50% Limit)" else 0.239
    if total == 0: return 0.0, "Clear for 1st MQ", 0
    current_pct = mqs / total
    projected_pct = (mqs + 1) / (total + 1)
    
    if projected_pct <= limit:
        available = 0
        while ((mqs + available + 1) / (total + available + 1)) <= limit: available += 1
        return current_pct, f"Clear (Can give {available} MQ{'s' if available > 1 else ''})", 0
    else:
        hqs_needed = math.ceil(((mqs + 1) / limit) - total - 1)
        return current_pct, f"Misfire Risk (Need {hqs_needed} HQ{'s' if hqs_needed > 1 else ''} first)", hqs_needed

# --- CACHE CLEARING PROTOCOL ---
if 'nr_periods' in st.session_state and list(st.session_state.nr_periods.columns) != ["Start (YYYYMMDD)", "End (YYYYMMDD)", "Code"]:
    del st.session_state['nr_periods']
if 'profile_ledger' in st.session_state and list(st.session_state.profile_ledger.columns) != ["Rank", "Rule Limit", "Total Evals", "Total MQs Given"]:
    del st.session_state['profile_ledger']

# --- MAIN APP ROUTING ---
def main():
    st.title("🦅 G-1 Executive Dashboard (v8.5)")
    
    with st.expander("📖 Quick Start Guide"):
        st.markdown("**For 90% of evaluations, you ONLY need Tab 1.** 1. Select type. 2. Select dates. 3. Scroll for IPPS-A text.")

    tabs = st.tabs(["📅 Eval Calculator", "📋 Profile Ledger [S1]", "📝 Text Scanner [Advanced]", "🧮 MQ Sequencer [Advanced]", "🔎 Crosswalk [Advanced]"])

    with tabs[0]:
        st.header("1. Evaluation Parameters")
        with st.expander("📖 Evaluation Type Guide"):
            st.markdown("* **Annual:** Standard yearly report.\n* **Change of Rater:** Mandatory when rater changes.\n* **Change of Duty:** Duty position change.\n* **Extended Annual:** >12 months.\n* **Relief for Cause:** Performance/Conduct issue.\n* **Complete the Record:** For promotion board.\n* **Academic:** Full-time schooling.")
        
        col_comp, col_eval = st.columns(2)
        with col_comp: component = st.selectbox("Army Component", options=["Active Duty", "USAR / ARNG"])
        with col_eval: eval_type = st.selectbox("Type of Evaluation", options=EVAL_TYPES)

        min_days = 90 if component == "Active Duty" else 120
        if eval_type in ["Relief for Cause", "Academic"]: min_days = 0 
        
        st.divider()
        st.header("2. Base Rating & Guardrails")
        date_range = st.date_input("📅 Select Rating Period", value=(), format="YYYY/MM/DD")
        col3, col4 = st.columns(2)
        with col3: prev_thru_str = st.text_input("Prior Eval Thru (Optional YYYYMMDD)", max_chars=8)
        with col4: rater_sig_str = st.text_input("Rater Sig Date (Optional YYYYMMDD)", max_chars=8)

        if len(date_range) != 2: st.info("👆 Please select both dates on the calendar above."); st.stop()
        from_date, thru_date = date_range[0], date_range[1]

        total_calendar_days = (thru_date - from_date).days + 1
        st.divider()

        st.header("3. Non-Rated Time (Optional - Skip if none)")
        with st.expander("📚 Non-Rated Code Glossary"):
            st.markdown("* **A:** AWOL | **C:** Confinement | **E:** Leave (30+) | **I:** In Transit | **P:** Patient | **Q:** Rater Qual | **S:** Student | **T:** TDY")
            
        if 'nr_periods' not in st.session_state: st.session_state.nr_periods = pd.DataFrame(columns=["Start (YYYYMMDD)", "End (YYYYMMDD)", "Code"])
        
        nr_col1, nr_col2, nr_col3 = st.columns([2, 2, 1])
        with nr_col1: nr_dates = st.date_input("Select Non-Rated Range", value=(), format="YYYY/MM/DD")
        with nr_col2: nr_code = st.selectbox("Select Non-Rated Code", options=NON_RATED_CODES)
        with nr_col3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ Add Period"):
                if len(nr_dates) == 2:
                    new_row = pd.DataFrame([{"Start (YYYYMMDD)": nr_dates[0].strftime("%Y%m%d"), "End (YYYYMMDD)": nr_dates[1].strftime("%Y%m%d"), "Code": nr_code}])
                    st.session_state.nr_periods = pd.concat([st.session_state.nr_periods, new_row], ignore_index=True)
                    st.rerun()

        edited_df = st.data_editor(st.session_state.nr_periods, num_rows="dynamic", use_container_width=True, hide_index=True)
        st.session_state.nr_periods = edited_df

        total_nr_days, valid_periods, ipps_a_codes = 0, [], []
        for _, row in edited_df.iterrows():
            s, e = parse_date(row["Start (YYYYMMDD)"]), parse_date(row["End (YYYYMMDD)"])
            if s and e and s <= e and s >= from_date and e <= thru_date:
                valid_periods.append({'start': s, 'end': e, 'code': row["Code"]})
                total_nr_days += (e - s).days + 1
                ipps_a_codes.append(f"{s.strftime('%Y%m%d')} - {e.strftime('%Y%m%d')}: {row['Code'].split(' - ')[0]}")
        
        total_rated_days = total_calendar_days - total_nr_days
        st.header("4. Output & Visualizer")
        st.altair_chart(plot_timeline(from_date, thru_date, valid_periods), use_container_width=True)
        st.metric("Total Rated Days", total_rated_days)
        st.code(f"FROM: {from_date.strftime('%Y%m%d')}\nTHRU: {thru_date.strftime('%Y%m%d')}\n\nNON-RATED:\n{chr(10).join(ipps_a_codes) if ipps_a_codes else 'None'}")

    with tabs[1]:
        st.header("📋 Command Profile Ledger")
        if 'profile_ledger' not in st.session_state:
            st.session_state.profile_ledger = pd.DataFrame({"Rank": ["COL", "LTC", "MAJ", "CPT", "CW5", "CW4", "CW3", "CSM/SGM", "1SG/MSG", "SFC"], "Rule Limit": ["OER (< 50% Limit)"] * 7 + ["NCOER (< 24% Limit)"] * 3, "Total Evals": [0]*10, "Total MQs Given": [0]*10})
        st.session_state.profile_ledger = st.data_editor(st.session_state.profile_ledger, num_rows="dynamic", use_container_width=True)
        
    with tabs[2]:
        st.header("📝 Policy & Banned Word Scanner")
        text_input = st.text_area("Draft Narrative", height=200)
        if text_input:
            found = [t for t in FLAGGED_TERMS if t in text_input.lower()]
            if found: st.error(f"🚨 Prohibited terms found: {', '.join(found)}")
            else: st.success("✅ Clean Scan.")

    with tabs[3]:
        st.header("🧮 MQ Sequencer")
        # Sequencing logic from v8.0...
    with tabs[4]:
        st.header("🔎 Career Crosswalk")
        # Audit logic from v8.0...

if __name__ == "__main__":
    main()
