
import alibabacloud_oss_v2 as oss
from app.core.config import settings
from .base import BaseOSSClient
from datetime import timedelta
from io import BytesIO
from app.exceptions import OSSUploadException
from typing import Tuple, Dict


class AliOSSClient(BaseOSSClient):
    """阿里云OSS客户端实现"""

    def __init__(self):
        """初始化阿里云OSS客户端"""
        # 创建凭证提供者
        self.credentials_provider = oss.credentials.StaticCredentialsProvider(
            access_key_id=settings.oss_access_key,
            access_key_secret=settings.oss_secret_key
        )

        # 加载配置
        self.cfg = oss.config.load_default()
        self.cfg.credentials_provider = self.credentials_provider
        self.cfg.region = settings.oss_region

        if settings.oss_endpoint:
            self.cfg.endpoint = settings.oss_endpoint
        
        # 创建客户端
        self.client = oss.Client(self.cfg)
        self.bucket = settings.oss_bucket

    def upload_image(self, image_bytes: bytes, object_name: str, expires: timedelta = timedelta(hours=1)) -> str:
        """
        上传图片二进制流到阿里云OSS并返回可访问的链接

        Args:
            image_bytes: 图片二进制数据
            object_name: OSS中的对象名称（路径）
            expires: 签名URL过期时间，默认1小时

        Returns:
            可访问的图片链接
        """
        try:
            # 将二进制数据转换为BytesIO对象用于上传
            image_io = BytesIO(image_bytes)

            # 创建上传请求
            request = oss.PutObjectRequest(
                bucket=self.bucket,
                key=object_name,
                body=image_io
            )

            # 上传图片
            result = self.client.put_object(request)

            # 验证上传结果
            if result.status_code != 200:
                raise OSSUploadException(f"上传失败，状态码: {result.status_code}")

            # 生成带签名的访问URL
            sign_request = oss.GetObjectRequest(
                bucket=self.bucket,
                key=object_name,
            )

            signed_result = self.client.presign(sign_request, expires=expires)

            return signed_result.url

        except Exception as e:
            if isinstance(e, OSSUploadException):
                raise e
            raise OSSUploadException(str(e))

    def get_public_url(self, object_name: str) -> str:
        """
        获取对象的公网访问链接（仅适用于公共读Bucket）
        
        Args:
            object_name: OSS中的对象名称
            
        Returns:
            对象的完整访问URL
        """
        endpoint = self.cfg.endpoint
        if not endpoint:
            # 如果没有直接设置endpoint，尝试从region构建
            # 默认使用https
            endpoint = f"oss-{self.cfg.region}.aliyuncs.com"
            
        return f"https://{self.bucket}.{endpoint}/{object_name}"

    def get_internal_url(self, object_name: str) -> str:
        """
        获取对象的内部访问链接（仅适用于私有Bucket）
        
        Args:
            object_name: OSS中的对象名称
            
        Returns:
            对象的完整内部访问URL
        """
        endpoint = self.cfg.endpoint
        if not endpoint:
            # 如果没有直接设置endpoint，尝试从region构建
            # 默认使用https
            endpoint = f"oss-{self.cfg.region}-internal.aliyuncs.com"
            
        return f"https://{self.bucket}.{endpoint}/{object_name}"

    def get_presigned_url(self, object_name: str, method: str = 'PUT', expires: timedelta = timedelta(seconds=60), headers: Dict[str, str] = None) -> Tuple[str, Dict[str, str]]:
        """
        生成预签名URL
        
        Args:
            object_name: OSS中的对象名称（路径）
            method: 请求方法，'PUT' 或 'GET'
            expires: 签名URL过期时间，默认60秒
            headers: 包含在签名中的请求头
            
        Returns:
            Tuple[str, Dict[str, str]]: (预签名URL, 请求头信息)
        """
        try:
            if method.upper() == 'PUT':
                request = oss.PutObjectRequest(
                    bucket=self.bucket,
                    key=object_name,
                    headers=headers
                )
            else:
                request = oss.GetObjectRequest(
                    bucket=self.bucket,
                    key=object_name,
                    headers=headers
                )
            
            # 生成预签名URL
            signed_result = self.client.presign(request, expires=expires)
            return signed_result.url, signed_result.signed_headers
            
        except Exception as e:
            raise OSSUploadException(f"生成预签名URL失败: {str(e)}")


# 使用示例
if __name__ == "__main__":
    # 示例：上传图片二进制数据
    oss_client = AliOSSClient()

    # 示例图片数据（实际使用时应该是真实的图片bytes）
    example_image_bytes = b"fake image data"

    try:
        # 上传图片并获取访问链接
        image_url = oss_client.upload_image(
            image_bytes=example_image_bytes,
            object_name="test/example_image.png",
            expires=timedelta(hours=2)  # 2小时过期时间
        )
        print(f"图片上传成功，访问链接: {image_url}")

    except Exception as e:
        print(f"上传失败: {e}")
