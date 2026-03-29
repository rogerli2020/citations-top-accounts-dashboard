import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Chicago Citations Dashboard", layout="wide")
st.title("Chicago Citations Account Dashboard")

@st.cache_data
def load_data():
    df_debt = pd.read_parquet("baked_top_debt_summary.parquet")
    df_paid = pd.read_parquet("baked_top_paid_summary.parquet")
    df_comp = pd.read_parquet("baked_top_compliant_summary.parquet")
    
    details_df = pd.read_parquet("baked_all_details.parquet")
    details_df['issue_date'] = pd.to_datetime(details_df['issue_date'])
    return df_debt, df_paid, df_comp, details_df

with st.spinner("Loading baked data..."):
    df_debt, df_paid, df_comp, all_details = load_data()

def get_notice_details(notice_number):
    return all_details[all_details['notice_number'] == notice_number].copy()

def highlight_ticket_rows(row):
    color = ''
    queue = str(row.get('ticket_queue', '')).upper()
    level = str(row.get('notice_level', '')).upper()
    
    if queue == 'PAID':
        color = 'background-color: rgba(39, 174, 96, 0.3)'       # Green
    elif queue == 'BANKRUPTCY':
        color = 'background-color: rgba(41, 128, 185, 0.3)'      # Blue
    elif queue == 'DISMISSED':
        color = 'background-color: rgba(149, 165, 166, 0.3)'     # Gray
    elif queue == 'NOTICE' and level == 'SEIZ':
        color = 'background-color: rgba(192, 57, 43, 0.4)'       # Red
    elif queue == 'NOTICE' and level == 'FINL':
        color = 'background-color: rgba(211, 84, 0, 0.4)'        # Orange
    return [color] * len(row)

@st.dialog("Account Details & Breakdown", width="large")
def show_account_modal(notice_number, summary_data):
    st.markdown(f"### Notice Number: `{notice_number}`")
    
    bk_map = {2: "Confirmed (2)", 1: "Unknown (1)", 0: "No (0)"}
    bk_text = bk_map.get(summary_data['bankruptcy_status'], "N/A")
    in_chi_text = "Yes" if summary_data['flag_owner_in_chicago'] else "No"
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Outstanding Debt", f"${summary_data['total_outstanding_debt']:,.2f}")
    col2.metric("Total Paid", f"${summary_data['total_paid']:,.2f}")
    col3.metric("Total Tickets", int(summary_data['total_tickets']))
    col4.metric("Bankruptcy Status", bk_text)
    
    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Owner ZIP", str(summary_data['owner_zip']))
    col6.metric("Median Income", f"${summary_data['owner_median_income']:,.2f}" if pd.notnull(summary_data['owner_median_income']) else "N/A")
    col7.metric("Owner in Chicago?", in_chi_text)
    col8.metric("Compliant Tickets (Paid/Dismissed)", int(summary_data['compliant_tickets']))
    
    st.divider()
    
    details_df = get_notice_details(notice_number)
    details_df = details_df.sort_values('issue_date', ascending=True)
    
    st.write("### Debt Accumulation & Payment Behavior")
    time_df = details_df.groupby(details_df['issue_date'].dt.date).agg({
        'current_amount_due': 'sum',
        'total_paid': 'sum',
        'violation_description': lambda x: ', '.join(x.dropna().astype(str)),
        'violation_zip': lambda x: ', '.join(x.dropna().astype(str))
    }).reset_index()
    
    time_df.rename(columns={'issue_date': 'Date'}, inplace=True)
    time_df = time_df.sort_values('Date')
    time_df['ticket_value'] = time_df['current_amount_due'] + time_df['total_paid']
    time_df['Cumulative Fines Incurred'] = time_df['ticket_value'].cumsum()
    
    fig_time = go.Figure()
    fig_time.add_trace(go.Scatter(
        x=time_df['Date'], y=time_df['Cumulative Fines Incurred'], mode='lines+markers', 
        name='Cumulative Fines Incurred', line=dict(color='firebrick', width=3),
        customdata=time_df[['violation_description', 'violation_zip']],
        hovertemplate="<b>Cumulative Fines:</b> $%{y:,.2f}<br><b>Violations:</b> %{customdata[0]}<br><b>ZIPs:</b> %{customdata[1]}<extra></extra>"
    ))
    fig_time.add_trace(go.Bar(
        x=time_df['Date'], y=time_df['total_paid'], name='Paid Towards Tickets (by Issue Date)',
        marker_color='seagreen', opacity=0.8, hovertemplate="<b>Paid:</b> $%{y:,.2f}<extra></extra>"
    ))
    fig_time.update_layout(
        xaxis_title='Ticket Issue Date', yaxis_title='Amount ($)', hovermode='x unified',
        margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_time, use_container_width=True)
    st.divider()

    st.write("### Ticket Distributions")
    
    # --- ROW 1: VIOLATION DESCRIPTION ---
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        count_df = details_df['violation_description'].value_counts().reset_index()
        count_df.columns = ['violation_description', 'count']
        fig1 = px.pie(count_df, names='violation_description', values='count', title='Description (by Count)', hole=0.4)
        fig1.update_traces(textposition='inside', textinfo='percent')
        st.plotly_chart(fig1, use_container_width=True)

    with chart_col2:
        debt_df = details_df[details_df['current_amount_due'] > 0].groupby('violation_description')['current_amount_due'].sum().reset_index()
        fig2 = px.pie(debt_df, names='violation_description', values='current_amount_due', title='Description (by Debt)', hole=0.4)
        fig2.update_traces(textposition='inside', textinfo='percent')
        st.plotly_chart(fig2, use_container_width=True)

    # --- ROW 2: VIOLATION CATEGORY ---
    chart_col3, chart_col4 = st.columns(2)
    with chart_col3:
        cat_count_df = details_df['violation_category'].value_counts().reset_index()
        cat_count_df.columns = ['violation_category', 'count']
        fig3 = px.pie(cat_count_df, names='violation_category', values='count', title='Category (by Count)', hole=0.4)
        fig3.update_traces(textposition='inside', textinfo='percent')
        st.plotly_chart(fig3, use_container_width=True)

    with chart_col4:
        cat_debt_df = details_df[details_df['current_amount_due'] > 0].groupby('violation_category')['current_amount_due'].sum().reset_index()
        fig4 = px.pie(cat_debt_df, names='violation_category', values='current_amount_due', title='Category (by Debt)', hole=0.4)
        fig4.update_traces(textposition='inside', textinfo='percent')
        st.plotly_chart(fig4, use_container_width=True)

    st.write("### Individual Ticket Breakdown (Oldest to Newest)")
    details_df['issue_date'] = details_df['issue_date'].dt.strftime('%Y-%m-%d')
    styled_df = details_df.drop(columns=['notice_number']).style.format({
        "current_amount_due": "${:,.2f}", 
        "total_paid": "${:,.2f}"
    }).apply(highlight_ticket_rows, axis=1)
    
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

# Main UI Layout
view_option = st.radio(
    "Select Account Ranking:",
    options=["Top Debtors (Highest Outstanding)", "Top Payers (Highest Total Paid)", "Most Compliant (Highest Count of Paid/Dismissed)"],
    horizontal=True
)

if view_option.startswith("Top Debtors"):
    current_df = df_debt
elif view_option.startswith("Top Payers"):
    current_df = df_paid
else:
    current_df = df_comp

col_left, col_right = st.columns([3, 1])

with col_left:
    selection_event = st.dataframe(
        current_df,
        use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row",
        column_config={
            "total_outstanding_debt": st.column_config.NumberColumn("Total Outstanding Debt", format="$%.2f"),
            "total_paid": st.column_config.NumberColumn("Total Paid", format="$%.2f"),
            "owner_median_income": st.column_config.NumberColumn("Owner Median Income", format="$%.2f"),
            "compliant_tickets": st.column_config.NumberColumn("Compliant Tickets"),
            "flag_owner_in_chicago": st.column_config.CheckboxColumn("In Chicago?")
        }
    )

default_index = 0
selected_indices = selection_event.selection.rows

if selected_indices:
    selected_row_idx = selected_indices[0]
    selected_notice_from_table = current_df.iloc[selected_row_idx]["notice_number"]
    default_index = current_df["notice_number"].tolist().index(selected_notice_from_table)

with col_right:
    st.subheader("Inspect Account")
    st.info("Select an account from the table or dropdown to view charts and details.")
    
    selected_notice = st.selectbox(
        "Select Notice Number:", 
        options=current_df["notice_number"].tolist(), 
        index=default_index
    )
    
    if st.button("🔍 View Details Overlay", use_container_width=True, type="primary"):
        account_summary = current_df[current_df["notice_number"] == selected_notice].iloc[0]
        show_account_modal(selected_notice, account_summary)