window.DEMO_DATA = {
  "environment": {
    "name": "模拟演示环境",
    "system": "无人机智能巡检系统",
    "operator": "江西省交投数智科技有限公司",
    "limitations": "当前为内部演示环境，不包含真实 DJI、真实 14 算法模型、真实国产卡实测和生产外部系统接入。",
    "testResult": "30/30 PASS",
    "date": "2026-06-17"
  },
  "accounts": [
    {
      "username": "platform_admin",
      "password": "Demo@2026",
      "role": "平台管理员",
      "tenant": "江西省交投数智科技有限公司",
      "tenantType": "PLATFORM_OPERATOR",
      "features": ["飞控", "视觉分析", "数据标注", "训练", "模型发布", "平台运维", "跨租户审计"]
    },
    {
      "username": "customer_flight",
      "password": "Demo@2026",
      "role": "客户飞控用户",
      "tenant": "高速公路运营管理分中心A",
      "tenantType": "CUSTOMER_TENANT",
      "features": ["飞控", "遥测", "媒体同步"]
    },
    {
      "username": "customer_viewer",
      "password": "Demo@2026",
      "role": "客户分析查看员",
      "tenant": "高速公路运营管理分中心A",
      "tenantType": "CUSTOMER_TENANT",
      "features": ["视觉分析结果", "告警", "工单"]
    },
    {
      "username": "customer_annotator",
      "password": "Demo@2026",
      "role": "客户标注用户",
      "tenant": "高速公路运营管理分中心A",
      "tenantType": "CUSTOMER_TENANT",
      "features": ["数据标注", "样本查看"]
    }
  ],
  "units": [
    {"unit": "U0", "name": "基础工程", "code": "规则验收骨架已实现", "test": "PASS", "status": "待正式 API/数据库/统一身份工程化"},
    {"unit": "U1", "name": "飞控平台", "code": "DJI 模拟器、状态机、网络边界规则已实现", "test": "PASS", "status": "真实 DJI 设备/证书/API 待确认"},
    {"unit": "U2", "name": "媒体与分析主链路", "code": "媒体入库、抽帧、分析、事件、工单闭环已实现", "test": "PASS", "status": "真实对象存储、弱网和性能环境待集成"},
    {"unit": "U3", "name": "推理运行时", "code": "Predict 契约和双后端一致性门禁已实现", "test": "PASS", "status": "国产卡仍是候选硬件池，未最终锁定"},
    {"unit": "U4", "name": "数据标注平台", "code": "标注、复检、FROZEN 数据集、导出授权规则已实现", "test": "PASS", "status": "真实标注工具和导出包待工程化"},
    {"unit": "U5", "name": "训练与算法库", "code": "训练授权、模型指标、发布/回滚门禁已实现", "test": "PASS", "status": "真实训练环境和模型仓库待接入"},
    {"unit": "U6", "name": "一期 14 算法接入", "code": "14 算法清单和验收门禁已实现", "test": "PASS", "status": "BLOCKED"},
    {"unit": "U7", "name": "联调验收", "code": "系统级验收门禁已实现", "test": "PASS", "status": "BLOCKED"}
  ],
  "workflow": [
    {"name": "创建飞行任务", "status": "DISPATCHED", "evidence": "ms_demo_001", "owner": "customer_flight"},
    {"name": "DJI 模拟回调", "status": "device_bound", "evidence": "dock-demo-001", "owner": "customer_flight"},
    {"name": "媒体入库", "status": "READY", "evidence": "med_001", "owner": "customer_flight"},
    {"name": "抽帧", "status": "FRAME_READY", "evidence": "frm_001", "owner": "customer_viewer"},
    {"name": "创建分析任务", "status": "COMPLETED", "evidence": "ana_001", "owner": "customer_viewer"},
    {"name": "生成事件", "status": "DISPATCHED", "evidence": "evt_001", "owner": "customer_viewer"},
    {"name": "派发工单", "status": "DISPATCHED", "evidence": "wo_001", "owner": "customer_viewer"}
  ],
  "missions": [
    {"id": "ms_demo_001", "route": "昌北机场互通巡检航线", "dock": "DJI Dock 3 模拟机巢 A", "status": "ANALYSIS_READY", "tenant": "高速公路运营管理分中心A", "battery": "76%", "signal": "-62 dBm"},
    {"id": "ms_demo_002", "route": "赣江新区桥下空间巡检", "dock": "DJI Dock 3 模拟机巢 B", "status": "MEDIA_READY", "tenant": "高速公路运营管理分中心A", "battery": "81%", "signal": "-59 dBm"}
  ],
  "events": [
    {"id": "evt_001", "algorithm": "road_crack", "label": "路面裂缝", "confidence": "0.88", "status": "DISPATCHED", "workOrder": "wo_001", "asset": "G70 福银高速 K612+200"},
    {"id": "evt_002", "algorithm": "road_pothole", "label": "路面坑槽", "confidence": "0.84", "status": "NEEDS_REVIEW", "workOrder": "-", "asset": "G60 沪昆高速 K458+900"},
    {"id": "evt_003", "algorithm": "bridge_under_space_stacking", "label": "桥下空间堆积物", "confidence": "0.79", "status": "NEEDS_GEO_REVIEW", "workOrder": "-", "asset": "待人工定位"}
  ],
  "annotationTasks": [
    {"id": "ann_001", "algorithm": "road_crack", "samples": 42, "status": "REVIEWING", "assignee": "customer_annotator"},
    {"id": "ann_002", "algorithm": "road_pothole", "samples": 36, "status": "ANNOTATING", "assignee": "customer_annotator"},
    {"id": "ds_001", "algorithm": "road_crack", "samples": 128, "status": "FROZEN", "assignee": "dataset"}
  ],
  "algorithms": [
    {"code": "traffic_congestion", "name": "交通拥堵", "target": "召回率 >= 85%，精确率 >= 75%", "status": "PENDING"},
    {"code": "pedestrian_intrusion", "name": "行人闯入", "target": "mAP@50 >= 80%，召回率 >= 85%", "status": "PENDING"},
    {"code": "two_wheeler_intrusion", "name": "两轮车闯入", "target": "mAP@50 >= 80%，召回率 >= 85%", "status": "PENDING"},
    {"code": "road_obstacle", "name": "路面障碍物", "target": "mAP@50 >= 80%，召回率 >= 85%", "status": "PENDING"},
    {"code": "road_construction", "name": "道路施工", "target": "mAP@50 >= 80%，召回率 >= 85%", "status": "PENDING"},
    {"code": "road_crack", "name": "路面裂缝", "target": "mAP@50 >= 75%，召回率 >= 80%", "status": "PENDING"},
    {"code": "road_pothole", "name": "路面坑槽", "target": "mAP@50 >= 75%，召回率 >= 80%", "status": "PENDING"},
    {"code": "road_water", "name": "路面积水", "target": "mAP@50 >= 75%，召回率 >= 80%", "status": "PENDING"},
    {"code": "marking_blur", "name": "路面标线模糊", "target": "mAP@50 >= 75%，召回率 >= 80%", "status": "PENDING"},
    {"code": "helmet_missing", "name": "施工人员未戴安全帽", "target": "mAP@50 >= 85%，召回率 >= 88%", "status": "PENDING"},
    {"code": "vest_missing", "name": "施工人员未穿反光衣", "target": "mAP@50 >= 85%，召回率 >= 88%", "status": "PENDING"},
    {"code": "guardrail_damage", "name": "护栏钢结构破损", "target": "mAP@50 >= 72%，召回率 >= 78%", "status": "PENDING"},
    {"code": "barrier_damage", "name": "隔离栏破损", "target": "mAP@50 >= 72%，召回率 >= 78%", "status": "PENDING"},
    {"code": "bridge_under_space_stacking", "name": "桥下空间堆积物", "target": "mAP@50 >= 72%，召回率 >= 78%", "status": "PENDING"}
  ],
  "hardware": {
    "status": "候选池",
    "note": "显卡清单仅用于候选评估，不是最终硬件锁定结论。",
    "candidates": ["华为昇腾 Atlas 300I Duo / Atlas 350", "寒武纪 MLU370-X8 / MLU590", "海光 DCU / 沐曦 C600 / 摩尔线程 S5000 / 壁仞 BR100"]
  },
  "reports": [
    {"name": "最终测试文档", "path": "docs/60-test-reports/FINAL_TEST_REPORT.md", "status": "30/30 PASS"},
    {"name": "14 算法交付跟踪表", "path": "docs/40-delivery-tracking/algorithm-delivery-tracker.md", "status": "U6 BLOCKED"},
    {"name": "候选硬件池", "path": "docs/30-integrations/视觉算法计划支持显卡清单20260617.md", "status": "候选池"}
  ]
};
