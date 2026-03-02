package erp

import (
	"net/http"
	"strconv"

	"github.com/Tencent/WeKnora/internal/models/erp"
	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

type Handler struct {
	db *gorm.DB
}

func NewHandler(db *gorm.DB) *Handler {
	return &Handler{db: db}
}

// StatsResponse defines the structure for dashboard statistics
type StatsResponse struct {
	Stats       map[string]int64          `json:"stats"`
	RecentFails []erp.DocumentStatus      `json:"recent_fails"`
	RecentRuns  []erp.ScriptProcessRecord `json:"recent_runs"`
}

// GetStats returns dashboard statistics
func (h *Handler) GetStats(c *gin.Context) {
	// Stats
	var results []struct {
		FileStatus string
		Count      int64
	}
	// GORM group by query
	if err := h.db.Model(&erp.DocumentStatus{}).Select("file_status, count(id) as count").Group("file_status").Scan(&results).Error; err != nil {
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
	if err := h.db.Model(&erp.DocumentStatus{}).Where("file_status = ?", "failed").Order("process_at desc").Limit(5).Find(&recentFails).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Recent Runs
	var recentRuns []erp.ScriptProcessRecord
	if err := h.db.Model(&erp.ScriptProcessRecord{}).Order("process_timestamp desc").Limit(5).Find(&recentRuns).Error; err != nil {
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
func (h *Handler) GetDocuments(c *gin.Context) {
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

	query := h.db.Model(&erp.DocumentStatus{})
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
	Logs    []erp.ScriptProcessRecord `json:"logs"`
	Total   int64                     `json:"total"`
	Page    int                       `json:"page"`
	PerPage int                       `json:"per_page"`
}

// GetLogs returns recent script logs
func (h *Handler) GetLogs(c *gin.Context) {
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	perPage, _ := strconv.Atoi(c.DefaultQuery("per_page", "20"))
	if page < 1 {
		page = 1
	}
	if perPage < 1 {
		perPage = 20
	}

	offset := (page - 1) * perPage

	var total int64
	if err := h.db.Model(&erp.ScriptProcessRecord{}).Count(&total).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	var logs []erp.ScriptProcessRecord
	if err := h.db.Model(&erp.ScriptProcessRecord{}).Order("id desc").Limit(perPage).Offset(offset).Find(&logs).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, LogsResponse{
		Logs:    logs,
		Total:   total,
		Page:    page,
		PerPage: perPage,
	})
}

// FailureStatsResponse defines the structure for failure statistics
type FailureStatsResponse struct {
	Stats []FailureStat `json:"stats"`
}

type FailureStat struct {
	Reason string `json:"reason"`
	Count  int64  `json:"count"`
}

// GetFailureStats returns aggregated failure statistics
func (h *Handler) GetFailureStats(c *gin.Context) {
	var results []struct {
		FailedMsg string
		Count     int64
	}

	// Filter by failed status and group by failed_msg
	if err := h.db.Model(&erp.DocumentStatus{}).
		Where("file_status = ?", "failed").
		Select("failed_msg, count(id) as count").
		Group("failed_msg").
		Order("count desc").
		Scan(&results).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	stats := make([]FailureStat, len(results))
	for i, r := range results {
		stats[i] = FailureStat{
			Reason: r.FailedMsg,
			Count:  r.Count,
		}
	}

	c.JSON(http.StatusOK, FailureStatsResponse{
		Stats: stats,
	})
}
