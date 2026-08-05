import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "../stores/auth";
import AlertTodoView from "../views/AlertTodoView.vue";
import BehaviorRecordView from "../views/BehaviorRecordView.vue";
import DashboardView from "../views/DashboardView.vue";
import DataIndexView from "../views/DataIndexView.vue";
import DeviceListView from "../views/DeviceListView.vue";
import ForbiddenView from "../views/ForbiddenView.vue";
import HistoryTrackView from "../views/HistoryTrackView.vue";
import LoginView from "../views/LoginView.vue";
import OperationLogView from "../views/OperationLogView.vue";
import PlaceholderView from "../views/PlaceholderView.vue";
import RealtimeTrackView from "../views/RealtimeTrackView.vue";
import RepairOrderView from "../views/RepairOrderView.vue";
import SystemPermView from "../views/SystemPermView.vue";
import SystemRoleView from "../views/SystemRoleView.vue";
import SystemUserView from "../views/SystemUserView.vue";
import UserProfileView from "../views/UserProfileView.vue";
import WorkOrderDetailView from "../views/WorkOrderDetailView.vue";
import LabSimulationView from "../views/LabSimulationView.vue";
import DataBackupView from "../views/DataBackupView.vue";

const placeholder = (title: string, perm: string) => ({ component: PlaceholderView, meta: { title, perm } });

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/dashboard" },
    { path: "/login", component: LoginView, meta: { title: "登录", public: true } },
    { path: "/403", component: ForbiddenView, meta: { title: "无权限" } },
    { path: "/dashboard", component: DashboardView, meta: { title: "总览看板", perm: "dashboard:view" } },
    { path: "/track/realtime", component: RealtimeTrackView, meta: { title: "实时轨迹管理", perm: "track:realtime" } },
    { path: "/track/history", component: HistoryTrackView, meta: { title: "事后轨迹查询", perm: "track:history" } },
    { path: "/device/list", component: DeviceListView, meta: { title: "设备列表管理", perm: "device:view" } },
    { path: "/device/repair-order", component: RepairOrderView, meta: { title: "设备维修工单", perm: "device:repair" } },
    { path: "/data/index", component: DataIndexView, meta: { title: "数据管理", perm: "data:view" } },
    { path: "/data/abnormal-record", component: BehaviorRecordView, meta: { title: "异常行为记录", perm: "behavior:query" } },
    { path: "/data/track-record", component: HistoryTrackView, meta: { title: "轨迹记录", perm: "track:query" } },
    { path: "/data/backup", component: DataBackupView, meta: { title: "数据备份与恢复", perm: "data:view" } },
    { path: "/data/user-profile", component: UserProfileView, meta: { title: "用户资料管理", perm: "person:query" } },
    { path: "/data/operation-log", component: OperationLogView, meta: { title: "系统操作日志", perm: "log:view" } },
    { path: "/alarm/todo", component: AlertTodoView, meta: { title: "告警待办队列", perm: "alarm:view" } },
    { path: "/workorder/detail/:orderId", component: WorkOrderDetailView, meta: { title: "处置工单详情", perm: "alarm:view" } },
    { path: "/lab/simulation", component: LabSimulationView, meta: { title: "模拟实验室", perm: "data:view" } },
    { path: "/lab/records", redirect: "/403" },
    { path: "/system/index", component: SystemPermView, meta: { title: "权限管理", perm: "system:view" } },
    { path: "/system/role", component: SystemRoleView, meta: { title: "角色管理", perm: "system:view" } },
    { path: "/system/user", component: SystemUserView, meta: { title: "账号管理", perm: "system:view" } },
  ],
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  if (!to.meta.public && !auth.isLoggedIn) {
    return { path: "/login", query: { redirect: to.fullPath } };
  }
  if (to.path === "/login" && auth.isLoggedIn) {
    return { path: "/dashboard" };
  }
  const perm = to.meta.perm as string | undefined;
  if (perm && !auth.hasPermission(perm)) {
    return { path: "/403" };
  }
  return true;
});

export default router;
