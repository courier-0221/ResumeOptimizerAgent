# 邮件发送

优化完成后可以通过 SMTP 自动发送优化后的简历 PDF：

```bash
python test/core/test_agent.py \
  -r test/pdf/test_1.pdf \
  -t "Python后端开发工程师" \
  --email-to hr@example.com
```

同时发送岗位匹配分析报告：

```bash
python test/core/test_agent.py \
  -r test/pdf/test_1.pdf \
  -t "Python后端开发工程师" \
  --email-to hr@example.com \
  --email-report
```

`.env` 中需要配置 SMTP：

```env
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USERNAME=your_email@qq.com
SMTP_PASSWORD=your_email_authorization_code
SMTP_FROM=your_email@qq.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

如果使用 465 端口，通常需要：

```env
SMTP_PORT=465
SMTP_USE_TLS=false
SMTP_USE_SSL=true
```

## 163 邮箱配置示例

163 邮箱建议先在网页端开启 SMTP 服务，并生成“客户端授权码”。`SMTP_PASSWORD`
通常应填写客户端授权码，而不是邮箱登录密码。

推荐使用 SSL 端口：

```env
SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_USERNAME=cv_optimizer_agent@163.com
SMTP_PASSWORD=your_163_authorization_code
SMTP_FROM=cv_optimizer_agent@163.com
SMTP_USE_TLS=false
SMTP_USE_SSL=true
```

也可以使用 STARTTLS 端口：

```env
SMTP_HOST=smtp.163.com
SMTP_PORT=587
SMTP_USERNAME=cv_optimizer_agent@163.com
SMTP_PASSWORD=your_163_authorization_code
SMTP_FROM=cv_optimizer_agent@163.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

如果暂时只想测试简历优化流程，不测试邮件发送，请不要传 `--email-to`。
