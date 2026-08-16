#!/usr/bin/env python3
"""CI 辅助脚本：解析 pytest JUnit XML 判定测试真实成败

背景：pytest 在 Windows 上存在"全部测试通过但进程返回非 0 退出码"的环境问题
（pytest-dev/pytest#9320 同类），导致 CI 误报失败。因此 CI 的测试步骤以
--junitxml 生成结果文件，由本脚本解析判定——真有失败/错误才以退出码 1 结束。

用法：python scripts/check_test_results.py [test-results.xml]
"""

import sys
import xml.etree.ElementTree as ET

path = sys.argv[1] if len(sys.argv) > 1 else "test-results.xml"

try:
    root = ET.parse(path).getroot()
except Exception as e:
    print(f"无法解析测试结果 XML {path}: {e}")
    sys.exit(1)

# pytest 的 junitxml 根是 <testsuites>，计数在子元素 <testsuite> 上
suite = root if root.tag == "testsuite" else root.find("testsuite")
if suite is None:
    print(f"测试结果 XML 中未找到 <testsuite>: {path}")
    sys.exit(1)

failures = int(suite.get("failures", 0))
errors = int(suite.get("errors", 0))
print(
    f"JUnit 结果: tests={suite.get('tests')} failures={failures} "
    f"errors={errors} skipped={suite.get('skipped')}"
)
sys.exit(1 if (failures + errors) > 0 else 0)
