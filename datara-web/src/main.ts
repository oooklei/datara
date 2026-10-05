import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles/theme.css'
import App from './App.vue'
import router from './router'
import { setupComponentStoreBus, useComponentStore } from './stores/componentStore'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus)
app.mount('#app')

/* 工作台优化 Task 5（方案§2.3）：组件规格缓存接线——启动预拉规格（ETag 条件请求），
   发布/回滚/下线广播失效重拉。ensureSpecs 内部自捕获异常（失败置 degraded → 消费方
   profile 兜底，见 GraphWorkbench.schemaFor），不阻断应用挂载；setupComponentStoreBus 幂等。 */
setupComponentStoreBus()
void useComponentStore().ensureSpecs()
