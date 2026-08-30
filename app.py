#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import json
import time
import shutil
import tempfile
import subprocess
import requests
from seleniumbase import SB

# 从环境变量获取 TG 配置
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID", "").strip()    # tg通知 chat id(可选)
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()  # tg通知bot token(可选)

BASE_URL = "https://dashboard.katabump.com"  # 网站链接


# ===== 工具函数 =====

def mask_email(email: str) -> str:
    """邮箱脱敏显示，保护隐私"""
    if not email:
        return "未知"
    if '@' in email:
        name, domain = email.split('@', 1)
        if len(name) > 4:
            return f"{name[:2]}****{name[-2:]}@{domain}"
        elif len(name) > 2:
            return f"{name[0]}****{name[-1]}@{domain}"
        else:
            return f"{name}****@{domain}"
    if len(email) > 4:
        return f"{email[:2]}****{email[-2:]}"
    return email[:2] + '****'


def parse_accounts() -> list[tuple[str, str]]:
    """
    智能解析多账号配置，支持以下多种格式：
    1. KATABUMP_ACCOUNTS: 
       - 组合格式: "a@b.com:pwd\nc@d.com:pwd2" 或 "a@b.com:pwd,c@d.com:pwd2"
       - JSON 格式: [{"email":"a@b.com","password":"pwd"}, ...]
    2. KATABUMP_EMAIL & KATABUMP_PASSWORD:
       - 组合格式填入 KATABUMP_EMAIL: "a@b.com:pwd\nc@d.com:pwd2" 或逗号/分号分隔
       - 换行分隔: EMAIL="a@b.com\nc@d.com", PASSWORD="pwd1\npwd2"
       - 逗号/分号/冒号分隔: EMAIL="a@b.com:c@d.com", PASSWORD="pwd1:pwd2"
       - 单密码多账号: EMAIL="a@b.com,c@d.com", PASSWORD="pwd" (共用同一密码)
       - 单账号 (向前兼容): EMAIL="a@b.com", PASSWORD="pwd"
    3. 编号环境变量:
       - KATABUMP_EMAIL_1, KATABUMP_PASSWORD_1, KATABUMP_EMAIL_2...
    """
    accounts = []
    seen = set()

    def add_account(u: str, p: str):
        u = u.strip()
        p = p.strip()
        if u and p and u not in seen:
            seen.add(u)
            accounts.append((u, p))

    def parse_text_tokens(text: str) -> list[tuple[str, str]]:
        if not text:
            return []
        
        trimmed = text.strip()
        # 1. 尝试 JSON 格式
        if (trimmed.startswith("[") and trimmed.endswith("]")) or (trimmed.startswith("{") and trimmed.endswith("}")):
            try:
                data = json.loads(trimmed)
                res = []
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            e = item.get("email") or item.get("user") or item.get("username") or ""
                            p = item.get("password") or item.get("pass") or item.get("pwd") or ""
                            if e and p: res.append((str(e).strip(), str(p).strip()))
                        elif isinstance(item, str) and ":" in item:
                            parts = item.split(":", 1)
                            res.append((parts[0].strip(), parts[1].strip()))
                elif isinstance(data, dict):
                    e = data.get("email") or data.get("user") or data.get("username") or ""
                    p = data.get("password") or data.get("pass") or data.get("pwd") or ""
                    if e and p: res.append((str(e).strip(), str(p).strip()))
                if res:
                    return res
            except Exception:
                pass

        # 2. 文本解析：先按换行切分，再按逗号、分号或空格切分
        lines = re.split(r'[\r\n]+', text)
        tokens = []
        for l in lines:
            l = l.strip()
            if not l or l.startswith("#"):
                continue
            if "," in l:
                tokens.extend([x.strip() for x in l.split(",") if x.strip()])
            elif ";" in l:
                tokens.extend([x.strip() for x in l.split(";") if x.strip()])
            elif " " in l and "@" in l and ":" in l:
                tokens.extend([x.strip() for x in l.split() if x.strip()])
            else:
                tokens.append(l)

        res = []
        for t in tokens:
            for sep in ["----", "---", "--", ":", "#"]:
                if sep in t:
                    parts = t.split(sep, 1)
                    left, right = parts[0].strip(), parts[1].strip()
                    # left 必须包含 @，且 right 不能包含 @（排除 user1@g.com:user2@g.com 的情况）
                    if left and right and "@" in left and "@" not in right:
                        res.append((left, right))
                        break
        return res

    # 1. 解析 KATABUMP_ACCOUNTS 环境变量
    raw_accounts = os.environ.get("KATABUMP_ACCOUNTS", "").strip()
    if raw_accounts:
        for u, p in parse_text_tokens(raw_accounts):
            add_account(u, p)

    # 2. 解析 KATABUMP_EMAIL 和 KATABUMP_PASSWORD
    raw_email = os.environ.get("KATABUMP_EMAIL", "").strip()
    raw_pwd = os.environ.get("KATABUMP_PASSWORD", "").strip()

    if raw_email:
        combined = parse_text_tokens(raw_email)
        if combined:
            for u, p in combined:
                add_account(u, p)
        else:
            # 判断分隔符：换行、分号、逗号或冒号
            if "\n" in raw_email or "\r" in raw_email:
                emails = [x.strip() for x in re.split(r'[\r\n]+', raw_email) if x.strip()]
                passwords = [x.strip() for x in re.split(r'[\r\n]+', raw_pwd) if x.strip()]
            elif ";" in raw_email:
                emails = [x.strip() for x in raw_email.split(";") if x.strip()]
                passwords = [x.strip() for x in raw_pwd.split(";") if x.strip()]
            elif "," in raw_email:
                emails = [x.strip() for x in raw_email.split(",") if x.strip()]
                passwords = [x.strip() for x in raw_pwd.split(",") if x.strip()]
            elif ":" in raw_email:
                emails = [x.strip() for x in raw_email.split(":") if x.strip()]
                passwords = [x.strip() for x in raw_pwd.split(":") if x.strip()]
            else:
                emails = [raw_email.strip()]
                passwords = [raw_pwd.strip()] if raw_pwd else []

            if len(emails) == len(passwords) and len(emails) > 0:
                for e, p in zip(emails, passwords):
                    add_account(e, p)
            elif len(emails) > 0 and len(passwords) == 1:
                for e in emails:
                    add_account(e, passwords[0])
            elif len(emails) > 0 and len(passwords) > 1:
                for idx, e in enumerate(emails):
                    if idx < len(passwords):
                        add_account(e, passwords[idx])

    # 3. 解析编号环境变量 KATABUMP_EMAIL_1, KATABUMP_PASSWORD_1, KATABUMP_EMAIL_2...
    numbered_accs = {}
    for k, v in os.environ.items():
        m_email = re.match(r'^KATABUMP_EMAIL_?(\d+)$', k, re.IGNORECASE)
        if m_email and v.strip():
            num = int(m_email.group(1))
            if num not in numbered_accs:
                numbered_accs[num] = {}
            numbered_accs[num]['email'] = v.strip()
        m_pwd = re.match(r'^KATABUMP_PASSWORD_?(\d+)$', k, re.IGNORECASE)
        if m_pwd and v.strip():
            num = int(m_pwd.group(1))
            if num not in numbered_accs:
                numbered_accs[num] = {}
            numbered_accs[num]['password'] = v.strip()
    
    for num in sorted(numbered_accs.keys()):
        e = numbered_accs[num].get('email')
        p = numbered_accs[num].get('password') or raw_pwd
        if e and p:
            add_account(e, p)

    return accounts


# ===== Telegram 推送模块 =====

def send_tg_message(status_icon: str, status_text: str, detail: str = "", email: str = ""):
    """发送单个账号的 Telegram 推送"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return

    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)
    masked_email = mask_email(email) if email else "未知账户"

    lines = [
        "🇫🇷 katabump 续期通知",
        "",
        f"{status_icon} 状态: {status_text}",
        f"👤 账户: {masked_email}",
        f"⏱️ 时间: {current_time_str}"
    ]
    if detail and detail.strip():
        lines.append(f"📝 详情: {detail.strip()}")

    text = "\n".join(lines)
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text
    }
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("📩 Telegram 通知发送成功！")
        else:
            print(f"⚠️ Telegram 通知发送失败: {r.text}")
    except Exception as e:
        print(f"⚠️ Telegram 通知发送异常: {e}")


def send_tg_summary(account_results: list[tuple[str, str, str]]):
    """当有多个账号时，发送汇总通知"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    if len(account_results) <= 1:
        return

    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)

    total = len(account_results)
    success_count = sum(1 for _, status, _ in account_results if status == "success")
    not_time_count = sum(1 for _, status, _ in account_results if status in ("not_time", "executed"))
    fail_count = sum(1 for _, status, _ in account_results if status in ("failed", "login_fail", "exception"))

    status_icon_map = {
        "success": "✅",
        "not_time": "⏳",
        "executed": "ℹ️",
        "login_fail": "❌",
        "failed": "❌",
        "exception": "⚠️"
    }

    lines = [
        "📊 KataBump 多账号续期汇总",
        "",
        f"📈 统计: 共 {total} 个 | 成功: {success_count} | 未到期: {not_time_count} | 失败: {fail_count}",
        f"⏱️ 完成时间: {current_time_str}",
        "",
        "📋 账号明细:"
    ]

    for idx, (email, status, detail) in enumerate(account_results, 1):
        icon = status_icon_map.get(status, "ℹ️")
        detail_msg = f" ({detail})" if detail else ""
        lines.append(f"{idx}. {mask_email(email)}: {icon} {detail_msg}")

    text = "\n".join(lines)
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text
    }

    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("📩 Telegram 汇总通知发送成功！")
        else:
            print(f"⚠️ Telegram 汇总通知发送失败: {r.text}")
    except Exception as e:
        print(f"⚠️ Telegram 汇总通知发送异常: {e}")


# ===== 页面注入与验证脚本 =====

_EXPAND_JS = """
(function() {
    var ts = document.querySelector('input[name="cf-turnstile-response"]');
    if (!ts) return 'no-turnstile';
    var el = ts;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var s = window.getComputedStyle(el);
        if (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.overflowY === 'hidden')
            el.style.overflow = 'visible';
        el.style.minWidth = 'max-content';
    }
    document.querySelectorAll('iframe').forEach(function(f){
        if (f.src && f.src.includes('challenges.cloudflare.com')) {
            f.style.width = '300px'; f.style.height = '65px';
            f.style.minWidth = '300px';
            f.style.visibility = 'visible'; f.style.opacity = '1';
        }
    });
    return 'done';
})()
"""

_EXISTS_JS = """
(function(){
    return document.querySelector('input[name="cf-turnstile-response"]') !== null;
})()
"""

_SOLVED_JS = """
(function(){
    var i = document.querySelector('input[name="cf-turnstile-response"]');
    return !!(i && i.value && i.value.length > 20);
})()
"""


# ===== 浏览器操作工具 =====

def js_fill_input(sb, selector: str, text: str):
    """通过 JS 填充输入框并触发事件"""
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"')
    sb.execute_script(f"""
    (function(){{
        var el = document.querySelector('{selector}');
        if (!el) return;
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        if (nativeInputValueSetter) {{
            nativeInputValueSetter.call(el, "{safe_text}");
        }} else {{
            el.value = "{safe_text}";
        }}
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }})()
    """)


def handle_turnstile(sb) -> bool:
    """人机验证处理（使用 SeleniumBase 内置 uc_gui_click_captcha）"""
    print("🔍 处理 Cloudflare Turnstile 验证...")
    time.sleep(2)

    # 检查是否已静默通过
    if sb.execute_script(_SOLVED_JS):
        print("✅ 已静默通过")
        return True

    # 尝试展开 Turnstile
    for _ in range(3):
        try:
            sb.execute_script(_EXPAND_JS)
        except Exception:
            pass
        time.sleep(0.5)

    for attempt in range(8):
        if sb.execute_script(_SOLVED_JS):
            print(f"✅ Turnstile 通过（第 {attempt} 次尝试）")
            return True

        print(f"🖱️ 第 {attempt + 1} 次调用 uc_gui_click_captcha...")
        try:
            sb.uc_gui_click_captcha()
        except Exception as e:
            print(f"⚠️ uc_gui_click_captcha 调用异常: {e}")

        # 等待验证结果（最多 8 秒）
        for _ in range(16):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS):
                print(f"✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
                return True

        print(f"⚠️ 第 {attempt + 1} 次未通过，重试...")

    print("  ❌ Turnstile 8 次均失败")
    return False


# ===== 登录模块 =====

def login(sb, email: str, password: str) -> bool:
    """登录指定账号"""
    masked = mask_email(email)
    print(f"🌐 打开登录页面: {BASE_URL}/auth/login")
    sb.uc_open_with_reconnect(BASE_URL + "/auth/login", reconnect_time=8)
    time.sleep(6)

    # 检查是否由于已登录而被重定向到仪表盘
    cur_url = sb.get_current_url().lower()
    page_title = sb.get_title() or ""
    if "/dashboard" in cur_url or "dashboard | katabump" in page_title.lower() or "/servers" in cur_url:
        print("ℹ️ 检测到已处于登录状态，执行登出以切换新账号...")
        try:
            sb.open(f"{BASE_URL}/auth/logout")
            time.sleep(3)
        except Exception:
            pass
        try:
            sb.delete_all_cookies()
            sb.execute_script("try{window.localStorage.clear(); window.sessionStorage.clear();}catch(e){}")
        except Exception:
            pass
        sb.uc_open_with_reconnect(BASE_URL + "/auth/login", reconnect_time=8)
        time.sleep(6)

    # 先等待 Cloudflare 验证通过（最多等 30 秒）
    print("⏳ 等待 Cloudflare 验证通过...")
    cf_passed = False
    for i in range(30):
        page_src = sb.get_page_source() or ""
        if 'input[name="email"]' in page_src.lower() or 'name="email"' in page_src.lower() or 'type="email"' in page_src.lower():
            cf_passed = True
            print(f"✅ Cloudflare 验证已通过（{i+1}s）")
            break
        time.sleep(1)
    if not cf_passed:
        print("⚠️ Cloudflare 验证可能未通过，继续尝试查找输入框...")

    try:
        sb.wait_for_element('input[type="email"]', timeout=15)
    except Exception:
        # 尝试后备选择器
        try:
            sb.wait_for_element('input[type="Email"]', timeout=5)
        except Exception:
            try:
                sb.wait_for_element('input[name="email"]', timeout=5)
            except Exception:
                print("❌ 页面未加载出登录表单")
                cur_url = sb.get_current_url()
                page_title = sb.get_title() or ""
                print(f"  当前 URL: {cur_url}")
                print(f"  当前标题: {page_title}")
                try:
                    sb.save_screenshot(f"login_load_fail_{masked}.png")
                except Exception:
                    pass
                return False

    print("🍪 关闭可能的 Cookie 弹窗...")
    try:
        for btn in sb.find_elements("button"):
            if "Accept" in (btn.text or "") or "同意" in (btn.text or ""):
                btn.click()
                time.sleep(0.5)
                break
    except Exception:
        pass

    print(f"📧 填写邮箱: {masked}")
    js_fill_input(sb, 'input[type="email"]', email)
    time.sleep(1)
    
    print("🔑 填写密码...")
    js_fill_input(sb, 'input[type="password"]', password)
    time.sleep(3)

    # 等待 Turnstile 验证框出现（最多 10 秒）
    print("⏳ 等待 Turnstile 验证框出现...")
    ts_found = False
    for i in range(10):
        if sb.execute_script(_EXISTS_JS):
            ts_found = True
            print(f"✅ 检测到 Turnstile（{i+1}s）")
            break
        time.sleep(1)

    if ts_found:
        if not handle_turnstile(sb):
            print("❌ 登录界面的 Turnstile 验证失败")
            try:
                sb.save_screenshot(f"login_turnstile_fail_{masked}.png")
            except Exception:
                pass
            return False
    else:
        print("ℹ️ 未检测到 Turnstile")

    print("🖱️ 提交登录表单...")
    submitted = False
    try:
        submit_btn = sb.find_element('button[type="submit"]', timeout=3)
        submit_btn.click()
        submitted = True
        print("✅ 点击登录按钮提交")
    except Exception:
        pass

    if not submitted:
        try:
            sb.press_keys('input[name="password"]', '\n')
            print("✅ 敲击回车提交")
        except Exception:
            try:
                sb.press_keys('input[type="password"]', '\n')
            except Exception:
                pass

    print("⏳ 等待登录跳转...")
    for _ in range(15):
        time.sleep(1)
        cur_url = sb.get_current_url().split('?')[0].lower()
        page_title = sb.get_title() or ""
        if cur_url.startswith(f"{BASE_URL}/dashboard") or "Dashboard | KataBump" in page_title.lower() or "/servers" in cur_url:
            break

    cur_url = sb.get_current_url().split('?')[0].lower()
    page_title = sb.get_title() or ""
    if cur_url.startswith(f"{BASE_URL}/dashboard") or "Dashboard | KataBump" in page_title.lower() or "/servers" in cur_url:
        print(f"✅ 登录成功！(URL: {sb.get_current_url()}, Title: {page_title})")
        return True
        
    print(f"❌ 登录失败，页面未跳转到账户页。(URL: {sb.get_current_url()}, Title: {page_title})")
    try:
        sb.save_screenshot(f"login_failed_{masked}.png")
    except Exception:
        pass
    return False


# ===== 自动续期流程 =====

def _read_alert(sb) -> str:
    """读取页面第一个 Bootstrap alert 的文本，找不到返回空串"""
    try:
        el = sb.find_element("div.alert", timeout=4)
        return (el.text or "").strip()
    except Exception:
        return ""


def _goto_server_detail(sb, email: str = "") -> bool:
    """在 Dashboard 首页查找并点击 See 进入服务器详情页"""
    print("\n🖥️  正在进入服务器续期页...")
    time.sleep(5)

    alert_text = _read_alert(sb)
    if alert_text and "can't renew" in alert_text.lower():
        print(f"ℹ️  页面顶部提示: {alert_text}")
        send_tg_message("⏳", "未到续期时间", alert_text, email=email)
        return False

    selectors = [
        'a[href*="/servers/edit?id="]',
        'td a[href*="/servers/edit"]',
        'table a[href*="/servers/edit"]',
        'table td a',
    ]

    see_link = None
    for sel in selectors:
        try:
            see_link = sb.find_element(sel, timeout=8)
            print(f"✅ 通过选择器找到链接: {sel}")
            break
        except Exception:
            continue

    if see_link is None:
        print("⚠️ 选择器未命中，尝试文本匹配...")
        try:
            for a in sb.find_elements("a"):
                if (a.text or "").strip().lower() == "see":
                    see_link = a
                    print("✅ 通过文本 'See' 找到链接")
                    break
        except Exception:
            pass

    if see_link is None:
        cur_url = sb.get_current_url()
        title = sb.get_title() or ""
        print("❌ 未找到 'See' 链接")
        print(f"当前 URL: {cur_url}")
        print(f"页面标题: {title}")
        try:
            links = sb.find_elements("a")
            print(f"     页面共 {len(links)} 个链接:")
            for a in links[:20]:
                txt  = (a.text or "").strip()[:30]
                href = a.get_attribute("href") or ""
                if href:
                    print(f"       - [{txt}] -> {href}")
        except Exception:
            pass
        try:
            sb.save_screenshot(f"servers_page_fail_{mask_email(email)}.png")
        except Exception:
            pass
        return False

    print("🖱️  点击 'See' 进入服务器详情页...")
    see_link.click()
    time.sleep(5)
    print(f"📄 当前页面: {sb.get_current_url()}")
    return True


def _open_renew_modal(sb) -> bool:
    """滚动到 Renew 按钮并点击，打开模态框"""
    print("\n🔄 查找 Renew 按钮...")
    try:
        renew_btn = sb.find_element('button[data-bs-target="#renew-modal"]', timeout=10)
    except Exception:
        try:
            renew_btn = sb.find_element('button.btn.btn-outline-primary', timeout=5)
        except Exception:
            print("  ❌ 未找到 Renew 按钮")
            return False

    sb.execute_script("""
        (function(){
            var btn = document.querySelector('button[data-bs-target="#renew-modal"]')
                     || document.querySelector('button.btn.btn-outline-primary');
            if (btn) btn.scrollIntoView({behavior:'smooth',block:'center'});
        })()
    """)
    time.sleep(0.8)
    renew_btn.click()
    print("🖱️ 已点击 Renew 按钮，等待确认框...")
    time.sleep(3)

    try:
        sb.find_element('div.modal.show', timeout=5)
        print("✅ Renew 模态框已弹出")
        return True
    except Exception:
        print("⚠️ 模态框未弹出")
        return False


def _submit_renew(sb):
    """点击模态框内的 Renew 提交按钮"""
    print("🖱️  点击模态框中的 Renew 按钮...")
    try:
        submit = sb.find_element('div.modal-footer button.btn.btn-primary', timeout=10)
        submit.click()
    except Exception:
        sb.execute_script("""
            (function(){
                var m = document.querySelector('div.modal-footer button.btn.btn-primary')
                     || document.querySelector('button.btn.btn-primary');
                if (!m) return;
                var bs = m.querySelectorAll ? m.querySelectorAll('button') : [];
                if (bs.length > 0) {
                    for (var i = 0; i < bs.length; i++)
                        if (/renew/i.test(bs[i].textContent)) bs[i].click();
                } else {
                    m.click();
                }
            })()
        """)
    time.sleep(8)


def _check_renew_result(sb, email: str = "") -> tuple[str, str]:
    """读取页面 alert 提示，判断续期结果并推送 TG 通知"""
    print("\n📋 检查续期结果...")
    alert_text = _read_alert(sb)
    if not alert_text:
        time.sleep(3)
        alert_text = _read_alert(sb)

    if alert_text:
        print(f"📩 页面提示: {alert_text}")
        low = alert_text.lower()
        if "can't renew" in low or "unable" in low:
            send_tg_message("⏳", "未到续期时间", alert_text, email=email)
            return "not_time", alert_text
        elif any(kw in low for kw in ("renewed", "success", "extended")):
            send_tg_message("✅", "续期成功", alert_text, email=email)
            return "success", alert_text
        else:
            send_tg_message("ℹ️", "续期操作已执行", alert_text, email=email)
            return "executed", alert_text
    else:
        print("ℹ️ 未检测到明确的提示框，可能续期操作未生效")
        send_tg_message("ℹ️", "续期操作已执行", "未检测到明确提示", email=email)
        return "executed", "未检测到明确提示"


def _process_single_server(sb, email: str) -> tuple[str, str]:
    """处理单个服务器详情页的续期流程"""
    alert_text = _read_alert(sb)
    if alert_text and ("can't renew" in alert_text.lower() or "unable" in alert_text.lower()):
        print(f"ℹ️ 页面提示: {alert_text}")
        send_tg_message("⏳", "未到续期时间", alert_text, email=email)
        return "not_time", alert_text

    if not _open_renew_modal(sb):
        alert_text = _read_alert(sb)
        if alert_text:
            print(f"ℹ️ 页面提示: {alert_text}")
            send_tg_message("⏳", "未到续期时间", alert_text, email=email)
            return "not_time", alert_text
        print("⚠️ 未能打开 Renew 模态框，可能未到续期时间或无需续期")
        send_tg_message("⏳", "无需续期或未到时间", "未找到可点击的 Renew 按钮", email=email)
        return "not_time", "未找到可点击的 Renew 按钮"

    _submit_renew(sb)
    return _check_renew_result(sb, email)


def renew_server(sb, email: str) -> tuple[str, str]:
    """登录成功后调用：进入详情页 -> Renew -> 提交"""
    masked = mask_email(email)
    print("\n" + "#" * 25)
    print(f"  开始自动续期流程: {masked}")
    print("#" * 25)

    # 检查仪表盘是否有不可续期提示
    alert_text = _read_alert(sb)
    if alert_text and "can't renew" in alert_text.lower():
        print(f"ℹ️  页面顶部提示: {alert_text}")
        send_tg_message("⏳", "未到续期时间", alert_text, email=email)
        return "not_time", alert_text

    # 查找所有服务器详情链接
    server_links = []
    try:
        elements = sb.find_elements('a[href*="/servers/edit"]')
        for el in elements:
            href = el.get_attribute("href")
            if href and href not in server_links:
                server_links.append(href)
    except Exception:
        pass

    results = []

    if server_links:
        print(f"🖥️ 发现 {len(server_links)} 个服务器详情链接")
        for s_idx, s_url in enumerate(server_links, 1):
            print(f"\n--- 正在处理第 {s_idx}/{len(server_links)} 个服务器 ---")
            sb.open(s_url)
            time.sleep(5)
            status, detail = _process_single_server(sb, email)
            results.append((status, detail))
    else:
        # 后备方案：查找并点击 See 链接
        if not _goto_server_detail(sb, email):
            return "failed", "未找到可用的服务器或未到续期时间"
        status, detail = _process_single_server(sb, email)
        results.append((status, detail))

    if any(r[0] == "success" for r in results):
        return "success", "; ".join([r[1] for r in results if r[1]])
    elif any(r[0] == "not_time" for r in results):
        return "not_time", "; ".join([r[1] for r in results if r[1]])
    elif results:
        return results[0][0], results[0][1]
    return "failed", "无续期结果"


def process_single_account(idx: int, total: int, email: str, password: str, sb_kwargs: dict) -> tuple[str, str]:
    """处理单个账号的独立浏览器会话，每个账号拥有完全独立的临时数据目录，彻底杜绝数据残留"""
    masked = mask_email(email)
    print("\n" + "=" * 55)
    print(f"▶ [{idx}/{total}] 正在处理账号: {masked}")
    print("=" * 55)

    # 为每个账号创建完全隔离的临时 profile 目录
    temp_profile_dir = tempfile.mkdtemp(prefix=f"sb_profile_{idx}_")
    account_sb_kwargs = dict(sb_kwargs)
    account_sb_kwargs["user_data_dir"] = temp_profile_dir

    try:
        with SB(**account_sb_kwargs) as sb:
            # 仅在第一个账号时探测出口 IP
            if idx == 1:
                try:
                    sb.open("https://api.ip.sb/ip")
                    print(f"📍 当前出口 IP: {sb.get_text('body').strip()}")
                except Exception:
                    pass

            if login(sb, email, password):
                status, detail = renew_server(sb, email)
                return status, detail
            else:
                print(f"\n❌ [{masked}] 登录失败，终止该账号后续操作。")
                send_tg_message("❌", "登录失败", "页面未成功跳转至仪表盘或验证码未通过", email=email)
                return "login_fail", "登录失败"
    except Exception as e:
        err_msg = str(e)
        print(f"\n⚠️ [{masked}] 处理过程中发生异常: {err_msg}")
        send_tg_message("⚠️", "运行异常", err_msg, email=email)
        return "exception", err_msg
    finally:
        # 清理临时数据目录
        try:
            shutil.rmtree(temp_profile_dir, ignore_errors=True)
        except Exception:
            pass


# ===== 主执行入口 =====

def main():
    print("#" * 55)
    print("       KataBump 自动登录续期（多账号支持版）")
    print("#" * 55)

    accounts = parse_accounts()
    if not accounts:
        print("❌ 未检测到任何账号配置！")
        print("👉 请在环境变量或 GitHub Secrets 中配置 KATABUMP_EMAIL 和 KATABUMP_PASSWORD")
        return

    print(f"👥 共检测到 {len(accounts)} 个账号待处理\n")

    IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
    proxy_str = os.environ.get("PROXY_SERVER", "").strip() or os.environ.get("HTTP_PROXY", "").strip() or "http://127.0.0.1:1081"
    sb_kwargs = {"uc": True, "headless": False}

    if IS_PROXY:
        print(f"🔗 挂载代理: {proxy_str}")
        sb_kwargs["proxy"] = proxy_str
    else:
        print("🌐 未使用代理，直连访问")

    results = []
    total = len(accounts)

    for idx, (email, password) in enumerate(accounts, 1):
        status, detail = process_single_account(idx, total, email, password, sb_kwargs)
        results.append((email, status, detail))

        # 账号间适度休眠，避免频繁并发被 Cloudflare 拦截
        if idx < total:
            print("\n⏳ 等待 5 秒后处理下一个账号...")
            time.sleep(5)

    # 打印汇总报告
    print("\n" + "=" * 55)
    print("                  📊 执行结果汇总")
    print("=" * 55)
    for idx, (email, status, detail) in enumerate(results, 1):
        status_text_map = {
            "success": "✅ 续期成功",
            "not_time": "⏳ 未到续期时间",
            "executed": "ℹ️ 续期操作已执行",
            "login_fail": "❌ 登录失败",
            "failed": "❌ 续期失败",
            "exception": "⚠️ 运行异常"
        }
        st = status_text_map.get(status, status)
        print(f"{idx}. {mask_email(email):<25} | {st:<12} | 详情: {detail}")
    print("=" * 55)

    # 发送 Telegram 汇总通知（如果有多账号）
    if total > 1:
        send_tg_summary(results)

    print("\n🎉 所有账号处理完毕！")


if __name__ == "__main__":
    main()
