import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase Admin SDK
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)

db = firestore.client()

collections_to_delete = [
    "OccupiedCells",
    "SingleCellReAllocation",
    "Transactions",
    "Users"
]

def delete_collection_quietly(coll_name, batch_size=500):
    coll_ref = db.collection(coll_name)
    docs = coll_ref.limit(batch_size).stream()

    deleted = 0
    for doc in docs:
        doc.reference.delete()
        deleted += 1

    if deleted >= batch_size:
        return delete_collection_quietly(coll_name, batch_size)

for collection in collections_to_delete:
    delete_collection_quietly(collection)

print("✅ Done: Collections cleared (documents deleted only).")
