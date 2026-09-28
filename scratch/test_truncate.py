import sys, os
from sqlalchemy import create_engine, text

eng = create_engine('postgresql://postgres:ganesh@localhost:5432/hla_db')
with eng.connect() as conn:
    try:
        conn.execute(text('TRUNCATE TABLE "Unique".order_ingest;'))
        conn.commit()
        print("Success with: TRUNCATE TABLE \"Unique\".order_ingest;")
    except Exception as e:
        print("Failed with \"Unique\".order_ingest:", e)
        conn.rollback()

    try:
        conn.execute(text('TRUNCATE TABLE "Unique"."order_ingest";'))
        conn.commit()
        print("Success with: TRUNCATE TABLE \"Unique\".\"order_ingest\";")
    except Exception as e:
        print("Failed with \"Unique\".\"order_ingest\":", e)
        conn.rollback()

    try:
        conn.execute(text('TRUNCATE TABLE Unique.order_ingest;'))
        conn.commit()
        print("Success with: TRUNCATE TABLE Unique.order_ingest;")
    except Exception as e:
        print("Failed with Unique.order_ingest:", e)
        conn.rollback()
