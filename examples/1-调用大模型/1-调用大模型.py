from alphora.models.llms.openai_like import OpenAILike
import asyncio
import time

llm_api_key: str = 'sk-68ac5f5ccf3540ba834deeeaecb48987'
llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
llm_model_name: str = "qwen-plus"


llm1 = OpenAILike(api_key=llm_api_key, base_url=llm_base_url, model_name='qwen-plus')
llm2 = OpenAILike(api_key=llm_api_key, base_url=llm_base_url, model_name='deepseek-v3')


llm = llm1 + llm2

# 全局列表保存各任务耗时（线程安全，因为 asyncio 是单线程事件循环）
task_durations = []


async def single_run(task_id: int):
    message = "你好，请用一句话介绍你自己。"
    start_time = time.time()
    token_count = 0
    try:
        gen = await llm.aget_streaming_response(message=message)
        async for chunk in gen:
            token_count += 1
            print(f"[Task-{task_id}] {chunk}")
    except Exception as e:
        print(f"[Task-{task_id}] Error: {e}")
    finally:
        elapsed = time.time() - start_time
        task_durations.append((task_id, elapsed, token_count))
        print(f"[Task-{task_id}] ✅ 完成 | 耗时: {elapsed:.2f}s | 接收 tokens: {token_count}")


async def main():
    num_concurrent_runs = 10  # 并发任务数
    print(f"🚀 启动 {num_concurrent_runs} 个并发任务...\n")

    start_overall = time.time()
    tasks = [single_run(i) for i in range(1, num_concurrent_runs + 1)]
    await asyncio.gather(*tasks)
    total_time = time.time() - start_overall

    # === 分析结果 ===
    print("\n" + "="*60)
    print("📊 执行时间分析:")
    for tid, dur, tokens in task_durations:
        tps = tokens / dur if dur > 0 else 0
        print(f"  Task-{tid}: {dur:.2f}s (tokens: {tokens}, TPS: {tps:.1f})")

    durations = [d for _, d, _ in task_durations]
    avg_time = sum(durations) / len(durations)
    max_time = max(durations)
    min_time = min(durations)

    print(f"\n📈 总体统计:")
    print(f"  并发任务数: {num_concurrent_runs}")
    print(f"  总耗时（从开始到全部完成）: {total_time:.2f}s")
    print(f"  单任务平均耗时: {avg_time:.2f}s")
    print(f"  最快任务: {min_time:.2f}s")
    print(f"  最慢任务: {max_time:.2f}s")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())