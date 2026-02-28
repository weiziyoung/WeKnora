<#
.SYNOPSIS
    SQL Server 数据库特定表(contract)批量导出脚本

.DESCRIPTION
    此脚本用于自动化导出指定 SQL Server 实例中多个数据库的 contract 表数据。
    
    主要功能包括：
    1. 连接到指定的 SQL Server 实例 (NJLB003)。
    2. 遍历预定义的数据库列表。
    3. 在本地目录 (D:\dump_data) 下自动创建与数据库同名的子文件夹。
    4. 使用 bcp 工具将 contract 表的数据以字符格式导出为 CSV 文件。

.NOTES
    - 需要安装 bcp 工具。
    - 运行环境需具备访问目标 SQL Server 的权限（使用 Windows 身份验证）。
#>

# 设置 SQL Server 服务器实例名称
$serverInstance = "WIN-K2TPMMTJLJM"

# 定义需要导出数据的数据库名称列表（数组）
$databases = @(
    "zbintel117_erp",
    "zbintel117_erp_jsznkj",
    "zbintel_erp_dst",
    "zbintel_erp_zgm",
    "zbintel_jsyyj",
    "zbintel117_jhxny_hf_8088",
    "zbintel117_lbjs_tc_9199",
    "zbintel117_weiyy_tg_9099",
    "zbintel117_yyjs1_9088",
    "zbintel117_yyjs2_9099"
)

# 定义导出数据存放的根目录路径
$exportDir = "D:\dump_data"

# 遍历数据库列表中的每一个数据库
foreach ($db in $databases) {
    # 拼接当前数据库的导出子目录路径（例如：D:\dump_data\zbintel117_erp）
    $dbExportDir = Join-Path -Path $exportDir -ChildPath $db
    
    # 检查该目录是否存在，如果不存在则创建
    if (-not (Test-Path -Path $dbExportDir)) {
        # 创建目录，-ItemType Directory 表示创建的是文件夹
        New-Item -ItemType Directory -Path $dbExportDir
    }

    # 指定要导出的表名
    $tableName = "contract"
    
    # 拼接导出文件的完整路径，文件名为 "contract.csv"
    $outputFile = Join-Path -Path $dbExportDir -ChildPath "$tableName.csv"
    
    Write-Host "正在导出数据库 $db 中的 $tableName 表..."

    # 使用 bcp (Bulk Copy Program) 工具将表数据导出到文件
    # queryout: 使用查询导出数据（相比 out 更灵活，可指定列）
    # $outputFile: 指定输出文件的路径
    # -c: 使用字符数据类型（Character data type），适合导出为文本/CSV
    # -T: 使用可信连接（Trusted Connection），即使用当前的 Windows 凭证进行身份验证
    # -S: 指定服务器实例
    # 指定导出 ord, title, intro 列
    $query = "SELECT ord, title, intro FROM $db.dbo.$tableName"
    bcp "$query" queryout $outputFile -c -T -S $serverInstance
}
