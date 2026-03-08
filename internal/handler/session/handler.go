package session

import (
	"net/http"
	"strconv"

	"github.com/Tencent/WeKnora/internal/config"
	"github.com/Tencent/WeKnora/internal/errors"
	"github.com/Tencent/WeKnora/internal/logger"
	"github.com/Tencent/WeKnora/internal/types"
	"github.com/Tencent/WeKnora/internal/types/interfaces"
	secutils "github.com/Tencent/WeKnora/internal/utils"
	"github.com/gin-gonic/gin"
)

// Handler handles all HTTP requests related to conversation sessions
type Handler struct {
	messageService       interfaces.MessageService       // Service for managing messages
	sessionService       interfaces.SessionService       // Service for managing sessions
	streamManager        interfaces.StreamManager        // Manager for handling streaming responses
	config               *config.Config                  // Application configuration
	knowledgebaseService interfaces.KnowledgeBaseService // Service for managing knowledge bases
	customAgentService   interfaces.CustomAgentService   // Service for managing custom agents
	tenantService        interfaces.TenantService        // Service for loading tenant (shared agent context)
	agentShareService    interfaces.AgentShareService    // Service for resolving shared agents (KB scope in retrieval)
}

// NewHandler creates a new instance of Handler with all necessary dependencies
func NewHandler(
	sessionService interfaces.SessionService,
	messageService interfaces.MessageService,
	streamManager interfaces.StreamManager,
	config *config.Config,
	knowledgebaseService interfaces.KnowledgeBaseService,
	customAgentService interfaces.CustomAgentService,
	tenantService interfaces.TenantService,
	agentShareService interfaces.AgentShareService,
) *Handler {
	return &Handler{
		sessionService:       sessionService,
		messageService:       messageService,
		streamManager:        streamManager,
		config:               config,
		knowledgebaseService: knowledgebaseService,
		customAgentService:   customAgentService,
		tenantService:        tenantService,
		agentShareService:    agentShareService,
	}
}

// CreateSession godoc
// @Summary      创建会话
// @Description  创建新的对话会话
// @Tags         会话
// @Accept       json
// @Produce      json
// @Param        request  body      CreateSessionRequest  true  "会话创建请求"
// @Success      201      {object}  map[string]interface{}  "创建的会话"
// @Failure      400      {object}  errors.AppError         "请求参数错误"
// @Security     Bearer
// @Security     ApiKeyAuth
// @Router       /sessions [post]
func (h *Handler) CreateSession(c *gin.Context) {
	ctx := c.Request.Context()
	// Parse and validate the request body
	var request CreateSessionRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		logger.Error(ctx, "Failed to validate session creation parameters", err)
		c.Error(errors.NewBadRequestError(err.Error()))
		return
	}

	// Get tenant ID from context
	tenantID, exists := c.Get(types.TenantIDContextKey.String())
	if !exists {
		logger.Error(ctx, "Failed to get tenant ID")
		c.Error(errors.NewUnauthorizedError("Unauthorized"))
		return
	}

	// Sessions are now knowledge-base-independent:
	// - All configuration comes from custom agent at query time
	// - Session only stores basic info (tenant ID, title, description)
	logger.Infof(
		ctx,
		"Processing session creation request, tenant ID: %d",
		tenantID,
	)

	// Create session object with base properties
	createdSession := &types.Session{
		TenantID:    tenantID.(uint64),
		Title:       request.Title,
		Description: request.Description,
	}

	// Call service to create session
	logger.Infof(ctx, "Calling session service to create session")
	createdSession, err := h.sessionService.CreateSession(ctx, createdSession)
	if err != nil {
		logger.ErrorWithFields(ctx, err, nil)
		c.Error(errors.NewInternalServerError(err.Error()))
		return
	}

	// Return created session
	logger.Infof(ctx, "Session created successfully, ID: %s", createdSession.ID)
	c.JSON(http.StatusCreated, gin.H{
		"success": true,
		"data":    createdSession,
	})
}

// GetSession godoc
// @Summary      获取会话详情
// @Description  根据ID获取会话详情
// @Tags         会话
// @Accept       json
// @Produce      json
// @Param        id   path      string  true  "会话ID"
// @Success      200  {object}  map[string]interface{}  "会话详情"
// @Failure      404  {object}  errors.AppError         "会话不存在"
// @Security     Bearer
// @Security     ApiKeyAuth
// @Router       /sessions/{id} [get]
func (h *Handler) GetSession(c *gin.Context) {
	ctx := c.Request.Context()

	logger.Info(ctx, "Start retrieving session")

	// Get session ID from URL parameter
	id := secutils.SanitizeForLog(c.Param("id"))
	if id == "" {
		logger.Error(ctx, "Session ID is empty")
		c.Error(errors.NewBadRequestError(errors.ErrInvalidSessionID.Error()))
		return
	}

	// Call service to get session details
	logger.Infof(ctx, "Retrieving session, ID: %s", id)
	session, err := h.sessionService.GetSession(ctx, id)
	if err != nil {
		if err == errors.ErrSessionNotFound {
			logger.Warnf(ctx, "Session not found, ID: %s", id)
			c.Error(errors.NewNotFoundError(err.Error()))
			return
		}
		logger.ErrorWithFields(ctx, err, nil)
		c.Error(errors.NewInternalServerError(err.Error()))
		return
	}

	// Return session data
	logger.Infof(ctx, "Session retrieved successfully, ID: %s", id)
	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"data":    session,
	})
}

// GetSessionsByTenant godoc
// @Summary      获取会话列表
// @Description  获取当前租户的会话列表，支持分页
// @Tags         会话
// @Accept       json
// @Produce      json
// @Param        page       query     int  false  "页码"
// @Param        page_size  query     int  false  "每页数量"
// @Success      200        {object}  map[string]interface{}  "会话列表"
// @Failure      400        {object}  errors.AppError         "请求参数错误"
// @Security     Bearer
// @Security     ApiKeyAuth
// @Router       /sessions [get]
func (h *Handler) GetSessionsByTenant(c *gin.Context) {
	ctx := c.Request.Context()

	// Parse pagination parameters from query
	var pagination types.Pagination
	if err := c.ShouldBindQuery(&pagination); err != nil {
		logger.Error(ctx, "Failed to parse pagination parameters", err)
		c.Error(errors.NewBadRequestError(err.Error()))
		return
	}

	// Use paginated query to get sessions
	result, err := h.sessionService.GetPagedSessionsByTenant(ctx, &pagination)
	if err != nil {
		logger.ErrorWithFields(ctx, err, nil)
		c.Error(errors.NewInternalServerError(err.Error()))
		return
	}

	// Return sessions with pagination data
	c.JSON(http.StatusOK, gin.H{
		"success":   true,
		"data":      result.Data,
		"total":     result.Total,
		"page":      result.Page,
		"page_size": result.PageSize,
	})
}

// UpdateSession godoc
// @Summary      更新会话
// @Description  更新会话属性
// @Tags         会话
// @Accept       json
// @Produce      json
// @Param        id       path      string         true  "会话ID"
// @Param        request  body      types.Session  true  "会话信息"
// @Success      200      {object}  map[string]interface{}  "更新后的会话"
// @Failure      404      {object}  errors.AppError         "会话不存在"
// @Security     Bearer
// @Security     ApiKeyAuth
// @Router       /sessions/{id} [put]
func (h *Handler) UpdateSession(c *gin.Context) {
	ctx := c.Request.Context()

	// Get session ID from URL parameter
	id := secutils.SanitizeForLog(c.Param("id"))
	if id == "" {
		logger.Error(ctx, "Session ID is empty")
		c.Error(errors.NewBadRequestError(errors.ErrInvalidSessionID.Error()))
		return
	}

	// Verify tenant ID from context for authorization
	tenantID, exists := c.Get(types.TenantIDContextKey.String())
	if !exists {
		logger.Error(ctx, "Failed to get tenant ID")
		c.Error(errors.NewUnauthorizedError("Unauthorized"))
		return
	}

	// Parse request body to session object
	var session types.Session
	if err := c.ShouldBindJSON(&session); err != nil {
		logger.Error(ctx, "Failed to parse session data", err)
		c.Error(errors.NewBadRequestError(err.Error()))
		return
	}

	session.ID = id
	session.TenantID = tenantID.(uint64)

	// Call service to update session
	if err := h.sessionService.UpdateSession(ctx, &session); err != nil {
		if err == errors.ErrSessionNotFound {
			logger.Warnf(ctx, "Session not found, ID: %s", id)
			c.Error(errors.NewNotFoundError(err.Error()))
			return
		}
		logger.ErrorWithFields(ctx, err, nil)
		c.Error(errors.NewInternalServerError(err.Error()))
		return
	}

	// Return updated session
	logger.Infof(ctx, "Session updated successfully, ID: %s", id)
	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"data":    session,
	})
}

// DeleteSession godoc
// @Summary      删除会话
// @Description  删除指定的会话
// @Tags         会话
// @Accept       json
// @Produce      json
// @Param        id   path      string  true  "会话ID"
// @Success      200  {object}  map[string]interface{}  "删除成功"
// @Failure      404  {object}  errors.AppError         "会话不存在"
// @Security     Bearer
// @Security     ApiKeyAuth
// @Router       /sessions/{id} [delete]
func (h *Handler) DeleteSession(c *gin.Context) {
	ctx := c.Request.Context()

	// Get session ID from URL parameter
	id := secutils.SanitizeForLog(c.Param("id"))
	if id == "" {
		logger.Error(ctx, "Session ID is empty")
		c.Error(errors.NewBadRequestError(errors.ErrInvalidSessionID.Error()))
		return
	}

	// Call service to delete session
	if err := h.sessionService.DeleteSession(ctx, id); err != nil {
		if err == errors.ErrSessionNotFound {
			logger.Warnf(ctx, "Session not found, ID: %s", id)
			c.Error(errors.NewNotFoundError(err.Error()))
			return
		}
		logger.ErrorWithFields(ctx, err, nil)
		c.Error(errors.NewInternalServerError(err.Error()))
		return
	}

	// Return success message
	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "Session deleted successfully",
	})
}

// batchDeleteRequest represents the request body for batch deleting sessions
type batchDeleteRequest struct {
	IDs []string `json:"ids" binding:"required,min=1"`
}

// BatchDeleteSessions godoc
// @Summary      批量删除会话
// @Description  根据ID列表批量删除对话会话
// @Tags         会话
// @Accept       json
// @Produce      json
// @Param        request  body      batchDeleteRequest  true  "批量删除请求"
// @Success      200      {object}  map[string]interface{}  "删除结果"
// @Failure      400      {object}  errors.AppError         "请求参数错误"
// @Security     Bearer
// @Security     ApiKeyAuth
// @Router       /sessions/batch [delete]
func (h *Handler) BatchDeleteSessions(c *gin.Context) {
	ctx := c.Request.Context()

	var req batchDeleteRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		logger.Errorf(ctx, "Invalid batch delete request: %v", err)
		c.Error(errors.NewBadRequestError("invalid request: ids are required"))
		return
	}

	// Sanitize all IDs
	sanitizedIDs := make([]string, 0, len(req.IDs))
	for _, id := range req.IDs {
		sanitized := secutils.SanitizeForLog(id)
		if sanitized != "" {
			sanitizedIDs = append(sanitizedIDs, sanitized)
		}
	}

	if len(sanitizedIDs) == 0 {
		c.Error(errors.NewBadRequestError("no valid session IDs provided"))
		return
	}

	if err := h.sessionService.BatchDeleteSessions(ctx, sanitizedIDs); err != nil {
		logger.ErrorWithFields(ctx, err, nil)
		c.Error(errors.NewInternalServerError(err.Error()))
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "Sessions deleted successfully",
	})
}

// UpdateFeedback godoc
// @Summary      更新消息反馈
// @Description  更新消息的反馈信息
// @Tags         消息
// @Accept       json
// @Produce      json
// @Param        session_id  path      string          true  "会话ID"
// @Param        message_id  path      string          true  "消息ID"
// @Param        request     body      types.Feedback  true  "反馈内容"
// @Success      200         {object}  map[string]interface{}
// @Failure      400         {object}  errors.AppError
// @Security     Bearer
// @Security     ApiKeyAuth
// @Router       /messages/{session_id}/{message_id}/feedback [put]
func (h *Handler) UpdateFeedback(c *gin.Context) {
	ctx := c.Request.Context()
	sessionID := c.Param("session_id")
	messageID := c.Param("message_id")

	var feedback types.Feedback
	if err := c.ShouldBindJSON(&feedback); err != nil {
		logger.Error(ctx, "Failed to validate feedback parameters", err)
		c.Error(errors.NewBadRequestError(err.Error()))
		return
	}

	if err := h.messageService.UpdateFeedback(ctx, sessionID, messageID, &feedback); err != nil {
		logger.ErrorWithFields(ctx, err, nil)
		c.Error(err)
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": true})
}

// GetFeedbacks godoc
// @Summary      获取反馈列表 (Admin)
// @Description  获取所有消息反馈 (仅管理员)
// @Tags         管理员
// @Accept       json
// @Produce      json
// @Param        page      query     int     false  "页码" default(1)
// @Param        page_size query     int     false  "每页数量" default(10)
// @Param        rating    query     string  false  "评分筛选 (like/dislike)"
// @Param        user_id   query     string  false  "用户ID筛选"
// @Success      200       {object}  map[string]interface{}
// @Failure      403       {object}  errors.AppError
// @Security     Bearer
// @Router       /admin/feedbacks [get]
func (h *Handler) GetFeedbacks(c *gin.Context) {
	ctx := c.Request.Context()

	// Check user existence in context (should be set by auth middleware)
	userVal, exists := c.Get(types.UserContextKey.String())
	if !exists {
		c.Error(errors.NewUnauthorizedError("Unauthorized"))
		return
	}
	user, ok := userVal.(*types.User)
	if !ok {
		c.Error(errors.NewUnauthorizedError("Invalid user context"))
		return
	}

	// Check admin permission
	if !user.IsAdmin {
		c.Error(errors.NewForbiddenError("Admin permission required"))
		return
	}

	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	if page < 1 {
		page = 1
	}
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "10"))
	if pageSize < 1 {
		pageSize = 10
	}
	if pageSize > 100 {
		pageSize = 100
	}

	rating := c.Query("rating")
	userID := c.Query("user_id")

	messages, total, err := h.messageService.GetFeedbacks(ctx, page, pageSize, rating, userID)
	if err != nil {
		logger.ErrorWithFields(ctx, err, nil)
		c.Error(err)
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"items": messages,
		"total": total,
		"page":  page,
		"size":  pageSize,
	})
}
