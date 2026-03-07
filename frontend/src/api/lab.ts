import { post } from '@/utils/request'

export interface CompareSplittersRequest {
  text: string
  chunk_size?: number
  chunk_overlap?: number
}

export interface Chunk {
  content: string
  seq: number
  start: number
  end: number
}

export interface SplitterResult {
  splitter_name: string
  chunks: Chunk[]
  total_chunks: number
  execution_time: number
}

export interface CompareSplittersResponse {
  results: SplitterResult[]
  error?: string
}

export function compareSplitters(data: CompareSplittersRequest) {
  return post('/api/v1/lab/splitter/compare', data) as Promise<CompareSplittersResponse>
}
