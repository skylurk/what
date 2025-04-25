from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import firebase_admin
from firebase_admin import credentials, firestore, auth as firebase_auth
import hashlib, os
from datetime import datetime
import stripe
import uuid
from dotenv import load_dotenv
load_dotenv()

app = Flask(
    __name__,
    template_folder='templates',
    static_folder='static'
)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# Firebase init
cred = credentials.Certificate(os.path.join(os.path.dirname(__file__), '..', 'serviceAccountKey.json'))
firebase_admin.initialize_app(cred)
db = firestore.client()

TREE_PRICE_EUR = 25

@app.route('/')
def home():
    return render_template(
        'home.html',
        logged_in=('user' in session),
        google_maps_key=os.getenv("GOOGLE_MAPS_API_KEY"),
        w3w_key=os.getenv("W3W_API_KEY")
    )

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.form
        email = data['email']
        password = data['password']
        first = data['first']
        last = data['last']

        try:
            user_record = firebase_auth.create_user(
                email=email,
                password=password,
                display_name=f"{first} {last}"
            )

            salt = os.urandom(16).hex()
            hash_pw = hashlib.sha256((password + salt).encode()).hexdigest()

            user_doc = {
                "First Name": first,
                "Last Name": last,
                "EmailAddress": email,
                "PasswordHash": hash_pw,
                "Salt": salt,
                "Timestamp": datetime.now().strftime("%d/%m/%Y")
            }

            db.collection("Users").document(user_record.uid).set(user_doc)
            flash("Account created successfully. Please log in!", "success")
            return redirect(url_for('login'))

        except Exception as e:
            error_str = str(e)

            if "email-already-exists" in error_str:
                flash("An account with this email already exists.", "error")
            elif "Password should be at least" in error_str:
                flash("Your password is too weak. Please use a stronger password.", "error")
            else:
                flash("An error occurred during registration. Please try again.", "error")

            return render_template('register.html')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.form
        email = data['email']
        password = data['password']

        users = db.collection("Users").where("EmailAddress", "==", email).stream()
        user_found = False

        for user in users:
            user_found = True
            user_data = user.to_dict()
            hashed = hashlib.sha256((password + user_data['Salt']).encode()).hexdigest()
            if hashed == user_data["PasswordHash"]:
                session['user'] = {
                    'email': email,
                    'uid': user.id
                }
                return redirect(url_for('home'))
            else:
                flash("Incorrect password. Please try again.", "error")
                return render_template('login.html')

        if not user_found:
            flash("No account found with that email address.", "error")
            return render_template('login.html')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout():
    if 'user' not in session:
        return jsonify({'error': 'Login required'}), 403

    try:
        num_trees = int(request.form.get('num_trees', 0))  # ✅ Read from form data
        if num_trees < 1 or num_trees > 39999:
            return jsonify({'error': 'Invalid number of trees selected'}), 400

        amount_eur = num_trees * TREE_PRICE_EUR

        session_checkout = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {
                        'name': f'{num_trees} Trees'
                    },
                    'unit_amount': TREE_PRICE_EUR * 100,
                },
                'quantity': num_trees,
            }],
            mode='payment',
            success_url=url_for('payment_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('home', _external=True),
        )
        session['pending_trees'] = num_trees
        return redirect(session_checkout.url)  # ✅ Redirect user instead of sending JSON

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/payment-success', methods=['GET'])
def payment_success():
    if 'user' not in session or 'pending_trees' not in session:
        return redirect(url_for('home'))

    num_trees = session.pop('pending_trees')
    uid = session['user']['uid']
    txn_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime('%d/%m/%Y')
    offset = num_trees * 3.8
    amount = num_trees * TREE_PRICE_EUR

    txn_data = {
        'UserID': uid,
        'TransactionID': txn_id,
        'NumTrees': num_trees,
        'Amount': amount,
        'Currency': 'EUR',
        'OffsetCarbon': offset,
        'Status': 'Awaiting Allocation',
        'Timestamp': timestamp
    }
    db.collection("Transactions").document(txn_id).set(txn_data)

    return render_template('payment_success.html', num_trees=num_trees, offset=offset, amount=amount, currency='EUR')

@app.route("/get-allocated-cells")
def get_allocated_cells():
    try:
        occupied = db.collection("OccupiedCells").stream()
        cells = [
            {
                "What3Words": doc.to_dict().get("What3Words"),
                "lat": doc.to_dict().get("Lat"),
                "lng": doc.to_dict().get("Lng")
            }
            for doc in occupied
        ]
        return jsonify(cells)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get-global-stats')
def get_global_stats():
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
            "totalCO2": round(total_offset, 1)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/user_trees')
def user_trees():
    if 'user' not in session:
        return redirect(url_for('login'))

    uid = session['user']['uid']
    user_doc = db.collection("Users").document(uid).get()

    if not user_doc.exists:
        return "User not found", 404

    user_data = user_doc.to_dict()
    first_name = user_data.get("First Name", "User")
    email = user_data.get("EmailAddress", "Unknown")

    # 🧮 Fetch and calculate stats + transaction table data
    transactions_ref = db.collection("Transactions").where("UserID", "==", uid).stream()
    total_trees = 0
    total_offset = 0.0
    transaction_rows = []

    for doc in transactions_ref:
        data = doc.to_dict()
        num = int(data.get("NumTrees", 0))
        amt = float(data.get("Amount", 0.0))
        status = data.get("Status", "Unknown")
        
        total_trees += num
        total_offset += float(data.get("OffsetCarbon", 0.0))

        transaction_rows.append({
            "trees": num,
            "amount": f"€{amt:.2f}",
            "status": status
        })


    return render_template(
        'user_trees.html',
        GOOGLE_MAPS_API_KEY=os.getenv("GOOGLE_MAPS_API_KEY"),
        w3w_key=os.getenv("W3W_API_KEY"),
        first_name=first_name,
        email=email,
        total_trees=total_trees,
        total_offset=round(total_offset, 1),
        transactions=transaction_rows
    )


@app.route("/get-user-cells")
def get_user_cells():
    if 'user' not in session:
        return jsonify({"error": "Not logged in"}), 403

    try:
        uid = session['user']['uid']
        occupied = db.collection("OccupiedCells").where("UserID", "==", uid).stream()
        cells = [
            {
                "What3Words": doc.to_dict().get("What3Words"),
                "lat": doc.to_dict().get("Lat"),
                "lng": doc.to_dict().get("Lng")
            }
            for doc in occupied
        ]
        return jsonify(cells)
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/termsandconditions')
def terms_and_conditions():
    return render_template('terms.html')

@app.route('/privacypolicy')
def privacy_policy():
    return render_template('privacy.html')

if __name__ == '__main__':
    app.run(debug=True)


