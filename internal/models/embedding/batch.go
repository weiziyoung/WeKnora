package embedding

import (
	"context"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/Tencent/WeKnora/internal/logger"
	"github.com/Tencent/WeKnora/internal/models/utils"
	"github.com/panjf2000/ants/v2"
)

type batchEmbedder struct {
	pool *ants.Pool
}

func NewBatchEmbedder(pool *ants.Pool) EmbedderPooler {
	return &batchEmbedder{pool: pool}
}

type textEmbedding struct {
	text    string
	results []float32
}

func (e *batchEmbedder) BatchEmbedWithPool(ctx context.Context, model Embedder, texts []string) ([][]float32, error) {
	// Create goroutine pool for concurrent processing of document chunks
	var wg sync.WaitGroup
	var mu sync.Mutex  // For synchronizing access to error
	var firstErr error // Record the first error that occurs
	batchSizeStr := os.Getenv("BATCH_EMBED_SIZE")
	if batchSizeStr == "" {
		batchSizeStr = "5"
	}
	batchSize, err := strconv.Atoi(batchSizeStr)
	if err != nil {
		return nil, err
	}
	textEmbeddings := utils.MapSlice(texts, func(text string) *textEmbedding {
		return &textEmbedding{text: text}
	})

	// Recursive function to handle 413 errors by splitting
	var embedRecursive func(ctx context.Context, chunkTexts []*textEmbedding) ([][]float32, error)
	embedRecursive = func(ctx context.Context, chunkTexts []*textEmbedding) ([][]float32, error) {
		if len(chunkTexts) == 0 {
			return nil, nil
		}

		// Extract strings
		textStrings := utils.MapSlice(chunkTexts, func(text *textEmbedding) string {
			return text.text
		})

		// Try to embed
		var embeddings [][]float32
		var err error

		for i := 0; i < 10; i++ {
			embeddings, err = model.BatchEmbed(ctx, textStrings)
			if err == nil {
				return embeddings, nil
			}

			// Check for 429 error
			if strings.Contains(err.Error(), "429") || strings.Contains(err.Error(), "Too Many Requests") {
				logger.GetLogger(ctx).Warnf("BatchEmbed failed with 429, waiting 2s before retry (attempt %d/5)", i+1)
				time.Sleep(2 * time.Second)
				continue
			}

			// If not 429, break the loop
			break
		}

		// Check for 413 error
		// "EmbedBatch API error: Http Status %s"
		if strings.Contains(err.Error(), "413") || strings.Contains(err.Error(), "Request Entity Too Large") {
			if len(chunkTexts) <= 1 {
				logger.GetLogger(ctx).Warnf("BatchEmbed failed with 413, cannot split further (batch size=1). Text length: %d", len(textStrings[0]))
				return nil, err
			}

			logger.GetLogger(ctx).Warnf("BatchEmbed failed with 413, splitting batch of size %d into two", len(chunkTexts))

			mid := len(chunkTexts) / 2
			leftChunk := chunkTexts[:mid]
			rightChunk := chunkTexts[mid:]

			leftEmbeddings, errLeft := embedRecursive(ctx, leftChunk)
			if errLeft != nil {
				return nil, errLeft
			}

			rightEmbeddings, errRight := embedRecursive(ctx, rightChunk)
			if errRight != nil {
				return nil, errRight
			}

			return append(leftEmbeddings, rightEmbeddings...), nil
		}

		return nil, err
	}

	// Function to process each document chunk
	processChunk := func(texts []*textEmbedding) func() {
		return func() {
			defer wg.Done()
			// If an error has already occurred, don't continue processing
			if firstErr != nil {
				return
			}
			// Embed text
			embedding, err := embedRecursive(ctx, texts)
			if err != nil {
				mu.Lock()
				if firstErr == nil {
					firstErr = err
				}
				mu.Unlock()
				return
			}
			mu.Lock()
			for i, text := range texts {
				if text == nil {
					continue
				}
				text.results = embedding[i]
			}
			mu.Unlock()
		}
	}

	// Submit all tasks to the goroutine pool
	for _, texts := range utils.ChunkSlice(textEmbeddings, batchSize) {
		wg.Add(1)
		err := e.pool.Submit(processChunk(texts))
		if err != nil {
			return nil, err
		}
	}

	// Wait for all tasks to complete
	wg.Wait()

	// Check if any errors occurred
	if firstErr != nil {
		return nil, firstErr
	}

	results := utils.MapSlice(textEmbeddings, func(text *textEmbedding) []float32 {
		return text.results
	})
	return results, nil
}
