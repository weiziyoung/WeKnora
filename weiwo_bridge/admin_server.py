from flask import Flask, render_template, request
import sqlite3
import os

app = Flask(__name__)
DB_PATH = 'weknora_bridge.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Stats
    cursor.execute("SELECT file_status, COUNT(*) as count FROM document_status_table GROUP BY file_status")
    rows = cursor.fetchall()
    stats = {
        'total': 0, 'discover': 0, 'pending': 0, 'processing': 0, 'completed': 0, 'failed': 0, 'deleted': 0
    }
    for row in rows:
        status = row['file_status']
        count = row['count']
        stats[status] = count
        stats['total'] += count
        
    # Recent Failures
    cursor.execute("SELECT filename, failed_msg, process_at FROM document_status_table WHERE file_status='failed' ORDER BY process_at DESC LIMIT 5")
    recent_fails = cursor.fetchall()
    
    # Recent Runs
    cursor.execute("SELECT script_name, process_timestamp, status, process_count FROM script_process_record ORDER BY process_timestamp DESC LIMIT 5")
    recent_runs = cursor.fetchall()
    
    conn.close()
    return render_template('dashboard.html', page='dashboard', stats=stats, recent_fails=recent_fails, recent_runs=recent_runs)

@app.route('/documents')
def documents():
    status = request.args.get('status', '')
    page = int(request.args.get('page', 1))
    per_page = 20
    offset = (page - 1) * per_page
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM document_status_table"
    params = []
    if status:
        query += " WHERE file_status = ?"
        params.append(status)
    
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    
    cursor.execute(query, params)
    docs = cursor.fetchall()
    
    # Check if has next page
    cursor.execute(f"SELECT COUNT(*) FROM document_status_table {'WHERE file_status = ?' if status else ''}", [status] if status else [])
    total_count = cursor.fetchone()[0]
    has_next = (offset + per_page) < total_count
    
    conn.close()
    return render_template('documents.html', page='documents', documents=docs, current_status=status, page_num=page, has_next=has_next)

@app.route('/logs')
def logs():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM script_process_record ORDER BY id DESC LIMIT 50")
    logs = cursor.fetchall()
    conn.close()
    return render_template('logs.html', page='logs', logs=logs)

if __name__ == '__main__':
    # Initialize DB if not exists (using discover_files logic or just let it fail if no DB)
    if not os.path.exists(DB_PATH):
        print(f"Warning: Database {DB_PATH} not found. Run discover_files.py first.")
    
    print("Starting Admin Server at http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
