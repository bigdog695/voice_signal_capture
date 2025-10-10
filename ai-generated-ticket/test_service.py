#!/usr/bin/env python3
"""
12345 市民热线工单总结服务测试脚本

测试 /summarize 接口的功能，包括正常情况和异常情况。
"""

import json
import requests
import time
from typing import Any, Dict, Optional, Tuple, Union

# 测试配置
BASE_URL = "http://100.120.241.10:8001"
SUMMARIZE_URL = f"{BASE_URL}/summarize"
HEALTH_URL = f"{BASE_URL}/health"


def test_health_check():
    """测试健康检查接口"""
    print("=" * 50)
    print("测试健康检查接口")
    print("=" * 50)

    try:
        response = requests.get(HEALTH_URL, timeout=10)
        print(f"状态码: {response.status_code}")
        print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"健康检查失败: {e}")
        return False


def test_basic_functionality():
    """测试基本功能 - 标准对话记录"""
    print("\n" + "=" * 50)
    print("测试基本功能 - 标准对话记录")
    print("=" * 50)

    test_data = {
        "1759649515307_4b58f788-ee1f-4949-97d4-accc71da1f23": [
            {"citizen": "停车库太吵了，我应该提供什么资料反映呢？"},
            {"hot-line": "看一下这停车库太吵是嗯。"},
            {"citizen": "晚上睡觉半夜还在想，一天到晚吵的，烦死了。"},
            {"hot-line": "就是小区停车场的地下停车场。"},
            {"citizen": "地下停车场出入口那里没有做一点隔音处理。"},
            {"hot-line": "做隔音处理啊，您是哪个小区啊？"},
            {"citizen": "六安市三十铺镇水韵东方小区。"},
            {"citizen": "靠近进门一百二十一栋。"}
        ]
    }

    return send_test_request("基本功能测试", test_data)


def test_multiple_sessions():
    """测试多会话数据"""
    print("\n" + "=" * 50)
    print("测试多会话数据")
    print("=" * 50)

    test_data = {
        "session_001": [
            {"citizen": "路灯坏了好几天了"},
            {"hot-line": "您具体是哪个位置的路灯？"},
            {"citizen": "人民路和建设路交叉口"}
        ],
        "session_002": [
            {"citizen": "垃圾清运不及时"},
            {"hot-line": "是哪个小区的？"},
            {"citizen": "阳光花园小区东门垃圾箱"}
        ]
    }

    return send_test_request("多会话测试", test_data)


def test_consultation_case():
    """测试咨询类工单"""
    print("\n" + "=" * 50)
    print("测试咨询类工单")
    print("=" * 50)

    test_data = {
        "consultation_case": [
            {"citizen": "请问办理营业执照需要什么材料？"},
            {"hot-line": "您要办理个体工商户还是公司营业执照？"},
            {"citizen": "个体工商户的"},
            {"hot-line": "需要身份证、经营场所证明、申请表等材料"},
            {"citizen": "在哪里办理呢？"},
            {"hot-line": "可以到市政务服务中心工商窗口办理"}
        ]
    }

    return send_test_request("咨询类测试", test_data)


def test_complaint_case():
    """测试投诉类工单"""
    print("\n" + "=" * 50)
    print("测试投诉类工单")
    print("=" * 50)

    test_data = {
        "complaint_case": [
            {"citizen": "餐厅油烟太大，影响我们居民生活"},
            {"hot-line": "是哪家餐厅？具体位置在哪里？"},
            {"citizen": "是楼下的川菜馆，每天晚上油烟很重"},
            {"hot-line": "您是哪个小区的住户？"},
            {"citizen": "金桂花园2号楼的住户"},
            {"citizen": "希望环保部门能检查一下他们的油烟净化设备"}
        ]
    }

    return send_test_request("投诉类测试", test_data)


def test_empty_data():
    """测试空数据"""
    print("\n" + "=" * 50)
    print("测试空数据")
    print("=" * 50)

    test_data = {}

    return send_test_request("空数据测试", test_data, expect_error=True)


def test_invalid_format():
    """测试无效格式"""
    print("\n" + "=" * 50)
    print("测试无效格式")
    print("=" * 50)

    test_data = {
        "invalid_session": "这不是一个数组"
    }

    return send_test_request("无效格式测试", test_data, expect_error=True)


def test_mixed_messages():
    """测试混合消息格式"""
    print("\n" + "=" * 50)
    print("测试混合消息格式")
    print("=" * 50)

    test_data = {
        "mixed_session": [
            {"citizen": "我要反映一个问题"},
            {"hot-line": "请您说"},
            {"citizen": "公园的健身器材坏了"},
            {"other_field": "这个字段会被忽略"},
            {"hot-line": "是哪个公园？"},
            {"citizen": "市中心公园"}
        ]
    }

    return send_test_request("混合消息测试", test_data)


def send_test_request(
    test_name: str,
    data: Dict[str, Any],
    expect_error: bool = False,
    return_response: bool = False,
) -> Union[bool, Tuple[bool, Optional[Dict[str, Any]]]]:
    """Send a request to the summarizer test endpoint."""
    print(f"\nTest name: {test_name}")
    print("Request payload:")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    def _wrap(success: bool, payload: Optional[Dict[str, Any]] = None):
        return (success, payload) if return_response else success

    try:
        start_time = time.time()
        response = requests.post(
            SUMMARIZE_URL,
            json=data,
            headers={'Content-Type': 'application/json'},
            timeout=120,
        )
        elapsed = time.time() - start_time
        print(f"\nElapsed: {elapsed:.2f}s")
        print(f"Status code: {response.status_code}")

        if expect_error:
            if response.status_code >= 400:
                detail = response.json().get('detail', 'Unknown error')
                print("Expected error received.")
                print(f"Detail: {detail}")
                return _wrap(True, None)
            print("Expected error, but request succeeded.")
            return _wrap(False, None)

        if response.status_code == 200:
            result: Dict[str, Any] = response.json()
            print("Response JSON:")
            print(json.dumps(result, ensure_ascii=False, indent=2))

            required_fields = ['ticket_type', 'ticket_zone', 'ticket_title', 'ticket_content']
            missing_fields = [field for field in required_fields if field not in result]

            if missing_fields:
                print(f"Missing fields: {missing_fields}")
                return _wrap(False, result)

            print("Response contains all required fields.")
            return _wrap(True, result)

        try:
            detail = response.json().get('detail', 'Unknown error')
        except Exception:
            detail = response.text
        print("Request failed.")
        print(f"Detail: {detail}")
        return _wrap(False, None)

    except requests.exceptions.Timeout:
        print("Request timed out.")
        return _wrap(False, None)
    except requests.exceptions.ConnectionError:
        print("Connection error.")
        return _wrap(False, None)
    except Exception as exc:
        print(f"Unexpected error: {exc}")
        return _wrap(False, None)


def test_invalid_json():
    """测试无效 JSON"""
    print("\n" + "=" * 50)
    print("测试无效 JSON 格式")
    print("=" * 50)

    try:
        response = requests.post(
            SUMMARIZE_URL,
            data="这不是有效的JSON",
            headers={'Content-Type': 'application/json'},
            timeout=10
        )

        print(f"状态码: {response.status_code}")
        if response.status_code == 400:
            print("✅ 正确处理无效 JSON")
            return True
        else:
            print("❌ 未正确处理无效 JSON")
            return False

    except Exception as e:
        print(f"❌ 测试异常: {e}")
        return False


def main():
    """运行所有测试"""
    print("🚀 开始测试 12345 市民热线工单总结服务")
    print(f"服务地址: {BASE_URL}")

    # 测试列表
    tests = [
        # ("健康检查", test_health_check),
        ("基本功能", test_basic_functionality),
        # ("多会话数据", test_multiple_sessions),
        # ("咨询类工单", test_consultation_case),
        # ("投诉类工单", test_complaint_case),
        # ("空数据处理", test_empty_data),
        # ("无效格式处理", test_invalid_format),
        # ("混合消息", test_mixed_messages),
        # ("无效JSON处理", test_invalid_json)
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except KeyboardInterrupt:
            print("\n测试被用户中断")
            break
        except Exception as e:
            print(f"\n❌ 测试 '{test_name}' 发生异常: {e}")
            results.append((test_name, False))

    # 输出测试结果汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    passed = 0
    failed = 0

    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\n总计: {len(results)} 个测试")
    print(f"通过: {passed} 个")
    print(f"失败: {failed} 个")
    print(f"成功率: {passed / len(results) * 100:.1f}%")

    if failed == 0:
        print("\n🎉 所有测试通过！")
    else:
        print(f"\n⚠️  有 {failed} 个测试失败，请检查服务状态")


if __name__ == "__main__":
    main()
