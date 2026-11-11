# 质检报告

运行：`6e1bdd5cad504f31bd4b0d3ae41c669f`
提供方：fixture (offline test double)

本报告按本次运行统计；候选通过检查不表示已被使用者采用。

本次模型 HTTP 请求尝试：0
计数包含超时请求，不代表服务端完成推理。

## ocr-layout-synthetic-01

OK 3 · 待人工 1 · 复用 4 · 未完成 0

### 节点 ocr-0001-0001

检查终态：OK
输入 SHA256：`ea1c0c02b6c7b01d3af058820083dc502d8143445cdae53be852f528f7b9ccb5`
执行上下文 SHA256：`df555664a15e5fb28fc2c52680988e3b054af3465efa6ee065b8ad48fc6c894b`

输入与执行上下文一致，复用运行 `d67398ae462145e389407eb533b086ab` 的终态；本次未修复此节点。

### 节点 ocr-0002-0002

检查终态：OK
输入 SHA256：`223c439727d5e7108bccf955295e178c2bf3a5cb77f8d68c505d67444cfce92b`
执行上下文 SHA256：`eb70beb4fbd3b21196d52a25de80040d27a7cd9b81a8796ff9a63bfea4882711`

输入与执行上下文一致，复用运行 `d67398ae462145e389407eb533b086ab` 的终态；本次未修复此节点。

处置原因：
```text
unsupported_node_type_not_checked
```

### 节点 ocr-0003-0006

检查终态：OK
输入 SHA256：`b77d2083e636096e283ba5c3ea22403c745a820575ce08f9e92c16609b5155fe`
执行上下文 SHA256：`26ef2763b4c67e2217ec63a13fccb6b9fe67c8abf9b505065b6cd811d1b4c54c`

输入与执行上下文一致，复用运行 `d67398ae462145e389407eb533b086ab` 的终态；本次未修复此节点。

### 节点 ocr-0007-0007

检查终态：NEEDS_HUMAN
输入 SHA256：`9b85de3494b773bba85bf190c7bc6dc01d31d41431821483af604b6e0b070889`
执行上下文 SHA256：`df555664a15e5fb28fc2c52680988e3b054af3465efa6ee065b8ad48fc6c894b`

输入与执行上下文一致，复用运行 `d67398ae462145e389407eb533b086ab` 的终态；本次未修复此节点。

处置原因：
```text
missing_operator_operand
```
