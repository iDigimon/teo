# Certbot DNS EdgeOne (TEO) 插件

通过腾讯云 EdgeOne API 完成 Certbot DNS-01 验证，支持普通域名和泛域名。

站点必须已通过 **NS 模式接入 EdgeOne**，并完成权威 DNS 服务器切换。CNAME 接入、DNSPod 托管接入及 Pages 站点请使用实际权威 DNS 服务商的插件；本插件不会修改 DNSPod。

## 功能特性

- 使用官方腾讯云 TEO SDK（API 版本 `2022-09-01`）
- 自动分页查询站点，按 DNS 标签边界选择最长匹配的站点，支持 IDN
- 支持同名多个 TXT 验证值，仅删除本次创建的记录，保留已有记录
- 支持临时凭证，可指定站点 ID 解决同名站点歧义
- 支持 Certbot 3/4/5，Python 3.9–3.15

Python 3.9 使用 Certbot 3/4（Certbot 4.2 起要求 Python ≥3.9.2）；Python 3.14–3.15 使用 Certbot 4/5。
Certbot 3 环境需额外安装 `pyopenssl<25`。

## 安装

在本仓库目录安装，插件和 Certbot 必须处于同一个 Python 环境：

```bash
python3 -m pip install .
# 或使用 uv 创建独立工具环境
uv tool install --with . 'certbot>=5,<6'
```

也可安装兼容包 `certbot-dns-tencent-edgeone`，它依赖同版本的 `certbot-dns-teo`，共用实现和插件入口。在仓库根目录同时安装两个本地项目：

```bash
python3 -m pip install . ./packages/certbot-dns-tencent-edgeone
```

两个包发布到 PyPI 后，也可用 `python3 -m pip install certbot-dns-tencent-edgeone` 安装。
使用任一包时，认证器均为 `dns-teo`，命令行参数和凭证前缀均保持 `dns-teo-` / `dns_teo_`。

## 配置文件

保存为 `~/teo.ini`：

```ini
dns_teo_secret_id = YOUR_SECRET_ID
dns_teo_secret_key = YOUR_SECRET_KEY
# 使用临时凭证时填写
# dns_teo_token = YOUR_SESSION_TOKEN
# 可选：仅允许操作指定的 NS 站点，同名站点有歧义时必须指定
# dns_teo_zone_id = zone-xxxxxxxxxxxx
```

```bash
chmod 600 ~/teo.ini
```

## 运行

```bash
certbot certonly \
  --authenticator dns-teo \
  --dns-teo-credentials ~/teo.ini \
  --dns-teo-propagation-seconds 30 \
  -d example.com \
  -d '*.example.com'
```

TXT TTL 默认 600 秒，可用 `--dns-teo-ttl` 设置为 60–86400 秒。
传播等待默认 30 秒，由 Certbot 在所有挑战记录创建后统一执行；如 DNS 尚未生效，可增加 `--dns-teo-propagation-seconds`。
成功签发后可用 `certbot renew` 续期，Certbot 会保存认证器和凭证路径。

## 腾讯云权限配置

SecretId / SecretKey 所属账号需要以下操作权限（CAM 自定义策略）：

```json
{
  "version": "2.0",
  "statement": [{
    "effect": "allow",
    "action": [
      "teo:DescribeZones",
      "teo:DescribeDnsRecords",
      "teo:CreateDnsRecord",
      "teo:DeleteDnsRecords"
    ],
    "resource": ["*"]
  }]
}
```

使用公共端点 `teo.tencentcloudapi.com`，不需要配置 Region。
指定 `dns_teo_zone_id` 后仍需 `DescribeZones` 权限，以校验域名范围和 NS 接入状态。

## 开发与验证

```bash
uv sync --locked --all-packages --python 3.13
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pytest --cov=certbot_dns_teo --cov-report=term-missing
uv run --no-sync tox run-parallel -p 4
uv build --all-packages --out-dir dist --clear
uv run --no-sync twine check --strict dist/*
uv run --no-sync python scripts/check_alias_installation.py
```

测试使用真实 SDK 请求/响应对象和 ACME 挑战对象，mock 云端调用，不修改真实 DNS 或申请证书。
兼容矩阵覆盖 Python 3.9–3.13 × Certbot 3、Python 3.9–3.15 × Certbot 4、Python 3.10–3.15 × Certbot 5；tox 从源码目录之外验证 wheel 和实际 Certbot CLI 插件发现。
GitHub Actions 执行相同检查，并在全新环境中仅以兼容包为安装目标，验证其自动安装核心依赖且 Certbot 只发现一个 `dns-teo` 插件。
两个包版本保持一致，兼容包的依赖固定为同版本核心包；升级时需同时修改根目录和 `packages/certbot-dns-tencent-edgeone/pyproject.toml` 中的版本及依赖，测试会检查一致性。
发布 `v1.0.0` 格式的正式 GitHub Release 后，经 CI 通过使用 PyPI Trusted Publishing 先发布核心包，再发布兼容包。两个包使用独立发布 job，各自的 environment URL 指向对应的 PyPI 项目。两个 PyPI 项目均需配置此仓库的受信任发布者（`release.yml` 工作流、GitHub `pypi` environment）。预发布仅验证和构建。

参考实现：[certbot-dns-tencent](https://github.com/iDigimon/certbot-dns-tencent)。
接口文档：[站点列表](https://cloud.tencent.com/document/api/1552/80713)、[DNS 记录列表](https://cloud.tencent.com/document/api/1552/80716)、[创建记录](https://cloud.tencent.com/document/api/1552/80720)、[删除记录](https://cloud.tencent.com/document/api/1552/80718)。
