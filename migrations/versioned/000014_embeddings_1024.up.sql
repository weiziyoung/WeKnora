-- Migration: embeddings_1024 (conditional)
-- Description: Create embeddings index for dimension 1024 (only for postgres retrieve driver)

DO $$
BEGIN
    -- Check if we should skip this migration
    IF current_setting('app.skip_embedding', true) = 'true' THEN
        RAISE NOTICE 'Skipping migration embeddings_1024 (app.skip_embedding=true)';
        RETURN;
    END IF;

    -- If we reach here, proceed with migration
    RAISE NOTICE '[Conditional Migration: embeddings_1024] Creating index for embeddings...';

    -- Create HNSW indexes for vector search (check if exists first)
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'embeddings_embedding_idx_1024' OR indexname LIKE 'embeddings_embedding%1024%') THEN
        CREATE INDEX embeddings_embedding_idx_1024 ON embeddings 
        USING hnsw ((embedding::halfvec(1024)) halfvec_cosine_ops) 
        WITH (m = 16, ef_construction = 64) 
        WHERE (dimension = 1024);
        RAISE NOTICE '[Conditional Migration: embeddings_1024] Created HNSW index for dimension 1024';
    ELSE
        RAISE NOTICE '[Conditional Migration: embeddings_1024] HNSW index for dimension 1024 already exists';
    END IF;

END $$;
