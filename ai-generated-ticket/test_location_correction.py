#!/usr/bin/env python3
"""测试LLM地名矫正功能"""

import sys
from pathlib import Path

# 导入LocationCorrector
sys.path.insert(0, str(Path(__file__).parent))
from app import LocationCorrector

# DeepSeek API配置
DEEPSEEK_API_URL = "http://127.0.0.1:11434/api/generate"


def test_location_correction():
    """测试地名矫正功能"""
    # 初始化矫正器
    location_file = Path(__file__).parent / "location.json"
    corrector = LocationCorrector(location_file)

    print("=" * 80)
    print("LLM地名矫正单元测试")
    print("=" * 80)

    # 测试案例
    test_cases = [
        {
            "input": "六安市霍邱县冯岭镇拱岗村",
            "expected": "六安市霍邱县冯瓴镇拱岗村",
            "description": "错别字：冯岭 → 冯瓴"
        },
        {
            "input": "刘安市金安区三十铺镇",
            "expected": "六安市金安区三十铺镇",
            "description": "错别字：刘安 → 六安"
        },
        {
            "input": "六安市裕安区顺河镇",
            "expected": "六安市裕安区顺河镇",  # 应该保持不变
            "description": "正确地名（顺河镇）"
        },
        {
            "input": "六安市霍邱县三流乡三桥村",
            "expected": "六安市霍邱县三流乡三桥村",
            "description": "正确地名（三流乡）"
        },
        {
            "input": "六安市金安区茅坦厂镇",
            "expected": "六安市金安区毛坦厂镇",
            "description": "错别字：茅坦厂 → 毛坦厂"
        },
        {
            "input": "六安市舒城县山西镇",
            "expected": "六安市舒城县山七镇",
            "description": "错别字：山西镇 → 山七镇"
        },
    ]

    passed = 0
    failed = 0

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n测试案例 #{i}: {test_case['description']}")
        print("-" * 80)
        print(f"输入地名: {test_case['input']}")
        print(f"期望输出: {test_case['expected']}")

        try:
            # 调用LLM矫正
            result = corrector.correct_zone(test_case['input'], DEEPSEEK_API_URL)

            corrected = result.get('corrected', '')
            print(f"实际输出: {corrected}")
            print(f"矫正方法: {result.get('method', 'unknown')}")
            print(f"是否改变: {result.get('changed', False)}")

            # 验证结果
            if corrected == test_case['expected']:
                print("✓ 测试通过")
                passed += 1
            else:
                print(f"✗ 测试失败")
                print(f"  期望: {test_case['expected']}")
                print(f"  实际: {corrected}")
                failed += 1

        except Exception as e:
            print(f"✗ 测试异常: {e}")
            failed += 1

    # 总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)
    print(f"总计: {len(test_cases)} 个测试")
    print(f"通过: {passed} 个")
    print(f"失败: {failed} 个")
    print(f"成功率: {passed / len(test_cases) * 100:.1f}%")
    print("=" * 80)

    return passed == len(test_cases)


if __name__ == "__main__":
    try:
        success = test_location_correction()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n测试执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

