# 更新记录

## 0.1.0

- 实现腾讯云 EdgeOne (TEO) 的 Certbot DNS-01 插件 `dns-teo`。
- 支持 NS 站点发现、泛域名、多 TXT 值、已有记录保护和临时凭证。
- 提供 Certbot 3/4/5 兼容测试、wheel 检查与 CI/CD。
- 新增兼容发行包 `certbot-dns-tencent-edgeone`，依赖同版本 `certbot-dns-teo`，继续使用 `dns-teo` 插件及原有配置；支持双包构建、安装验证和按依赖顺序发布。
