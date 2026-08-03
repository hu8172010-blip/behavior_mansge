import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./AppShell.vue";
import router from "./router";
import { useAuthStore } from "./stores/auth";
import "./app.css";

const pinia = createPinia();
const app = createApp(App);
app.use(pinia);

const auth = useAuthStore();
auth.restore();

app.use(router).mount("#app");
