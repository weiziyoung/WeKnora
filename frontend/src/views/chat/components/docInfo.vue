<template>
    <div class="refer">
        <div class="refer_header" @click="referBoxSwitch" v-if="session.knowledge_references && session.knowledge_references.length">
            <div class="refer_title">
                <img src="@/assets/img/ziliao.svg" :alt="$t('chat.referenceIconAlt')" />
                <span>{{ $t('chat.referencesTitle', { count: session.knowledge_references?.length ?? 0 }) }}</span>
            </div>
            <div class="refer_show_icon">
                <t-icon :name="showReferBox ? 'chevron-up' : 'chevron-down'" />
            </div>
        </div>
        <div class="refer_box" v-show="showReferBox">
            <div v-for="(item, index) in session.knowledge_references" :key="index">
                <!-- Web search references: show URL and make it clickable -->
                <template v-if="item.chunk_type === 'web_search'">
                    <a 
                        :href="getWebSearchUrl(item)" 
                        target="_blank" 
                        rel="noopener noreferrer"
                        class="doc doc-web"
                        @click.stop
                    >
                        {{ session.knowledge_references.length < 2 ? getWebSearchDisplayText(item) : `${index + 1}.${getWebSearchDisplayText(item)}` }}
                    </a>
                </template>
                <!-- Regular knowledge references: show title with popup -->
                <template v-else>
                    <t-popup overlayClassName="refer-to-layer" placement="bottom-left" width="400" :showArrow="false"
                        trigger="hover">
                        <template #content>
                            <ContentPopup :content="renderMarkdown(item.content)" :is-html="true" />
                        </template>
                        <span class="doc" @click="handleDocClick(item)">
                            {{ session.knowledge_references.length < 2 ? item.knowledge_title : `${index +
                                1}.${item.knowledge_title}` }} </span>
                    </t-popup>
                </template>
            </div>
        </div>
    </div>
</template>
<script setup>
import { onMounted, defineProps, computed, ref, reactive } from "vue";
import { sanitizeHTML } from '@/utils/security';
import { processContentUrls } from '@/utils/url';
import ContentPopup from './tool-results/ContentPopup.vue';
import { marked } from 'marked';
import { MessagePlugin } from 'tdesign-vue-next';
import { downKnowledgeDetails } from '@/api/knowledge-base';

// Configure marked
marked.use({
    mangle: false,
    headerIds: false,
    breaks: true,
});

const props = defineProps({
    // 必填项
    content: {
        type: String,
        required: false
    },
    session: {
        type: Object,
        required: false
    }
});
const showReferBox = ref(false);
const referBoxSwitch = () => {
    showReferBox.value = !showReferBox.value;
};

// 渲染 Markdown 内容
const renderMarkdown = (content) => {
    if (!content) return '';
    
    const processedContent = processContentUrls(content);
    
    try {
        const html = marked.parse(processedContent);
        return sanitizeHTML(html);
    } catch (e) {
        console.error('Markdown rendering failed:', e);
        return sanitizeHTML(processedContent);
    }
};

// 点击文档标题跳转到原始文件
const handleDocClick = async (item) => {
    if (!item.knowledge_id) {
        MessagePlugin.warning('无法找到对应的文件ID');
        return;
    }

    try {
        const loading = MessagePlugin.loading('正在打开文件...');
        const response = await downKnowledgeDetails(item.knowledge_id);
        
        // Check if response is Blob
        if (response instanceof Blob) {
            let blob = response;
            // Try to detect MIME type from filename for better preview support
            const filename = item.knowledge_title || '';
            const ext = filename.split('.').pop().toLowerCase();
            const mimeMap = {
                'pdf': 'application/pdf',
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'png': 'image/png',
                'gif': 'image/gif',
                'txt': 'text/plain',
                'html': 'text/html',
                'htm': 'text/html',
                'json': 'application/json',
                'md': 'text/markdown',
                'svg': 'image/svg+xml'
            };
            const mimeType = mimeMap[ext];
            if (mimeType) {
                blob = new Blob([response], { type: mimeType });
            }

            const url = window.URL.createObjectURL(blob);
            window.open(url, '_blank');
            // Clean up URL object after a delay
            setTimeout(() => {
                window.URL.revokeObjectURL(url);
            }, 1000);
        } else {
            // Handle error response (sometimes error is returned as JSON but axios treats as blob)
             // Check if it's a JSON blob
            if (response.type === 'application/json') {
                const text = await response.text();
                const json = JSON.parse(text);
                throw new Error(json.message || '文件打开失败');
            }
             // Should be unreachable if interceptor handles it, but safety first
             throw new Error('文件打开失败');
        }
        loading.close();
    } catch (error) {
        console.error('Failed to open file:', error);
        MessagePlugin.closeAll();
        MessagePlugin.error(error.message || '文件打开失败');
    }
};

// 安全地处理内容
const safeProcessContent = (content) => {
    if (!content) return '';
    // 先进行安全清理，然后处理换行
    const sanitized = sanitizeHTML(content);
    return sanitized.replace(/\n/g, '<br/>');
};

// 获取 web_search 类型的 URL
const getWebSearchUrl = (item) => {
    // 优先使用 metadata.url，其次使用 id（如果 id 是 URL）
    if (item.metadata?.url) {
        return item.metadata.url;
    }
    if (item.id && (item.id.startsWith('http://') || item.id.startsWith('https://'))) {
        return item.id;
    }
    return '#';
};

// 获取 web_search 类型的显示文本
const getWebSearchDisplayText = (item) => {
    // 优先使用 knowledge_title，其次使用 metadata.title，最后使用 URL 的域名
    if (item.knowledge_title) {
        return item.knowledge_title;
    }
    if (item.metadata?.title) {
        return item.metadata.title;
    }
    // 如果都没有，使用 URL 的域名部分
    const url = getWebSearchUrl(item);
    if (url && url !== '#') {
        try {
            const urlObj = new URL(url);
            return urlObj.hostname;
        } catch {
            return url;
        }
    }
    return 'Web Search Result';
};

</script>
<style lang="less" scoped>
.refer {
    display: flex;
    flex-direction: column;
    font-size: 12px;
    width: 100%;
    border-radius: 8px;
    background-color: #ffffff;
    box-shadow: 0 2px 4px rgba(7, 192, 95, 0.08);
    overflow: hidden;
    box-sizing: border-box;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    margin-bottom: 8px;

    .refer_header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 6px 14px;
        color: #333333;
        font-weight: 500;

        .refer_title {
            display: flex;
            align-items: center;

            img {
                width: 16px;
                height: 16px;
                color: #07c05f;
                fill: currentColor;
                margin-right: 8px;
            }

            span {
                white-space: nowrap;
                font-size: 12px;
            }
        }

        .refer_show_icon {
            font-size: 14px;
            padding: 0 2px 1px 2px;
            color: #07c05f;
        }
    }

    .refer_header:hover {
        background-color: rgba(7, 192, 95, 0.04);
        cursor: pointer;
    }

    .refer_box {
        padding: 4px 14px 4px 14px;
        flex-direction: column;
        border-top: 1px solid #f0f0f0;
    }
}

.doc_content {
    max-height: 400px;
    overflow: auto;
    font-size: 14px;
    color: #000000e6;
    line-height: 23px;
    text-align: justify;
    border: 1px solid #07c05f33;
    padding: 8px;
}

.doc {
    text-decoration: none;
    color: #07c05f;
    cursor: pointer;
    display: inline-block;
    white-space: nowrap;
    max-width: calc(100% - 24px);
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 20px;
    padding: 2px 0;
    transition: all 0.2s ease;
    border-bottom: 1px solid transparent;
    
    &:hover {
        border-bottom-color: #07c05f;
    }
    
    &.doc-web {
        // Web search links can be longer, allow wrapping if needed
        white-space: normal;
        word-break: break-all;
        
        &:hover {
            text-decoration: underline;
        }
    }
}
</style>

<style>
.refer-to-layer {
    width: 400px;
    max-width: 500px;
    
    .t-popup__content {
        max-height: 400px;
        max-width: 500px;
        overflow-y: auto;
        overflow-x: hidden;
        word-wrap: break-word;
        word-break: break-word;
    }
}
</style>