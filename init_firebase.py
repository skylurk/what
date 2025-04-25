import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import hashlib
import os

# Load credentials and initialize Firebase app
cred = credentials.Certificate("serviceAccountKey.json")  # Path to your downloaded key
firebase_admin.initialize_app(cred)

# Connect to Firestore
db = firestore.client()

# ---------- INIT COLLECTION STRUCTURES ---------- #

# Create a dummy transaction to define the structure
def create_dummy_transaction():
    transaction = {
        "UserID": "user_12345",
        "TransactionID": "txn_001",
        "NumTrees": 3,
        "Amount": 30.0,
        "Currency": "EUR",
        "OffsetCarbon": 3 * 3.8,
        "Status": "Awaiting Allocation",
        "Timestamp": datetime.now().strftime("%d/%m/%Y")
    }
    db.collection("Transactions").document(transaction["TransactionID"]).set(transaction)

# Create a dummy occupied cell
def create_dummy_occupied_cell():
    occupied = {
        "TransactionID": "txn_001",
        "UserID": "user_12345",
        "What3Words": "filled.breeze.hatch",
        "Lat": 40.7128,
        "Lng": -74.0060
    }
    db.collection("OccupiedCells").add(occupied)

# Create a dummy user
def create_dummy_user():
    first_name = "John"
    last_name = "Doe"
    email = "john.doe@example.com"
    password = "securepassword123"
    salt = os.urandom(16).hex()
    password_hash = hashlib.sha256((password + salt).encode()).hexdigest()

    user = {
        "First Name": first_name,
        "Last Name": last_name,
        "EmailAddress": email,
        "PasswordHash": password_hash,
        "Salt": salt,
        "Timestamp": datetime.now().strftime("%d/%m/%Y")
    }
    db.collection("Users").document(email).set(user)

def create_dummy_reallocation():
    dummy = {
        "TransactionID": "dummy-txn-id",
        "UserID": "dummy-user-id",
        "Status": "Was Allocated"
    }

    db.collection("SingleCellReAllocation").add(dummy)
    print("✅ Dummy reallocation entry created.")


# Add super admin user
def create_super_admin():
    email = "luis.walsh@what3trees.org"
    password = "w3t2025"
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    super_admin = {
        "UserEmail": email,
        "UserPassword": password_hash,
        "IsSuperUser": 1
    }
    db.collection("Admin_Users").document(email).set(super_admin)

# ---------- RUN THE INITIALIZATION ---------- #

if __name__ == "__main__":
    print("Initializing Firestore with dummy data...")
    create_dummy_transaction()
    create_dummy_occupied_cell()
    create_dummy_user()
    create_super_admin()
    create_dummy_reallocation()
    print("Initialization complete.")
