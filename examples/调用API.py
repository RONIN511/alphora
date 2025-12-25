from openai import OpenAI


client = OpenAI(
    api_key="chatbi",
    base_url="http://127.0.0.1:8002/alphadata",
)

response = client.chat.completions.create(
    model="chatexcel",
    messages=[
        {
            "role": "user",
            "content": "看下"
        }
    ],
    extra_body={
        "session_id": "6b0707a5-db07-4527-8b2e-87943f5cd8ef",  # 会话ID
    },
    stream=True  # 流式输出
)

# 流式输出
for r in response:
    char = r.choices[0].delta.content
    print(char, end='', flush=True)
