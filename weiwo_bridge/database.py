import os
import urllib.parse
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text, event
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

# Configuration
# Postgres setup from env vars
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres123!@#")
DB_NAME = os.getenv("DB_NAME", "weknora")

encoded_password = urllib.parse.quote_plus(DB_PASSWORD)
DATABASE_URL = f"postgresql://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

Base = declarative_base()

class DocumentStatus(Base):
    __tablename__ = 'document_status_table'

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String, nullable=False, index=True, comment='文件名')  # 文件名
    filepath = Column(String, nullable=False, unique=True, index=True, comment='物理路径')  # 物理路径
    file_status = Column(String, default='discover', index=True)
    created_at = Column(DateTime, index=True)
    last_modified_time = Column(Float, index=True)
    process_at = Column(DateTime)
    finish_at = Column(DateTime)
    failed_msg = Column(Text)
    file_size = Column(Integer)
    file_hash = Column(String, index=True)
    file_store_path = Column(String)
    knowledge_id = Column(String, index=True)
    database_name = Column(String, comment='智邦数据库库名',index=True) # 智邦数据库来源

    # New fields
    contract_title = Column(String, comment='合同标题', index=True)  # 合同标题
    contract_ord = Column(Integer, comment='合同序号', index=True)    # 合同序号
    zb_link = Column(Integer, comment='智邦系统链接',index=True)     # 智邦系统链接

class ScriptProcessRecord(Base):
    __tablename__ = 'script_process_record'

    id = Column(Integer, primary_key=True, autoincrement=True)
    script_name = Column(String)
    process_duration = Column(Float)
    process_count = Column(Integer)
    insert_count = Column(Integer)
    update_count = Column(Integer)
    delete_count = Column(Integer)
    process_timestamp = Column(DateTime)
    status = Column(String)
    failed_reason = Column(Text)

def get_engine():
    engine = create_engine(DATABASE_URL)
    return engine

def init_db():
    """Initialize database tables if they don't exist."""
    engine = get_engine()
    Base.metadata.create_all(engine)

def get_session():
    """Create a new database session."""
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()
