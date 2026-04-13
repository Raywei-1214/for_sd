import sys
import os
import subprocess

print("=" * 60)
print("           安装 aiohttp 库")
print("=" * 60)
print()

# 切换到 python_portable 目录
script_dir = os.path.dirname(os.path.abspath(__file__))
python_portable_dir = os.path.join(script_dir, 'python_portable')
os.chdir(python_portable_dir)

print(f"[1/3] 当前目录: {os.getcwd()}")
print()

# 检查 Python
print("[2/3] 检查 Python...")
result = subprocess.run([sys.executable, '--version'], capture_output=True, text=True)
if result.returncode == 0:
    print(f"[√] Python 版本: {result.stdout.strip()}")
else:
    print("[×] Python 未找到")
    input("按回车键退出...")
    sys.exit(1)
print()

# 安装 aiohttp
print("[3/3] 安装 aiohttp...")
print("使用官方源安装...")

pip_commands = [
    [sys.executable, '-m', 'pip', 'install', 'aiohttp', '--no-proxy'],
    [sys.executable, '-m', 'pip', 'install', 'aiohttp', '-i', 'https://pypi.org/simple/', '--no-proxy'],
    [sys.executable, '-m', 'pip', 'install', 'aiohttp', '--default-timeout=100'],
]

for i, cmd in enumerate(pip_commands, 1):
    print(f"尝试方法 {i}/{len(pip_commands)}...")
    print(f"命令: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print("[√] aiohttp 安装成功！")
        print()
        print("=" * 60)
        print("           安装完成！")
        print("=" * 60)
        input("按回车键退出...")
        sys.exit(0)
    else:
        print(f"[!] 方法 {i} 失败")
        print(f"错误: {result.stderr[:200]}")
        print()

print("[×] 所有方法都失败")
print()
print("请尝试手动安装：")
print(f"  cd {python_portable_dir}")
print(f"  {sys.executable} -m pip install aiohttp --no-proxy")
print()
input("按回车键退出...")
sys.exit(1)
