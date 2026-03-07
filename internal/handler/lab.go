package handler

import (
	"context"
	"net/http"
	"time"

	"github.com/Tencent/WeKnora/docreader/client"
	docreader_proto "github.com/Tencent/WeKnora/docreader/proto"
	"github.com/Tencent/WeKnora/internal/logger"
	"github.com/gin-gonic/gin"
)

type LabHandler struct {
	docReaderClient *client.Client
}

func NewLabHandler(docReaderClient *client.Client) *LabHandler {
	return &LabHandler{docReaderClient: docReaderClient}
}

type CompareSplittersRequest struct {
	Text         string `json:"text" binding:"required"`
	ChunkSize    int32  `json:"chunk_size"`
	ChunkOverlap int32  `json:"chunk_overlap"`
}

func (h *LabHandler) CompareSplitters(c *gin.Context) {
	ctx := c.Request.Context()
	var req CompareSplittersRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Call DocReader RPC
	rpcReq := &docreader_proto.CompareSplittersRequest{
		Text:         req.Text,
		ChunkSize:    req.ChunkSize,
		ChunkOverlap: req.ChunkOverlap,
	}

	// Set timeout
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	resp, err := h.docReaderClient.CompareSplitters(ctx, rpcReq)
	if err != nil {
		logger.Error(ctx, "Failed to call CompareSplitters", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, resp)
}
