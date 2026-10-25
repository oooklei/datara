import { createPinia } from 'pinia'
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
// 设计令牌层：唯一色值/圆角/阴影/间距真源 + 全局兜底类 + EP 品牌化覆盖
// 权威设计 §4.4.3 风格统一；对标旧前端 datara-web/src/styles/theme.css
import './styles/theme.css'
import App from './App.vue'
import router from './router'

createApp(App).use(createPinia()).use(router).use(ElementPlus).mount('#app')
