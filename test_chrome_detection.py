
# -*- coding: utf-8 -*-
import os
import sys

# 导入主脚本的函数
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dreamina_register_playwright_usa import find_chrome_browser

print("=" * 60)
print("Chrome浏览器检测测试")
print("=" * 60)
print()

chrome_path = find_chrome_browser()

print()
if chrome_path:
    print("✓ Chrome检测成功！")
    print(f"  路径: {chrome_path}")
    
    # 验证文件
    if os.path.exists(chrome_path):
        print("  ✓ 文件存在")
    else:
        print("  ✗ 文件不存在")
    
    if os.path.isfile(chrome_path):
        print("  ✓ 是文件")
    else:
        print("  ✗ 不是文件")
    
    if chrome_path.lower().endswith('.exe'):
        print("  ✓ 是.exe文件")
    else:
        print("  ✗ 不是.exe文件")
    
    try:
        file_size = os.path.getsize(chrome_path)
        print(f"  ✓ 文件大小: {file_size / 1024 / 1024:.1f}MB")
        if file_size > 1024 * 1024:
            print("  ✓ 文件大小合理")
        else:
            print("  ✗ 文件太小，可能不是有效Chrome")
    except Exception as e:
        print(f"  ✗ 获取文件大小失败: {e}")
else:
    print("✗ 未检测到Chrome浏览器")
    print("  程序将使用Playwright内置Chromium浏览器")

print()
print("=" * 60)
print("测试完成")
print("=" * 60)
