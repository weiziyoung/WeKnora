from flask import Flask, render_template, request
import os
from sqlalchemy import func, desc
from database import get_session, DocumentStatus, ScriptProcessRecord, DB_PATH

app = Flask(__name__)

@app.route('/')
def dashboard():
    session = get_session()
    try:
        # Stats
        # cursor.execute("SELECT file_status, COUNT(*) as count FROM document_status_table GROUP BY file_status")
        rows = session.query(
            DocumentStatus.file_status, 
            func.count(DocumentStatus.id).label('count')
        ).group_by(DocumentStatus.file_status).all()
        
        stats = {
            'total': 0, 'discover': 0, 'pending': 0, 'processing': 0, 'completed': 0, 'failed': 0, 'deleted': 0
        }
        for status, count in rows:
            if status in stats:
                stats[status] = count
            stats['total'] += count
            
        # Recent Failures
        # cursor.execute("SELECT filename, failed_msg, process_at FROM document_status_table WHERE file_status='failed' ORDER BY process_at DESC LIMIT 5")
        recent_fails = session.query(DocumentStatus).filter(
            DocumentStatus.file_status == 'failed'
        ).order_by(desc(DocumentStatus.process_at)).limit(5).all()
        
        # Recent Runs
        # cursor.execute("SELECT script_name, process_timestamp, status, process_count FROM script_process_record ORDER BY process_timestamp DESC LIMIT 5")
        recent_runs = session.query(ScriptProcessRecord).order_by(
            desc(ScriptProcessRecord.process_timestamp)
        ).limit(5).all()
        
        return render_template('dashboard.html', page='dashboard', stats=stats, recent_fails=recent_fails, recent_runs=recent_runs)
    finally:
        session.close()

@app.route('/documents')
def documents():
    status = request.args.get('status', '')
    page = int(request.args.get('page', 1))
    per_page = 20
    offset = (page - 1) * per_page
    
    session = get_session()
    try:
        query = session.query(DocumentStatus)
        
        if status:
            query = query.filter(DocumentStatus.file_status == status)
        
        # Total count for pagination
        total_count = query.count()
        
        # Fetch documents
        docs = query.order_by(desc(DocumentStatus.id)).limit(per_page).offset(offset).all()
        
        has_next = (offset + per_page) < total_count
        
        return render_template('documents.html', page='documents', documents=docs, current_status=status, page_num=page, has_next=has_next)
    finally:
        session.close()

@app.route('/logs')
def logs():
    session = get_session()
    try:
        # cursor.execute("SELECT * FROM script_process_record ORDER BY id DESC LIMIT 50")
        logs = session.query(ScriptProcessRecord).order_by(desc(ScriptProcessRecord.id)).limit(50).all()
        return render_template('logs.html', page='logs', logs=logs)
    finally:
        session.close()

if __name__ == '__main__':
    # Initialize DB if not exists (using discover_files logic or just let it fail if no DB)
    if not os.path.exists(DB_PATH):
        print(f"Warning: Database {DB_PATH} not found. Run discover_files.py first.")
    
    print("Starting Admin Server at http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
