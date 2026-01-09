# 项目概述

本项目是一个桌面端电商爬虫与选品辅助工具，核心流程是：
- 在本地通过 Firefox + Selenium **人工辅助**爬取 AliExpress / Amazon 商品数据与图片；
- 将结构化商品数据与图片缓存到本地 `cache` 目录，并按 `product_id` 分文件保存；
- 通过 AWS API Gateway + Lambda + Bedrock 对抓取的内容进行**文案与定价辅助生成**；
- 通过 DynamoDB 与 S3（经 CloudFront）持久化部分结构化数据与处理后的图片；
- 由人工在 GUI 中审核后，再用于 Amazon 上架与后续处理。

运行形态：
- 入口为 `main.py`，使用 PySide6 GUI，打包为本地可执行程序运行；
- 爬虫核心逻辑在 `scraper_firefox.py`（AliExpress）和 `scraper_amazon.py` 中；
- 图像处理与 S3 上传逻辑在 `image_processor.py`；
- AI 文案与定价辅助逻辑在远端 `lambda_function.py` 中实现，通过 `API_GATEWAY_URL` 调用。

**重要约束：**
- 依赖真实 Firefox 浏览器、真实用户登录与手动处理 CAPTCHA；
- 不做全自动“无人值守”暴力爬取，所有搜索入口、登录、复杂验证码均假定由人工配合。


## 核心目标（Goals）

- **G1 – AliExpress → Amazon 上架准备：**  
  从 AliExpress 商品详情页和搜索结果页抓取用于 Amazon 上架的原始素材（标题、价格、图片、属性、描述、卖点、SKU 组合等），并为每个 AliExpress 商品生成一个稳定的 `product_id` 与本地 JSON。

- **G2 – 竞争价格感知：**  
  在抓取 AliExpress 商品时，**可选地**使用当前 Selenium 实例访问 Amazon 搜索页，抓取若干竞争商品价格，用于后续定价辅助（不做自动改价/监控，只做一次性采样）。

- **G3 – AI 辅助内容生成：**  
  将抓取到的标题 / 卖点 / 描述与价格信息拼接为 `input_text`，发送到已部署的 AWS API Gateway / Lambda / Bedrock，获得结构化输出（标题、要点、描述与价格统计），写回到本地商品 JSON 中。

- **G4 – 图片标准化与托管：**  
  对商品图片（主图、描述图、SKU 图）进行本地处理（缩放/填充到固定尺寸）后，上传到 S3，并记录对应 CloudFront URL（`*_recommended` 字段）到商品 JSON 中。

- **G5 – 图形界面协作：**  
  通过 PySide6 GUI（`ui/main_window.py` 等）管理爬取任务、状态展示与人工审核，保证用户可以在 GUI 中**查看 / 复用 / 审核**本地缓存的数据与图片。


## 非目标（Non-Goals）

- **NG1 – 不自动下单 / 不直接操作电商账户：**  
  不实现任何下单、支付、购物车操作，也不在 Amazon 卖家后台执行自动上架或改价操作。

- **NG2 – 不实现无人值守的大规模爬虫集群：**  
  不做分布式调度、任务队列、调度中心等；当前设计假定为**单机 + 人工参与**模式。

- **NG3 – 不做长期价格监控 / 竞品追踪系统：**  
  Amazon 价格抓取仅用于**调用时的一次性参考**，不是持续监控系统。

- **NG4 – 不在本项目中定义业务决策逻辑：**  
  不在代码中固化复杂的定价规则 / 上架规则，AI 输出仅为参考文本与简单价格统计，不直接驱动业务决策。


## 数据来源与类型

- **站点 / 平台**
  - AliExpress：商品详情页 + 搜索结果页（通过 `scraper_firefox.AliExpressScraper`）。
  - Amazon：商品详情页 + 搜索结果页（通过 `scraper_amazon.AmazonScraper`，以及 AliExpress 抓取中的 `search_amazon_prices_with_driver` 辅助搜索）。

- **访问方式**
  - 真实 Firefox 浏览器 + Selenium WebDriver（`webdriver.Firefox`），使用本地 `firefox_real_profile` 目录；
  - 手动登录与手动解决 CAPTCHA（在控制台或 GUI 中暂停提示，等待用户点击“Resume”或按回车）；
  - 部分图片通过 `requests` 直接下载（缓存与 S3 上传前使用）。

- **页面类型**
  - AliExpress：
    - 商品搜索结果页：通过 `SEARCH_ITEM_SELECTOR` 选出商品链接，再逐个进入详情；
    - 商品详情页：通过配置在 `config.py` 中的一组 CSS 选择器提取标题、价格、图片、SKU、描述、卖点等。
  - Amazon：
    - 商品搜索结果页：通过 `AMAZON_SEARCH_ITEM_SELECTOR` / `AMAZON_SEARCH_ITEM_FALLBACK` 提取商品链接；
    - 商品详情页：通过 `config.py` 中的 Amazon 相关 CSS 选择器提取标题、品牌、价格、评分、图片、SKU、描述等。

- **外部 API / 云服务**
  - AWS API Gateway（`config.API_GATEWAY_URL`）：接收 `input_text` 及价格信息，调用后端 `lambda_function.py`；
  - AWS Lambda（`lambda_function.py`）：使用 Bedrock 模型（Anthropic Claude）生成结构化电商文案与价格建议；
  - AWS DynamoDB：按 `config.DYNAMODB_TABLE`（例如 `AliExpressProducts`）存储结构化商品数据（通过 `auth_service.get_dynamodb_resource()` 获取）；
  - AWS S3 + CloudFront：存储与分发经 `image_processor.ImageProcessor` 处理后的图片。


## 爬取策略概览

- **总体流程（AliExpress 主路径）**
  1. 用户在 Firefox 中**手工导航**到 AliExpress 搜索结果页，并登录其账户；
  2. `AliExpressScraper.scrape_search_results()` 暂停等待用户确认（或 GUI Resume），然后：
     - 通过 `config.SEARCH_ITEM_SELECTOR` 找到所有商品链接；
     - 过滤为 `/item/` 详情链接，去重后按 `MAX_PRODUCTS_TO_SCRAPE` 限制数量；
  3. 对每个目标链接调用 `scrape_product_details(url)`：
     - 生成 `product_id`（UUID）；
     - 加载商品详情页，随机等待（基于 `config.WAIT_*` 配置）；
     - 检测并处理 CAPTCHA（人工），必要时等待 GUI `resume_event`；
     - 在不大量滚动前，优先解析 SKU 行与 SKU 组合，并对每个组合自动点击、读取当前价格（避免滚动后 DOM 改变导致丢失）；
     - 依次提取：
       - 标题 / 当前价格 / 原价；
       - 主图 / 图集图片；
       - SKU 列表（名称、图片、本组合价格）；
       - 描述文本 + 描述图片（包括 Shadow DOM / SEO 描述 / A+ 内容等多种路径）；
       - 卖点列表（卖家自填要点区域）；
     - （可选）根据商品标题调用 `search_amazon_prices_with_driver`，抓取若干 Amazon 搜索结果的标题、价格与链接，并计算：
       - `amazon_avg_price`、`amazon_min_price`、`amazon_min_price_product`、`amazon_min_price_product_url` 等统计字段；
     - 构造 `input_text` 与价格 payload，经 API Gateway 调用远端 Lambda / Bedrock，获取结构化输出字段：
       - `suggested_title`、`suggested_seller_point`、`suggested_description`；
     - 使用 `image_processor.process_product_images`：
       - 以远程 URL 为源，下载并处理主图 / 描述图 / SKU 图；
       - 上传到 S3，记录对应 CloudFront URL 到 `*_recommended` 字段；
     - 将最终结构化商品数据保存到本地 `cache/products/{product_id}.json`。

- **Amazon 辅助爬取流程**
  - 与 AliExpress 类似的 Selenium + 手工登录 + 手工处理 CAPTCHA 流程；
  - `AmazonScraper.scrape_search_results()` 从搜索结果页抽取若干商品链接，再对每个链接调用 `scrape_product_details(url)`；
  - 提取字段与 AliExpress 相似，但以 Amazon 站点为主（包含 `asin`、品牌、评分、评论数等）。

- **等待与节奏控制**
  - 所有页面加载、滚动、元素等待等使用 `config.WAIT_PAGE_LOAD` / `WAIT_SCROLL` / `WAIT_ELEMENT_LOAD` / `WAIT_BETWEEN_ACTIONS` / `WAIT_BETWEEN_PRODUCTS` 控制；
  - 这些值使用**随机区间**（`random.uniform`）实现，避免固定间隔带来的模式风险；
  - 当前源码未内置严格的 QPS / 并发上限，**后续如需更强的频率限制，必须通过修改 `config.py` 与相关 wait 函数实现，而不是在业务逻辑中硬编码常量**。

- **人工参与点**
  - 登录 AliExpress / Amazon 账号；
  - 手工处理登录验证码 / 图形验证码 / 滑块等；
  - 当 `_check_and_handle_captcha()` 检测到 CAPTCHA 时，在命令行按下回车或在 GUI 中点击“Resume”；
  - 通过 GUI 查看/筛选/审核本地 JSON 数据与图片，决定是否进一步用于 Amazon 上架。


## 失败与异常的设计原则

- **登录 / 认证 / 权限**
  - GUI 启动时通过 `auth_service` 进行登录与 Session 校验，失败时不应静默忽略；
  - `Application._validate_session` 只在明确检测到 `AccessRevokedError` 时强制退出应用，其余网络错误或暂时性校验失败应**记录日志但不中断运行**；
  - 修改任何认证相关逻辑时，必须保证：
    - 不在后台静默降级为“匿名模式”继续访问云端资源；
    - 不缓存明文密码，所有长期凭证必须通过 `keyring` 或 AWS 官方机制管理。

- **爬取过程中的异常**
  - 单个商品页面爬取失败时，应：
    - 在控制台打印错误信息（并尽量带上 `product_id` / URL）；
    - **不中断整个批次**的爬取流程，继续处理后续商品；
    - 对于失败商品，允许写入带有 `status='error'` 或缺失字段的 JSON，但不得伪造成功状态。
  - 在解析 DOM 的过程中，所有局部字段提取都应包裹 `try/except`，并写入安全的默认值（例如 `"N/A"`、空列表、空字符串）。

- **反爬 / CAPTCHA 处理**
  - 当 `_check_and_handle_captcha()` / `_check_captcha()` 检测到反爬机制时，必须**暂停 Selenium 自动操作**，等待人工解决；
  - 不允许在此项目中引入未经授权的验证码识别服务或模拟人类操作的外挂逻辑；
  - 当用户解决完成并点击 Resume 后，可以适当增加 `WAIT_PAGE_LOAD` 或额外 `sleep`，保证页面状态稳定再继续爬取。

- **外部服务（API Gateway / DynamoDB / S3 / Bedrock）失败**
  - API Gateway / Lambda / Bedrock：
    - 当调用失败时（HTTP 错误、超时、解析 JSON 失败、命中 `FORBIDDEN_RETURN_WORD` 等），应：
      - 在控制台打印详细错误与 `raw_output`（若安全可行）；
      - 将 `suggested_*` 字段设为空字符串；
      - 仍然继续保存本地 JSON 与已抓取的原始字段，避免数据整体丢失。
  - DynamoDB：
    - 当 `auth_service.get_dynamodb_resource()` 失败时，当前实现会退化到本地-only 模式；
    - AI 修改代码时，不得假设 DynamoDB 一定可用，所有写入必须是“可选增强”，而不是“必经路径”。
  - S3 / CloudFront：
    - 如果图片处理或上传失败，`*_recommended` 字段可以为空；
    - 不得删除原始本地图片路径或远程源 URL 字段，确保后续有机会重试上传。

- **本地文件与缓存**
  - 所有本地 JSON 与图片写入路径应通过统一的 `CACHE_DIR` / `PRODUCT_CACHE_DIR` / `IMAGE_CACHE_DIR` 管理；
  - AI 修改路径时，必须保证：
    - 不覆盖已有文件语义（例如不要复用同一个 `product_id` 文件保存不同站点的数据）；
    - 不在爬虫主流程中引入大规模清空缓存的行为（如 `rm -rf cache`），清理操作应由明确的维护脚本执行。


## 扩展与演进方向（仅列方向，不做设计）

- **方向 E1 – 频率控制与限流策略显式化：**  
  在不改变现有使用体验前提下，把当前基于随机等待的节奏控制，演进为可配置的“站点级限流策略”（例如：每站点最大并发、每分钟最大请求数），集中定义在 `config.py` 中。

- **方向 E2 – 数据 Schema 与版本管理：**  
  为本地 JSON 与 DynamoDB 中的商品结构引入**显式版本号**与最小字段集约束，保证未来字段增减时，旧数据仍可被 GUI 与后端 Lambda 正确处理。

- **方向 E3 – GUI 与爬虫的解耦：**  
  在维持现有 GUI 使用体验的同时，逐步把爬虫执行部分封装为“工作单元”（job），从而支持更清晰的任务重试 / 状态展示 / 批次管理。

- **方向 E4 – 多站点支持与配置驱动化：**  
  在不重写核心逻辑的前提下，引入更清晰的“站点配置层”（选择器 / 反爬策略 / 价格字段映射），以支持更多电商站点或不同区域版本。

- **方向 E5 – AI 行为约束强化：**  
  为本项目单独维护一份“AI 贡献者守则”（可在后续文档中补充），明确哪些模块可以自由重构、哪些模块只能在保持行为等价的前提下优化，尤其是认证、反爬处理、频率控制和数据 Schema 等关键路径。


