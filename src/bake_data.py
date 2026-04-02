import duckdb

CITATIONS_PATH = "./data/citations.parquet"
N = 1000

print(f"Baking Top {N} accounts data...")

base_select = """
    SELECT 
        notice_number,
        SUM(current_amount_due) AS total_outstanding_debt,
        SUM(total_paid) AS total_paid,
        COUNT(ticket_number) AS total_tickets,
        SUM(CASE WHEN ticket_queue IN ('PAID', 'DISMISSED') THEN 1 ELSE 0 END) AS compliant_tickets,
        ANY_VALUE(owner_zip) AS owner_zip,
        ANY_VALUE("owner_median_income") AS owner_median_income,
        MAX(bankruptcy_status) AS bankruptcy_status,
        ANY_VALUE(flag_owner_in_chicago) AS flag_owner_in_chicago,
        ANY_VALUE(owner_zone) AS owner_zone,
        ANY_VALUE(last_active_date) AS last_active_date
    FROM read_parquet('{path}')
    WHERE 
        notice_number IS NOT NULL
        AND notice_number != '0' 
        AND is_fleet IS FALSE
        AND NOT plate_type = 'PFR'
        AND NOT hearing_disposition_reason LIKE '%FLEET%'

        -- filter for only 'active' individuals
        AND date_diff( 'day', last_active_date, '2026-01-12' ) <= 365
    GROUP BY notice_number
"""

# 1-3. Bake Summaries
query_debt = f"COPY ({base_select.format(path=CITATIONS_PATH)} ORDER BY total_outstanding_debt DESC LIMIT {N}) TO 'baked_top_debt_summary.parquet' (FORMAT PARQUET);"
query_paid = f"COPY ({base_select.format(path=CITATIONS_PATH)} ORDER BY total_paid DESC LIMIT {N}) TO 'baked_top_paid_summary.parquet' (FORMAT PARQUET);"
query_compliant = f"COPY ({base_select.format(path=CITATIONS_PATH)} ORDER BY compliant_tickets DESC LIMIT {N}) TO 'baked_top_compliant_summary.parquet' (FORMAT PARQUET);"

# 4. Bake Ticket Details (Now includes violation_category)
query_details = f"""
    COPY (
        SELECT 
            ticket_number,
            notice_number,
            issue_date,
            violation_category,  -- <--- NEW COLUMN ADDED HERE
            violation_description,
            violation_zip,
            ticket_queue,
            payment_count,
            total_paid,
            current_amount_due,
            notice_level,
            boot_status
        FROM read_parquet('{CITATIONS_PATH}')
        WHERE notice_number IN (SELECT notice_number FROM read_parquet('baked_top_debt_summary.parquet'))
           OR notice_number IN (SELECT notice_number FROM read_parquet('baked_top_paid_summary.parquet'))
           OR notice_number IN (SELECT notice_number FROM read_parquet('baked_top_compliant_summary.parquet'))
    ) TO 'baked_all_details.parquet' (FORMAT PARQUET);
"""

with duckdb.connect() as con:
    print("Baking Debtors...")
    con.execute(query_debt)
    print("Baking Payers...")
    con.execute(query_paid)
    print("Baking Compliant Tickets...")
    con.execute(query_compliant)
    print("Baking Details...")
    con.execute(query_details)
    print("All data baked successfully!")