import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import altair as alt
import math

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Army Evaluation Dashboard", page_icon="🦅", layout="wide")

# --- CONSTANTS & DICTIONARIES ---
NON_RATED_CODES = [
    "A - AWOL", "C - Confinement", "D - Dropped from rolls", 
    "E - Leave (30+ days)", "F - Under arrest", "I - In transit", 
    "M - Missing in Action", "P - Patient", "Q - Lack of rater qualification", 
    "R - Retirement/Resignation leave", "S - Student", "T - TDY", "W - Prisoner of War"
]

EVAL_TYPES = ["Annual", "Change of Rater", "Change of Duty", "Extended Annual", "Relief for Cause", "Complete the Record", "Academic"]
RANK_GROUPS = ["OER (< 50% Limit)", "NCOER (< 24% Limit)"]

# AR 623-3 Flagged Terms
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
EXPECTED_NR_COLS = ["Start (YYYYMMDD)", "End (YYYYMMDD)", "Code"]
if 'nr_periods' in st.session_state and list(st.session_state.nr_periods.columns) != EXPECTED_NR_COLS:
    del st.session_state['nr_periods']

EXPECTED_LEDGER_COLS = ["Rank", "Rule Limit", "Total Evals", "Total MQs Given"]
if 'profile_ledger' in st.session_state and list(st.session_state.profile_ledger.columns) != EXPECTED_LEDGER_COLS:
    del st.session_state['profile_ledger']


# --- MAIN APP ROUTING ---
def main():
    st.title("🦅 G-1 Executive Dashboard (v8.4)")
    
    with st.expander("📖 Quick Start Guide (Read Me First)"):
        st.markdown("""
        **For 95% of evaluations, you ONLY need Tab 1.**
        1. Select your Component and Eval Type.
        2. Click the Date Box and select your **From** and **Thru** dates on the calendar.
        3. *Done.* Scroll down for your exact IPPS-A output.
        
        *Everything labeled "(Optional)" and all other tabs are advanced power-tools for the S1/G1 staff. Skip them if you don't need them.*
        """)

    tabs = st.tabs([
        "📅 Eval Calculator", 
        "📋 Profile Ledger [S1]", 
        "📝 Text Scanner [Advanced]", 
        "🧮 MQ Sequencer [Advanced]", 
        "🔎 Crosswalk [Advanced]"
    ])

    # ==========================================
    # TAB 1: DATE CALCULATOR 
    # ==========================================
    with tabs[0]:
        st.header("1. Evaluation Parameters")
        col_comp, col_eval = st.columns(2)
        with col_comp: component = st.selectbox("Army Component", options=["Active Duty", "USAR / ARNG"])
        with col_eval: eval_type = st.selectbox("Type of Evaluation", options=EVAL_TYPES)

        min_days = 90 if component == "Active Duty" else 120
        if eval_type in ["Relief for Cause", "Academic"]: min_days = 0 
        
        st.divider()
        st.header("2. Base Rating & Guardrails")
        
        date_range = st.date_input("📅 Select Rating Period (Click Start Date, then click End Date)", value=(), format="YYYY/MM/DD")
        
        st.caption("Advanced Guardrails (Optional - Leave blank if unsure)")
        col3, col4 = st.columns(2)
        with col3: prev_thru_str = st.text_input("Prior Eval Thru (Optional YYYYMMDD)", max_chars=8)
        with col4: rater_sig_str = st.text_input("Rater Sig Date (Optional YYYYMMDD)", max_chars=8)

        if len(date_range) != 2:
            st.info("👆 Please select both a **From Date** and a **Thru Date** on the calendar above to continue.")
            st.stop()
            
        from_date, thru_date = date_range[0], date_range[1]

        if from_date > thru_date:
            st.error("Error: 'From Date' cannot be after 'Thru Date'."); st.stop()

        if len(prev_thru_str) == 8:
            prev_date = parse_date(prev_thru_str)
            if prev_date:
                expected_from = prev_date + timedelta(days=1)
                if from_date != expected_from:
                    st.error(f"⚠️ **GAP/OVERLAP:** Prior eval ended {prev_date.strftime('%Y%m%d')}. This MUST start {expected_from.strftime('%Y%m%d')}.")
                else:
                    st.success("✅ Gap Check Passed.")

        if len(rater_sig_str) == 8:
            r_date = parse_date(rater_sig_str)
            if r_date and r_date < thru_date: st.warning("⚠️ **WARNING:** Rater signing before Thru Date.")

        total_calendar_days = (thru_date - from_date).days + 1
        st.divider()

        # --- THE NEW INTAKE FORM FOR NON-RATED TIME ---
        st.header("3. Non-Rated Time (Optional - Skip if none)")
        
        # Injecting the Point-of-Need Glossary
        with st.expander("📚 Non-Rated Code Glossary (Click to view definitions)"):
            st.markdown("""
            * **A (AWOL):** Absent without leave.
            * **C (Confinement):** Military or civilian confinement.
            * **E (Leave):** Authorized leave of 30 or more consecutive days.
            * **I (In Transit):** Travel time between duty stations (PCS).
            * **P (Patient):** Hospitalization (including convalescent leave).
            * **Q (Rater Qual):** Rater lacks minimum time (e.g., rater leaves before 90/120 days).
            * **S (Student):** Attending military/civilian school full-time.
            * **T (TDY):** Temporary duty away from the rated position.
            """)
            
        if 'nr_periods' not in st.session_state: st.session_state.nr_periods = pd.DataFrame(columns=EXPECTED_NR_COLS)
        
        st.subheader("Add a Non-Rated Period")
        nr_col1, nr_col2, nr_col3 = st.columns([2, 2, 1])
        with nr_col1:
            nr_dates = st.date_input("Select Non-Rated Range", value=(), format="YYYY/MM/DD", key="nr_date_picker")
        with nr_col2:
            nr_code = st.selectbox("Select Non-Rated Code", options=NON_RATED_CODES, key="nr_code_picker")
        with nr_col3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ Add Period", use_container_width=True):
                if len(nr_dates) == 2:
                    new_row = pd.DataFrame([{
                        "Start (YYYYMMDD)": nr_dates[0].strftime("%Y%m%d"),
                        "End (YYYYMMDD)": nr_dates[1].strftime("%Y%m%d"),
                        "Code": nr_code
                    }])
                    st.session_state.nr_periods = pd.concat([st.session_state.nr_periods, new_row], ignore_index=True)
                    st.rerun()
                else:
                    st.warning("Select Start AND End dates.")

        st.caption("Active Non-Rated Periods (You can delete rows or type to edit below)")
        edited_df = st.data_editor(
            st.session_state.nr_periods,
            column_config={
                "Start (YYYYMMDD)": st.column_config.TextColumn("Start", max_chars=8, validate=r"^\d{8}$"),
                "End (YYYYMMDD)": st.column_config.TextColumn("End", max_chars=8, validate=r"^\d{8}$"),
                "Code": st.column_config.SelectboxColumn("Code", options=NON_RATED_CODES)
            }, num_rows="dynamic", use_container_width=True, hide_index=True
        )
        
        st.session_state.nr_periods = edited_df

        total_nr_days, valid_periods, ipps_a_codes = 0, [], []
        for _, row in edited_df.iterrows():
            raw_start, raw_end, code = row["Start (YYYYMMDD)"], row["End (YYYYMMDD)"], row["Code"]
            if pd.isna(raw_start) or pd.isna(raw_end) or pd.isna(code): continue 
            start, end = parse_date(raw_start), parse_date(raw_end)
            if start and end and start <= end and start >= from_date and end <= thru_date:
                valid_periods.append({'start': start, 'end': end, 'code': code})
                total_nr_days += (end - start).days + 1
                ipps_a_codes.append(f"{start.strftime('%Y%m%d')} - {end.strftime('%Y%m%d')}: {code.split(' - ')[0]}")
        
        total_rated_days = total_calendar_days - total_nr_days
        rated_months, leftover_days = total_rated_days // 30, total_rated_days % 30

        st.header("4. Output & Visualizer")
        suspense_date = thru_date + timedelta(days=90)
        today = datetime.today().date()
        if today > suspense_date: st.error(f"🚨 **DELINQUENT:** {(today - suspense_date).days} days LATE to HRC.")
        else: st.success(f"📅 **HRC Suspense Date:** {suspense_date.strftime('%Y-%m-%d')}")

        st.altair_chart(plot_timeline(from_date, thru_date, valid_periods), use_container_width=True)

        colA, colB, colC = st.columns(3)
        colA.metric("Box 1i: Rated Months", rated_months)
        colB.metric("Box 1i: Rated Days", leftover_days)
        colC.metric("Total Rated Days", total_rated_days)

        if total_rated_days < min_days:
            st.error(f"🛑 **INVALID:** Short {min_days - total_rated_days} days (Min is {min_days}).")
        
        st.code(f"FROM: {from_date.strftime('%Y%m%d')}\nTHRU: {thru_date.strftime('%Y%m%d')}\n\nNON-RATED:\n{chr(10).join(ipps_a_codes) if ipps_a_codes else 'No Non-Rated Time'}")

    # ==========================================
    # TAB 2: COMMAND PROFILE LEDGER
    # ==========================================
    with tabs[1]:
        st.header("📋 Command Profile Ledger")
        
        col_up, col_down = st.columns(2)
        with col_up:
            uploaded_file = st.file_uploader("📂 Load Saved Profile (CSV)", type="csv")
            if uploaded_file: st.session_state.profile_ledger = pd.read_csv(uploaded_file)
        
        if 'profile_ledger' not in st.session_state:
            default_ranks = ["COL", "LTC", "MAJ", "CPT", "CW5", "CW4", "CW3", "CSM/SGM", "1SG/MSG", "SFC"]
            default_rules = ["OER (< 50% Limit)"] * 7 + ["NCOER (< 24% Limit)"] * 3
            st.session_state.profile_ledger = pd.DataFrame({"Rank": default_ranks, "Rule Limit": default_rules, "Total Evals": [0]*10, "Total MQs Given": [0]*10})

        edited_ledger = st.data_editor(st.session_state.profile_ledger, num_rows="dynamic", use_container_width=True, hide_index=True)
        st.session_state.profile_ledger = edited_ledger
        
        with col_down:
            st.markdown("<br>", unsafe_allow_html=True)
            st.download_button("💾 Save Profile Backup", data=edited_ledger.to_csv(index=False).encode('utf-8'), file_name=f"Profile_{datetime.today().strftime('%Y%m%d')}.csv")

        st.subheader("📊 Real-Time Health Dashboard")
        dash_data = []
        for _, row in edited_ledger.iterrows():
            total, mqs = int(row["Total Evals"]) if not pd.isna(row["Total Evals"]) else 0, int(row["Total MQs Given"]) if not pd.isna(row["Total MQs Given"]) else 0
            pct, status, _ = calculate_profile_health(total, mqs, row["Rule Limit"])
            dash_data.append({"Rank": row["Rank"], "Current %": f"{pct * 100:.1f}%", "Action Required": status})
        
        if dash_data:
            df_dash = pd.DataFrame(dash_data)
            def hl(v): return 'color: #2e7d32; font-weight: bold' if 'Clear' in str(v) else ('color: #d32f2f; font-weight: bold' if 'Misfire' in str(v) else '')
            try: st.dataframe(df_dash.style.map(hl, subset=['Action Required']), use_container_width=True, hide_index=True)
            except: st.dataframe(df_dash.style.applymap(hl, subset=['Action Required']), use_container_width=True, hide_index=True)

    # ==========================================
    # TAB 3: POLICY & TEXT SCANNER
    # ==========================================
    with tabs[2]:
        st.header("📝 Policy & Banned Word Scanner")
        st.markdown("Scans narratives against AR 623-3 flagged terms (medical, EO/SHARP, religion, etc.) to prevent HRC kickbacks.")
        text_input = st.text_area("Draft Narrative/Bullets", height=200)
        
        if text_input:
            st.metric("Character Count", len(text_input))
            st.metric("Line Count", text_input.count('\n') + 1)
            
            st.subheader("🛡️ Policy Scan Results")
            found_flags = []
            lower_text = text_input.lower()
            for term in FLAGGED_TERMS:
                if term in lower_text: found_flags.append(term)
            
            if found_flags:
                st.error(f"🚨 **POLICY WARNING:** Found potentially prohibited terms: **{', '.join(found_flags).upper()}**")
                st.info("Check AR 623-3. Medical profiles, pregnancy, or unverified investigations cannot be mentioned.")
            else:
                st.success("✅ Clean Scan. No commonly banned terms detected.")

    # ==========================================
    # TAB 4: PROFILE SEQUENCER (MATH ENGINE)
    # ==========================================
    with tabs[3]:
        st.header("🧮 Senior Rater Sequencing Engine")
        st.markdown("Processing multiple evals today? Mathematically calculate the optimal chronological signing order to maximize MQs without misfiring.")
        
        col_seq1, col_seq2 = st.columns(2)
        with col_seq1: seq_rule = st.radio("Rule Set", ["OER (< 50% Limit)", "NCOER (< 24% Limit)"])
        with col_seq2:
            s_total = st.number_input("Current Profile: Total Evals", min_value=0, value=0)
            s_mqs = st.number_input("Current Profile: MQs Given", min_value=0, value=0)
            
        st.divider()
        st.subheader("Evaluations to Process Today")
        planned_mqs = st.number_input("How many MQs do you WANT to give?", min_value=0, value=1)
        planned_hqs = st.number_input("How many HQs/Others are you giving?", min_value=0, value=2)
        
        if st.button("Generate Optimal Signing Sequence"):
            sim_total, sim_mqs = s_total, s_mqs
            limit = 0.499 if "OER" in seq_rule else 0.239
            
            sequence_log = []
            misfire = False
            
            for i in range(planned_hqs):
                sim_total += 1
                sequence_log.append(f"**Step {len(sequence_log)+1}:** Sign an HQ (Profile: {(sim_mqs/sim_total)*100:.1f}%)")
                
            for i in range(planned_mqs):
                if ((sim_mqs + 1) / (sim_total + 1)) <= limit:
                    sim_total += 1
                    sim_mqs += 1
                    sequence_log.append(f"**Step {len(sequence_log)+1}:** Sign an MQ ✅ (Profile: {(sim_mqs/sim_total)*100:.1f}%)")
                else:
                    sequence_log.append(f"**Step {len(sequence_log)+1}:** 🛑 FAILED. Cannot sign MQ without misfiring. (Profile would hit {((sim_mqs+1)/(sim_total+1))*100:.1f}%)")
                    misfire = True
                    break
            
            st.write("### Recommended Chronological Signing Order:")
            for log in sequence_log: st.markdown(log)
            
            if misfire: st.error("❌ It is mathematically impossible to give that many MQs today, even if you sign the HQs first.")
            else: st.success("✅ Sequence is clear! Sign them exactly in this order to preserve the profile.")

    # ==========================================
    # TAB 5: CAREER CROSSWALK (AUDIT TOOL)
    # ==========================================
    with tabs[4]:
        st.header("🔎 5-Year Career Crosswalk (Board Prep)")
        st.markdown("Audit a Soldier's last several evaluations to spot unrated gaps or overlapping dates.")
        
        if 'audit_df' not in st.session_state:
            st.session_state.audit_df = pd.DataFrame({"From (YYYYMMDD)": ["20230101", "20240101"], "Thru (YYYYMMDD)": ["20231231", "20241231"], "Type": ["Annual", "Annual"]})
            
        edited_audit = st.data_editor(st.session_state.audit_df, num_rows="dynamic", use_container_width=True)
        
        if st.button("Run Audit"):
            audit_records = []
            for _, row in edited_audit.iterrows():
                f_date, t_date = parse_date(row["From (YYYYMMDD)"]), parse_date(row["Thru (YYYYMMDD)"])
                if f_date and t_date: audit_records.append({"From": f_date, "Thru": t_date, "Type": row["Type"]})
            
            if len(audit_records) > 1:
                audit_records = sorted(audit_records, key=lambda x: x["From"])
                chart_data = []
                st.subheader("Audit Results:")
                for i in range(len(audit_records)-1):
                    current_thru = audit_records[i]["Thru"]
                    next_from = audit_records[i+1]["From"]
                    gap_days = (next_from - current_thru).days
                    
                    if gap_days == 1:
                        st.success(f"✅ Clean transition: {current_thru.strftime('%Y%m%d')} -> {next_from.strftime('%Y%m%d')}")
                    elif gap_days < 1:
                        st.error(f"🛑 **OVERLAP DETECTED:** {current_thru.strftime('%Y%m%d')} overlaps with {next_from.strftime('%Y%m%d')}")
                    elif gap_days > 1:
                        st.warning(f"⚠️ **UNRATED GAP DETECTED:** {gap_days - 1} days missing between {current_thru.strftime('%Y%m%d')} and {next_from.strftime('%Y%m%d')}")
                    
                    chart_data.append({"Eval": f"Eval {i+1} ({audit_records[i]['Type']})", "Start": pd.to_datetime(audit_records[i]["From"]), "End": pd.to_datetime(audit_records[i]["Thru"])})
                
                chart_data.append({"Eval": f"Eval {len(audit_records)} ({audit_records[-1]['Type']})", "Start": pd.to_datetime(audit_records[-1]["From"]), "End": pd.to_datetime(audit_records[-1]["Thru"])})
                
                st.altair_chart(alt.Chart(pd.DataFrame(chart_data)).mark_bar().encode(
                    x=alt.X('Start', title='Date'), x2='End', y='Eval', color=alt.value('#1976D2'), tooltip=['Eval', 'Start', 'End']
                ).properties(height=250).interactive(), use_container_width=True)

if __name__ == "__main__":
    main()
