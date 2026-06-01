# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 语言

所有对话、代码注释、提交信息、文档必须用中文。

## 项目概述

海森堡抖音评论查询 — 从指定抖音视频抓取特定用户的一级评论 + 二级回复（楼中楼），GUI 展示完整对话链。

## 核心架构

### 一级评论（Playwright 拦截）

`crawler.py` 用 Playwright 打开 Chromium，在浏览器内注册 `page.on("response")` 拦截 `/aweme/v1/web/comment/list/` API 响应。滚动评论区触发懒加载，`_extract_comment_data()` 从 JSON 提取每条评论的文本、图片、贴纸、点赞、时间、IP、用户标识。

### 二级回复（httpx + execjs 签名）

`sign.py` + `douyin.js` 用 execjs 生成 a_bogus 签名，`crawler.py` 从浏览器提取 Cookie 后用 httpx 直接调 `/aweme/v1/web/comment/list/reply/` API。返回数据用 `reply_to_reply_id` 字段搭嵌套树，显示完整对话链。

### GUI（CustomTkinter）

`gui.py` 暗色主题双标签页界面。爬虫在后台线程运行，print 重定向到日志框。结果用彩色标签渲染：目标用户金色背景 + 橙色箭头 ◀ 标记，青色粗体树线 `├──` `└──` `│` 展示层级，圆圈序号 ①②③ 按时间排序。

### 数据处理

`output.py` — 含递归匹配 `filter_by_douyin_id()`（支持深层嵌套回复），`compute_stats()`（含回复统计），JSON / TXT 输出。

## 关键约束

- **不要动 kkk 目录**：ylc114514 / ylc114514aaa 是实验副本，只在桌面文件夹操作
- **不要改爬取方法**：一级=拦截、二级=httpx+签名，这是已验证的稳定方案
- **git push 需手动**：在 kkk 文件夹下 `git push origin master`

## 环境

- Python 3.12，依赖见 `requirements.txt`
- 需要 Node.js（execjs 执行 douyin.js），通过 `pip install nodejs-bin` 获取
- Playwright Chromium：`python -m playwright install chromium`
- 运行 GUI：`python gui.py` 或双击 `gui启动.bat`
- 命令行模式：`python main.py`
