from openai import OpenAI


client = OpenAI(
    api_key="empty",
    base_url="http://127.0.0.1:8002/alphadata"
)

response = client.chat.completions.create(
    model="alphadata",
    messages=[
        {
            "role": "user",
            "content": "介绍一下故宫"
        }
    ],
    extra_body={
        "session_id": "6b0707a5-db07-4527-8b2e-87943f5cd8ef",  # 会话ID
    },
    stream=True  # 流式输出
)


# 流式输出
# for r in response:
#     char = r.choices[0].delta.content
#     print(char, end='', flush=True)


for r in response:
    char = r.choices[0].delta.content
    type = r.choices[0].delta.content_type    # 这里输出的类型，前端可根据此类型来进行相应的渲染

    print(char, end='', flush=True)
