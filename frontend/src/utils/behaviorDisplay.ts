/**
 * 异常行为描述展示工具：
 * 模拟数据落库时 description 存的是原始证据 JSON，真实告警存的是中文文本。
 * 列表展示统一经过 formatBehaviorDesc，禁止把原始 JSON 直接渲染到表格。
 */

/** 事件类型 → 中文描述（与后端 ingest.EVENT_TYPE_MAP 对齐） */
export const EVENT_TYPE_ZH: Record<string, string> = {
  suspected_fall: "疑似跌倒",
  suspected_violence: "疑似暴力冲突",
  suspected_intense_interaction: "激烈互动",
  abnormal_staying: "异常滞留",
  long_loitering: "长时间徘徊",
  rapid_movement: "快速移动",
  repeated_entry_exit: "反复出入",
  route_deviation: "路线偏离",
  dangerous_zone_proximity: "危险区域靠近",
};

/** 模型规则编码 → 中文说明（未知规则不展示） */
export const RULE_ZH: Record<string, string> = {
  "horizontal posture sustained over time": "水平姿态持续超时",
  "small movement radius over dwell threshold": "活动范围过小且滞留超时",
  "long path with small net displacement": "路径长但位移小（徘徊特征）",
  "image-plane speed exceeded threshold": "移动速度超过阈值",
  "repeated boundary crossings inside the configured window": "时间窗内反复穿越边界",
  "sustained distance from the calibrated route": "持续偏离标定路线",
  "sustained proximity to a configured dangerous zone": "持续靠近危险区域",
  "close pair with sustained high motion": "双人近距离且持续剧烈运动",
  "second track is close and both tracks have high motion": "双人近距离且持续剧烈运动",
};

const UNKNOWN_TEXT = "未知事件";

/** 判断 description 是否是原始证据 JSON 字符串 */
export function isEvidenceJson(text: string | null | undefined): boolean {
  if (!text) return false;
  const trimmed = text.trim();
  if (!trimmed.startsWith("{")) return false;
  try {
    const parsed = JSON.parse(trimmed);
    return typeof parsed === "object" && parsed !== null && "event_type" in parsed;
  } catch {
    return false;
  }
}

/**
 * 统一的行为描述格式化：
 * - 证据 JSON → 事件中文描述（命中规则时括号补充规则译文）；
 * - 普通文本（真实告警）→ 原样返回；
 * - 解析失败或无映射 → “未知事件”，绝不返回原始 JSON。
 */
export function formatBehaviorDesc(description: string | null | undefined, typeName?: string | null): string {
  if (!description) return "";
  const trimmed = description.trim();
  if (isEvidenceJson(trimmed)) {
    try {
      const payload = JSON.parse(trimmed) as {
        event_type?: string;
        evidence?: { rule?: string; source?: string };
      };
      const eventType = typeof payload.event_type === "string" ? payload.event_type : "";
      let zh = EVENT_TYPE_ZH[eventType] || (typeName || "").trim() || UNKNOWN_TEXT;
      const rule = payload.evidence?.rule;
      if (typeof rule === "string" && RULE_ZH[rule]) {
        zh += `（${RULE_ZH[rule]}）`;
      } else if (payload.evidence?.source === "model") {
        zh += "（模型识别）";
      }
      return zh;
    } catch {
      return UNKNOWN_TEXT;
    }
  }
  return description;
}
