from flask import Flask, request, jsonify
import os
from sqlalchemy import func, desc
from database import get_session, DocumentStatus, ScriptProcessRecord, DB_PATH
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route('/api/stats')
def api_stats():
    session = get_session()
    try:
        # Stats
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
        recent_fails_query = session.query(DocumentStatus).filter(
            DocumentStatus.file_status == 'failed'
        ).order_by(desc(DocumentStatus.process_at)).limit(5).all()
        
        recent_fails = []
        for f in recent_fails_query:
            recent_fails.append({
                'filename': f.filename,
                'failed_msg': f.failed_msg,
                'process_at': f.process_at.isoformat() if f.process_at else None
            })

        # Recent Runs
        recent_runs_query = session.query(ScriptProcessRecord).order_by(
            desc(ScriptProcessRecord.process_timestamp)
        ).limit(5).all()
        
        recent_runs = []
        for r in recent_runs_query:
            recent_runs.append({
                'script_name': r.script_name,
                'process_timestamp': r.process_timestamp.isoformat() if r.process_timestamp else None,
                'status': r.status,
                'process_count': r.process_count
            })
            
        return jsonify({
            'stats': stats,
            'recent_fails': recent_fails,
            'recent_runs': recent_runs
        })
    finally:
        session.close()

@app.route('/api/documents')
def api_documents():
    status = request.args.get('status', '')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    offset = (page - 1) * per_page
    
    session = get_session()
    try:
        query = session.query(DocumentStatus)
        
        if status:
            query = query.filter(DocumentStatus.file_status == status)
        
        # Total count for pagination
        total_count = query.count()
        
        # Fetch documents
        docs_query = query.order_by(desc(DocumentStatus.id)).limit(per_page).offset(offset).all()
        
        docs = []
        for d in docs_query:
            docs.append({
                'id': d.id,
                'filename': d.filename,
                'file_status': d.file_status,
                'process_at': d.process_at.isoformat() if d.process_at else None,
                'failed_msg': d.failed_msg,
                'file_hash': d.file_hash
            })
        
        return jsonify({
            'documents': docs,
            'total': total_count,
            'page': page,
            'per_page': per_page
        })
    finally:
        session.close()

@app.route('/api/logs')
def api_logs():
    session = get_session()
    try:
        logs_query = session.query(ScriptProcessRecord).order_by(desc(ScriptProcessRecord.id)).limit(50).all()
        
        logs = []
        for l in logs_query:
            logs.append({
                'id': l.id,
                'script_name': l.script_name,
                'process_timestamp': l.process_timestamp.isoformat() if l.process_timestamp else None,
                'status': l.status,
                'process_count': l.process_count,
                'message': l.message
            })
            
        return jsonify({
            'logs': logs
        })
    finally:
        session.close()

if __name__ == '__main__':
    # Initialize DB if not exists (using discover_files logic or just let it fail if no DB)
    if not os.path.exists(DB_PATH):
        print(f"Warning: Database {DB_PATH} not found. Run discover_files.py first.")
    
    print("Starting Admin Server at http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
