/**
 * URL 处理工具函数
 */

/**
 * 处理 URL，将 localhost/127.0.0.1 替换为当前访问的域名
 * 主要用于解决内网部署的服务在外网访问时，图片或链接无法加载的问题
 * @param url 需要处理的 URL
 * @returns 处理后的 URL
 */
export const processUrl = (url: string) => {
  if (!url) return '';
  if (typeof window === 'undefined') return url;

  try {
    const urlObj = new URL(url);
    if (urlObj.hostname === 'localhost' || urlObj.hostname === '127.0.0.1') {
      urlObj.hostname = window.location.hostname;
    }
    return urlObj.toString();
  } catch (e) {
    return url;
  }
};

/**
 * 处理文本内容中的 URL，将 localhost/127.0.0.1 替换为当前访问的域名
 * @param content 包含 URL 的文本内容
 * @returns 处理后的文本内容
 */
export const processContentUrls = (content: string) => {
  if (!content) return '';
  if (typeof window === 'undefined') return content;

  try {
    const hostname = window.location.hostname;
    // Replace http://localhost, https://localhost, http://127.0.0.1, https://127.0.0.1
    return content.replace(/(https?:\/\/)(localhost|127\.0\.0\.1)/g, (match, protocol, host) => {
      return `${protocol}${hostname}`;
    });
  } catch (e) {
    return content;
  }
};
