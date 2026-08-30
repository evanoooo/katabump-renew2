## 🚀 katabump 自动续期（GitHub Actions）

这是一个基于 GitHub Actions 的自动化脚本，用于定时登录自动续期 [katabump](https://dashboard.katabump.com) 应用，现已全面支持**多账号批量自动续期**与**独立环境隔离**。

⚠️ 有 CF 盾，太差的机房节点可能过不了，建议使用干净的住宅代理或质量较好的节点。

━━━━━━━━━━━━━━━━━━━━━━

### 🔐 Secrets 配置说明

| Secret 名称 | 是否必填 | 说明 |
| :--- | :--- | :--- |
| `KATABUMP_EMAIL` | ✅ 必填 | katabump 登录邮箱（支持单账号或多账号） |
| `KATABUMP_PASSWORD` | ✅ 必填 | katabump 登录密码（支持单密码或多密码） |
| `KATABUMP_ACCOUNTS` | ❌ 可选 | 账号密码组合列表（可选，填入后优先使用） |
| `NODE_LINK` | ❌ 可选 | 代理链接（支持填入单行或多行换行填入多个备用节点） |
| `TG_BOT_TOKEN` | ❌ 可选 | Telegram Bot Token（用于推送续期结果） |
| `TG_CHAT_ID` | ❌ 可选 | Telegram Chat ID（接收通知的用户或群组 ID） |

━━━━━━━━━━━━━━━━━━━━━━

### 👥 多账号配置方式（任选其一即可）

#### 方式一：多行或逗号分隔（推荐）

- **`KATABUMP_EMAIL`**（支持换行或逗号分隔）：
  ```text
  account1@gmail.com
  account2@gmail.com
  account3@gmail.com
  ```
  *(也可以写成 `account1@gmail.com, account2@gmail.com, account3@gmail.com`)*

- **`KATABUMP_PASSWORD`**（与邮箱顺序一一对应）：
  ```text
  password_for_acc1
  password_for_acc2
  password_for_acc3
  ```
  *(💡 若所有账号使用相同密码，只需在 `KATABUMP_PASSWORD` 中填写一个密码即可！)*

---

#### 方式二：邮箱与密码组合填入

直接在 `KATABUMP_EMAIL` 或 `KATABUMP_ACCOUNTS` 中按行填入 `邮箱:密码` 或 `邮箱----密码`（无需单独配置 `KATABUMP_PASSWORD`）：
```text
account1@gmail.com:password123
account2@gmail.com:password456
```

---

#### 方式三：单账号模式（完全向前兼容）

- **`KATABUMP_EMAIL`**: `your_email@gmail.com`
- **`KATABUMP_PASSWORD`**: `your_password`

━━━━━━━━━━━━━━━━━━━━━━

### 🌐 代理格式（确认在 v2rayN / Clash 里使用正常的节点）

`NODE_LINK` 支持按行填入一个或**多个备用节点**（支持换行分隔，脚本会自动按顺序尝试，直到连接成功）：

```text
vless://uuid1@server1:port?security=reality&sni=...
hysteria2://auth@server2:port?sni=...
socks5://user:pass@server3:port
```

支持以下任意一种代理协议的完整分享链接（不配置则直连）：
- **VLESS**：`vless://uuid@server:port?security=reality&sni=...&type=ws&...`
- **VMess**：`vmess://base64encoded...`
- **Trojan**：`trojan://password@server:port?sni=...&type=ws&...`
- **tuic**：`tuic://uuid:password@server:port...`
- **anytls**：`anytls://uuid@server:port...`
- **hysteria2**：`hysteria2://base64@server:port...`
- **SOCKS5**：`socks5://user:pass@server:port` 或 `socks://user:pass@server:port`

━━━━━━━━━━━━━━━━━━━━━━

### 💡 特性与注意事项

1. **会话环境隔离**：每个账号均在独立干净的浏览器进程和会话中运行，Cookie 与缓存互不干扰。
2. **容错保障**：单个账号因密码错误或网络波动失败不会中断其他账号的执行。
3. **智能通知**：每个账号执行完成后推送实时通知，多账号全部完成后自动推送汇总报告。
4. **频率保护**：账号切换之间内置缓冲延迟，减少触发 Cloudflare 风控的概率。
5. **定时配置**：可在 `.github/workflows/renew.yml` 中修改 cron 触发时间（建议在服务到期前 1~2 天）。
