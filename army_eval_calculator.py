import streamlit as st
import pandas as pd
from datetime import date

# Set page configuration for the Streamlit app
st.set_page_config(page_title="Army Eval Date Calculator", page_icon="🇺🇸", layout="centered")

# DA PAM 623-3 Standard Non-Rated Codes
NON_RATED_CODES = [
    "A - AWOL", 
    "C - Confinement", 
    "D - Dropped from rolls", 
    "E - Leave (30+ days)", 
    "F - Under arrest", 
    "I - In transit", 
    "M - Missing in Action", 
    "P - Patient", 
    "Q - Lack of rater qualification", 
    "R - Retirement/Resignation leave", 
    "S - Student", 
    "T - TDY", 
    "W - Prisoner of War"
]

def check_overlaps(periods):
    """
    Checks a list of date periods for any overlapping days.
    periods: list of dicts with 'start' and 'end' dates.
    """
    if not periods:
        return False
    # Sort periods by start date
    sorted_periods = sorted(periods, key=lambda x: x['start'])
    for i in range(1, len(sorted_periods)):
        # If the current period's start date is on or before the previous period's end date, it's an overlap.
        if sorted_periods[i]['start'] <= sorted_periods[i-1]['end']:
            return True
    return False

def main():
    st.title("🎖️ Army Evaluation Date Calculator")
    st.markdown("Automates date math for OERs (DA Form 67-11) and NCOERs (DA Form 2166-9) IAW AR/DA PAM 623-3.")

    st.divider()

    # --- 1. BASE RATING PERIOD ---
    st.header("1. Base Rating Period")
    col1, col2 = st.columns(2)
    with col1:
        from_date = st.date_input("From Date (YYYYMMDD)", format="YYYY/MM/DD")
    with col2:
        thru_date = st.date_input("Thru Date (YYYYMMDD)", format="YYYY/MM/DD", value=date.today())

    if from_date > thru_date:
        st.error("Error: 'From Date' cannot be after 'Thru Date'.")
        st.stop()

    # Calculate Total Calendar Days (Inclusive of start and end date per DA PAM 623-3)
    total_calendar_days = (thru_date - from_date).days + 1
    st.info(f"**Total Calendar Days in Period:** {total_calendar_days}")

    st.divider()

    # --- 2. NON-RATED TIME MODULE ---
    st.header("2. Non-Rated Periods")
    st.markdown("Add any non-rated periods below. The system will automatically compute the days.")

    # Initialize session state for non-rated periods
    if 'nr_periods' not in st.session_state:
        # Start with an empty dataframe containing the necessary columns
        st.session_state.nr_periods = pd.DataFrame(columns=["Start Date", "End Date", "Code"])

    # Use Streamlit's dynamic data editor for a clean, Excel-like input experience
    edited_df = st.data_editor(
        st.session_state.nr_periods,
        column_config={
            "Start Date": st.column_config.DateColumn("Start Date", required=True),
            "End Date": st.column_config.DateColumn("End Date", required=True),
            "Code": st.column_config.SelectboxColumn("Non-Rated Code", options=NON_RATED_CODES, required=True)
        },
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    # --- 3. CALCULATION ENGINE & VALIDATION ---
    st.header("3. Evaluation Calculations")

    total_nr_days = 0
    valid_periods = []
    has_errors = False

    # Process each row from the data editor
    for index, row in edited_df.iterrows():
        start = row["Start Date"]
        end = row["End Date"]
        code = row["Code"]

        if pd.isna(start) or pd.isna(end) or pd.isna(code):
            continue # Skip incomplete rows

        # Validation A: Start must be before End
        if start > end:
            st.error(f"Error in Period {index + 1}: Start Date must be before End Date.")
            has_errors = True
            continue

        # Validation B: Period must fall within the From/Thru dates
        if start < from_date or end > thru_date:
            st.error(f"Error in Period {index + 1}: Non-Rated dates must fall within the Base Rating Period ({from_date} to {thru_date}).")
            has_errors = True
            continue

        valid_periods.append({'start': start, 'end': end, 'code': code})
        # Calculate days for this period (inclusive)
        total_nr_days += (end - start).days + 1

    # Validation C: Overlap check
    if check_overlaps(valid_periods):
        st.error("Error: Two or more Non-Rated periods overlap. Please correct the dates.")
        has_errors = True

    # Stop calculations if there are errors in the inputs
    if has_errors:
        st.warning("Please resolve the errors above to view the final calculations.")
        st.stop()

    # The Math IAW DA PAM 623-3
    total_rated_days = total_calendar_days - total_nr_days
    
    # Months are calculated by dividing total rated days by 30. Remainder is days.
    rated_months = total_rated_days // 30
    leftover_days = total_rated_days % 30

    # Validation D: Minimum 90-day warning
    if total_rated_days < 90:
        st.warning(f"⚠️ **Warning:** Total rated time is {total_rated_days} days. Annual evaluations require a minimum of 90 rated days unless covered by a specific exception (e.g., Change of Rater, Relief for Cause).")

    # --- 4. OUTPUT GENERATION ---
    col3, col4, col5 = st.columns(3)
    col3.metric("Total Rated Days", total_rated_days)
    col4.metric("Rated Months", rated_months)
    col5.metric("Leftover Days", leftover_days)

    st.success(f"**DA Form Output (Box 1i):** {rated_months} Months, {leftover_days} Days")

    # Generate Chronological Code String for Admin Data
    if valid_periods:
        sorted_periods = sorted(valid_periods, key=lambda x: x['start'])
        codes_used = []
        for p in sorted_periods:
            # Extract just the single letter code from the string (e.g., "I" from "I - In transit")
            letter_code = p['code'].split(" - ")[0]
            codes_used.append(letter_code)
        
        code_string = ", ".join(codes_used)
        st.info(f"**Non-Rated Codes used (Chronological):** {code_string}")
    else:
        st.info("**Non-Rated Codes used:** None")

if __name__ == "__main__":
    main()
