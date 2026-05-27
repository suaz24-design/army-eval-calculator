import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import altair as alt

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Army Eval Planner v4.0", page_icon="🦅", layout="wide")

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
    if not periods: return False
    sorted_periods = sorted(periods, key=lambda x: x['start'])
    for i in range(1, len(sorted_periods)):
        if sorted_periods[i]['start'] <= sorted_periods[i-1]['end']: return True
    return False

def plot_timeline(from_date, thru_date, valid_periods):
    """Generates a visual Gantt chart of the rating period."""
    # Create base period data
    chart_data = [{"Task": "Base Rating Period", "Start": pd.to_datetime(from_date), "End": pd.to_datetime(thru_date), "Type": "Rated Time"}]
    
    # Add non-rated periods
    for p in valid_periods:
        code_letter = p['code'].split(" - ")[0]
        chart_data.append({
            "Task": f"Non-Rated ({code_letter})", 
            "Start": pd.to_datetime(p['start']), 
            "End": pd.to_datetime(p['end']), 
            "Type": "Non-Rated Time"
        })
        
    df_chart = pd.DataFrame(chart_data)
    
    # Altair Gantt Chart
    chart = alt.Chart(df_chart).mark_bar(size=30).encode(
        x=alt.X('Start', title='Date', axis=alt.Axis(format='%Y-%m-%d', labelAngle=-45)),
        x2='End',
        y=alt.Y('Task', sort=['Base Rating Period']),
        color=alt.Color('Type', scale=alt.Scale(domain=['Rated Time', 'Non-Rated Time'], range=['#2e7d32', '#d32f2f']), legend=None),
        tooltip=['Task', 'Start', 'End']
    ).properties(height=200).interactive()
    
    return chart

# --- MAIN APP ---
def main():
    st.title("🦅 Army Evaluation Planner & Kiosk")
    st.markdown("Strictly automated IPPS-A date math and Senior Rater profile tracking.")

    tab1, tab2 = st.tabs(["📅 Dates & IPPS-A Output", "📊 Senior Rater Profile Check"])

    # ==========================================
    # TAB 1: DATE CALCULATOR & VISUALIZER
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

            st.header("3. Add Non-Rated Time (If Applicable)")
            if 'nr_periods' not in st.session_state:
                st.session_state.nr_periods = pd.DataFrame(columns=["Start (YYYYMMDD)", "End (YYYYMMDD)", "Code"])

            edited_df = st.data_editor(
                st.session_state.nr_periods,
                column_config={
                    "Start (YYYYMMDD)": st.column_config.TextColumn("Start Date", max_chars=8, validate="^\d{8}$", required=True),
                    "End (YYYYMMDD)": st.column_config.TextColumn("End Date", max_chars=8, validate="^\d{8}$", required=True),
                    "Code": st.column_config.SelectboxColumn("Non-Rated Code", options=NON_RATED_CODES, required=True)
                },
                num_rows="dynamic", use_container_width=True, hide_index=True
            )

            st.divider()

            # --- CALCULATIONS ---
            total_nr_days = 0
            valid_periods = []
            has_errors = False
            ipps_a_codes = []

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

            # --- VISUAL DASHBOARD ---
            st.header("4. Final IPPS-A Output & Visualizer")
            
            # The Gantt Chart
            st.altair_chart(plot_timeline(from_date, thru_date, valid_periods), use_container_width=True)

            colA, colB, colC = st.columns(3)
            colA.metric("Box 1i: Rated Months", rated_months)
            colB.metric("Box 1i: Rated Days", leftover_days)
            colC.metric("Total Rated Days", total_rated_days)

            # --- STOPLIGHT GUARDRAILS ---
            if total_rated_days < min_days:
                shortfall = min_days - total_rated_days
                target_thru_date = thru_date + timedelta(days=shortfall)
                st.error(f"🛑 **INVALID EVALUATION:** You are short **{shortfall} days** (Minimum required is {min_days}).")
                st.info(f"💡 **FIX:** To meet the 90/120 day minimum, change the Thru Date to **{target_thru_date.strftime('%Y%m%d')}**.")
            else:
                st.success(f"✅ **VALID EVALUATION:** Minimum rating requirements met.")

            st.code(f"FROM: {from_date.strftime('%Y%m%d')}\nTHRU: {thru_date.strftime('%Y%m%d')}\n\nNON-RATED:\n{chr(10).join(ipps_a_codes) if ipps_a_codes else 'None'}", language="text")

    # ==========================================
    # TAB 2: SENIOR RATER PROFILE CHECK
    # ==========================================
    with tab2:
        st.header("📊 Senior Rater Profile Misfire Check")
        st.markdown("Ensure you have the math to support a 'Most Qualified' (MQ) before routing the evaluation.")
        
        prof_col1, prof_col2 = st.columns(2)
        with prof_col1:
            eval_category = st.radio("Evaluation Type", ["OER (Officers - Max <50%)", "NCOER (SSG-CSM - Max <24%)"])
        
        with prof_col2:
            current_total = st.number_input("Current Profile: TOTAL EVALS", min_value=0, value=0, step=1)
            current_mqs = st.number_input("Current Profile: TOTAL MQs GIVEN", min_value=0, value=0, step=1)

        st.divider()
        
        if current_total >= 0:
            # Simulate adding this new evaluation as an MQ
            new_total = current_total + 1
            new_mqs = current_mqs + 1
            
            # Math limits based on AR 623-3
            if "OER" in eval_category:
                mq_limit = 0.499 # Less than 50%
            else:
                mq_limit = 0.239 # Less than 24%

            projected_percentage = new_mqs / new_total if new_total > 0 else 0

            st.subheader("Projected Profile if you give an MQ today:")
            st.write(f"Total Evals: **{new_total}** | Total MQs: **{new_mqs}** | Profile: **{(projected_percentage * 100):.1f}%**")

            if projected_percentage <= mq_limit:
                st.success("✅ **CLEAR TO GIVE MQ:** This evaluation will not cause a misfire.")
            else:
                st.error("🛑 **PROFILE MISFIRE WARNING!**")
                st.markdown(f"Giving an MQ right now will spike your profile to **{(projected_percentage * 100):.1f}%** (which violates the limit). You must give a **Highly Qualified (HQ)** or wait for more total evaluations to mature the profile.")

if __name__ == "__main__":
    main()
