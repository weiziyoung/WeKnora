package erp

import (
	"log"
	"net/http"
	"os"
	"strconv"

	"github.com/Tencent/WeKnora/internal/models/erp"
	"github.com/gin-gonic/gin"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
)

var db *gorm.DB

func initDB() {
	// Attempt to find the database file
	// It might be in ./weiwo_bridge/weknora_bridge.db if running from project root
	// or ../weiwo_bridge/weknora_bridge.db if running from bin

	paths := []string{
		"./weiwo_bridge/weknora_bridge.db",
		"../weiwo_bridge/weknora_bridge.db",
		"/Users/young/Documents/codehub/WeiWo/WeKnora/weiwo_bridge/weknora_bridge.db", // Fallback to absolute path
	}

	var dbPath string
	for _, p := range paths {
		if _, err := os.Stat(p); err == nil {
			dbPath = p
			break
		}
	}

	if dbPath == "" {
		log.Println("Warning: weknora_bridge.db not found in common locations")
		return
	}

	var err error
	db, err = gorm.Open(sqlite.Open(dbPath), &gorm.Config{})
	if err != nil {
		log.Printf("Failed to connect to SQLite database at %s: %v", dbPath, err)
	} else {
		log.Printf("Connected to SQLite database at %s", dbPath)
	}
}

// Ensure DB is initialized
func getDB() *gorm.DB {
	if db == nil {
		initDB()
	}
	return db
}

// StatsResponse defines the structure for dashboard statistics
type StatsResponse struct {
	Stats       map[string]int64          `json:"stats"`
	RecentFails []erp.DocumentStatus      `json:"recent_fails"`
	RecentRuns  []erp.ScriptProcessRecord `json:"recent_runs"`
}

// GetStats returns dashboard statistics
func GetStats(c *gin.Context) {
	db := getDB()
	if db == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Database connection not available"})
		return
	}

	// Stats
	var results []struct {
		FileStatus string
		Count      int64
	}
	// GORM group by query
	if err := db.Model(&erp.DocumentStatus{}).Select("file_status, count(id) as count").Group("file_status").Scan(&results).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	stats := map[string]int64{
		"total":      0,
		"discover":   0,
		"pending":    0,
		"processing": 0,
		"completed":  0,
		"failed":     0,
		"deleted":    0,
	}

	for _, r := range results {
		stats[r.FileStatus] = r.Count
		stats["total"] += r.Count
	}

	// Recent Failures
	var recentFails []erp.DocumentStatus
	if err := db.Model(&erp.DocumentStatus{}).Where("file_status = ?", "failed").Order("process_at desc").Limit(5).Find(&recentFails).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Recent Runs
	var recentRuns []erp.ScriptProcessRecord
	if err := db.Model(&erp.ScriptProcessRecord{}).Order("process_timestamp desc").Limit(5).Find(&recentRuns).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, StatsResponse{
		Stats:       stats,
		RecentFails: recentFails,
		RecentRuns:  recentRuns,
	})
}

// DocumentsResponse defines the structure for document list response
type DocumentsResponse struct {
	Documents []erp.DocumentStatus `json:"documents"`
	Total     int64                `json:"total"`
	Page      int                  `json:"page"`
	PerPage   int                  `json:"per_page"`
}

// GetDocuments returns paginated document list
func GetDocuments(c *gin.Context) {
	db := getDB()
	if db == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Database connection not available"})
		return
	}

	status := c.Query("status")
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	perPage, _ := strconv.Atoi(c.DefaultQuery("per_page", "20"))
	if page < 1 {
		page = 1
	}
	if perPage < 1 {
		perPage = 20
	}

	offset := (page - 1) * perPage

	query := db.Model(&erp.DocumentStatus{})
	if status != "" {
		query = query.Where("file_status = ?", status)
	}

	var total int64
	if err := query.Count(&total).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	var docs []erp.DocumentStatus
	if err := query.Order("id desc").Limit(perPage).Offset(offset).Find(&docs).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, DocumentsResponse{
		Documents: docs,
		Total:     total,
		Page:      page,
		PerPage:   perPage,
	})
}

// LogsResponse defines the structure for logs response
type LogsResponse struct {
	Logs []erp.ScriptProcessRecord `json:"logs"`
}

// GetLogs returns recent script logs
func GetLogs(c *gin.Context) {
	db := getDB()
	if db == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Database connection not available"})
		return
	}

	var logs []erp.ScriptProcessRecord
	if err := db.Model(&erp.ScriptProcessRecord{}).Order("id desc").Limit(50).Find(&logs).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, LogsResponse{
		Logs: logs,
	})
}
