import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import altair as alt
import math

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Army Eval Planner v5.1", page_icon="🦅", layout="wide")

# --- DATA DICTIONARIES ---
NON_RATED_CODES = [
    "A - AWOL", "C - Confinement", "D - Dropped from rolls", 
    "E - Leave (30+ days)", "F - Under arrest", "I - In transit", 
    "M - Missing in Action", "P - Patient", "Q - Lack of rater qualification", 
    "R - Retirement/Resignation leave", "S - Student", "T - TDY", "W - Prisoner of War"
]

EVAL_TYPES = [
    "Annual", "Change of Rater", "Change of Duty", 
    "Extended Annual", "Relief for Cause", "Complete the Record"
]

RANK_GROUPS = ["OER (< 50% Limit)", "NCOER (< 24% Limit)"]

# --- HELPER FUNCTIONS ---
def parse_date(date_str):
    try:
        return datetime.strptime(str(date_str).strip(), "%Y%m%d").date()
    except ValueError:
        return None

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
    df_chart = pd.DataFrame(chart_data)
    chart = alt.Chart(df_chart).mark_bar(size=30).encode(
        x=alt.X('Start', title='Date', axis=alt.Axis(format='%Y-%m-%d', labelAngle=-45)),
        x2='End',
        y=alt.Y('Task', sort=['Base Rating Period']),
        color=alt.Color('Type', scale=alt.Scale(domain=['Rated Time', 'Non-Rated Time'], range=['#2e7d32', '#d32f2f']), legend=None),
        tooltip=['Task', 'Start', 'End']
    ).properties(height=200).interactive()
    return chart

def calculate_profile_health(total, mqs, limit_type):
    """Calculates profile health and future requirements."""
    limit = 0.499 if limit_type == "OER (< 50% Limit)" else 0.239
    
    if total == 0:
        return 0.0, "Clear for 1st MQ", 0
        
    current_pct = mqs / total
    
    # Simulate giving an MQ right now
    projected_pct = (mqs + 1) / (total + 1)
    
    if projected_pct <= limit:
        # Calculate how many total MQs they could give right now
        available = 0
        while ((mqs + available + 1) / (total + available + 1)) <= limit:
            available += 1
        return current_pct, f"Clear (Can give {available} MQ{'s' if available > 1 else ''})", 0
    else:
        # Calculate how many HQs needed to unlock the next MQ
        hqs_needed = math.ceil(((mqs + 1) / limit) - total - 1)
        return current_pct, f"Misfire Risk (Need {hqs_needed} HQ{'s' if hqs_needed > 1 else ''} first)", hqs_needed

# --- MAIN APP ---
def main():
    st.title("🦅 Army Evaluation Planner & Kiosk v5.1")
    st.markdown("Strictly automated IPPS-A date math and Command Profile Ledger.")

    tab1, tab2 = st.tabs(["📅 Dates & IPPS-A Output", "📋 Command Profile Ledger"])

    # ==========================================
    # TAB 1: DATE CALCULATOR 
    # ==========================================
    with tab1:
        st.header("1. Evaluation Parameters")
        col_comp, col_eval = st.columns(2)
        with col_comp:
            component = st.selectbox("Army Component", options=["Active Duty", "USAR / ARNG"])
        with col_eval:
            eval_type = st.selectbox("Type of Evaluation", options=EVAL_TYPES)

        min_days = 90 if component == "Active Duty" else 120
        if eval_type == "Relief for Cause": min_days = 0 

        st.divider()

        st.header("2. Base Rating Period")
        st.caption("Type dates strictly as 8 numbers (YYYYMMDD).")
        
        col1, col2 = st.columns(2)
        with col1:
            from_str = st.text_input("From Date (YYYYMMDD)", max_chars=8, placeholder="20250705")
        with col2:
            thru_str = st.text_input("Thru Date (YYYYMMDD)", max_chars=8, placeholder="20260705")

        if len(from_str) == 8 and len(thru_str) == 8:
            from_date = parse_date(from_str)
            thru_date = parse_date(thru_str)

            if not from_date or not thru_date:
                st.error("Invalid date format. Use YYYYMMDD.")
                st.stop()
            if from_date > thru_date:
                st.error("Error: 'From Date' cannot be after 'Thru Date'.")
                st.stop()

            total_calendar_days = (thru_date - from_date).days + 1
            st.divider()

            st.header("3. Add Non-Rated Time")
            if 'nr_periods' not in st.session_state:
                st.session_state.nr_periods = pd.DataFrame(columns=["Start (YYYYMMDD)", "End (YYYYMMDD)", "Code"])

            edited_df = st.data_editor(
                st.session_state.nr_periods,
                column_config={
                    # Using raw strings (r"") for regex to prevent Python warnings
                    "Start (YYYYMMDD)": st.column_config.TextColumn("Start Date", max_chars=8, validate=r"^\d{8}$", required=True),
                    "End (YYYYMMDD)": st.column_config.TextColumn("End Date", max_chars=8, validate=r"^\d{8}$", required=True),
                    "Code": st.column_config.SelectboxColumn("Non-Rated Code", options=NON_RATED_CODES, required=True)
                },
                num_rows="dynamic", use_container_width=True, hide_index=True
            )
            st.divider()

            # --- CALCULATIONS ---
            total_nr_days, valid_periods, has_errors, ipps_a_codes = 0, [], False, []
            for index, row in edited_df.iterrows():
                raw_start, raw_end, code = row["Start (YYYYMMDD)"], row["End (YYYYMMDD)"], row["Code"]
                if pd.isna(raw_start) or pd.isna(raw_end) or pd.isna(code): continue 
                start, end = parse_date(raw_start), parse_date(raw_end)
                if not start or not end:
                    st.error(f"Row {index + 1}: Invalid date."); has_errors = True; continue
                if start > end:
                    st.error(f"Row {index + 1}: Start must be before End."); has_errors = True; continue
                if start < from_date or end > thru_date:
                    st.error(f"Row {index + 1}: Dates must be within Base Period."); has_errors = True; continue
                valid_periods.append({'start': start, 'end': end, 'code': code})
                total_nr_days += (end - start).days + 1
                ipps_a_codes.append(f"{start.strftime('%Y%m%d')} - {end.strftime('%Y%m%d')}: {code.split(' - ')[0]}")

            if check_overlaps(valid_periods):
                st.error("Error: Overlapping non-rated periods detected."); has_errors = True
            if has_errors: st.stop()

            total_rated_days = total_calendar_days - total_nr_days
            rated_months, leftover_days = total_rated_days // 30, total_rated_days % 30

            st.header("4. Final IPPS-A Output & Visualizer")
            st.altair_chart(plot_timeline(from_date, thru_date, valid_periods), use_container_width=True)

            colA, colB, colC = st.columns(3)
            colA.metric("Box 1i: Rated Months", rated_months)
            colB.metric("Box 1i: Rated Days", leftover_days)
            colC.metric("Total Rated Days", total_rated_days)

            if total_rated_days < min_days:
                shortfall = min_days - total_rated_days
                target_thru_date = thru_date + timedelta(days=shortfall)
                st.error(f"🛑 **INVALID EVALUATION:** You are short **{shortfall} days** (Minimum required is {min_days}).")
                st.info(f"💡 **FIX:** To meet the minimum, change the Thru Date to **{target_thru_date.strftime('%Y%m%d')}**.")
            else:
                st.success(f"✅ **VALID EVALUATION:** Minimum rating requirements met.")

            st.code(f"FROM: {from_date.strftime('%Y%m%d')}\nTHRU: {thru_date.strftime('%Y%m%d')}\n\nNON-RATED:\n{chr(10).join(ipps_a_codes) if ipps_a_codes else 'No Non-Rated Time'}", language="text")

    # ==========================================
    # TAB 2: COMMAND PROFILE LEDGER
    # ==========================================
    with tab2:
        st.header("📋 Command Profile Ledger")
        st.markdown("""
        Manage all rated grades simultaneously. Input your current profile numbers for each grade. 
        The system will calculate your exact limits and forecast how many 'HQs' are needed to unlock your next 'MQ'.
        """)
        
        # Initialize Ledger in session state
        if 'profile_ledger' not in st.session_state:
            st.session_state.profile_ledger = pd.DataFrame({
                "Grade (e.g. MAJ)": ["CPT", "MAJ", "SFC"],
                "Rule Limit": ["OER (< 50% Limit)", "OER (< 50% Limit)", "NCOER (< 24% Limit)"],
                "Total Evals": [5, 2, 8],
                "Total MQs Given": [2, 1, 1]
            })

        edited_ledger = st.data_editor(
            st.session_state.profile_ledger,
            column_config={
                "Grade (e.g. MAJ)": st.column_config.TextColumn("Grade", required=True),
                "Rule Limit": st.column_config.SelectboxColumn("Rule Limit", options=RANK_GROUPS, required=True),
                "Total Evals": st.column_config.NumberColumn("Total Evals", min_value=0, step=1, required=True),
                "Total MQs Given": st.column_config.NumberColumn("Total MQs Given", min_value=0, step=1, required=True)
            },
            num_rows="dynamic", use_container_width=True, hide_index=True
        )

        st.subheader("📊 Profile Health Dashboard")
        
        dashboard_data = []
        for index, row in edited_ledger.iterrows():
            grade = row["Grade (e.g. MAJ)"]
            rule = row["Rule Limit"]
            total = row["Total Evals"]
            mqs = row["Total MQs Given"]
            
            if pd.isna(grade) or pd.isna(rule): continue
            
            total = 0 if pd.isna(total) else int(total)
            mqs = 0 if pd.isna(mqs) else int(mqs)

            pct, status, hqs_needed = calculate_profile_health(total, mqs, rule)
            
            dashboard_data.append({
                "Grade": grade,
                "Current %": f"{pct * 100:.1f}%",
                "Status & Action Required": status
            })

        if dashboard_data:
            df_dash = pd.DataFrame(dashboard_data)
            
            # Apply dynamic color coding to the dashboard output
            def highlight_status(val):
                if 'Clear' in str(val): return 'color: #2e7d32; font-weight: bold'
                if 'Misfire' in str(val): return 'color: #d32f2f; font-weight: bold'
                return ''
                
            # FIX: Safely try the new Pandas map(), fallback to older applymap() if needed
            try:
                styled_dash = df_dash.style.map(highlight_status, subset=['Status & Action Required'])
            except AttributeError:
                styled_dash = df_dash.style.applymap(highlight_status, subset=['Status & Action Required'])

            st.dataframe(styled_dash, use_container_width=True, hide_index=True)
        else:
            st.info("Add grades to the ledger above to view health metrics.")

if __name__ == "__main__":
    main()
