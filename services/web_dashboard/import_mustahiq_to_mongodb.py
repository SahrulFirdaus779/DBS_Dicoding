import os
import sys
import glob
import pandas as pd
from pymongo import MongoClient
import time

# Path to the data
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), 'data', 'raw')

def main():
    print(f"Scanning for mustahiq files in: {RAW_DATA_DIR}")
    csv_files = glob.glob(os.path.join(RAW_DATA_DIR, 'mustahiq_*.csv'))
    
    if not csv_files:
        print("No mustahiq CSV files found!")
        sys.exit(1)
        
    print(f"Found {len(csv_files)} files.")

    print("Connecting to MongoDB (localhost:27017)...")
    try:
        client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=5000)
        client.server_info() # trigger connection check
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)

    db = client["zakatsight"]
    collection = db["mustahiq"]

    print("Dropping existing 'mustahiq' collection to avoid duplicates...")
    collection.drop()

    chunk_size = 50000
    total_inserted = 0

    for file_path in csv_files:
        print(f"\nProcessing {os.path.basename(file_path)}...")
        
        try:
            for chunk_idx, df_chunk in enumerate(pd.read_csv(file_path, low_memory=False, chunksize=chunk_size)):
                
                # Format dates if they exist
                if 'tgl_penyaluran' in df_chunk.columns:
                    df_chunk['tgl_dt'] = pd.to_datetime(df_chunk['tgl_penyaluran'], errors='coerce')
                elif 'tgl' in df_chunk.columns:
                    df_chunk['tgl_dt'] = pd.to_datetime(df_chunk['tgl'], errors='coerce')
                
                # Make sure it's a python datetime, not pandas timestamp
                # and clean up all NaNs and NaTs
                records = df_chunk.to_dict('records')
                clean_records = []
                for rec in records:
                    clean_rec = {}
                    for k, v in rec.items():
                        if pd.isna(v):
                            clean_rec[k] = None
                        elif k == 'tgl_dt':
                            clean_rec[k] = v.to_pydatetime() if hasattr(v, 'to_pydatetime') else v
                        else:
                            clean_rec[k] = v
                    clean_records.append(clean_rec)
                
                if clean_records:
                    collection.insert_many(clean_records)
                    total_inserted += len(records)
                    print(f"  -> Inserted {total_inserted} records total...")
                    
        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    print("\nCreating indexes on 'tgl_dt', 'kategori_asnaf', 'kategori_program', and 'status_penyaluran' for performance...")
    collection.create_index("tgl_dt")
    collection.create_index("kategori_asnaf")
    collection.create_index("kategori_program")
    collection.create_index("status_penyaluran")
    collection.create_index("mustahiq_id")
    collection.create_index("channel")

    print("\n[OK] Mustahiq Data migration completed successfully!")
    print(f"Total records inserted: {total_inserted}")

if __name__ == "__main__":
    main()
