<template>
  <div class="splitter-arena">
    <t-card :bordered="false" class="config-card" hover-shadow>
      <template #header>
        <div class="card-header">
          <t-icon name="layers" size="24px" class="header-icon" />
          <div>
            <div class="title">Splitter Arena</div>
            <div class="subtitle">Compare different text splitting strategies side-by-side</div>
          </div>
        </div>
      </template>
      
      <div class="input-section">
        <div class="text-input-wrapper">
          <div class="section-label">
            <t-icon name="file-text" /> Input Text
          </div>
          <t-textarea
            v-model="text"
            placeholder="Paste your text here (Markdown supported)..."
            :autosize="{ minRows: 8, maxRows: 15 }"
            class="text-input"
          />
        </div>
        
        <t-divider layout="vertical" class="config-divider" />

        <div class="controls-wrapper">
          <div class="section-label">
            <t-icon name="setting" /> Configuration
          </div>
          <div class="control-group">
            <div class="control-item">
              <div class="control-label">
                <span>Chunk Size</span>
                <span class="control-value">{{ chunkSize }}</span>
              </div>
              <t-slider v-model="chunkSize" :min="64" :max="2048" :step="64" />
            </div>
            
            <div class="control-item">
              <div class="control-label">
                <span>Overlap</span>
                <span class="control-value">{{ chunkOverlap }}</span>
              </div>
              <t-slider v-model="chunkOverlap" :min="0" :max="512" :step="10" />
            </div>

            <t-button block theme="primary" size="large" :loading="loading" @click="handleCompare">
              <template #icon><t-icon name="play-circle" /></template>
              Run Comparison
            </t-button>
          </div>
        </div>
      </div>
    </t-card>

    <div v-if="results.length > 0" class="results-section">
      <t-row :gutter="[24, 24]">
        <t-col v-for="result in results" :key="result.splitter_name" :span="12 / results.length">
          <t-card :bordered="false" class="result-card" hover-shadow>
            <template #header>
              <div class="result-header">
                <div class="splitter-info">
                  <div class="splitter-name">{{ result.splitter_name }}</div>
                  <div class="splitter-meta">
                    <t-tag theme="primary" variant="light" size="small">
                      <template #icon><t-icon name="layers" /></template>
                      {{ result.total_chunks }} chunks
                    </t-tag>
                    <t-tag theme="success" variant="light" size="small">
                      <template #icon><t-icon name="time" /></template>
                      {{ result.execution_time.toFixed(4) }}s
                    </t-tag>
                  </div>
                </div>
              </div>
            </template>
            
            <div class="chunks-container custom-scrollbar">
              <div v-if="result.chunks.length === 0" class="empty-state">
                <t-empty description="No chunks generated" />
              </div>
              <div v-else v-for="(chunk, index) in result.chunks" :key="chunk.seq" class="chunk-item">
                <div class="chunk-header">
                  <span class="chunk-index">#{{ index + 1 }}</span>
                  <span class="chunk-info">{{ chunk.content.length }} chars</span>
                </div>
                <div class="chunk-body">
                  {{ chunk.content }}
                </div>
              </div>
            </div>
          </t-card>
        </t-col>
      </t-row>
    </div>
    
    <div v-else-if="!loading && text" class="empty-results">
      <div class="empty-content">
        <t-icon name="chart-bubble" size="64px" style="color: var(--td-brand-color)" />
        <p class="empty-text">Ready to compare! Click "Run Comparison" to analyze.</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { compareSplitters, type SplitterResult } from '@/api/lab'
import { MessagePlugin } from 'tdesign-vue-next'

const text = ref('')
const chunkSize = ref(512)
const chunkOverlap = ref(50)
const loading = ref(false)
const results = ref<SplitterResult[]>([])

const handleCompare = async () => {
  if (!text.value) {
    MessagePlugin.warning('Please enter text first')
    return
  }

  loading.value = true
  try {
    const res = await compareSplitters({
      text: text.value,
      chunk_size: chunkSize.value,
      chunk_overlap: chunkOverlap.value
    })
    results.value = res.results || []
  } catch (err: any) {
    MessagePlugin.error(err.message || 'Comparison failed')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.splitter-arena {
  padding: 24px;
  background-color: var(--td-bg-color-page);
  min-height: 100vh;
}

.config-card {
  margin-bottom: 24px;
  border-radius: var(--td-radius-large);
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-icon {
  color: var(--td-brand-color);
  background: var(--td-brand-color-light);
  padding: 8px;
  border-radius: var(--td-radius-medium);
  box-sizing: content-box;
}

.title {
  font-size: 20px;
  font-weight: 700;
  color: var(--td-text-color-primary);
  line-height: 1.2;
}

.subtitle {
  font-size: 14px;
  color: var(--td-text-color-secondary);
  margin-top: 4px;
}

.input-section {
  display: flex;
  gap: 32px;
}

.text-input-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.config-divider {
  height: auto;
  margin: 0;
}

.controls-wrapper {
  width: 320px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-left: 8px;
}

.section-label {
  font-size: 16px;
  font-weight: 600;
  color: var(--td-text-color-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.control-group {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 16px 0;
}

.control-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.control-label {
  display: flex;
  justify-content: space-between;
  color: var(--td-text-color-secondary);
  font-size: 14px;
}

.control-value {
  color: var(--td-brand-color);
  font-weight: 600;
  font-family: var(--td-font-family-medium);
}

.results-section {
  margin-top: 24px;
  animation: fadeIn 0.3s ease-in-out;
}

.result-card {
  height: 100%;
  border-radius: var(--td-radius-large);
  display: flex;
  flex-direction: column;
  background-color: var(--td-bg-color-container);
  border: 1px solid var(--td-component-border);
}

.result-header {
  padding: 4px 0;
}

.splitter-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.splitter-name {
  font-weight: 700;
  font-size: 18px;
  color: var(--td-text-color-primary);
}

.splitter-meta {
  display: flex;
  gap: 8px;
}

.chunks-container {
  max-height: calc(100vh - 400px);
  min-height: 400px;
  overflow-y: auto;
  padding-right: 8px;
  margin-top: 8px;
}

.chunk-item {
  margin-bottom: 16px;
  border-radius: var(--td-radius-medium);
  background-color: var(--td-bg-color-secondarycontainer);
  overflow: hidden;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.chunk-item:hover {
  background-color: var(--td-bg-color-container);
  border-color: var(--td-brand-color);
  transform: translateY(-2px);
  box-shadow: var(--td-shadow-1);
}

.chunk-header {
  display: flex;
  justify-content: space-between;
  padding: 6px 12px;
  background-color: rgba(0, 0, 0, 0.02);
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
  font-size: 12px;
  color: var(--td-text-color-placeholder);
}

.chunk-index {
  font-weight: 600;
  color: var(--td-text-color-secondary);
}

.chunk-body {
  padding: 12px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--td-text-color-primary);
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
}

.empty-results {
  display: flex;
  justify-content: center;
  padding: 80px 0;
}

.empty-content {
  text-align: center;
  color: var(--td-text-color-placeholder);
}

.empty-text {
  margin-top: 16px;
  font-size: 16px;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Custom Scrollbar */
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: var(--td-scrollbar-color);
  border-radius: 3px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background-color: transparent;
}

@media (max-width: 768px) {
  .input-section {
    flex-direction: column;
    gap: 24px;
  }
  
  .config-divider {
    display: none;
  }
  
  .controls-wrapper {
    width: 100%;
    padding-left: 0;
  }
}
</style>
