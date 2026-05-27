import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Army Eval Date Calculator", page_icon="🦅", layout="wide")

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

# --- HELPER FUNCTIONS ---
def parse_date(date_str):
    """Converts an 8-digit string into a Python date object."""
    try:
        return datetime.strptime(str(date_str).strip(), "%Y%m%d").date()
    except ValueError:
        return None

def check_overlaps(periods):
    """Checks a list of date periods for any overlapping days."""
    if not periods:
        return False
    sorted_periods = sorted(periods, key=lambda x: x['start'])
    for i in range(1, len(sorted_periods)):
        if sorted_periods[i]['start'] <= sorted_periods[i-1]['end']:
            return True
    return False

# --- MAIN APP ---
def main():
    st.title("🦅 Army Evaluation Date Calculator v3.0")
    st.markdown("Automates IPPS-A date math and enforces rating minimums IAW AR/DA PAM 623-3.")

    # UI Polish: Hide the glossary in an expander to save space
    with st.expander("📚 View Non-Rated Code Glossary & Rules"):
        st.markdown("""
        * **A (AWOL):** Absent without leave.
        * **E (Leave):** Authorized leave of 30 or more consecutive days.
        * **I (In Transit):** Travel time between duty stations (PCS).
        * **Q (Rater Qual):** Rater lacks minimum time (e.g., rater leaves before 90/120 days).
        * **S (Student):** Attending military/civilian school full-time.
        * **T (TDY):** Temporary duty away from the rated position.
        """)

    # --- TAB SETUP ---
    tab1, tab2 = st.tabs(["👤 Single Evaluation Planner", "📑 Bulk IPPS-A Processing (PERSTAT)"])

    with tab1:
        # --- 1. EVALUATION PARAMETERS ---
        st.header("1. Evaluation Parameters")
        col_comp, col_eval, col_target = st.columns(3)
        with col_comp:
            component = st.selectbox("Army Component", options=["Active Duty", "USAR / ARNG"])
        with col_eval:
            eval_type = st.selectbox("Type of Evaluation", options=EVAL_TYPES)
        with col_target:
            # The Board Forecaster input
            board_date_str = st.text_input("Target Board/Close Date (Optional YYYYMMDD)", max_chars=8, placeholder="e.g. 20260701")

        min_days = 90 if component == "Active Duty" else 120
        if eval_type == "Relief for Cause":
            min_days = 0 

        st.divider()

        # --- 2. BASE RATING PERIOD (STRICT 8-DIGIT TEXT INPUT) ---
        st.header("2. Base Rating Period")
        st.caption("Enter dates strictly as 8 numbers (YYYYMMDD). No slashes required.")
        
        col1, col2 = st.columns(2)
        with col1:
            from_str = st.text_input("From Date (YYYYMMDD)", max_chars=8, placeholder="20250705")
        with col2:
            thru_str = st.text_input("Thru Date (YYYYMMDD)", max_chars=8, placeholder="20260705")

        # Wait until user types exactly 8 characters before processing
        if len(from_str) == 8 and len(thru_str) == 8:
            from_date = parse_date(from_str)
            thru_date = parse_date(thru_str)

            if not from_date or not thru_date:
                st.error("Invalid date format. Please ensure dates are real days formatted as YYYYMMDD.")
                st.stop()

            if from_date > thru_date:
                st.error("Error: 'From Date' cannot be after 'Thru Date'.")
                st.stop()

            total_calendar_days = (thru_date - from_date).days + 1
            st.info(f"**Total Calendar Days in Period:** {total_calendar_days}")

            st.divider()

            # --- 3. NON-RATED TIME MODULE (TEXT COLUMN ENFORCED) ---
            st.header("3. Non-Rated Periods")
            
            if 'nr_periods' not in st.session_state:
                st.session_state.nr_periods = pd.DataFrame(columns=["Start (YYYYMMDD)", "End (YYYYMMDD)", "Code"])

            # Use TextColumn with regex to force exactly 8 numbers
            edited_df = st.data_editor(
                st.session_state.nr_periods,
                column_config={
                    "Start (YYYYMMDD)": st.column_config.TextColumn(
                        "Start Date", max_chars=8, validate="^\d{8}$", required=True
                    ),
                    "End (YYYYMMDD)": st.column_config.TextColumn(
                        "End Date", max_chars=8, validate="^\d{8}$", required=True
                    ),
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
            ipps_a_codes = []

            for index, row in edited_df.iterrows():
                raw_start = row["Start (YYYYMMDD)"]
                raw_end = row["End (YYYYMMDD)"]
                code = row["Code"]

                if pd.isna(raw_start) or pd.isna(raw_end) or pd.isna(code):
                    continue 

                start = parse_date(raw_start)
                end = parse_date(raw_end)

                if not start or not end:
                    st.error(f"Row {index + 1}: Invalid date format. Use YYYYMMDD.")
                    has_errors = True
                    continue

                if start > end:
                    st.error(f"Row {index + 1}: Start Date must be before End Date.")
                    has_errors = True
                    continue

                if start < from_date or end > thru_date:
                    st.error(f"Row {index + 1}: Non-Rated dates must fall within the Base Rating Period.")
                    has_errors = True
                    continue

                valid_periods.append({'start': start, 'end': end, 'code': code})
                total_nr_days += (end - start).days + 1
                
                # Format for IPPS-A output block
                letter_code = code.split(" - ")[0]
                ipps_a_codes.append(f"{start.strftime('%Y%m%d')} - {end.strftime('%Y%m%d')}: {letter_code}")

            if check_overlaps(valid_periods):
                st.error("Error: Two or more Non-Rated periods overlap. Please correct the dates.")
                has_errors = True

            if has_errors:
                st.stop()

            total_rated_days = total_calendar_days - total_nr_days
            rated_months = total_rated_days // 30
            leftover_days = total_rated_days % 30

            # --- DA FORM OUTPUT ---
            col3, col4, col5 = st.columns(3)
            col3.metric("Total Rated Days", total_rated_days)
            col4.metric("Rated Months", rated_months)
            col5.metric("Leftover Days", leftover_days)

            st.success(f"**DA Form Output (Box 1i):** {rated_months} Months, {leftover_days} Days")

            # --- IPPS
