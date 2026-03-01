import axios from 'axios';
import { generateRandomString } from '@/utils/index';

// Create a dedicated axios instance for the ERP Sync Admin Server
// Assuming the main backend server runs on port 8080 on localhost
const BASE_URL = import.meta.env.VITE_IS_DOCKER ? "" : "http://localhost:8080";

const erpSyncApi = axios.create({
  baseURL: `${BASE_URL}/api/v1/erp`,
  timeout: 10000,
  headers: {
    "Content-Type": "application/json",
    "X-Request-ID": `${generateRandomString(12)}`,
  },
});

// Add auth token interceptor
erpSyncApi.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('weknora_token');
    if (token) {
      config.headers["Authorization"] = `Bearer ${token}`;
    }
    
    // Add tenant ID header
    const selectedTenantId = localStorage.getItem('weknora_selected_tenant_id');
    const defaultTenantId = localStorage.getItem('weknora_tenant');
    if (selectedTenantId) {
      try {
        const defaultTenant = defaultTenantId ? JSON.parse(defaultTenantId) : null;
        const defaultId = defaultTenant?.id ? String(defaultTenant.id) : null;
        if (selectedTenantId !== defaultId) {
          config.headers["X-Tenant-ID"] = selectedTenantId;
        }
      } catch (e) {
        console.error('Failed to parse tenant info', e);
      }
    }
    
    config.headers["X-Request-ID"] = `${generateRandomString(12)}`;
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

export interface ErpStats {
  total: number;
  discover: number;
  pending: number;
  processing: number;
  completed: number;
  failed: number;
  deleted: number;
}

export interface RecentFail {
  filename: string;
  failed_msg: string;
  process_at: string;
}

export interface RecentRun {
  script_name: string;
  process_timestamp: string;
  status: string;
  process_count: number;
}

export interface DashboardData {
  stats: ErpStats;
  recent_fails: RecentFail[];
  recent_runs: RecentRun[];
}

export interface DocumentItem {
  id: number;
  filename: string;
  file_status: string;
  process_at: string | null;
  failed_msg: string | null;
  file_hash: string | null;
}

export interface DocumentListResponse {
  documents: DocumentItem[];
  total: number;
  page: number;
  per_page: number;
}

export interface LogItem {
  id: number;
  script_name: string;
  process_timestamp: string;
  status: string;
  process_count: number;
  message: string | null;
}

export interface LogsResponse {
  logs: LogItem[];
}

// API Methods
export const getDashboardStats = async (): Promise<DashboardData> => {
  const response = await erpSyncApi.get<DashboardData>('/stats');
  return response.data;
};

export const getDocuments = async (page: number = 1, status: string = '', per_page: number = 20): Promise<DocumentListResponse> => {
  const response = await erpSyncApi.get<DocumentListResponse>('/documents', {
    params: { page, status, per_page }
  });
  return response.data;
};

export const getLogs = async (): Promise<LogsResponse> => {
  const response = await erpSyncApi.get<LogsResponse>('/logs');
  return response.data;
};
