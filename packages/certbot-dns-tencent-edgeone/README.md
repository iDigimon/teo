# certbot-dns-tencent-edgeone

腾讯云 EdgeOne（TEO）Certbot DNS-01 插件的兼容包，依赖同版本 `certbot-dns-teo`，共用其实现和 `dns-teo` 插件入口。

两个包发布到 PyPI 后，可选择安装：

```bash
python3 -m pip install certbot-dns-tencent-edgeone
```

尚未发布时，在仓库根目录同时安装本地两个项目：

```bash
python3 -m pip install . ./packages/certbot-dns-tencent-edgeone
```

凭证文件 `~/teo.ini`：

```ini
dns_teo_secret_id = YOUR_SECRET_ID
dns_teo_secret_key = YOUR_SECRET_KEY
```

```bash
chmod 600 ~/teo.ini
certbot certonly \
  --authenticator dns-teo \
  --dns-teo-credentials ~/teo.ini \
  -d example.com \
  -d '*.example.com'
```

站点必须使用 EdgeOne NS 模式并完成 NS 切换。支持 Certbot 3/4/5 和 Python 3.9–3.15：Python 3.9 使用 Certbot 3/4，Python 3.14–3.15 使用 Certbot 4/5；Certbot 3 环境需安装 `pyopenssl<25`。

完整配置、权限及参数见[项目说明](https://github.com/iDigimon/teo#readme)。
