# 项目模块化整理计划

## 目标
根据 `crawler-design-document.md` 的设计原则，将项目重构为清晰的模块化结构，提高代码可维护性和可扩展性。

## 当前问题分析

### 文件结构混乱
- 核心模块文件散落在根目录
- 测试文件、工具脚本、文档、构建脚本混杂
- 缺乏清晰的模块边界

### 依赖关系
- `scraper_firefox.py` 依赖 `image_processor`, `auth_service`, `config`
- `scraper_amazon.py` 依赖 `image_processor`, `auth_service`, `config`
- `image_processor.py` 依赖 `auth_service`, `config`
- `auth_service.py` 依赖 `config`
- `ui/` 模块依赖所有核心模块
- `main.py` 依赖 `auth_service`, `ui`

## 新的目录结构

```
ecomm_crawler/
├── main.py                    # 入口文件（保持不变）
├── requirements.txt           # 依赖文件（保持不变）
├── .gitignore                # Git忽略文件（保持不变）
│
├── scrapers/                  # 爬虫模块
│   ├── __init__.py
│   ├── base.py               # 基础爬虫类（提取公共逻辑）
│   ├── aliexpress.py         # AliExpress爬虫（从scraper_firefox.py重构）
│   └── amazon.py              # Amazon爬虫（从scraper_amazon.py重构）
│
├── auth/                      # 认证模块
│   ├── __init__.py
│   └── service.py            # 认证服务（从auth_service.py移动）
│
├── processors/                # 处理模块
│   ├── __init__.py
│   └── image.py              # 图片处理（从image_processor.py移动）
│
├── config/                    # 配置模块
│   ├── __init__.py
│   ├── settings.py           # 主配置（从config.py移动）
│   └── obfuscation.py        # 配置混淆工具（从config_obfuscation.py移动）
│
├── utils/                     # 工具模块
│   ├── __init__.py
│   └── cache.py              # 缓存路径管理（提取公共常量）
│
├── ui/                        # UI模块（保持现有结构）
│   ├── __init__.py
│   ├── main_window.py
│   ├── login_dialog.py
│   └── components/
│       ├── __init__.py
│       ├── scraper_thread.py
│       ├── image_gallery.py
│       ├── sku_gallery.py
│       └── collapsible_section.py
│
├── aws/                       # AWS相关
│   ├── __init__.py
│   └── lambda_function.py    # Lambda函数（从lambda_function.py移动）
│
├── tests/                     # 测试模块
│   ├── __init__.py
│   └── test_s3_upload.py     # S3上传测试（从test_s3_upload.py移动）
│
├── tools/                     # 工具脚本
│   ├── obfuscate_config.py   # 配置混淆工具（从obfuscate_config.py移动）
│   └── README.md             # 工具使用说明
│
├── docs/                      # 文档目录
│   ├── crawler-design-document.md
│   ├── BUILD_INSTRUCTIONS.md
│   ├── BUILD_QUICK_REFERENCE.md
│   ├── COGNITO_IDENTITY_POOL_SETUP.md
│   ├── DYNAMODB_AUTHENTICATION.md
│   └── README.md             # 项目主文档（从readme.md移动）
│
├── build/                     # 构建脚本
│   ├── build_nuitka.ps1
│   ├── build_nuitka_win32.ps1
│   ├── build_nuitka_win64.ps1
│   └── build_nuitka_all.ps1
│
├── cache/                     # 缓存目录（保持不变）
│   ├── products/
│   └── images/
│
└── firefox_real_profile/      # Firefox配置目录（保持不变）
```

## 重构步骤

### 阶段1：创建新目录结构
1. 创建所有新目录
2. 创建必要的 `__init__.py` 文件

### 阶段2：移动和重构核心模块

#### 2.1 配置模块 (config/)
- [ ] 移动 `config.py` → `config/settings.py`
- [ ] 移动 `config_obfuscation.py` → `config/obfuscation.py`
- [ ] 更新 `config/settings.py` 中的导入路径
- [ ] 创建 `config/__init__.py` 导出主要配置

#### 2.2 认证模块 (auth/)
- [ ] 移动 `auth_service.py` → `auth/service.py`
- [ ] 更新导入路径（从 `config` 改为 `config.settings`）
- [ ] 创建 `auth/__init__.py` 导出主要类和函数

#### 2.3 处理模块 (processors/)
- [ ] 移动 `image_processor.py` → `processors/image.py`
- [ ] 更新导入路径
- [ ] 创建 `processors/__init__.py` 导出主要类和函数

#### 2.4 爬虫模块 (scrapers/)
- [ ] 创建 `scrapers/base.py` 提取公共逻辑
- [ ] 移动 `scraper_firefox.py` → `scrapers/aliexpress.py`
- [ ] 移动 `scraper_amazon.py` → `scrapers/amazon.py`
- [ ] 重构两个爬虫类继承自 `BaseScraper`
- [ ] 更新导入路径
- [ ] 创建 `scrapers/__init__.py` 导出主要类

#### 2.5 工具模块 (utils/)
- [ ] 创建 `utils/cache.py` 统一管理缓存路径常量
- [ ] 创建 `utils/__init__.py`

### 阶段3：移动辅助文件

#### 3.1 AWS模块 (aws/)
- [ ] 移动 `lambda_function.py` → `aws/lambda_function.py`
- [ ] 创建 `aws/__init__.py`

#### 3.2 测试模块 (tests/)
- [ ] 移动 `test_s3_upload.py` → `tests/test_s3_upload.py`
- [ ] 更新导入路径
- [ ] 创建 `tests/__init__.py`

#### 3.3 工具脚本 (tools/)
- [ ] 移动 `obfuscate_config.py` → `tools/obfuscate_config.py`
- [ ] 更新导入路径
- [ ] 创建 `tools/README.md`

#### 3.4 文档 (docs/)
- [ ] 移动所有 `.md` 文件到 `docs/`
- [ ] 移动 `schema.txt` 到 `docs/`
- [ ] 创建 `docs/README.md` 索引

#### 3.5 构建脚本 (build/)
- [ ] 移动所有 `.ps1` 文件到 `build/`
- [ ] 更新脚本中的路径引用（如有）

### 阶段4：更新导入语句

#### 4.1 更新所有Python文件的导入
- [ ] `main.py`: `from auth.service import ...`
- [ ] `ui/main_window.py`: 更新所有导入
- [ ] `ui/login_dialog.py`: 更新导入
- [ ] `ui/components/scraper_thread.py`: `from scrapers.aliexpress import ...`
- [ ] 其他所有文件

#### 4.2 确保向后兼容
- [ ] 在根目录创建兼容性导入（可选，用于平滑过渡）

### 阶段5：清理和验证

#### 5.1 删除旧文件
- [ ] 删除根目录下的旧文件（移动后）
- [ ] 删除 `config_obfuscated_values.txt`（临时文件）

#### 5.2 验证功能
- [ ] 运行测试确保所有功能正常
- [ ] 检查导入路径是否正确
- [ ] 验证GUI启动正常
- [ ] 验证爬虫功能正常

## 导入路径映射表

| 旧导入 | 新导入 |
|--------|--------|
| `import config` | `from config import settings as config` 或 `from config.settings import *` |
| `from config_obfuscation import ...` | `from config.obfuscation import ...` |
| `from auth_service import ...` | `from auth.service import ...` |
| `from image_processor import ...` | `from processors.image import ...` |
| `from scraper_firefox import ...` | `from scrapers.aliexpress import ...` |
| `from scraper_amazon import ...` | `from scrapers.amazon import ...` |

## 注意事项

1. **保持功能不变**：重构过程中不改变任何业务逻辑
2. **逐步迁移**：可以分阶段进行，每个阶段完成后验证功能
3. **保留备份**：在开始前建议创建git分支或备份
4. **测试优先**：每个模块移动后立即测试相关功能
5. **文档更新**：更新所有文档中的路径引用

## 预期收益

1. **清晰的模块边界**：每个模块职责单一
2. **易于扩展**：新增站点或功能更容易
3. **更好的测试**：模块化后更容易编写单元测试
4. **降低耦合**：通过清晰的导入关系降低模块间耦合
5. **提高可维护性**：代码组织更清晰，维护更容易

## 风险评估

- **低风险**：主要是文件移动和导入路径更新，不涉及业务逻辑变更
- **缓解措施**：分阶段进行，每阶段完成后充分测试

