<template>
  <div class="erp-sync-container">
    <div class="header">
      <div class="title">ERP文档同步进度</div>
    </div>

    <t-tabs v-model="activeTab" theme="normal" class="tabs">
      <t-tab-panel value="dashboard" label="仪表盘">
        <div class="tab-content">
          <!-- Stats Cards -->
          <t-row :gutter="[16, 16]">
            <t-col :span="3" v-for="(count, status) in statsDisplay" :key="status">
              <t-card :bordered="false" class="stat-card" :class="status">
                <div class="stat-title">{{ statusMap[status] || status }}</div>
                <div class="stat-value">{{ count }}</div>
              </t-card>
            </t-col>
          </t-row>

          <t-row :gutter="[16, 16]" class="mt-4">
            <!-- Recent Failures -->
            <t-col :span="6">
              <t-card title="最近失败记录" :bordered="false">
                <t-table
                  :data="recentFails"
                  :columns="failColumns"
                  row-key="filename"
                  size="small"
                  :pagination="null"
                >
                  <template #process_at="{ row }">
                    {{ formatDate(row.process_at) }}
                  </template>
                </t-table>
              </t-card>
            </t-col>
            
            <!-- Recent Runs -->
            <t-col :span="6">
              <t-card title="最近运行记录" :bordered="false">
                <t-table
                  :data="recentRuns"
                  :columns="runColumns"
                  row-key="process_timestamp"
                  size="small"
                  :pagination="null"
                >
                  <template #process_timestamp="{ row }">
                    {{ formatDate(row.process_timestamp) }}
                  </template>
                  <template #status="{ row }">
                    <t-tag :theme="row.status === 'success' ? 'success' : 'danger'" variant="light">
                      {{ row.status }}
                    </t-tag>
                  </template>
                </t-table>
              </t-card>
            </t-col>
          </t-row>
        </div>
      </t-tab-panel>

      <t-tab-panel value="documents" label="文档列表">
        <div class="tab-content">
          <div class="filter-bar">
            <t-select
              v-model="docFilterStatus"
              placeholder="按状态筛选"
              clearable
              style="width: 200px"
              @change="fetchDocuments(1)"
            >
              <t-option v-for="(label, value) in statusMap" :key="value" :value="value" :label="label" />
            </t-select>
            <t-button theme="primary" @click="fetchDocuments(1)">刷新</t-button>
          </div>
          
          <t-table
            :data="documents"
            :columns="docColumns"
            row-key="id"
            :pagination="pagination"
            :loading="docsLoading"
            @page-change="onPageChange"
          >
            <template #file_status="{ row }">
              <t-tag :theme="getStatusTheme(row.file_status)" variant="light">
                {{ statusMap[row.file_status] || row.file_status }}
              </t-tag>
            </template>
            <template #process_at="{ row }">
              {{ formatDate(row.process_at) }}
            </template>
          </t-table>
        </div>
      </t-tab-panel>

      <t-tab-panel value="logs" label="运行日志">
        <div class="tab-content">
          <t-button theme="primary" class="mb-2" @click="fetchLogs">刷新</t-button>
          <t-table
            :data="logs"
            :columns="logColumns"
            row-key="id"
            :loading="logsLoading"
            size="small"
          >
            <template #process_timestamp="{ row }">
              {{ formatDate(row.process_timestamp) }}
            </template>
            <template #status="{ row }">
              <t-tag :theme="row.status === 'success' ? 'success' : 'danger'" variant="light">
                {{ row.status }}
              </t-tag>
            </template>
          </t-table>
        </div>
      </t-tab-panel>
    </t-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { 
  getDashboardStats, 
  getDocuments, 
  getLogs,
  type ErpStats,
  type RecentFail,
  type RecentRun,
  type DocumentItem,
  type LogItem
} from '@/api/erp-sync';
import { MessagePlugin } from 'tdesign-vue-next';

// State
const activeTab = ref('dashboard');
const stats = ref<ErpStats>({
  total: 0, discover: 0, pending: 0, processing: 0, completed: 0, failed: 0, deleted: 0
});
const recentFails = ref<RecentFail[]>([]);
const recentRuns = ref<RecentRun[]>([]);
const documents = ref<DocumentItem[]>([]);
const logs = ref<LogItem[]>([]);
const docFilterStatus = ref('');
const docsLoading = ref(false);
const logsLoading = ref(false);

const pagination = ref({
  current: 1,
  pageSize: 20,
  total: 0
});

// Constants
const statusMap: Record<string, string> = {
  'total': '总数',
  'discover': '新发现',
  'pending': '等待中',
  'processing': '处理中',
  'completed': '已完成',
  'failed': '失败',
  'deleted': '已删除'
};

const statsDisplay = computed(() => {
  // Ensure order matches desired display
  return {
    total: stats.value.total,
    discover: stats.value.discover,
    pending: stats.value.pending,
    processing: stats.value.processing,
    completed: stats.value.completed,
    failed: stats.value.failed,
    deleted: stats.value.deleted
  };
});

const failColumns = [
  { colKey: 'filename', title: '文件名', ellipsis: true },
  { colKey: 'failed_msg', title: '失败原因', ellipsis: true },
  { colKey: 'process_at', title: '失败时间', width: 180 }
];

const runColumns = [
  { colKey: 'script_name', title: '脚本名称' },
  { colKey: 'process_timestamp', title: '执行时间', width: 180 },
  { colKey: 'status', title: '状态', width: 100 },
  { colKey: 'process_count', title: '处理数量', width: 100 }
];

const docColumns = [
  { colKey: 'id', title: 'ID', width: 80 },
  { colKey: 'filename', title: '文件名', ellipsis: true },
  { colKey: 'file_status', title: '状态', width: 100 },
  { colKey: 'failed_msg', title: '失败信息', ellipsis: true },
  { colKey: 'process_at', title: '处理时间', width: 180 }
];

const logColumns = [
  { colKey: 'id', title: 'ID', width: 80 },
  { colKey: 'script_name', title: '脚本名称' },
  { colKey: 'process_timestamp', title: '执行时间', width: 180 },
  { colKey: 'status', title: '状态', width: 100 },
  { colKey: 'process_count', title: '处理数量', width: 100 }
];

// Methods
const formatDate = (dateStr: string | null) => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString();
};

const getStatusTheme = (status: string) => {
  switch (status) {
    case 'completed': return 'success';
    case 'processing': return 'primary';
    case 'failed': return 'danger';
    case 'pending': return 'warning';
    case 'discover': return 'default';
    default: return 'default';
  }
};

const fetchDashboard = async () => {
  try {
    const data = await getDashboardStats();
    stats.value = data.stats;
    recentFails.value = data.recent_fails;
    recentRuns.value = data.recent_runs;
  } catch (error) {
    console.error('Failed to fetch dashboard stats', error);
    MessagePlugin.error('获取仪表盘数据失败');
  }
};

const fetchDocuments = async (page = 1) => {
  docsLoading.value = true;
  try {
    const data = await getDocuments(page, docFilterStatus.value, pagination.value.pageSize);
    documents.value = data.documents;
    pagination.value.current = data.page;
    pagination.value.total = data.total;
  } catch (error) {
    console.error('Failed to fetch documents', error);
    MessagePlugin.error('获取文档列表失败');
  } finally {
    docsLoading.value = false;
  }
};

const onPageChange = (pageInfo: { current: number; pageSize: number }) => {
  pagination.value.current = pageInfo.current;
  pagination.value.pageSize = pageInfo.pageSize;
  fetchDocuments(pageInfo.current);
};

const fetchLogs = async () => {
  logsLoading.value = true;
  try {
    const data = await getLogs();
    logs.value = data.logs;
  } catch (error) {
    console.error('Failed to fetch logs', error);
    MessagePlugin.error('获取日志失败');
  } finally {
    logsLoading.value = false;
  }
};

onMounted(() => {
  fetchDashboard();
  fetchDocuments();
  fetchLogs();
});
</script>

<style lang="less" scoped>
.erp-sync-container {
  padding: 24px;
  background-color: var(--td-bg-color-page);
  min-height: 100%;
}

.header {
  margin-bottom: 24px;
  .title {
    font-size: 20px;
    font-weight: bold;
    color: var(--td-text-color-primary);
  }
}

.tabs {
  background: var(--td-bg-color-container);
  border-radius: var(--td-radius-medium);
  padding: 16px;
}

.tab-content {
  padding-top: 16px;
}

.stat-card {
  text-align: center;
  border-radius: var(--td-radius-medium);
  transition: all 0.3s;
  
  &:hover {
    transform: translateY(-2px);
    box-shadow: var(--td-shadow-1);
  }
  
  .stat-title {
    font-size: 14px;
    color: var(--td-text-color-secondary);
    margin-bottom: 8px;
  }
  
  .stat-value {
    font-size: 24px;
    font-weight: bold;
    color: var(--td-text-color-primary);
  }
}

.mt-4 {
  margin-top: 16px;
}

.mb-2 {
  margin-bottom: 8px;
}

.filter-bar {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}
</style>
