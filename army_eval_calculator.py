import streamlit as st
import pandas as pd
from datetime import date, timedelta
import io

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Army Eval Date Calculator v2.0", page_icon="🎖️", layout="wide")

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

def check_overlaps(periods):
    """Checks a list of date periods for any overlapping days."""
    if not periods:
        return False
    sorted_periods = sorted(periods, key=lambda x: x['start'])
    for i in range(1, len(sorted_periods)):
        if sorted_periods[i]['start'] <= sorted_periods[i-1]['end']:
            return True
    return False

def generate_export_text(from_d, thru_d, comp, eval_t, cal_days, nr_days, r_days, r_months, leftover, codes):
    """Generates a clean text summary for export."""
    lines = [
        "ARMY EVALUATION REPORT - DATE CALCULATION SUMMARY",
        "="*50,
        f"Component: {comp}",
        f"Evaluation Type: {eval_t}",
        f"Period: {from_d.strftime('%Y%m%d')} thru {thru_d.strftime('%Y%m%d')}",
        "-"*50,
        f"Total Calendar Days: {cal_days}",
        f"Total Non-Rated Days: {nr_days}",
        f"Total Rated Days: {r_days}",
        "-"*50,
        "DA FORM OUTPUT (Box 1i):",
        f"Rated Months: {r_months}",
        f"Rated Days: {leftover}",
        f"Non-Rated Codes Used: {codes}",
        "="*50,
        "Calculated in accordance with AR/DA PAM 623-3."
    ]
    return "\n".join(lines)

def main():
    st.title("🎖️ Army Evaluation Date Calculator v2.0")
    st.markdown("Automates date math and enforces rating minimums IAW AR/DA PAM 623-3.")

    # --- SIDEBAR: CODE GLOSSARY ---
    with st.sidebar:
        st.header("📚 Non-Rated Code Glossary")
        st.markdown("""
        * **A (AWOL):** Absent without leave.
        * **C (Confinement):** Military or civilian confinement.
        * **E (Leave):** Authorized leave of 30 or more consecutive days.
        * **I (In Transit):** Travel time between duty stations (PCS).
        * **P (Patient):** Hospitalization (including convalescent leave).
        * **Q (Rater Qual):** Rater lacks minimum time (e.g., rater leaves before 90/120 days).
        * **S (Student):** Attending military/civilian school full-time.
        * **T (TDY):** Temporary duty away from the rated position (less than 90 days usually requires rater to keep rating, but over 90 days or specific TDY uses this code).
        """)
        st.divider()
        st.info("Tip: Always verify specific code application in DA PAM 623-3, Table 3-1.")

    # --- 1. EVALUATION PARAMETERS ---
    st.header("1. Evaluation Parameters")
    col_comp, col_eval = st.columns(2)
    with col_comp:
        component = st.selectbox("Army Component", options=["Active Duty", "USAR / ARNG"])
    with col_eval:
        eval_type = st.selectbox("Type of Evaluation", options=EVAL_TYPES)

    # Determine Minimum Rated Days Based on Component and Eval Type
    min_days = 90 if component == "Active Duty" else 120
    
    # Exceptions to the rule
    if eval_type == "Relief for Cause":
        min_days = 0 # No minimum
    elif eval_type == "Extended Annual":
        pass # Still requires the base minimums to be met, but period is > 365 calendar days

    st.caption(f"**Required Minimum Rated Time:** {min_days} days (Based on {component} - {eval_type})")
    st.divider()

    # --- 2. BASE RATING PERIOD ---
    st.header("2. Base Rating Period")
    col1, col2 = st.columns(2)
    with col1:
        from_date = st.date_input("From Date (YYYYMMDD)", format="YYYY/MM/DD")
    with col2:
        thru_date = st.date_input("Thru Date (YYYYMMDD)", format="YYYY/MM/DD", value=date.today())

    if from_date > thru_date:
        st.error("Error: 'From Date' cannot be after 'Thru Date'.")
        st.stop()

    total_calendar_days = (thru_date - from_date).days + 1
    st.info(f"**Total Calendar Days in Period:** {total_calendar_days}")
    
    if eval_type == "Extended Annual" and total_calendar_days <= 365:
         st.warning("⚠️ Extended Annual reports typically cover a calendar period greater than 365 days.")

    st.divider()

    # --- 3. NON-RATED TIME MODULE ---
    st.header("3. Non-Rated Periods")
    
    if 'nr_periods' not in st.session_state:
        st.session_state.nr_periods = pd.DataFrame(columns=["Start Date", "End Date", "Code"])

    edited_df = st.data_editor(
        st.session_state.nr_periods,
        column_config={
            "Start Date": st.column_config.DateColumn("Start Date", format="YYYY/MM/DD", required=True),
            "End Date": st.column_config.DateColumn("End Date", format="YYYY/MM/DD", required=True),
            "Code": st.column_config.SelectboxColumn("Non-Rated Code", options=NON_RATED_CODES, required=True)
        },
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    # --- 4. CALCULATION & GUARDRAILS ---
    st.header("4. Evaluation Calculations")

    total_nr_days = 0
    valid_periods = []
    has_errors = False

    for index, row in edited_df.iterrows():
        raw_start = row["Start Date"]
        raw_end = row["End Date"]
        code = row["Code"]

        if pd.isna(raw_start) or pd.isna(raw_end) or pd.isna(code):
            continue 

        start = pd.to_datetime(raw_start).date()
        end = pd.to_datetime(raw_end).date()

        if start > end:
            st.error(f"Error in Period {index + 1}: Start Date must be before End Date.")
            has_errors = True
            continue

        if start < from_date or end > thru_date:
            st.error(f"Error in Period {index + 1}: Non-Rated dates must fall within the Base Rating Period.")
            has_errors = True
            continue

        valid_periods.append({'start': start, 'end': end, 'code': code})
        total_nr_days += (end - start).days + 1

    if check_overlaps(valid_periods):
        st.error("Error: Two or more Non-Rated periods overlap. Please correct the dates.")
        has_errors = True

    if has_errors:
        st.stop()

    total_rated_days = total_calendar_days - total_nr_days
    rated_months = total_rated_days // 30
    leftover_days = total_rated_days % 30

    # --- OUTPUT GENERATION ---
    col3, col4, col5 = st.columns(3)
    col3.metric("Total Rated Days", total_rated_days)
    col4.metric("Rated Months", rated_months)
    col5.metric("Leftover Days", leftover_days)

    st.success(f"**DA Form Output (Box 1i):** {rated_months} Months, {leftover_days} Days")

    # Chronological Code String
    code_string = "None"
    if valid_periods:
        sorted_periods = sorted(valid_periods, key=lambda x: x['start'])
        codes_used = [p['code'].split(" - ")[0] for p in sorted_periods]
        code_string = ", ".join(codes_used)
        st.info(f"**Non-Rated Codes used (Chronological):** {code_string}")
    else:
        st.info("**Non-Rated Codes used:** None")

    # --- STRATEGY ENGINE & GUARDRAILS ---
    if total_rated_days < min_days:
        shortfall = min_days - total_rated_days
        target_thru_date = thru_date + timedelta(days=shortfall)
        
        st.error(f"🚨 **RATING REQUIREMENT NOT MET**")
        st.markdown(f"""
        This {component} {eval_type} evaluation requires **{min_days} rated days**, but currently only has **{total_rated_days}**. 
        
        **Strategy to fix:**
        1. **Extend the Period:** If possible, extend the 'Thru Date' by {shortfall} days to **{target_thru_date.strftime('%Y/%m/%d')}**.
        2. **Check Non-Rated Time:** Verify if any non-rated time (like a school or TDY) was actually performed in the rated duty position and shouldn't be deducted.
        3. **Change Eval Type:** If the rater is leaving, this cannot be a Change of Rater. It will likely require an Extended Annual at a later date, or a 'Q - Lack of rater qualification' non-rated period for the next evaluator.
        """)
    elif total_rated_days >= min_days and min_days > 0:
        st.success(f"✅ Minimum rating requirements met for {component} {eval_type}.")

    # --- EXPORT FEATURE ---
    st.divider()
    export_str = generate_export_text(from_date, thru_date, component, eval_type, total_calendar_days, total_nr_days, total_rated_days, rated_months, leftover_days, code_string)
    
    st.download_button(
        label="📄 Download Calculation Summary (TXT)",
        data=export_str,
        file_name=f"Eval_Calc_{thru_date.strftime('%Y%m%d')}.txt",
        mime="text/plain"
    )

if __name__ == "__main__":
    main()
