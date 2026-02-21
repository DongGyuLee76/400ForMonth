from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import functools
import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')
if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY not set in .env file")
DB_NAME = "financial_plan.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER NOT NULL UNIQUE,
            age INTEGER NOT NULL,
            pension_savings INTEGER DEFAULT 0,
            isa_account INTEGER DEFAULT 0,
            general_account INTEGER DEFAULT 0,
            total INTEGER DEFAULT 0,
            health_insurance TEXT,
            tax TEXT,
            withdrawal_strategy TEXT
        )
    ''')
    # New table for tracking actual inputs/transactions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            pension INTEGER DEFAULT 0,
            isa INTEGER DEFAULT 0,
            general INTEGER DEFAULT 0
        )
    ''')
    
    # User Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    # Create Default Admin if not exists
    admin_username = os.getenv('ADMIN_USERNAME')
    admin_password = os.getenv('ADMIN_PASSWORD')
    
    if not admin_username or not admin_password:
        # Fallback if .env is missing or variables are not defined
        # This prevents errors during startup but reminds the user
        print("Warning: ADMIN_USERNAME or ADMIN_PASSWORD not set in .env")
        return 
    
    admin = cursor.execute('SELECT * FROM users WHERE username = ?', (admin_username,)).fetchone()
    if not admin:
        hashed_pw = generate_password_hash(admin_password)
        cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (admin_username, hashed_pw))
        
    conn.commit()
    conn.close()

# Login Required Decorator
def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if session.get('user_id') is None:
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user is None:
            error = 'Incorrect username.'
        elif not check_password_hash(user['password'], password):
            error = 'Incorrect password.'
        else:
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))
            
        flash(error)
        
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Admin Management Routes
@app.route('/admin/users')
@login_required
def admin_users():
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users').fetchall()
    conn.close()
    return render_template('admin_users.html', users=users)

@app.route('/admin/add_user', methods=['POST'])
@login_required
def add_user():
    username = request.form['username']
    password = request.form['password']
    hashed_pw = generate_password_hash(password)
    
    try:
        conn = get_db_connection()
        conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_pw))
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        flash(f"User {username} already exists.")
        
    return redirect(url_for('admin_users'))

@app.route('/admin/delete_user/<int:id>', methods=['POST'])
@login_required
def delete_user(id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (id,)).fetchone()
    if user['username'] == 'admin':
        flash("Cannot delete admin user.")
    else:
        conn.execute('DELETE FROM users WHERE id = ?', (id,))
        conn.commit()
    conn.close()
    return redirect(url_for('admin_users'))

@app.route('/')
@login_required
def index():
    conn = get_db_connection()
    plans = conn.execute('SELECT * FROM plan ORDER BY year ASC').fetchall()
    transactions = conn.execute('SELECT * FROM transactions').fetchall()
    
    # Calculate Summary (Same logic as input_data/manage_data)
    import collections
    yearly_inputs = collections.defaultdict(lambda: {'pension': 0, 'isa': 0, 'general': 0})
    for t in transactions:
        y = t['date'][:4]
        yearly_inputs[y]['pension'] += t['pension']
        yearly_inputs[y]['isa'] += t['isa']
        yearly_inputs[y]['general'] += t['general']

    summary = []
    plans_map = {str(row['year']): row for row in plans}
    
    running_p = START_PENSION
    running_i = START_ISA
    running_g = START_GENERAL
    
    # Determine years range
    min_year = 2026
    max_year = 2026
    if plans:
        max_year = max(max_year, plans[-1]['year'])
    if yearly_inputs:
        max_year = max(max_year, int(max(yearly_inputs.keys())))

    for year_num in range(min_year, max_year + 1):
        y = str(year_num)
        inputs = yearly_inputs.get(y, {'pension': 0, 'isa': 0, 'general': 0})
        
        running_p += inputs['pension']
        running_i += inputs['isa']
        running_g += inputs['general']
        total = running_p + running_i + running_g
        
        goal = plans_map.get(y)
        goal_total = goal['total'] if goal else 0
        
        gap_pct = 0
        if goal_total > 0:
            gap_pct = round((1 + (total - goal_total) / goal_total) * 100, 1)
            
        summary.append({
            'year': int(y),
            'total': total,
            'goal_total': goal_total,
            'gap_pct': gap_pct,
            'gap_total': total - goal_total,
            'pension': running_p,
            'isa': running_i,
            'general': running_g
        })

    # Get Current Year Data (2026)
    current_year_stat = next((s for s in summary if s['year'] == 2026), None)
    
    # Projection Logic: Selected Year + 3
    selected_year = request.args.get('proj_year', 2026, type=int)
    projection_data = [s for s in summary if selected_year <= s['year'] <= selected_year + 3]

    conn.close()
    return render_template('dashboard.html', 
                           plans=plans, 
                           summary=summary, 
                           current_stat=current_year_stat,
                           projection=projection_data,
                           selected_year=selected_year)

from datetime import datetime

# Start values defined by user
START_PENSION = 7000
START_ISA = 0
START_GENERAL = 20000

@app.route('/input', methods=['GET', 'POST'])
@login_required
def input_data():
    conn = get_db_connection()
    if request.method == 'POST':
        # If adding a new transaction
        date = request.form.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        def clean_currency(val):
            if not val: return 0
            return int(float(str(val).replace(',', '').strip() or 0))

        pension = clean_currency(request.form.get('pension'))
        isa = clean_currency(request.form.get('isa'))
        general = clean_currency(request.form.get('general'))

        conn.execute('INSERT INTO transactions (date, pension, isa, general) VALUES (?, ?, ?, ?)',
                     (date, pension, isa, general))
        conn.commit()
        return redirect(url_for('input_data'))
    
    # Fetch transactions
    transactions = conn.execute('SELECT * FROM transactions ORDER BY date DESC').fetchall()
    
    # Calculate yearly totals (Cumulative)
    import collections
    yearly_inputs = collections.defaultdict(lambda: {'pension': 0, 'isa': 0, 'general': 0})
    
    for t in transactions:
        y = t['date'][:4] # YYYY-MM-DD -> YYYY
        yearly_inputs[y]['pension'] += t['pension']
        yearly_inputs[y]['isa'] += t['isa']
        yearly_inputs[y]['general'] += t['general']
    
    summary = []
    
    # Pre-fetch plans for comparison (Goal)
    plans_rows = conn.execute('SELECT * FROM plan ORDER BY year ASC').fetchall()
    plans_map = {str(row['year']): row for row in plans_rows}
    
    # Determine range of years to display
    min_year = 2026
    max_year = 2026
    if plans_rows:
        max_year = max(max_year, plans_rows[-1]['year'])
    if yearly_inputs:
        max_year = max(max_year, int(max(yearly_inputs.keys())))
        
    # Running totals
    running_p = START_PENSION
    running_i = START_ISA
    running_g = START_GENERAL
    
    for year_num in range(min_year, max_year + 1):
        y = str(year_num)
        
        inputs = yearly_inputs.get(y, {'pension': 0, 'isa': 0, 'general': 0})
        
        # Add this year's inputs to the running total
        running_p += inputs['pension']
        running_i += inputs['isa']
        running_g += inputs['general']
        
        total = running_p + running_i + running_g
        
        # Get Goal
        goal = plans_map.get(y)
        goal_total = goal['total'] if goal else 0
        
        # Achievement (Gap %: (Goal - Actual) / Goal * 100)
        # GAP Calculation: 1 + (Actual - Target) / Target (Achievement Rate)
        gap_pct = 0
        if goal_total > 0:
            gap_pct = round((1 + (total - goal_total) / goal_total) * 100, 1)
        
        summary.append({
            'year': y,
            'pension': running_p,
            'isa': running_i,
            'general': running_g,
            'total': total,
            'input_p': inputs['pension'],
            'input_i': inputs['isa'],
            'input_g': inputs['general'],
            'goal_total': goal_total,
            'gap_pct': gap_pct
        })

    conn.close()
    return render_template('input.html', transactions=transactions, summary=summary)

@app.route('/delete_transaction/<int:id>', methods=['POST'])
@login_required
def delete_transaction(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM transactions WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('input_data'))

@app.route('/update_transaction/<int:id>', methods=['POST'])
@login_required
def update_transaction(id):
    conn = get_db_connection()
    date = request.form['date']
    
    def clean_currency(val):
        if not val: return 0
        return int(float(str(val).replace(',', '').strip() or 0))

    pension = clean_currency(request.form.get('pension'))
    isa = clean_currency(request.form.get('isa'))
    general = clean_currency(request.form.get('general'))
    
    conn.execute('''
        UPDATE transactions 
        SET date = ?, pension = ?, isa = ?, general = ?
        WHERE id = ?
    ''', (date, pension, isa, general, id))
    conn.commit()
    conn.close()
    return redirect(url_for('input_data'))

@app.route('/manage')
@login_required
def manage_data():
    conn = get_db_connection()
    import collections
    
    # 1. Goal Data
    plans = conn.execute('SELECT * FROM plan ORDER BY year ASC').fetchall()
    
    # 2. Actual Data (Cumulative)
    transactions = conn.execute('SELECT * FROM transactions').fetchall()
    
    yearly_inputs = collections.defaultdict(lambda: {'pension': 0, 'isa': 0, 'general': 0})
    for t in transactions:
        y = t['date'][:4]
        yearly_inputs[y]['pension'] += t['pension']
        yearly_inputs[y]['isa'] += t['isa']
        yearly_inputs[y]['general'] += t['general']

    actuals = []
    
    # Determine range
    min_year = 2026
    max_year = 2026
    if plans:
        max_year = max(max_year, plans[-1]['year'])
    if yearly_inputs:
        max_year = max(max_year, int(max(yearly_inputs.keys())))

    running_p = START_PENSION
    running_i = START_ISA
    running_g = START_GENERAL
    
    achievements = []

    for year_num in range(min_year, max_year + 1):
        y = str(year_num)
        inputs = yearly_inputs.get(y, {'pension': 0, 'isa': 0, 'general': 0})
        
        running_p += inputs['pension']
        running_i += inputs['isa']
        running_g += inputs['general']
        total = running_p + running_i + running_g
        
        # Find plan for this year
        plan_row = next((p for p in plans if p['year'] == int(y)), None)
        goal_total = plan_row['total'] if plan_row else 0
        
        # Prepare Actuals Row (Include Plan details for Goal Actions)
        actuals.append({
            'year': int(y),
            'pension': running_p,
            'isa': running_i,
            'general': running_g,
            'total': total,
            'plan': plan_row  # Attach plan for Edit/Delete actions
        })
        
        # Prepare Achievement Row
        gap_pct = 0.0
        # GAP Calculation: 1 + (Actual - Target) / Target
        gap_pct = 0.0
        if goal_total > 0:
            gap_pct = (1 + (total - goal_total) / goal_total) * 100
            
        achievements.append({
            'year': int(y),
            'goal': goal_total,
            'actual': total,
            'gap_pct': gap_pct,
            'plan': plan_row  # Attach plan for Edit/Delete actions
        })
        
    conn.close()
    
    # 3. Render
    return render_template('manage.html', plans=plans, actuals=actuals, achievements=achievements)

@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_data(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM plan WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('manage_data'))

@app.route('/update/<int:id>', methods=['POST'])
@login_required
def update_data(id):
    year = request.form.get('year')
    age = request.form.get('age')

    def clean_currency(val):
        if not val: return 0
        return int(float(str(val).replace(',', '').strip() or 0))

    pension_savings = clean_currency(request.form.get('pension_savings'))
    isa_account = clean_currency(request.form.get('isa_account'))
    general_account = clean_currency(request.form.get('general_account'))
    
    total = pension_savings + isa_account + general_account
    
    health_insurance = request.form.get('health_insurance')
    tax = request.form.get('tax')
    withdrawal_strategy = request.form.get('withdrawal_strategy')

    conn = get_db_connection()
    conn.execute('''
        UPDATE plan SET 
        year = ?, age = ?, pension_savings = ?, isa_account = ?, general_account = ?, 
        total = ?, health_insurance = ?, tax = ?, withdrawal_strategy = ?
        WHERE id = ?
    ''', (year, age, pension_savings, isa_account, general_account, total, health_insurance, tax, withdrawal_strategy, id))
    conn.commit()
    conn.close()
    return redirect(url_for('manage_data'))


@app.route('/api/chart-data')
def chart_data():
    conn = get_db_connection()
    plans = conn.execute('SELECT year, pension_savings, isa_account, general_account, total FROM plan ORDER BY year ASC').fetchall()
    conn.close()
    
    data = {
        'labels': [row['year'] for row in plans],
        'pension': [row['pension_savings'] for row in plans],
        'isa': [row['isa_account'] for row in plans],
        'general': [row['general_account'] for row in plans],
        'total': [row['total'] for row in plans]
    }
    return jsonify(data)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
