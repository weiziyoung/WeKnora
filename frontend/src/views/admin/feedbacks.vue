<template>
  <div class="feedback-page">
    <div class="header">
      <h2>反馈管理</h2>
      <div class="filters">
        <t-radio-group v-model="filterRating" variant="default-filled" @change="fetchFeedbacks">
          <t-radio-button value="">全部</t-radio-button>
          <t-radio-button value="like">点赞</t-radio-button>
          <t-radio-button value="dislike">点踩</t-radio-button>
        </t-radio-group>
      </div>
    </div>

    <t-card :bordered="false" class="content-card">
      <t-table
        :data="feedbacks"
        :columns="columns"
        :pagination="pagination"
        :loading="loading"
        row-key="id"
        @page-change="onPageChange"
      >
        <template #rating="{ row }">
          <t-tag v-if="row.feedback?.rating === 'like'" theme="success" variant="light">
            <template #icon><t-icon name="thumb-up" /></template>
            点赞
          </t-tag>
          <t-tag v-else-if="row.feedback?.rating === 'dislike'" theme="danger" variant="light">
            <template #icon><t-icon name="thumb-down" /></template>
            点踩
          </t-tag>
          <span v-else>-</span>
        </template>

        <template #reason="{ row }">
          {{ row.feedback?.reason || '-' }}
        </template>

        <template #comment="{ row }">
          <t-tooltip v-if="row.feedback?.comment" :content="row.feedback.comment">
            <span class="comment-text">{{ row.feedback.comment }}</span>
          </t-tooltip>
          <span v-else>-</span>
        </template>

        <template #session_id="{ row }">
          {{ row.session_id || '-' }}
        </template>

        <template #query="{ row }">
          <t-tooltip v-if="row.query" :content="row.query" placement="top" :overlay-style="{ maxWidth: '500px' }">
            <span class="message-content">{{ truncate(row.query, 50) }}</span>
          </t-tooltip>
          <span v-else>-</span>
        </template>

        <template #answer="{ row }">
          <t-tooltip :content="row.answer || row.content" placement="top" :overlay-style="{ maxWidth: '500px' }">
            <span class="message-content">{{ truncate(row.answer || row.content, 50) }}</span>
          </t-tooltip>
        </template>

        <template #created_at="{ row }">
          {{ formatDate(row.created_at) }}
        </template>
        
        <template #action="{ row }">
            <t-button variant="text" theme="primary" @click="viewDetail(row)">查看详情</t-button>
        </template>
      </t-table>
    </t-card>
    
    <t-dialog
        v-model:visible="showDetail"
        header="反馈详情"
        :footer="false"
        width="600px"
    >
        <div v-if="currentDetail" class="detail-content">
            <div class="detail-item">
                <div class="label">提交时间:</div>
                <div class="value">{{ formatDate(currentDetail.created_at) }}</div>
            </div>
            <div class="detail-item">
                <div class="label">评价:</div>
                <div class="value">
                    <t-tag v-if="currentDetail.feedback?.rating === 'like'" theme="success" variant="light">点赞</t-tag>
                    <t-tag v-else-if="currentDetail.feedback?.rating === 'dislike'" theme="danger" variant="light">点踩</t-tag>
                </div>
            </div>
            <div class="detail-item" v-if="currentDetail.feedback?.reason">
                <div class="label">原因:</div>
                <div class="value">{{ currentDetail.feedback.reason }}</div>
            </div>
            <div class="detail-item" v-if="currentDetail.feedback?.comment">
                <div class="label">详细说明:</div>
                <div class="value">{{ currentDetail.feedback.comment }}</div>
            </div>
            <div class="detail-item">
                <div class="label">会话ID:</div>
                <div class="value">{{ currentDetail.session_id || '-' }}</div>
            </div>
            <div class="detail-item">
                <div class="label">用户问题:</div>
                <div class="value content-box">{{ currentDetail.query || '-' }}</div>
            </div>
            <div class="detail-item">
                <div class="label">回答内容:</div>
                <div class="value content-box">{{ currentDetail.answer || currentDetail.content }}</div>
            </div>
        </div>
    </t-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue';
import { getFeedbacks } from '@/api/chat';
import { MessagePlugin } from 'tdesign-vue-next';

const loading = ref(false);
const feedbacks = ref([]);
const filterRating = ref('');
const showDetail = ref(false);
const currentDetail = ref<any>(null);

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0,
});

const columns = [
  { colKey: 'created_at', title: '时间', width: 180 },
  { colKey: 'session_id', title: '会话ID', width: 220, ellipsis: true },
  { colKey: 'rating', title: '评价', width: 100 },
  { colKey: 'query', title: '用户问题', width: 260, ellipsis: true },
  { colKey: 'answer', title: '回答内容', width: 260, ellipsis: true },
  { colKey: 'reason', title: '原因', width: 200, ellipsis: true },
  { colKey: 'comment', title: '详细说明', width: 200, ellipsis: true },
  { colKey: 'action', title: '操作', width: 100, fixed: 'right' },
];

const fetchFeedbacks = async () => {
  loading.value = true;
  try {
    const res = await getFeedbacks({
      page: pagination.current,
      page_size: pagination.pageSize,
      rating: filterRating.value,
    }) as any;
    feedbacks.value = res.items || [];
    pagination.total = res.total || 0;
  } catch (err) {
    console.error(err);
    MessagePlugin.error('获取反馈列表失败');
  } finally {
    loading.value = false;
  }
};

const onPageChange = (pageInfo: any) => {
  pagination.current = pageInfo.current;
  pagination.pageSize = pageInfo.pageSize;
  fetchFeedbacks();
};

const formatDate = (dateString: string) => {
  if (!dateString) return '-';
  const date = new Date(dateString);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
};

const truncate = (str: string, length: number) => {
  if (!str) return '';
  return str.length > length ? str.substring(0, length) + '...' : str;
};

const viewDetail = (row: any) => {
    currentDetail.value = row;
    showDetail.value = true;
};

onMounted(() => {
  fetchFeedbacks();
});
</script>

<style scoped lang="less">
.feedback-page {
  padding: 24px;
  
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
    
    h2 {
      margin: 0;
      font-size: 20px;
      font-weight: 600;
    }
  }
}

.content-card {
  border-radius: 8px;
}

.comment-text, .message-content {
  cursor: pointer;
}

.detail-content {
    display: flex;
    flex-direction: column;
    gap: 16px;
    
    .detail-item {
        display: flex;
        flex-direction: column;
        gap: 8px;
        
        .label {
            font-weight: 600;
            color: #666;
        }
        
        .value {
            color: #333;
            line-height: 1.5;
            
            &.content-box {
                background: #f5f5f5;
                padding: 12px;
                border-radius: 6px;
                max-height: 300px;
                overflow-y: auto;
                white-space: pre-wrap;
            }
        }
    }
}
</style>
