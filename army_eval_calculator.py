import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import altair as alt
import math

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Army Eval Planner v7.0", page_icon="🦅", layout="wide")

# --- DATA DICTIONARIES ---
NON_RATED_CODES = [
    "A - AWOL", "C - Confinement", "D - Dropped from rolls", 
    "E - Leave (30+ days)", "F - Under arrest", "I - In transit", 
    "M - Missing in Action", "P - Patient", "Q - Lack of rater qualification", 
    "R - Retirement/Resignation leave", "S - Student", "T - TDY", "W - Prisoner of War"
]

EVAL_TYPES = [
    "Annual", "Change of Rater", "Change of Duty", 
    "Extended Annual", "Relief for Cause", "Complete the Record", "Academic"
]

RANK_GROUPS = ["OER (< 50% Limit)", "NCOER (< 24% Limit)"]

# --- HELPER FUNCTIONS ---
def parse_date(date_str):
    if not date_str: return None
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
    limit = 0.499 if limit_type == "OER (< 50% Limit)" else 0.239
    if total == 0: return 0.0, "Clear for 1st MQ", 0
    current_pct = mqs / total
    projected_pct = (mqs + 1) / (total + 1)
    
    if projected_pct <= limit:
        available = 0
        while ((mqs + available + 1) / (total + available + 1)) <= limit:
            available += 1
        return current_pct, f"Clear (Can give {available} MQ{'s' if available > 1 else ''})", 0
    else:
        hqs_needed = math.ceil(((mqs + 1) / limit) - total - 1)
        return current_pct, f"Misfire Risk (Need {hqs_needed} HQ{'s' if hqs_needed > 1 else ''} first)", hqs_needed

# --- SELF-HEALING MEMORY PROTOCOL ---
# Ensures old cache data doesn't crash the app after updates
EXPECTED_NR_COLS = ["Start (YYYYMMDD)", "End (YYYYMMDD)", "Code"]
if 'nr_periods' in st.session_state:
    if list(st.session_state.nr_periods.columns) != EXPECTED_NR_COLS:
        del st.session_state['nr_periods']

EXPECTED_LEDGER_COLS = ["Rank", "Rule Limit", "Total Evals", "Total MQs Given"]
if 'profile_ledger' in st.session_state:
    if list(st.session_state.profile_ledger.columns) != EXPECTED_LEDGER_COLS:
        del st.session_state['profile_ledger']


# --- MAIN APP ---
def main():
    st.title("🦅 Army Evaluation Planner & Kiosk v7.0")
    st.markdown("Strictly automated IPPS-A date math, Suspense Tracking, and Command Profile Ledger.")

    tab1, tab2, tab3 = st.tabs(["📅 Dates & Output", "📋 Command Profile Ledger", "📝 IPPS-A Formatting"])

    # ==========================================
    # TAB 1: DATE CALCULATOR 
    # ==========================================
    with tab1:
        st.header("1. Evaluation Parameters")
        col_comp, col_eval = st.columns(2)
        with col_comp: component = st.selectbox("Army Component", options=["Active Duty", "USAR / ARNG"])
        with col_eval: eval_type = st.selectbox("Type of Evaluation", options=EVAL_TYPES)

        min_days = 90 if component == "Active Duty" else 120
        if eval_type in ["Relief for Cause", "Academic"]: min_days = 0 
        st.divider()

        st.header("2. Base Rating & Guardrails")
        st.caption("Type dates strictly as 8 numbers (YYYYMMDD).")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1: from_str = st.text_input("From Date", max_chars=8, placeholder="20250705")
        with col2: thru_str = st.text_input("Thru Date", max_chars=8, placeholder="20260705")
        with col3: prev_thru_str = st.text_input("Prior Eval Thru Date (Gap Check)", max_chars=8)
        with col4: rater_sig_str = st.text_input("Rater Sig Date", max_chars=8)

        if len(from_str) == 8 and len(thru_str) == 8:
            from_date, thru_date = parse_date(from_str), parse_date(thru_str)
            if not from_date or not thru_date:
                st.error("Invalid base date format. Use YYYYMMDD."); st.stop()
            if from_date > thru_date:
                st.error("Error: 'From Date' cannot be after 'Thru Date'."); st.stop()

            # Gap Checker
            if len(prev_thru_str) == 8:
                prev_date = parse_date(prev_thru_str)
                if prev_date:
                    expected_from = prev_date + timedelta(days=1)
                    if from_date != expected_from:
                        st.error(f"⚠️ **GAP/OVERLAP DETECTED:** The prior eval ended on {prev_date.strftime('%Y%m%d')}. This eval MUST start on {expected_from.strftime('%Y%m%d')} to prevent an unrated gap.")
                    else:
                        st.success("✅ Gap Check Passed: No unrated time between evaluations.")

            # Signature Date Guardrails
            if len(rater_sig_str) == 8:
                r_date = parse_date(rater_sig_str)
                if r_date and r_date < thru_date:
                    st.warning("⚠️ **SIGNATURE WARNING:** The Rater is signing before the Thru Date. Ensure this meets an authorized exception.")

            total_calendar_days = (thru_date - from_date).days + 1
            st.divider()

            st.header("3. Add Non-Rated Time")
            if 'nr_periods' not in st.session_state:
                st.session_state.nr_periods = pd.DataFrame(columns=EXPECTED_NR_COLS)

            edited_df = st.data_editor(
                st.session_state.nr_periods,
                column_config={
                    "Start (YYYYMMDD)": st.column_config.TextColumn("Start Date", max_chars=8, validate=r"^\d{8}$", required=True),
                    "End (YYYYMMDD)": st.column_config.TextColumn("End Date", max_chars=8, validate=r"^\d{8}$", required=True),
                    "Code": st.column_config.SelectboxColumn("Non-Rated Code", options=NON_RATED_CODES, required=True)
                },
                num_rows="dynamic", use_container_width=True, hide_index=True
            )
            st.divider()

            # Calculations
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
            
            # HRC Suspense Tracker
            suspense_date = thru_date + timedelta(days=90)
            today = datetime.today().date()
            
            colS1, colS2 = st.columns(2)
            with colS1:
                st.info(f"📅 **HRC Suspense Date:** {suspense_date.strftime('%Y-%m-%d')}")
            with colS2:
                if today > suspense_date:
                    days_late = (today - suspense_date).days
                    st.error(f"🚨 **DELINQUENT:** This evaluation is {days_late} days LATE to HRC.")
                else:
                    days_left = (suspense_date - today).days
                    st.success(f"✅ On Time: {days_left} days remaining until HRC suspense.")

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
        
        col_up, col_down = st.columns(2)
        with col_up:
            uploaded_file = st.file_uploader("📂 Load Saved Profile (CSV)", type="csv")
            if uploaded_file is not None:
                st.session_state.profile_ledger = pd.read_csv(uploaded_file)
                st.success("Profile loaded successfully!")
        
        if 'profile_ledger' not in st.session_state:
            default_ranks = ["COL", "LTC", "MAJ", "CPT", "CW5", "CW4", "CW3", "CSM/SGM", "1SG/MSG", "SFC"]
            default_rules = ["OER (< 50% Limit)"] * 7 + ["NCOER (< 24% Limit)"] * 3
            st.session_state.profile_ledger = pd.DataFrame({
                "Rank": default_ranks,
                "Rule Limit": default_rules,
                "Total Evals": [0] * 10,
                "Total MQs Given": [0] * 10
            })

        st.caption("Update your totals below. Add or remove rows if needed.")
        edited_ledger = st.data_editor(
            st.session_state.profile_ledger,
            column_config={
                "Rank": st.column_config.TextColumn("Rank", required=True),
                "Rule Limit": st.column_config.SelectboxColumn("Rule Limit", options=RANK_GROUPS, required=True),
                "Total Evals": st.column_config.NumberColumn("Total Evals", min_value=0, step=1, required=True),
                "Total MQs Given": st.column_config.NumberColumn("Total MQs Given", min_value=0, step=1, required=True)
            },
            num_rows="dynamic", use_container_width=True, hide_index=True
        )
        
        st.session_state.profile_ledger = edited_ledger
        
        with col_down:
            st.markdown("<br>", unsafe_allow_html=True)
            csv = edited_ledger.to_csv(index=False).encode('utf-8')
            st.download_button("💾 Save Profile Backup (CSV)", data=csv, file_name=f"Profile_Backup_{datetime.today().strftime('%Y%m%d')}.csv", mime="text/csv")

        st.subheader("📊 Real-Time Profile Health")
        dashboard_data = []
        for index, row in edited_ledger.iterrows():
            grade, rule = row["Rank"], row["Rule Limit"]
            total, mqs = row["Total Evals"], row["Total MQs Given"]
            
            if pd.isna(grade) or pd.isna(rule): continue
            total = 0 if pd.isna(total) else int(total)
            mqs = 0 if pd.isna(mqs) else int(mqs)

            pct, status, hqs_needed = calculate_profile_health(total, mqs, rule)
            dashboard_data.append({"Rank": grade, "Current %": f"{pct * 100:.1f}%", "Status & Action Required": status})

        if dashboard_data:
            df_dash = pd.DataFrame(dashboard_data)
            def highlight_status(val):
                if 'Clear' in str(val): return 'color: #2e7d32; font-weight: bold'
                if 'Misfire' in str(val): return 'color: #d32f2f; font-weight: bold'
                return ''
            try:
                styled_dash = df_dash.style.map(highlight_status, subset=['Status & Action Required'])
            except AttributeError:
                styled_dash = df_dash.style.applymap(highlight_status, subset=['Status & Action Required'])

            st.dataframe(styled_dash, use_container_width=True, hide_index=True)

    # ==========================================
    # TAB 3: IPPS-A TEXT FORMATTER & VALIDATOR
    # ==========================================
    with tab3:
        st.header("📝 IPPS-A Bullet & Text Validator")
        st.markdown("Actively monitors line breaks, formatting, and character limits to ensure a clean copy/paste into IPPS-A.")
        
        col_text1, col_text2 = st.columns(2)
        with col_text1:
            st.subheader("General Text / Narrative")
            text_input = st.text_area("Draft Evaluation Text", height=200, placeholder="Paste narrative here...")
            if text_input:
                char_count = len(text_input)
                line_count = text_input.count('\n') + 1
                st.metric("Character Count", char_count)
                st.metric("Line Count (Hard Returns)", line_count)

        with col_text2:
            st.subheader("NCOER Bullet Validator")
            bullet_input = st.text_area("Paste NCOER Bullets", height=200, placeholder="o Must start with 'o '\no Second line...")
            if bullet_input:
                bullets = bullet_input.split('\n')
                st.write("**Bullet Check Results:**")
                for i, bullet in enumerate(bullets):
                    if bullet.strip(): # Skip empty lines
                        if not bullet.startswith("o "):
                            st.error(f"Line {i+1}: Missing required 'o ' at start.")
                        elif len(bullet) > 120: # Rough approximation for a single line length
                            st.warning(f"Line {i+1}: Bullet is very long and may wrap into a 3rd line in IPPS-A.")
                        else:
                            st.success(f"Line {i+1}: Format looks good.")
                            
        st.info("💡 **IPPS-A Tip:** Extra spaces and hidden characters from Microsoft Word often inflate the character count. Ensure bullets use standard spacing.")

if __name__ == "__main__":
    main()
