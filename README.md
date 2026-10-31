# ML702 鼠标电量托盘工具

为雷神（ThundeRobot）**ML702** 2.4G 无线鼠标提供系统托盘电量显示。设备通过 USB 接收器连接（`VID 3554` / `PID F501`），系统本身不暴露电量，需通过 HID 私有协议主动查询。

## 目录结构

```
.
├── README.md
├── ThunderbotAppPkg/               # 厂家官方材料（归档）
│   ├── TRM_App_ML702cx.exe         # 官方驱动/应用安装包
│   └── ML702_installed.zip         # 安装完成后程序目录的压缩包
└── ml702_battery/                  # 托盘工具
    ├── ml702_hid.py                # 主动查询电量（动态 HID）
    ├── tray_app.py                 # 托盘 UI（动态绘制图标）
    ├── requirements.txt
    ├── build_exe.bat               # 重新打包 exe
    ├── run_tray.bat
    └── bin/ML702Battery.exe        # 可直接运行
```

## 厂家官方材料（`ThunderbotAppPkg/`）

| 文件 | 说明 |
|------|------|
| [`TRM_App_ML702cx.exe`](ThunderbotAppPkg/TRM_App_ML702cx.exe) | 厂家官方驱动安装包（ML702 纯享版应用软件）。安装后可设置 DPI、按键、灯光，并在界面中查看电量。 |
| [`ML702_installed.zip`](ThunderbotAppPkg/ML702_installed.zip) | 官方软件安装完成后目录的压缩包，对应本机路径通常为 `C:\Program Files (x86)\Thunderobot\ML702`（主程序 `OemDrv.exe`、`Cfg.ini`、皮肤资源等）。 |

官方下载入口也可参考：[雷神驱动下载页](https://www.thunderobot.com/service/download.html)（「ML702 纯享版鼠标应用软件」/「ML702 达摩鲨鼠标应用软件」）。

本项目分析官方安装目录与同厂（江萌 / Jiangmeng，`VID 3554`）HID 帧格式后，实现了独立的托盘读电量程序，**无需一直开着官方客户端**。

## 托盘工具用法

### 直接运行

双击：

`ml702_battery/bin/ML702Battery.exe`

或：

`ml702_battery/run_tray.bat`

- 托盘图标显示电量数字
- **绿色 + 闪电 + 顶部白条** = 充电中
- 蓝 / 橙 / 红 = 未充电（按电量高低）
- 约每 **3 秒**主动查询一次；右键可「立即刷新」或「退出」

### 从源码运行

```bat
cd ml702_battery
python -m pip install -r requirements.txt
python tray_app.py
```

命令行只读一次电量：

```bat
python ml702_hid.py
```

### 重新打包 exe

```bat
cd ml702_battery
build_exe.bat
```

产物：`ml702_battery/bin/ML702Battery.exe`

### 开机自启动

推荐用 Windows「启动」文件夹（当前用户登录后自动运行）：

1. 确认要启动的程序路径，例如仓库内的  
   `ml702_battery/bin/ML702Battery.exe`  
   或你拷贝到别处的路径（如 `D:\Apps_Personal\ThunderBot-Mouse-ML702-Battery\ML702Battery.exe`）。
2. `Win + R`，输入 `shell:startup`，回车，打开启动文件夹。
3. 在资源管理器中对 `ML702Battery.exe` 右键 → **创建快捷方式**，把快捷方式放进上述启动文件夹（可改名为 `ML702Battery`）。
4. 注销或重启后，登录时会自动出现托盘电量图标。

取消自启动：删掉启动文件夹里对应的快捷方式即可。

也可在 PowerShell 中一键创建（按实际 exe 路径改 `$exe`）：

```powershell
$exe = "D:\Apps_Personal\ThunderBot-Mouse-ML702-Battery\ML702Battery.exe"
$startup = [Environment]::GetFolderPath("Startup")
$w = New-Object -ComObject WScript.Shell
$lnk = $w.CreateShortcut((Join-Path $startup "ML702Battery.lnk"))
$lnk.TargetPath = $exe
$lnk.WorkingDirectory = Split-Path $exe
$lnk.Save()
```

## 在其他电脑上开发 / 编译

仅运行现成的 `bin/ML702Battery.exe` **不需要**安装 Python。若要改代码、从源码运行或重新打包，需要：

| 项 | 说明 |
|----|------|
| 系统 | Windows（托盘与 HID 依赖 Windows API；`pystray` 走 Win32） |
| Python | 3.10+ 建议（需已加入 `PATH`，或自行改 `build_exe.bat` / `run_tray.bat` 里的解释器路径） |
| 运行依赖 | `pip install -r ml702_battery/requirements.txt`（`hidapi`、`pystray`、`Pillow`） |
| 打包依赖 | 另装 `pip install pyinstaller`，再执行 `build_exe.bat` |
| 硬件 | 插入 ML702 2.4G 接收器（`VID 3554` / `PID F501`）才能真正读到电量 |

注意：`build_exe.bat` 里默认写死了本机 Python 路径（`set PY=...`）。换机后请改成你本机的 `python.exe`，或改成 `set PY=python`（前提是命令行里能直接跑 `python`）。

打包时 PyInstaller 会在 `ml702_battery/build/` 下生成中间文件，并可能产生 `*.spec`；这些已在 `.gitignore` 中忽略，不必提交。`bin/ML702Battery.exe` 为成品，可按需保留或提交。

## 技术说明

- 接收器：`USB\VID_3554&PID_F501`（有线模式配置中还出现 `PID F500`）
- 控制接口：Usage Page `0xFF02` / Usage `0x0002`
- 主动查询：向设备发送 17 字节帧（Report `0x08`，命令 `0x04`），解析应答中的电量百分比、电压与充电标志
- 查询前会清空 HID 输入缓冲，并忽略请求回显等无效帧，避免「被动等信号」导致的不准

与 [HaloBattery](https://github.com/HeyOkay/HaloBattery)、[python-pulsar-mouse-tool](https://github.com/andrewrabert/python-pulsar-mouse-tool) 等对同厂 `3554` 设备的描述一致，并已在本机 ML702 接收器上验证。

## 注意

1. **不要与官方 `OemDrv.exe` 同时长时间占用同一 HID 控制接口**；若托盘读不到电量，先退出雷神官方软件再试。
2. 鼠标休眠时偶发超时，动一下鼠标或点「立即刷新」即可。
3. 本工具仅用于本人设备的电量显示与互操作，请合法使用官方安装包与软件。

## 设备配置摘要（来自官方 `Cfg.ini`）

```
Title=ML702 Gaming Mouse
VID=3554
PID=f500
PID2=f501
```
