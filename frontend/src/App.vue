<template>
  <el-container style="min-height: 100vh; padding: 24px">
    <el-main>
      <el-card shadow="never">
        <template #header>
          <span>高校分级智能排课系统（多级通用版）</span>
        </template>
        <el-alert
          title="T1.1 工程骨架已就绪"
          type="success"
          description="支持单院系独立启动与全校多级统筹协同，下一步将接入 T1.2 数据库迁移与 T1.4 CP-SAT 求解引擎。"
          show-icon
          :closable="false"
        />
      </el-card>
    </el-main>
  </el-container>
</template>
