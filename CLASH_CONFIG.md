# Clash 配置说明

为了让脚本能够自动切换代理，你需要在 Clash 的配置文件中启用 external-controller 功能。

## 配置步骤：

### 1. 打开 Clash 的配置文件
找到你的 Clash 配置文件 `config.yaml`（通常在 Clash 安装目录下）

### 2. 添加以下配置

```yaml
# RESTful API 配置
external-controller: 127.0.0.1:9090

# 如果需要密码保护（可选）
# secret: 'your_secret_password'
```

### 3. 完整配置示例

```yaml
port: 7890
socks-port: 7891
allow-lan: true
mode: Rule
log-level: info
external-controller: 127.0.0.1:9090

# 如果有密码
# secret: 'your_secret_password'

# 你的代理配置
proxies:
  - {代理配置...}

# 你的规则配置
rules:
  - {规则配置...}
```

### 4. 重启 Clash
修改配置后，重启 Clash 使配置生效。

### 5. 验证配置
打开浏览器访问：`http://127.0.0.1:9090/configs`
如果能看到配置信息，说明 API 已启用。

## 脚本参数说明

如果使用了 secret 密码，在运行脚本时需要设置环境变量：

```bash
# Windows PowerShell
$env:CLASH_SECRET='your_secret_password'

# Windows CMD
set CLASH_SECRET=your_secret_password

# Linux/Mac
export CLASH_SECRET='your_secret_password'
```

## 故障排除

### 问题：无法连接到 Clash API
**解决方案：**
1. 检查 Clash 是否正在运行
2. 确认 external-controller 配置正确
3. 检查端口 9090 是否被占用
4. 如果使用了防火墙，确保允许 9090 端口

### 问题：切换模式失败
**解决方案：**
1. 确认 Clash 配置文件格式正确
2. 检查是否有 secret 密钥需要配置
3. 查看 Clash 日志是否有错误信息

## 常用 API 端点

- `GET http://127.0.0.1:9090/configs` - 获取配置
- `PUT http://127.0.0.1:9090/configs` - 更新配置
- `GET http://127.0.0.1:9090/proxies` - 获取代理列表
- `GET http://127.0.0.1:9090/rules` - 获取规则列表

## 注意事项

1. 确保 external-controller 只在本地监听（127.0.0.1），不要暴露到公网
2. 如果使用了 secret，请妥善保管，不要泄露
3. 修改配置后记得重启 Clash
