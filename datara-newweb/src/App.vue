<template><div class="app-shell"><header>Datara</header><aside aria-label="主导航"></aside><main><RouterView /></main><div id="ai-assistant-global-mount" aria-label="AI 助手全局挂载点"></div></div></template>
<style scoped>.app-shell{display:grid;grid-template:"header header" 56px "aside main" 1fr/240px 1fr;min-height:100vh}header{grid-area:header}aside{grid-area:aside}main{grid-area:main}</style>
