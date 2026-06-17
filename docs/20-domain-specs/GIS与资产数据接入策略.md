# GIS 与资产数据接入策略

## 1. 结论

一期正式开发采用：

```text
最小资产台账 + 坐标系可追溯 + 后续 GIS 正式接入适配
```

核心决策：

| 问题 | 决策 |
| --- | --- |
| 道路、桥梁、边坡资产来源 | 先用最小资产台账，生产再对接客户权威 GIS / 交通资产系统 |
| 坐标系 | 开发期以 WGS84 / EPSG:4326 作为内部空间计算基线，同时保留 `source_crs` |
| 路段、桩号、资产编码规则 | 先定义最小内部编码，生产以客户资产编码为准并保留映射 |
| 是否先用最小资产台账 | 是，必须先用，避免 U1/U2 主链路被完整 GIS 阻塞 |

不得在客户 GIS 数据、坐标系和桩号映射未确认前，把某一坐标系或资产来源写成生产最终结论。

## 2. 资产来源策略

| 资产类型 | 一期开发建议 | 生产建议 |
| --- | --- | --- |
| 道路资产 | 维护最小路段台账 | 对接江西省交通现有路网 / GIS / 养护资产系统 |
| 桥梁资产 | 维护桥梁名称、编码、所属路段、桩号范围 | 对接桥梁资产库或 GIS 平台 |
| 边坡资产 | 维护边坡编码、位置描述、所属路段、风险等级 | 对接边坡、地灾或养护资产数据 |
| 坐标几何 | 可先为空或粗略点 / 线 / 面 | 生产使用客户确认的数据源 |

一期开发重点是先跑通：

- 飞行任务绑定巡检目标。
- 任务关联道路、桥梁、边坡资产。
- 检测事件关联资产。
- 无法自动定位时进入人工定位复核。
- 工单可以带出资产信息。

完整 GIS 数据不得成为 U1/U2 主链路开发阻断项。

## 3. 坐标系策略

### 3.1 三层坐标策略

| 层级 | 用途 | 建议 |
| --- | --- | --- |
| 原始坐标 | 保存 DJI、GIS、地图服务原始数据 | 必须保存 `source_crs` |
| 内部计算坐标 | PostGIS 空间查询、事件定位、资产匹配 | 一期先用 WGS84 / EPSG:4326 |
| 生产权威坐标 | 客户正式 GIS / 交通资产系统 | 待客户确认，可能为 CGCS2000 或地方投影坐标 |

### 3.2 坐标系使用建议

| 坐标系 | 使用建议 |
| --- | --- |
| WGS84 | 适合 DJI 遥测、无人机位置、一期开发表内空间字段基线 |
| GCJ-02 | 如使用高德、腾讯等互联网地图底图，可作为显示坐标，不作为权威资产坐标 |
| CGCS2000 | 适合作为生产权威资产坐标，但必须等待客户 GIS 数据确认 |

### 3.3 必须保留的追溯字段

涉及坐标和空间数据的表建议保留：

| 字段 | 说明 |
| --- | --- |
| `source_crs` | 原始坐标系，如 WGS84、GCJ-02、CGCS2000 |
| `source_system` | 数据来源系统 |
| `transform_status` | NOT_REQUIRED / PENDING / SUCCEEDED / FAILED |
| `transform_config_id` | 坐标转换配置 ID |
| `geom` | PostGIS 空间字段，可为空 |
| `raw_location` | 原始位置 JSONB，可选 |

## 4. 最小资产台账

### 4.1 是否必须先做

必须先做最小资产台账。

原因：

1. U1 飞控任务需要绑定巡检目标。
2. U2 事件需要关联道路、桥梁、边坡资产。
3. 一期最低定位目标是 L1 资产级。
4. GIS 来源和坐标系仍是待确认项，不能阻塞 M1 主链路。
5. 后续正式 GIS 接入后，可通过外部资产编码映射升级。

### 4.2 最小字段

| 字段 | 说明 |
| --- | --- |
| `tenant_id` | 所属租户 |
| `asset_type` | road / bridge / slope |
| `asset_code` | 平台内部资产编码 |
| `external_asset_code` | 客户或外部系统资产编码，可空 |
| `asset_name` | 资产名称 |
| `route_code` | 路线编码 |
| `route_name` | 路线名称 |
| `stake_start` | 起点桩号 |
| `stake_end` | 终点桩号 |
| `direction` | 上行 / 下行 / 双向 / 未确认 |
| `side` | 左侧 / 右侧 / 中央 / 未确认，边坡等资产可用 |
| `source_crs` | 原始坐标系 |
| `geom` | PostGIS 几何，可空 |
| `source_system` | 数据来源 |
| `status` | ACTIVE / INACTIVE / ARCHIVED |

### 4.3 最小资产示例

道路：

```text
t_customer_001-road-G70-K612+200-K613+000
```

桥梁：

```text
t_customer_001-bridge-G70-K612+450
```

边坡：

```text
t_customer_001-slope-G70-K613+100-R
```

## 5. 编码规则

### 5.1 内部编码建议

内部资产编码建议：

```text
tenant_id + asset_type + route_code + stake_or_sequence
```

示例：

```text
t_customer_001-road-G70-K612+200-K613+000
t_customer_001-bridge-G70-K612+450
t_customer_001-slope-G70-K613+100-R
```

### 5.2 生产编码原则

生产环境如果客户已有资产编码：

- 以客户资产编码为准。
- 平台内部保留 `external_asset_code`。
- 内部 `asset_code` 继续保持唯一。
- 不直接覆盖历史编码。
- 编码映射变更必须写审计。

### 5.3 桩号格式建议

桩号建议保留结构化字段，避免只存字符串：

| 字段 | 示例 |
| --- | --- |
| `stake_label` | K612+200 |
| `stake_meter` | 612200 |
| `stake_offset_meter` | 200 |

说明：

- `stake_label` 用于展示。
- `stake_meter` 用于排序、范围查询和匹配。
- 生产桩号映射规则待客户确认后再固化。

## 6. 事件定位分级

一期事件定位按以下等级处理：

| 等级 | 名称 | 一期处理 |
| --- | --- | --- |
| L0 | 图像证据级 | 保留帧、检测框、时间、无人机粗略位置 |
| L1 | 资产级 | 通过任务、航线、资产台账关联到道路、桥梁、边坡 |
| L2 | 桩号 / 区段级 | 待 GIS、坐标转换、桩号映射确认后再验收 |
| L3 | 精确空间级 | 二三期目标，一期不承诺 |

如果无法自动定位到资产，事件必须进入：

```text
NEEDS_GEO_REVIEW
```

由人工修正资产、桩号或地图点位后，再生成正式工单。

## 7. 数据库字段建议

本策略与 `docs/20-domain-specs/数据库建模边界与PostGIS启用策略.md` 配套执行。

| 表 | 字段建议 |
| --- | --- |
| `road_assets` | `tenant_id`, `asset_code`, `external_asset_code`, `route_code`, `stake_start`, `stake_end`, `source_crs`, `geom geometry(LineString, 4326)` |
| `bridge_assets` | `tenant_id`, `bridge_code`, `external_asset_code`, `route_code`, `center_stake`, `start_stake`, `end_stake`, `source_crs`, `geom geometry(Geometry, 4326)` |
| `slope_assets` | `tenant_id`, `slope_code`, `external_asset_code`, `route_code`, `stake_start`, `stake_end`, `side`, `risk_level`, `source_crs`, `geom geometry(Polygon, 4326)` |
| `coordinate_transforms` | `source_crs`, `target_crs`, `method`, `params`, `status` |
| `routes` | `tenant_id`, `route_code`, `path_geom geometry(LineString, 4326)` |
| `route_versions` | `tenant_id`, `route_id`, `version`, `path_geom geometry(LineString, 4326)` |
| `flight_events` | `tenant_id`, `mission_id`, `device_sn`, `location geometry(Point, 4326)`, `source_crs`, `raw_payload` |
| `frame_assets` | `tenant_id`, `media_file_id`, `frame_time`, `geo_hint`, `location geometry(Point, 4326)` |
| `events` | `tenant_id`, `location geometry(Point, 4326)`, `location_level`, `evidence`, `status` |
| `event_asset_links` | `tenant_id`, `event_id`, `asset_type`, `asset_id`, `confidence`, `reviewed_by` |

## 8. 与飞控和分析链路的关系

### 8.1 U1 飞控

最小资产台账用于：

- 航线绑定巡检资产。
- 飞行任务选择巡检目标。
- 任务审批时展示路段、桥梁、边坡范围。
- 遥测和任务日志关联资产。

### 8.2 U2 视觉分析

资产数据用于：

- 检测结果聚合为业务事件。
- 事件绑定道路、桥梁、边坡。
- 低置信或定位不确定事件进入人工复核。
- 工单携带资产信息。
- 误报漏报回流时保留资产来源。

### 8.3 U4/U5 标注与训练

资产数据用于：

- 样本来源追踪。
- 数据集场景覆盖统计。
- 按路段、桥梁、边坡筛选样本。
- 模型评估按资产类型和场景分组。

## 9. 待确认项

以下事项不得自行做最终决策：

| 待确认项 | 影响 |
| --- | --- |
| 客户权威 GIS 数据来源 | 影响生产资产导入 |
| 坐标系 | 影响空间字段、坐标转换、地图展示 |
| 桩号映射规则 | 影响 L2 定位验收 |
| 资产编码规范 | 影响与客户资产系统对接 |
| 地图底图来源 | 影响 GCJ-02 / WGS84 / CGCS2000 展示转换 |
| 资产更新频率 | 影响同步任务和数据版本 |

处理规则：

- 可先做最小资产台账。
- 可先做导入模板。
- 可先做坐标转换配置表。
- 必须标注待确认。
- 不得把最小台账写成生产权威 GIS 已接入。

## 10. 验收建议

### 10.1 M1 / 演示环境

可验收：

- 任务可绑定最小资产。
- 事件可关联资产。
- 工单可展示资产信息。
- 无法定位时进入 `NEEDS_GEO_REVIEW`。
- 资产数据按 `tenant_id` 隔离。

不可声称：

- 权威 GIS 已接入。
- 坐标转换精度已生产验收。
- 桩号映射已生产验收。

### 10.2 生产 / U7

需补齐：

- 客户确认的 GIS 数据源。
- 坐标系说明。
- 资产编码规则。
- 桩号映射规则。
- 坐标转换测试报告。
- 资产导入校验报告。
- L1 / L2 定位验收记录。

## 11. 正式开发执行原则

后续 U1、U2、数据库和 GIS 相关开发按本文件执行：

1. 先建最小资产台账。
2. 从第一版启用 PostGIS。
3. 所有资产必须包含 `tenant_id`。
4. 所有空间数据必须保留 `source_crs`。
5. 生产权威 GIS 未确认前，不写死最终坐标系。
6. 内部计算优先使用 WGS84 / EPSG:4326。
7. GCJ-02 只作为地图展示适配，不作为权威资产坐标。
8. CGCS2000 等生产坐标系待客户确认后接入。
9. 无法自动定位的事件进入 `NEEDS_GEO_REVIEW`。
10. 最小资产台账可用于 M1 和演示，但不得声明生产 GIS 已完成。
