"""
对话逻辑：chat / chat_stream 与全局运行锁
==========================================

从 agent.py 拆分而来。chat 与 chat_stream 接收 agent_ctx 参数，
不直接依赖全局 agent 实例；_run_lock 保证同一进程内所有 agent 运行
（用户对话/定时任务/提醒触发）串行执行，避免并发 run 共享同一组
MCP 工具集导致会话冲突（pydantic-ai 已知问题 #2700/#2355）。
"""

import asyncio

from history import ModelRequest, UserPromptPart

# 全局运行锁：同一进程内所有 agent 运行（用户对话/定时任务/提醒触发）串行执行
_run_lock = asyncio.Lock()


async def chat(
    agent_ctx,
    message: str,
    history=None,
    memory=None,
    original_message: str | None = None,
) -> list:  # pyright: ignore[reportMissingTypeArgument]
    """在 agent 上下文内发送消息并输出回复

    Args:
        memory: 外部记忆系统实例，启用时自动检索相似记忆并注入上下文
        original_message: 用户原始输入（不带记忆/附件注入）。Web 端传入，
            未传入时回退到本函数收到的 message 参数（CLI 场景即原始输入）。
    """
    # 保存原始用户输入用于后续记忆判断（避免增强后消息干扰）
    raw_question = message
    restore_to = original_message if original_message is not None else message

    # 外部记忆检索：在用户消息前注入相关历史（耗时操作放线程，避免阻塞事件循环）
    if memory and memory.enabled:
        memories = await asyncio.to_thread(memory.search, message)
        context = memory.format_context(memories)
        if context:
            message = context + message

    async with _run_lock:
        result = await agent_ctx.run(message, message_history=history)
    print(result.output, flush=True)

    # 存储本轮问答到记忆（用原始问题判断，不是增强后的）
    if memory and memory.enabled:
        await asyncio.to_thread(memory.add, raw_question, result.output)

    new_msgs = result.new_messages()
    # 还原用户消息为原始输入：记忆/附件注入只属于本轮上下文，不写入历史，
    # 否则重新打开会话会看到"长期记忆""附件内容"等杂乱前缀
    for m in new_msgs:
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, UserPromptPart):
                    try:
                        p.content = restore_to
                    except Exception:  # noqa: BLE001  # 个别版本字段只读时保持原样
                        pass
                    break
            break
    return new_msgs


async def chat_stream(
    agent_ctx,
    message: str,
    history=None,
    memory=None,
    original_message: str | None = None,
):
    """流式对话：逐块产出事件字典，结束时通过 StopAsyncIteration.value 返回本轮消息

    Yields:
        {"type": "text", "text": str}              文本增量
        {"type": "tool", "toolName": str}          工具调用开始
        {"type": "toolResult", "toolName": str}    工具执行完成

    与 chat() 行为对齐：记忆检索注入、消息历史还原、记忆存储。
    整个 run 持有 _run_lock，保证与 chat() 串行，规避 MCP 并发冲突。
    """
    raw_question = message
    restore_to = original_message if original_message is not None else message

    # 外部记忆检索：在用户消息前注入相关历史（耗时操作放线程，避免阻塞事件循环）
    if memory and memory.enabled:
        memories = await asyncio.to_thread(memory.search, message)
        context = memory.format_context(memories)
        if context:
            message = context + message

    from pydantic_ai import CallToolsNode, ModelRequestNode
    from pydantic_ai.messages import ToolCallPart, ToolReturnPart
    from pydantic_graph import End

    async with _run_lock:
        async with agent_ctx.iter(message, message_history=history) as run:
            node = run.next_node
            while not isinstance(node, End):
                if isinstance(node, ModelRequestNode):
                    # 上一轮工具调用的结果已回到模型：先通知前端工具完成
                    for part in node.request.parts:
                        if isinstance(part, ToolReturnPart):
                            yield {"type": "toolResult", "toolName": part.tool_name}
                    # 真流式：逐块产出模型文本
                    async with node.stream(run.ctx) as stream:
                        async for delta in stream.stream_text(delta=True):
                            yield {"type": "text", "text": delta}
                elif isinstance(node, CallToolsNode):
                    # 模型决定调用工具：通知前端展示工具消息
                    for part in node.model_response.parts:
                        if isinstance(part, ToolCallPart):
                            yield {"type": "tool", "toolName": part.tool_name}
                node = await run.next(node)

            result = run.result
            if result is None:
                raise RuntimeError("流式运行未产生结果")
            output = result.output
            new_msgs = run.new_messages()

    # 还原用户消息为原始输入（记忆/附件注入只属于本轮上下文，不写入历史）
    for m in new_msgs:
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, UserPromptPart):
                    try:
                        p.content = restore_to
                    except Exception:  # noqa: BLE001  # 个别版本字段只读时保持原样
                        pass
                    break
            break

    # 存储本轮问答到记忆（用原始问题判断，不是增强后的）
    if memory and memory.enabled:
        await asyncio.to_thread(memory.add, raw_question, output)

    print(output, flush=True)
    # 异步生成器不能 return 带值，最后一个事件携带本轮消息
    yield {"type": "done", "new_msgs": new_msgs}
