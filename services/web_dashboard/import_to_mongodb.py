import os
import sys
import pandas as pd
from pymongo import MongoClient
from datetime import datetime

# Path to the data
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), 'data', 'raw', 'penerimaan_full.csv')

def main():
    if not os.path.exists(DATA_PATH):
        print(f"File not found: {DATA_PATH}")
        sys.exit(1)

    print("Connecting to MongoDB (localhost:27017)...")
    try:
        client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=5000)
        client.server_info() # trigger connection check
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)

    db = client["zakatsight"]
    collection = db["penerimaan"]

    print(f"Reading CSV from {DATA_PATH} (this might take a minute)...")
    
    # Read the data in chunks to prevent memory overload
    chunk_size = 50000
    total_inserted = 0

    # Drop existing collection to prevent duplicates on multiple runs
    print("Dropping existing 'penerimaan' collection if it exists...")
    collection.drop()

    print("Parsing and inserting data in chunks...")
    for chunk_idx, df_chunk in enumerate(pd.read_csv(DATA_PATH, low_memory=False, chunksize=chunk_size)):
        # Convert 'tgl' string to datetime objects
        # Format might be 'YYYY-MM-DD' or similar. coerce handles invalid formats.
        if 'tgl' in df_chunk.columns:
            df_chunk['tgl_dt'] = pd.to_datetime(df_chunk['tgl'], errors='coerce')
        
        # Convert DataFrame to a list of dicts for MongoDB insertion
        # Drop rows where 'tgl_dt' is NaT for cleaner querying
        df_chunk = df_chunk.dropna(subset=['tgl_dt'])
        
        # Keep original columns, but ensure MongoDB gets native Python types
        # Drop the original 'tgl' if 'tgl_dt' is reliable, but let's keep both for now
        # Also handle potential NaN in other columns
        df_chunk = df_chunk.where(pd.notnull(df_chunk), None)
        
        records = df_chunk.to_dict('records')
        
        if records:
            collection.insert_many(records)
            total_inserted += len(records)
            print(f"  -> Inserted {total_inserted} records so far...")

    print("Creating indexes on 'tgl_dt', 'channel', 'bank' for blazing fast queries...")
    collection.create_index("tgl_dt")
    collection.create_index("channel")
    collection.create_index("bank")
    
    # Create distribution mock data
    print("Creating mock distribution (penyaluran) data...")
    dist_collection = db["penyaluran"]
    dist_collection.drop()
    dist_records = [
        {"kategori": "Pendidikan", "persentase": 35.5},
        {"kategori": "Kesehatan", "persentase": 25.0},
        {"kategori": "Ekonomi & Modal Usaha", "persentase": 20.0},
        {"kategori": "Bantuan Bencana", "persentase": 10.0},
        {"kategori": "Operasional", "persentase": 9.5}
    ]
    dist_collection.insert_many(dist_records)

    print("\n✅ Data migration to MongoDB completed successfully!")
    print(f"Total records inserted: {total_inserted}")

if __name__ == "__main__":
    main()
