package erp

import (
	"time"
)

// DocumentStatus 对应 document_status_table 表
type DocumentStatus struct {
	ID               int        `gorm:"primaryKey;autoIncrement" json:"id"`
	Filename         string     `gorm:"column:filename;not null;index" json:"filename"`
	Filepath         string     `gorm:"column:filepath;not null;unique;index" json:"filepath"`
	FileStatus       string     `gorm:"column:file_status;default:discover;index" json:"file_status"`
	CreatedAt        time.Time  `gorm:"column:created_at;index" json:"created_at"`
	LastModifiedTime float64    `gorm:"column:last_modified_time;index" json:"last_modified_time"`
	ProcessAt        *time.Time `gorm:"column:process_at" json:"process_at"`
	FinishAt         *time.Time `gorm:"column:finish_at" json:"finish_at"`
	FailedMsg        string     `gorm:"column:failed_msg" json:"failed_msg"`
	FileSize         int        `gorm:"column:file_size" json:"file_size"`
	FileHash         string     `gorm:"column:file_hash;index" json:"file_hash"`
	FileStorePath    string     `gorm:"column:file_store_path" json:"file_store_path"`
	KnowledgeID      string     `gorm:"column:knowledge_id;index" json:"knowledge_id"`
	DatabaseName     string     `gorm:"column:database_name;index" json:"database_name"`
	ContractTitle    string     `gorm:"column:contract_title;index" json:"contract_title"`
	ContractOrd      int        `gorm:"column:contract_ord;index" json:"contract_ord"`
	ZbLink           int        `gorm:"column:zb_link;index" json:"zb_link"`
}

// TableName 指定表名
func (DocumentStatus) TableName() string {
	return "document_status_table"
}

// ScriptProcessRecord 对应 script_process_record 表
type ScriptProcessRecord struct {
	ID               int        `gorm:"primaryKey;autoIncrement" json:"id"`
	ScriptName       string     `gorm:"column:script_name" json:"script_name"`
	ProcessDuration  float64    `gorm:"column:process_duration" json:"process_duration"`
	ProcessCount     int        `gorm:"column:process_count" json:"process_count"`
	InsertCount      int        `gorm:"column:insert_count" json:"insert_count"`
	UpdateCount      int        `gorm:"column:update_count" json:"update_count"`
	DeleteCount      int        `gorm:"column:delete_count" json:"delete_count"`
	ProcessTimestamp *time.Time `gorm:"column:process_timestamp" json:"process_timestamp"`
	Status           string     `gorm:"column:status" json:"status"`
	FailedReason     string     `gorm:"column:failed_reason" json:"failed_reason"`
}

// TableName 指定表名
func (ScriptProcessRecord) TableName() string {
	return "script_process_record"
}
