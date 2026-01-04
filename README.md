工具已实现功能：
1.可以保存用户数据，记录上一次关闭程序的网址和其他数据；
2.网页打开后自动进入滚动状态；
3.界面实时显示翻滚间隔；
4.用户可调节翻滚间隔，能通过手动输入进行修改（手动输入后需点击按钮“速度设定”）。

注意事项：
本工具适配windows系统，在其他系统可能出现数据

请导航目录到驱动所在文件夹，驱动所在文件夹内必须带有浏览器对应版本的驱动文件，名称为msedgedriver.exe或chromedriver.exe（均是可执行文件exe）

如何下载驱动？
Edge官方：https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver?form=MA13LH#downloads
Chrome指引：https://zhuanlan.zhihu.com/p/1893999472998081839
	由于官方网址可能产生变化，以及DownLoad时驱动文件名称不够清晰，个人建议去知乎搜索“chrome驱动”或“edge驱动”
  
请不要用工具打开多个浏览器进程（切换浏览器先关闭网页），建议只打开一个网页，工具可能无法在你想要的网页里滚动。

建议输入的网址从浏览器中完整复制

最大间隔为60秒，最小间隔为0.5秒

工具产生的用户数据在C盘的local\AutoNovelReader中，删除该文件会清空你所有网站的账号登录状态。
