import duckdb

CITATIONS_PATH = "./data/citations.parquet"
N = 5000

print(f"Baking Top {N} accounts data...")

# 1. Bake the Top N Summary Table
summary_query = f"""
    COPY (
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
        FROM read_parquet('{CITATIONS_PATH}')
        WHERE 
            notice_number IS NOT NULL
            AND notice_number != '0' 
            AND is_fleet IS FALSE
            AND NOT (plate_type = 'PFR' OR hearing_disposition_reason LIKE '%FLEET%')
        GROUP BY notice_number
        ORDER BY total_outstanding_debt DESC
        LIMIT {N}
    ) TO 'baked_top_{N}_summary.parquet' (FORMAT PARQUET);
"""

# 2. Bake the Ticket Details (Now includes violation_zip)
details_query = f"""
    COPY (
        SELECT 
            ticket_number,
            notice_number,
            issue_date,
            violation_description,
            violation_zip,
            ticket_queue,
            payment_count,
            total_paid,
            current_amount_due,
            notice_level
        FROM read_parquet('{CITATIONS_PATH}')
        WHERE notice_number IN (
            SELECT notice_number FROM read_parquet('baked_top_{N}_summary.parquet')
        )
    ) TO 'baked_top_{N}_details.parquet' (FORMAT PARQUET);
"""

with duckdb.connect() as con:
    con.execute(summary_query)
    print("Summary data baked successfully!")
    con.execute(details_query)
    print("Details data baked successfully!")