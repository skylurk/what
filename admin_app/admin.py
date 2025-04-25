# admin.py
from flask import Flask, render_template, session, redirect, url_for, jsonify, request
from dotenv import load_dotenv
import os
import firebase_admin
from firebase_admin import credentials, firestore
import hashlib

# Load env variables
load_dotenv()

# Initialize Flask
admin_app = Flask(
    __name__,
    template_folder='templates',
    static_folder='static'
)

admin_app.secret_key = os.getenv("FLASK_SECRET_KEY")

# Firebase init
if not firebase_admin._apps:
    cred = credentials.Certificate(os.path.join(os.path.dirname(__file__), '..', 'serviceAccountKey.json'))
    firebase_admin.initialize_app(cred)

db = firestore.client()

@admin_app.route('/')
def admin_home():
    maps_key = os.getenv("GOOGLE_MAPS_API_KEY")
    w3w_key = os.getenv("W3W_API_KEY")
    return render_template('admin.html', maps_key=maps_key, w3w_key=w3w_key)

@admin_app.route('/get-awaiting-transactions')
def get_awaiting_transactions():
    transactions_ref = db.collection("Transactions").where("Status", "==", "Awaiting Allocation").stream()
    
    transactions = []
    for doc in transactions_ref:
        data = doc.to_dict()
        transactions.append({
            'TransactionID': data.get('TransactionID'),
            'NumTrees': data.get('NumTrees')
        })

    return jsonify(transactions)

@admin_app.route('/save-grid-selection', methods=['POST'])
def save_grid_selection():
    try:
        data = request.json
        transaction_id = data["transactionID"]
        selected_cells = data["selectedCells"]

        # Get the transaction document
        txn_ref = db.collection("Transactions").document(transaction_id)
        txn_doc = txn_ref.get()

        if not txn_doc.exists:
            return jsonify({"error": "Transaction not found"}), 404

        txn_data = txn_doc.to_dict()
        user_id = txn_data.get("UserID")

        # Write each grid cell to OccupiedCells
        batch = db.batch()
        for cell in selected_cells:
            cell_ref = db.collection("OccupiedCells").document()
            batch.set(cell_ref, {
                "TransactionID": transaction_id,
                "UserID": user_id,
                "What3Words": cell["what3words"],
                "Lat": cell["lat"],
                "Lng": cell["lng"]
            })

        # Update transaction status
        batch.update(txn_ref, {"Status": "Allocated"})
        batch.commit()

        return jsonify({"success": True})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_app.route("/get-allocated-cells")
def get_allocated_cells():
    try:
        occupied_ref = db.collection("OccupiedCells").stream()
        occupied_cells = []

        for doc in occupied_ref:
            data = doc.to_dict()
            occupied_cells.append({
                "what3words": data.get("What3Words"),
                "lat": data.get("Lat"),
                "lng": data.get("Lng")
            })

        return jsonify(occupied_cells)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_app.route('/get-transaction-stats')
def get_transaction_stats():
    try:
        transactions = db.collection("Transactions").stream()
        total_trees = 0
        total_offset = 0.0

        for doc in transactions:
            data = doc.to_dict()
            total_trees += int(data.get("NumTrees", 0))
            total_offset += float(data.get("OffsetCarbon", 0.0))

        return jsonify({
            "totalTrees": total_trees,
            "totalOffset": round(total_offset, 2)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_app.route('/admin-users')
def admin_users():
    return render_template('admin_users.html')

@admin_app.route('/get-admin-users')
def get_admin_users():
    try:
        users_ref = db.collection("Admin_Users").stream()
        admin_users = []

        for doc in users_ref:
            data = doc.to_dict()
            admin_users.append({
                "UserEmail": data.get("UserEmail", ""),
                "UserPassword": data.get("UserPassword", ""),
                "IsSuperUser": data.get("IsSuperUser", 0)
            })

        return jsonify(admin_users)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_app.route('/create-admin-user', methods=['POST'])
def create_admin_user():
    try:
        data = request.json
        email = data.get("email")
        password = data.get("password")
        is_super_user = 1 if data.get("isSuperUser") else 0

        if not email or not password:
            return jsonify({"error": "Email and password are required."}), 400

        password_hash = hashlib.sha256(password.encode()).hexdigest()

        db.collection("Admin_Users").document(email).set({
            "UserEmail": email,
            "UserPassword": password_hash,
            "IsSuperUser": is_super_user
        })

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_app.route('/delete-admin-user', methods=['POST'])
def delete_admin_user():
    try:
        data = request.json
        email = data.get("email")

        if not email:
            return jsonify({"error": "Email required"}), 400

        db.collection("Admin_Users").document(email).delete()

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_app.route('/admin-map')
def admin_map():
    maps_key = os.getenv("GOOGLE_MAPS_API_KEY")
    w3w_key = os.getenv("W3W_API_KEY")
    return render_template('admin_map.html', maps_key=maps_key, w3w_key=w3w_key)

@admin_app.route('/reallocate-cell', methods=['POST'])
def reallocate_cell():
    try:
        data = request.json
        lat = data.get("lat")
        lng = data.get("lng")
        w3w = data.get("what3words")

        # Find the occupied cell document
        occupied_query = db.collection("OccupiedCells") \
            .where("Lat", "==", lat) \
            .where("Lng", "==", lng) \
            .where("What3Words", "==", w3w) \
            .limit(1) \
            .stream()

        doc_to_move = None
        for doc in occupied_query:
            doc_to_move = doc
            break

        if not doc_to_move:
            return jsonify({"error": "Occupied cell not found"}), 404

        cell_data = doc_to_move.to_dict()
        cell_ref = db.collection("OccupiedCells").document(doc_to_move.id)

        # Delete from OccupiedCells
        cell_ref.delete()

        # Add to SingleCellReAllocation
        db.collection("SingleCellReAllocation").add({
            "TransactionID": cell_data.get("TransactionID"),
            "UserID": cell_data.get("UserID"),
            "Status": "Was Allocated"
        })

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_app.route('/get-pending-reallocations')
def get_pending_reallocations():
    try:
        docs = db.collection("SingleCellReAllocation") \
            .where("Status", "==", "Was Allocated") \
            .stream()

        reallocations = []
        for doc in docs:
            data = doc.to_dict()
            reallocations.append({
                "TransactionID": data.get("TransactionID"),
                "UserID": data.get("UserID")
            })

        return jsonify(reallocations)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_app.route('/finalize-reallocation', methods=['POST'])
def finalize_reallocation():
    try:
        data = request.json
        txn_id = data["transactionID"]
        user_id = data["userID"]
        lat = data["lat"]
        lng = data["lng"]
        w3w = data["what3words"]

        # 1. Add new cell to OccupiedCells
        db.collection("OccupiedCells").add({
            "TransactionID": txn_id,
            "UserID": user_id,
            "What3Words": w3w,
            "Lat": lat,
            "Lng": lng
        })

        # 2. Update matching doc in SingleCellReAllocation
        reallocation_docs = db.collection("SingleCellReAllocation") \
            .where("TransactionID", "==", txn_id) \
            .where("UserID", "==", user_id) \
            .where("Status", "==", "Was Allocated") \
            .limit(1) \
            .stream()

        for doc in reallocation_docs:
            db.collection("SingleCellReAllocation").document(doc.id).update({
                "Status": "Allocated"
            })
            break

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    admin_app.run(debug=True, port=5001)
