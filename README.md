# Fail2ban-Via-Telegram_bot
在Telegram的bot上用服务器的Fail2ban封禁或解封IP
***
## 1.前言

这个脚本是我用GPT完全搞出来的，因为我不会编程，所以只能这样了。
最开始的目的是想通过一种第三方的方式解封被误封的IP，因为我的服务器登录条件过于苛刻，错一次就会被永久封禁，故有了这想法。
其实我一开始想的是通过电子邮件解封，奈何GPT写不出这么复杂的脚本，所以换上了Telegram。
脚本的基本功能我自己实验过了，理论上只要好好用应该就不会有问题。
可能还会有一些莫名其妙的BUG且没有发现，还请各位懂python的大佬们使用之前看一看。
已知小问题：使用/list命令后，控制台会返回一个telegram的空信息报错，不过不影响使用。
脚本需要服务器可以连接上telegram，否则会报错退出并返回telegram.error.TimedOut: Timed out
所以建议服务器设在海外或使用7890、10808等端口(

***

## 2.使用前配置

首先，先去telegram那里搞一个bot，网上有教程，这里不再赘述。

配置python的虚拟环境
~~~bash
python3 -m venv <虚拟环境名称>
source <虚拟环境名称>/bin/activate
~~~

这里我给个示例：
~~~shell
python3 -m venv myenv
source myenv/bin/activate
~~~

这么做，shell会进入到虚拟环境，就可以使用pip安装telegram的bot库
~~~shell
pip install python-telegram-bot
~~~

然后，打开脚本，前面有几个基本参数，需要你自己修改。
~~~python
API_TOKEN = '123456'    #你的机器人密钥
TOTP_SECRET = '123456'  # 替换为你的 TOTP 密钥

# 设置允许操作的用户ID列表（可以是一个或多个ID）
AUTHORIZED_USER_IDS = [123456]  # 替换为你的用户ID
~~~

这个TOTP是对于我的一个小功能，因为我的服务器靠TOTP登录。没有这方面需求的可以忽略，随便给几个字符。
用户ID是判断和机器人对话的是不是你本人，可以用https://t.me/userinfobot这个机器人查询自己的ID。
改好后，可以使用supervisor挂着，这里我也再写一下方法：
~~~bash
sudo apt install supervisor
~~~

不好意思我用的是Debian，RHEL系的朋友们要自己打了。
来到/etc/supervisor/conf.d这个目录，随便创建一个后缀名是.conf的文件
~~~conf
[program:telegram_bot]
command=<虚拟环境的路径>/bin/python3 <脚本路径>
directory=<脚本所在目录>
autostart=true
autorestart=true
stderr_logfile=/var/log/telegram_bot.err.log
stdout_logfile=/var/log/telegram_bot.out.log
user=root    #运行脚本使用的用户，
~~~

然后重启一下supervisor
~~~bash
sudo systemctl restart supervisor
~~~

如果成功运行，给机器人发送/test，那么就会回应。
***
## 3.命令使用

脚本目前有以下命令：
ban - 在特定的 jail 中封禁 IP。
unban - 在特定的 jail 中解封 IP。
list - 列出所有 jail 或者指定 jail 的状态。
test - 检查指定服务器是否在线。
update - 热更新系统的 jail 列表，并返回更新详情。
checkban - 查询IP是否被封禁以及所在的 jail。
uuid - 生成一个或多个 UUID。
totp - 获取当前的 TOTP、剩余时间和下一个 TOTP。
help - 显示帮助信息。

先说一下ban和unban
~~~bot
/ban <jail> <IP1>,<IP2>
~~~

示例：
~~~bot
/ban sshd 192.168.3.3,192.168.4.5
~~~

这会让服务器在sshd这个jail封禁192.168.3.3和192.168.4.5这两个IP，使用英文逗号分隔。
unban同理：
~~~bot
/unban sshd 192.168.4.3
~~~

这会让服务器把在sshd里的192.168.4.3解除封禁。
此外，脚本还支持两种范围表达式：
~~~bot
/ban sshd 192.168.8.[5-9]
~~~

这是第一种，会封禁192.168.8.5到192.168.8.9的IP。
允许同时多个使用，比如[192-194].[168-170].5.9，代表：
192.168.5.9
192.169.5.9
192.170.5.9
193.168.5.9
193.169.5.9
193.170.5.9
194.168.5.9
194.169.5.9
194.170.5.9
第二种：
~~~bot
/ban sshd <192.168.10.2~192.168.10.50>
~~~

这个稍微直观一些，可以跨网段使用
这两个表达式都可以在ban和unban使用，尽管如此，还是不建议在ban使用大规模的范围表达式。
听GPT说Fail2ban使用SQLite存储IP，一下子处理这么多，SQLite八成受不了，就会卡。不过unban倒是没什么问题，挺快的。
还有一种特殊的定义字符，$all，代表全局。
~~~bot
/ban $all 192.168.5.3
~~~

意思为在所有jail里封禁192.168.5.3。

~~~bot
/unban sshd $all
~~~

解封sshd里的所有IP

~~~bot
/unban $all $all
~~~

解封所有jail里的所有IP
我相信你不会给jail的名字改为$all的

list命令：
~~~bot
/list
~~~

其实很简单，不带参数就返回所有的jail。参数是jail名，它不会直接返回，黑名单IP多一点就返回不了。所以是打包为txt后发送给你。
我也相信你服务器黑名单里的IP在一个文件内的大小不会超过2GB。

checkban命令：
~~~bot
/checkban <IP1>,<IP2>
~~~

查询一个IP有没有在你服务器里的黑名单，如果有，就显示在哪个jail里面。

UUID命令：
~~~bot
/uuid
~~~

这也算是一个小功能，参数是一个正整数，就会给你返回多少个的UUID。

update命令：
~~~bot
/update
~~~

所有jail在脚本运行时就会记录在常量里，这个命令是给在运行时添加或删除了jail的情况下更新用的。

***

## 4.最后

好了，基本就这样了。这个脚本的意外事件判断比较少，如果碰上冲突或者fail2ban没运行的，估计都会报错。。。可能还会停止运行。
没办法，GPT还写不出长复杂代码。估计改进会很少了，除非GPT-5出来了或者我学会python了。
还是开头那句话，只要好好使用应该不会有大问题。
这是本人的第一个Github项目，所以把这个上传顺便当练习使用Github了。
