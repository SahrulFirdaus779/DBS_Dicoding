import datetime
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client["zakatsight"]
col = db["penerimaan"]

# Delete any record with year >= 2100 (like 2202)
query = {"tgl_dt": {"$gte": datetime.datetime(2100, 1, 1)}}
deleted = col.delete_many(query)

print(f"Deleted {deleted.deleted_count} typo records with future dates.")
