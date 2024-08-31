import re
import subprocess
import pyotp
import time
import uuid
from telegram import Update, error
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters
from datetime import datetime

API_TOKEN = '123456'
TOTP_SECRET = '123456'  # 替换为你的 TOTP 密钥

# 设置允许操作的用户ID列表（可以是一个或多个ID）
AUTHORIZED_USER_IDS = [123456]  # 替换为你的用户ID

# 全局变量存储 jail 列表
AVAILABLE_JAILS = []

# 获取所有 jails 的函数
def get_available_jails():
    output = subprocess.check_output("fail2ban-client status", shell=True).decode('utf-8')
    jails = []
    for line in output.split('\n'):
        if "Jail list:" in line:
            jails = line.split(":")[1].strip().split(", ")
            break
    return jails

# 解析范围表达式的函数
def parse_ip_range(ip_range):
    if '[' in ip_range:
        pattern = re.compile(r'\[(\d+)-(\d+)\]')
        ranges = pattern.findall(ip_range)
        ips = [ip_range]
        for start, end in ranges:
            expanded_ips = []
            range_values = range(int(start), int(end) + 1) if int(start) < int(end) else range(int(start), int(end) - 1, -1)
            for ip in ips:
                for i in range_values:
                    expanded_ips.append(ip.replace(f'[{start}-{end}]', str(i)))
            ips = expanded_ips
        return ips
    elif '<' in ip_range:
        match = re.match(r'<(\d+\.\d+\.\d+\.\d+)~(\d+\.\d+\.\d+\.\d+)>', ip_range)
        if match:
            start_ip = list(map(int, match.group(1).split('.')))
            end_ip = list(map(int, match.group(2).split('.')))
            ips = []
            while start_ip != end_ip:
                ips.append('.'.join(map(str, start_ip)))
                if start_ip < end_ip:
                    start_ip[3] += 1
                    for i in (3, 2, 1):
                        if start_ip[i] > 255:
                            start_ip[i] = 0
                            start_ip[i-1] += 1
                else:
                    start_ip[3] -= 1
                    for i in (3, 2, 1):
                        if start_ip[i] < 0:
                            start_ip[i] = 255
                            start_ip[i-1] -= 1
            ips.append('.'.join(map(str, end_ip)))  # 最后一个 IP
            return ips
    else:
        return [ip_range]

# 检查IP地址是否合法
def is_valid_ip(ip):
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    for part in parts:
        try:
            if not 0 <= int(part) <= 255:
                return False
        except ValueError:
            return False
    return True

# 获取当前时间，精确到毫秒
def get_current_time():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

# 检查用户是否有操作权限
def is_authorized(user_id):
    return user_id in AUTHORIZED_USER_IDS

# 执行fail2ban命令并返回结果
def execute_fail2ban_command(command):
    try:
        output = subprocess.check_output(command, shell=True)
        return "成功", output.decode('utf-8').strip()
    except subprocess.CalledProcessError as e:
        return "失败", f"命令执行失败: {str(e)}"

# 获取被封禁的IP
def get_banned_ips(jail):
    try:
        output = subprocess.check_output(f"fail2ban-client status {jail}", shell=True).decode('utf-8')
        ips = []
        for line in output.split('\n'):
            if "Banned IP list:" in line:
                ips = line.split(":")[1].strip().split()
                break
        return ips
    except subprocess.CalledProcessError as e:
        return []

# 处理ban命令
async def handle_ban(jail, ips, update: Update):
    await update.message.reply_text(f"{get_current_time()} - 开始执行 /ban 命令...")
    
    if jail == "$all":
        jails = AVAILABLE_JAILS
    else:
        if jail not in AVAILABLE_JAILS:
            return f"{get_current_time()} - Jail '{jail}' 不存在。"
        jails = [jail]
    
    responses = []
    for jail in jails:
        for ip in ips:
            if not is_valid_ip(ip):
                responses.append(f"{get_current_time()} - IP '{ip}' 非法，跳过。")
                continue
            command = f"fail2ban-client set {jail} banip {ip}"
            status, response = execute_fail2ban_command(command)
            if status == "成功" and "1" in response:
                responses.append(f"{get_current_time()} - 在 {jail} 中封禁 IP {ip}: 成功")
            else:
                responses.append(f"{get_current_time()} - 在 {jail} 中封禁 IP {ip}: 失败 - {response}")
    return '\n'.join(responses)

# 处理unban命令
async def handle_unban(jail, ips, update: Update):
    await update.message.reply_text(f"{get_current_time()} - 开始执行 /unban 命令...")
    
    if jail == "$all":
        jails = AVAILABLE_JAILS
    else:
        if jail not in AVAILABLE_JAILS:
            return f"{get_current_time()} - Jail '{jail}' 不存在。"
        jails = [jail]
    
    responses = []
    for jail in jails:
        if ips == ["$all"]:
            banned_ips = get_banned_ips(jail)
            if not banned_ips:
                responses.append(f"{get_current_time()} - 在 {jail} 中没有被封禁的 IP。")
            else:
                for ip in banned_ips:
                    command = f"fail2ban-client set {jail} unbanip {ip}"
                    status, response = execute_fail2ban_command(command)
                    if status == "成功" and "1" in response:
                        responses.append(f"{get_current_time()} - 在 {jail} 中解封 IP {ip}: 成功")
                    else:
                        responses.append(f"{get_current_time()} - 在 {jail} 中解封 IP {ip}: 失败 - {response}")
        else:
            for ip in ips:
                if not is_valid_ip(ip):
                    responses.append(f"{get_current_time()} - IP '{ip}' 非法，跳过。")
                    continue
                command = f"fail2ban-client set {jail} unbanip {ip}"
                status, response = execute_fail2ban_command(command)
                if status == "成功" and "1" in response:
                    responses.append(f"{get_current_time()} - 在 {jail} 中解封 IP {ip}: 成功")
                else:
                    responses.append(f"{get_current_time()} - 在 {jail} 中解封 IP {ip}: 失败 - {response}")
    return '\n'.join(responses)

# 处理list命令
async def handle_list(update: Update, jail=None):
    try:
        await update.message.reply_text(f"{get_current_time()} - 开始执行 /list 命令...")
        
        if not jail:
            status, response = execute_fail2ban_command("fail2ban-client status")
            await update.message.reply_text(f"{get_current_time()} - {response} - {status}")
        else:
            if jail not in AVAILABLE_JAILS:
                await update.message.reply_text(f"{get_current_time()} - Jail '{jail}' 不存在。")
            else:
                status, response = execute_fail2ban_command(f"fail2ban-client status {jail}")
                file_path = f"{jail}_banned_ips.txt"
                with open(file_path, 'w') as file:
                    file.write(f"Jail: {jail}\n{response}\n")
                await update.message.reply_text(f"{get_current_time()} - 查询结果已保存至 {file_path}")
                await update.message.reply_document(document=open(file_path, 'rb'))
    except error.BadRequest as e:
        # 捕获 BadRequest 异常并记录日志，但不让程序崩溃
        print(f"An error occurred: {e}")

# 更新Jail列表并返回详细信息
async def handle_update(update: Update, context: CallbackContext) -> None:
    if not is_authorized(update.message.from_user.id):
        await update.message.reply_text(f"{get_current_time()} - 你没有操作权限。")
        return
    
    await update.message.reply_text(f"{get_current_time()} - 开始执行 /update 命令...")
    
    global AVAILABLE_JAILS
    before_update_jails = AVAILABLE_JAILS.copy()
    new_jails = get_available_jails()
    updated_jails = [jail for jail in new_jails if jail not in before_update_jails]
    AVAILABLE_JAILS = new_jails
    
    update_summary = (
        f"更新时间: {get_current_time()}\n"
        f"更新前 Jail 列表: {before_update_jails}\n"
        f"更新后 Jail 列表: {AVAILABLE_JAILS}\n"
        f"新增 Jail: {updated_jails if updated_jails else '无'}\n"
    )
    await update.message.reply_text(update_summary)

# 查询IP是否被封禁以及所在的jail
async def handle_checkban(update: Update, context: CallbackContext) -> None:
    if not is_authorized(update.message.from_user.id):
        await update.message.reply_text(f"{get_current_time()} - 你没有操作权限。")
        return

    await update.message.reply_text(f"{get_current_time()} - 开始执行 /checkban 命令...")
    
    if len(context.args) < 1:
        await update.message.reply_text(f"{get_current_time()} - 用法: /checkban <IP1,IP2,...>")
        return
    
    ips = context.args[0].split(',')
    responses = []
    for ip in ips:
        if not is_valid_ip(ip):
            responses.append(f"{get_current_time()} - IP '{ip}' 非法，跳过。")
            continue
        
        found = False
        for jail in AVAILABLE_JAILS:
            banned_ips = get_banned_ips(jail)
            if ip in banned_ips:
                responses.append(f"{get_current_time()} - IP {ip} 被封禁在 Jail '{jail}' 中。")
                found = True
                break
        
        if not found:
            responses.append(f"{get_current_time()} - IP {ip} 未被封禁。")
    
    await update.message.reply_text('\n'.join(responses))

# 生成UUID
async def handle_uuid(update: Update, context: CallbackContext) -> None:
    if not is_authorized(update.message.from_user.id):
        await update.message.reply_text(f"{get_current_time()} - 你没有操作权限。")
        return

    await update.message.reply_text(f"{get_current_time()} - 开始执行 /uuid 命令...")

    if len(context.args) == 0:
        count = 1
    else:
        try:
            count = int(context.args[0])
            if count <= 0:
                await update.message.reply_text(f"{get_current_time()} - 参数错误，请输入一个正整数。")
                return
        except ValueError:
            await update.message.reply_text(f"{get_current_time()} - 参数错误，请输入一个正整数。")
            return

    uuids = [str(uuid.uuid4()) for _ in range(count)]
    await update.message.reply_text(f"{get_current_time()} - 生成了以下UUID:\n" + "\n".join(uuids))

# 返回帮助信息
async def handle_help(update: Update, context: CallbackContext) -> None:
    help_text = (
        "使用说明：\n"
        "/ban <jail> <IP> - 在特定的 jail 中封禁 IP。例如：/ban sshd 192.168.1.100\n"
        "    支持范围表达：\n"
        "    1. 192.168.1.[1-10] - 封禁从 192.168.1.1 到 192.168.1.10 的 IP 地址。\n"
        "    2. 192.168.[1-3].1 - 封禁 192.168.1.1, 192.168.2.1, 192.168.3.1\n"
        "    3. <192.168.1.1~192.168.1.10> - 封禁从 192.168.1.1 到 192.168.1.10 的所有 IP。\n"
        "/unban <jail> <IP> - 在特定的 jail 中解封 IP。例如：/unban sshd 192.168.1.100\n"
        "/list [jail] - 列出所有 jail 或者指定 jail 的状态。例如：/list sshd\n"
        "/ping <IP> - 检查指定服务器是否在线。例如：/ping 192.168.1.1\n"
        "/userinfo - 获取你的用户信息。\n"
        "/update - 热更新系统的 jail 列表，并返回更新详情。\n"
        "/checkban <IP1,IP2,...> - 查询IP是否被封禁以及所在的 jail。\n"
        "/uuid [数量] - 生成一个或多个 UUID。\n"
        "/totp - 获取当前的 TOTP、剩余时间和下一个 TOTP。\n"
        "/help - 显示此帮助信息。"
    )
    await update.message.reply_text(help_text)

# 检查服务器是否在线
async def handle_ping(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(f"{get_current_time()} - 服务器在线")

# 获取用户信息
async def handle_userinfo(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    user_info = (
        f"你好，{user.first_name}！\n"
        f"你的用户ID是: {user.id}\n"
        f"用户名: @{user.username}" if user.username else "用户名: 无"
    )
    await update.message.reply_text(user_info)

# 处理TOTP命令
async def handle_totp(update: Update, context: CallbackContext) -> None:
    if not is_authorized(update.message.from_user.id):
        await update.message.reply_text(f"{get_current_time()} - 你没有操作权限。")
        return
    
    # 创建 TOTP 对象
    totp = pyotp.TOTP(TOTP_SECRET)
    
    # 获取当前 OTP
    current_otp = totp.now()
    
    # 计算剩余有效时间
    time_remaining = totp.interval - int(time.time()) % totp.interval
    
    # 获取下一个 OTP
    next_otp = totp.at(int(time.time()) + totp.interval)
    
    # 构建返回信息
    totp_info = (
        f"当前的 TOTP 是: {current_otp}\n"
        f"剩余有效时间: {time_remaining} 秒\n"
        f"下一个 TOTP 将是: {next_otp}"
    )
    
    await update.message.reply_text(totp_info)

# 处理ban命令的入口函数
async def process_ban(update: Update, context: CallbackContext) -> None:
    if not is_authorized(update.message.from_user.id):
        await update.message.reply_text(f"{get_current_time()} - 你没有操作权限。")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(f"{get_current_time()} - 用法: /ban <jail> <IP>")
        return
    
    jail = context.args[0]
    ips = context.args[1]

    # 检查特殊情况
    if jail == "$all" and ips == "$all":
        await update.message.reply_text(f"{get_current_time()} - 禁止执行 /ban $all $all 命令。这会导致不必要的错误和操作。")
        return

    ips = ips.split(',')
    all_ips = []
    for ip in ips:
        all_ips.extend(parse_ip_range(ip))
    
    result = await handle_ban(jail, all_ips, update)
    await update.message.reply_text(result)

# 处理unban命令的入口函数
async def process_unban(update: Update, context: CallbackContext) -> None:
    if not is_authorized(update.message.from_user.id):
        await update.message.reply_text(f"{get_current_time()} - 你没有操作权限。")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(f"{get_current_time()} - 用法: /unban <jail> <IP>")
        return
    
    jail = context.args[0]
    ips = context.args[1].split(',')
    all_ips = []
    for ip in ips:
        all_ips.extend(parse_ip_range(ip))
    
    result = await handle_unban(jail, all_ips, update)
    await update.message.reply_text(result)

# 处理list命令的入口函数
async def process_list(update: Update, context: CallbackContext) -> None:
    if not is_authorized(update.message.from_user.id):
        await update.message.reply_text(f"{get_current_time()} - 你没有操作权限。")
        return
    
    jail = context.args[0] if context.args else None
    try:
        result = await handle_list(update, jail)
        await update.message.reply_text(result)
    except error.BadRequest as e:
        # 捕获异常，继续运行
        print(f"An error occurred: {e}")

# 处理未知命令
async def unknown_command(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(f"{get_current_time()} - 未知命令。请使用 /ban, /unban, /list, /ping, /userinfo, /update, /totp, /uuid 或 /checkban。")

# 处理未知参数或无效的文本消息
async def unknown_argument(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(f"{get_current_time()} - 参数错误。请检查并重试。")

# 主函数
def main() -> None:
    global AVAILABLE_JAILS
    AVAILABLE_JAILS = get_available_jails()

    application = Application.builder().token(API_TOKEN).build()

    application.add_handler(CommandHandler("ban", process_ban))
    application.add_handler(CommandHandler("unban", process_unban))
    application.add_handler(CommandHandler("list", process_list))
    application.add_handler(CommandHandler("help", handle_help))
    application.add_handler(CommandHandler("test", handle_ping))
    application.add_handler(CommandHandler("userinfo", handle_userinfo))
    application.add_handler(CommandHandler("update", handle_update))
    application.add_handler(CommandHandler("checkban", handle_checkban))
    application.add_handler(CommandHandler("totp", handle_totp))
    application.add_handler(CommandHandler("uuid", handle_uuid))

    # 捕获未知命令
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    # 捕获未知参数或无效的文本消息
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_argument))

    application.run_polling()

if __name__ == '__main__':
    main()
