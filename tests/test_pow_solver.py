# -*- coding: utf-8 -*-
"""
PoW 挑战求解器测试类

测试内容包括：
- nonce 提取（从挑战页 HTML）
- PoW 求解（已知 nonce → 已知 i）
- 挑战页识别
- cookie 返回格式验证
"""

import hashlib
import os
import sys
import unittest

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zlibrary import pow_solver


class PowSolverTest(unittest.TestCase):
    """PoW 求解器测试"""

    # 已知 nonce（来自实际挑战页，已验证 i=52496 为正确解）
    # nonce 首字符 'F' → n1 = int('F', 16) = 15
    KNOWN_NONCE = "FFC94FB5494564E790490AE31D23373533758C70"
    EXPECTED_I = 52496

    # 模拟挑战页 HTML（包含 nonce）
    MOCK_CHALLENGE_HTML = """
    <html>
    <head><title>Checking your browser...</title></head>
    <body>
    <script>
    var nonce = 'FFC94FB5494564E790490AE31D23373533758C70';
    // PoW challenge code...
    </script>
    </body>
    </html>
    """

    # 普通页面 HTML（非挑战页）
    NORMAL_HTML = """
    <html>
    <head><title>Z-Library - Search Results</title></head>
    <body>
    <z-bookcard id="123" href="/book/xxx" download="/dl/xxx">...</z-bookcard>
    </body>
    </html>
    """

    def test_extract_nonce(self):
        """测试从挑战页 HTML 提取 nonce"""
        nonce = pow_solver.extract_nonce(self.MOCK_CHALLENGE_HTML)
        self.assertEqual(nonce, self.KNOWN_NONCE)
        self.assertEqual(len(nonce), 40)

    def test_extract_nonce_not_found(self):
        """测试无法提取 nonce 时抛出 ValueError"""
        with self.assertRaises(ValueError):
            pow_solver.extract_nonce("<html><body>No nonce here</body></html>")

    def test_solve_pow_known_nonce(self):
        """测试 PoW 求解（已知 nonce → 已知 i）

        验证：SHA1(nonce + str(52496)) 的第 15 字节 == 0xb0 且第 16 字节 == 0x0b
        """
        result = pow_solver.solve_pow(self.KNOWN_NONCE)

        # 验证返回的 cookie 字典
        self.assertIn("c_token", result)
        self.assertIn("c_time", result)

        # 验证 c_token 格式：nonce + str(i)
        self.assertEqual(result["c_token"], self.KNOWN_NONCE + str(self.EXPECTED_I))

        # 验证 c_time 是字符串数字
        float(result["c_time"])  # 不抛异常即通过

    def test_solve_pow_correctness(self):
        """验证 PoW 求解结果确实满足字节条件"""
        result = pow_solver.solve_pow(self.KNOWN_NONCE)
        c_token = result["c_token"]

        # c_token = nonce + str(i)，提取 i
        i_str = c_token[len(self.KNOWN_NONCE):]
        i = int(i_str)

        # 验证 SHA1(nonce + str(i)) 满足字节条件
        digest = hashlib.sha1((self.KNOWN_NONCE + str(i)).encode()).digest()
        n1 = int(self.KNOWN_NONCE[0], 16)  # n1 = 15

        self.assertEqual(digest[n1], 0xB0, f"Byte {n1} should be 0xB0")
        self.assertEqual(digest[n1 + 1], 0x0B, f"Byte {n1+1} should be 0x0B")

    def test_solve_challenge(self):
        """测试完整流程：从挑战页 HTML 提取 nonce + 求解"""
        result = pow_solver.solve_challenge(self.MOCK_CHALLENGE_HTML)

        self.assertIn("c_token", result)
        self.assertIn("c_time", result)
        self.assertTrue(result["c_token"].startswith(self.KNOWN_NONCE))

    def test_is_challenge_page_true(self):
        """测试识别挑战页（包含特征词）"""
        self.assertTrue(pow_solver.is_challenge_page(self.MOCK_CHALLENGE_HTML))

        # 测试标题特征词
        self.assertTrue(pow_solver.is_challenge_page("<html><title>Checking your browser...</title></html>"))
        self.assertTrue(pow_solver.is_challenge_page("<html>Checking your browser before access</html>"))

    def test_is_challenge_page_false(self):
        """测试识别非挑战页"""
        self.assertFalse(pow_solver.is_challenge_page(self.NORMAL_HTML))
        self.assertFalse(pow_solver.is_challenge_page("<html><body>Normal page</body></html>"))
        self.assertFalse(pow_solver.is_challenge_page(""))

    def test_solve_pow_returns_cookies(self):
        """测试 solve_pow 返回正确的 cookie 格式"""
        result = pow_solver.solve_pow(self.KNOWN_NONCE)

        # 验证返回的是字典
        self.assertIsInstance(result, dict)

        # 验证包含两个 cookie
        self.assertEqual(len(result), 2)

        # 验证 c_token 以 nonce 开头
        self.assertTrue(result["c_token"].startswith(self.KNOWN_NONCE))

        # 验证 c_time 可以转为浮点数
        c_time = float(result["c_time"])
        self.assertGreaterEqual(c_time, 0)


if __name__ == "__main__":
    unittest.main()
