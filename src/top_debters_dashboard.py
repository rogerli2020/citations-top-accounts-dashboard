import streamlit as st
import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Define your paths 
CITATIONS_PATH = "./data/citations.parquet"
TRANSACTIONS_PATH = "./data/transactions.parquet"

N = 5000

st.set_page_config(page_title="Chicago Citations Dashboard", layout="wide")
st.title(f"Chicago Citations: Top {N} Debt Accounts")

# 1. Query Top N Debtors directly from Parquet
@st.cache_data
def get_top_debtors(file_path):
    query = f"""
        SELECT 
            notice_number,
            SUM(current_amount_due) AS total_outstanding_debt,
            SUM(total_paid) AS total_paid,
            COUNT(ticket_number) AS total_tickets,
            ANY_VALUE(owner_zip) AS owner_zip,
            ANY_VALUE("owner_median_income") AS owner_median_income,
            MAX(bankruptcy_status) AS bankruptcy_status,
            ANY_VALUE(flag_owner_in_chicago) AS flag_owner_in_chicago,
            ANY_VALUE(owner_zone) AS owner_zone
        FROM read_parquet('{file_path}')
        WHERE 
            notice_number IS NOT NULL
            AND notice_number != '0' 
            AND is_fleet IS FALSE
        GROUP BY notice_number
        ORDER BY total_outstanding_debt DESC
        LIMIT {N}
    """
    with duckdb.connect() as con:
        df = con.execute(query).df()
    return df

with st.spinner("Calculating top accounts across 34.8M records..."):
    top_debtors = get_top_debtors(CITATIONS_PATH)

# 2. Helper function to fetch ticket details
def get_notice_details(file_path, notice_number):
    query = f"""
        SELECT 
            ticket_number,
            issue_date,
            violation_description,
            ticket_queue,
            payment_count,
            total_paid,
            current_amount_due,
            notice_level
        FROM read_parquet('{file_path}')
        WHERE notice_number = ?
    """
    with duckdb.connect() as con:
        df = con.execute(query, [notice_number]).df()
    return df

# 3. Define the Modal/Popup for Account Details
@st.dialog("Account Details & Breakdown", width="large")
def show_account_modal(notice_number, summary_data):
    st.markdown(f"### Notice Number: `{notice_number}`")
    
    # Map the bankruptcy status integer to a readable string
    bk_map = {2: "Confirmed (2)", 1: "Unknown (1)", 0: "No (0)"}
    bk_text = bk_map.get(summary_data['bankruptcy_status'], "N/A")
    
    # Format the boolean flag
    in_chi_text = "Yes" if summary_data['flag_owner_in_chicago'] else "No"
    
    # Display Key Metrics - Split into two rows for cleaner UI
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Outstanding Debt", f"${summary_data['total_outstanding_debt']:,.2f}")
    col2.metric("Total Paid", f"${summary_data['total_paid']:,.2f}")
    col3.metric("Total Tickets", int(summary_data['total_tickets']))
    col4.metric("Bankruptcy Status", bk_text)
    
    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Owner ZIP", str(summary_data['owner_zip']))
    col6.metric("Median Income", f"${summary_data['owner_median_income']:,.2f}" if pd.notnull(summary_data['owner_median_income']) else "N/A")
    col7.metric("Owner in Chicago?", in_chi_text)
    col8.metric("Owner Zone", str(summary_data['owner_zone']) if pd.notnull(summary_data['owner_zone']) else "N/A")
    
    st.divider()
    
    # Fetch detailed tickets
    with st.spinner("Loading ticket details..."):
        details_df = get_notice_details(CITATIONS_PATH, notice_number)
    
    # Time Series Chart for Debt & Payments
    st.write("### Debt Accumulation & Payment Behavior")
    
    # Ensure issue_date is datetime and aggregate by date
    details_df['issue_date'] = pd.to_datetime(details_df['issue_date'])
    time_df = details_df.groupby(details_df['issue_date'].dt.date).agg({
        'current_amount_due': 'sum',
        'total_paid': 'sum'
    }).reset_index()
    time_df.rename(columns={'issue_date': 'Date'}, inplace=True)
    time_df = time_df.sort_values('Date')
    
    # Calculate the total value of tickets issued on that date, and a running total
    time_df['ticket_value'] = time_df['current_amount_due'] + time_df['total_paid']
    time_df['Cumulative Fines Incurred'] = time_df['ticket_value'].cumsum()
    
    fig_time = go.Figure()
    
    # Add Cumulative Debt Line
    fig_time.add_trace(go.Scatter(
        x=time_df['Date'], 
        y=time_df['Cumulative Fines Incurred'],
        mode='lines+markers', 
        name='Cumulative Fines Incurred',
        line=dict(color='firebrick', width=3)
    ))
    
    # Add Payments as a Bar Chart
    fig_time.add_trace(go.Bar(
        x=time_df['Date'], 
        y=time_df['total_paid'],
        name='Paid Towards Tickets (by Issue Date)',
        marker_color='seagreen',
        opacity=0.8
    ))
    
    fig_time.update_layout(
        xaxis_title='Ticket Issue Date',
        yaxis_title='Amount ($)',
        hovermode='x unified',
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    st.plotly_chart(fig_time, use_container_width=True)
    st.divider()

    # Layout for Pie Charts
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        count_df = details_df['violation_description'].value_counts().reset_index()
        count_df.columns = ['violation_description', 'count']
        
        fig1 = px.pie(
            count_df, 
            names='violation_description', 
            values='count',
            title='Violation Types (by Count)',
            hole=0.4
        )
        fig1.update_traces(textposition='inside', textinfo='percent')
        st.plotly_chart(fig1, use_container_width=True)

    with chart_col2:
        debt_df = details_df[details_df['current_amount_due'] > 0].groupby('violation_description')['current_amount_due'].sum().reset_index()
        
        fig2 = px.pie(
            debt_df, 
            names='violation_description', 
            values='current_amount_due',
            title='Outstanding Debt (by Type)',
            hole=0.4
        )
        fig2.update_traces(textposition='inside', textinfo='percent')
        st.plotly_chart(fig2, use_container_width=True)

    st.write("### Individual Ticket Breakdown")
    
    # Convert issue_date back to strings or cleanly formatted dates for the dataframe display
    details_df['issue_date'] = details_df['issue_date'].dt.strftime('%Y-%m-%d')
    
    st.dataframe(
        details_df.style.format({
            "current_amount_due": "${:,.2f}", 
            "total_paid": "${:,.2f}"
        }), 
        use_container_width=True,
        hide_index=True
    )

# 4. Main UI Layout
col_left, col_right = st.columns([3, 1])

with col_left:
    st.subheader("Top Debtors Table")
    
    # Interactive Table Selection
    selection_event = st.dataframe(
        top_debtors,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "total_outstanding_debt": st.column_config.NumberColumn(
                "Total Outstanding Debt", format="$%.2f"
            ),
            "total_paid": st.column_config.NumberColumn(
                "Total Paid", format="$%.2f"
            ),
            "owner_median_income": st.column_config.NumberColumn(
                "Owner Median Income", format="$%.2f"
            ),
            # You can also format the boolean here if you'd like
            "flag_owner_in_chicago": st.column_config.CheckboxColumn(
                "In Chicago?"
            )
        }
    )

# Sync the selected row with the Search box
default_index = 0
selected_indices = selection_event.selection.rows

if selected_indices:
    selected_row_idx = selected_indices[0]
    selected_notice_from_table = top_debtors.iloc[selected_row_idx]["notice_number"]
    
    notice_list = top_debtors["notice_number"].tolist()
    default_index = notice_list.index(selected_notice_from_table)

with col_right:
    st.subheader("Inspect Account")
    st.info("Select an account from the table or dropdown to view charts and details.")
    
    selected_notice = st.selectbox(
        "Select Notice Number:", 
        options=top_debtors["notice_number"].tolist(),
        index=default_index
    )
    
    # Trigger the modal
    if st.button("🔍 View Details Overlay", use_container_width=True, type="primary"):
        account_summary = top_debtors[top_debtors["notice_number"] == selected_notice].iloc[0]
        show_account_modal(selected_notice, account_summary)