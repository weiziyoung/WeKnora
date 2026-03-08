package erp

import (
	"net/http"
	"strconv"

	"github.com/Tencent/WeKnora/internal/logger"
	"github.com/Tencent/WeKnora/internal/models/erp"
	"github.com/Tencent/WeKnora/internal/types/interfaces"
	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

type Handler struct {
	db        *gorm.DB
	kgService interfaces.KnowledgeService
}

func NewHandler(db *gorm.DB, kgService interfaces.KnowledgeService) *Handler {
	return &Handler{
		db:        db,
		kgService: kgService,
	}
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

type BatchOperationRequest struct {
	Reason string `json:"reason" binding:"required"`
}

// BatchRetryFailures retries failed documents by reason
func (h *Handler) BatchRetryFailures(c *gin.Context) {
	ctx := c.Request.Context()
	var req BatchOperationRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	logger.Infof(ctx, "Starting batch retry for failure reason: %s", req.Reason)

	// Find all failures with this reason
	var docs []erp.DocumentStatus
	if err := h.db.Model(&erp.DocumentStatus{}).
		Where("file_status = ? AND failed_msg = ?", "failed", req.Reason).
		Find(&docs).Error; err != nil {
		logger.Errorf(ctx, "Failed to query failed documents: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	successCount := 0
	failCount := 0

	successIDs := make([]int, 0)
	for _, doc := range docs {
		if doc.KnowledgeID == "" {
			logger.Warnf(ctx, "Skipping document with empty KnowledgeID: %s", doc.Filename)
			continue
		}

		// Call ReparseKnowledge
		if _, err := h.kgService.ReparseKnowledge(ctx, doc.KnowledgeID); err != nil {
			logger.Errorf(ctx, "Failed to reparse knowledge %s: %v", doc.KnowledgeID, err)
			failCount++
		} else {
			successCount++
			successIDs = append(successIDs, doc.ID)
		}
	}

	if len(successIDs) > 0 {
		if err := h.db.Model(&erp.DocumentStatus{}).
			Where("id IN ?", successIDs).
			Updates(map[string]interface{}{
				"file_status": "pending",
				"failed_msg":  "",
			}).Error; err != nil {
			logger.Errorf(ctx, "Failed to update document status to pending: %v", err)
		}
	}

	logger.Infof(ctx, "Batch retry completed. Success: %d, Failed: %d", successCount, failCount)
	c.JSON(http.StatusOK, gin.H{
		"success":       true,
		"total":         len(docs),
		"success_count": successCount,
		"fail_count":    failCount,
	})
}

// BatchDeleteFailures deletes failed documents by reason
func (h *Handler) BatchDeleteFailures(c *gin.Context) {
	ctx := c.Request.Context()
	var req BatchOperationRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	logger.Infof(ctx, "Starting batch delete for failure reason: %s", req.Reason)

	// Find all failures with this reason
	var docs []erp.DocumentStatus
	if err := h.db.Model(&erp.DocumentStatus{}).
		Where("file_status = ? AND failed_msg = ?", "failed", req.Reason).
		Find(&docs).Error; err != nil {
		logger.Errorf(ctx, "Failed to query failed documents: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	successCount := 0
	failCount := 0

	// Collect IDs for batch deletion
	knowledgeIDs := make([]string, 0)
	docIDs := make([]int, 0)

	for _, doc := range docs {
		if doc.KnowledgeID != "" {
			knowledgeIDs = append(knowledgeIDs, doc.KnowledgeID)
		}
		docIDs = append(docIDs, doc.ID)
	}

	// Batch delete knowledge entries if any
	if len(knowledgeIDs) > 0 {
		if err := h.kgService.DeleteKnowledgeList(ctx, knowledgeIDs); err != nil {
			logger.Errorf(ctx, "Failed to batch delete knowledge list: %v", err)
			// Fallback to individual delete if batch fails? Or just report error.
			// Let's assume batch failure means all failed.
			failCount = len(knowledgeIDs)
		} else {
			successCount = len(knowledgeIDs)
		}
	}

	// Also update or delete DocumentStatus records?
	// The user asked for "Batch Delete", which implies removing them from the failure list.
	// So we should either delete them or mark them as deleted.
	// Let's mark them as 'deleted' to keep history, or delete them if they are clutter.
	// Given the table is `document_status_table`, deleting rows might be cleaner if they are truly gone.
	// But let's check `statusMap` in frontend: 'deleted': '已删除'.
	// So updating status to 'deleted' seems appropriate.
	if len(docIDs) > 0 {
		if err := h.db.Model(&erp.DocumentStatus{}).
			Where("id IN ?", docIDs).
			Updates(map[string]interface{}{
				"file_status": "deleted",
				"failed_msg":  "", // Clear failure message so it doesn't show up in stats
			}).Error; err != nil {
			logger.Errorf(ctx, "Failed to update document status to deleted: %v", err)
			// Even if knowledge deletion succeeded, this failing is an issue for the UI.
		}
	}

	logger.Infof(ctx, "Batch delete completed. Processed: %d", len(docs))
	c.JSON(http.StatusOK, gin.H{
		"success":       true,
		"total":         len(docs),
		"success_count": successCount,
		"fail_count":    failCount,
	})
}
