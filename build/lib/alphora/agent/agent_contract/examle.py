
from alphora.agent.agent_contract.schema import *


# 定义一个多功能智能体
agent = AgentSpec(
    name="Guide",
    description="导游智能体",
    input_ports=[
        AgentInputPort(
            port=8000,
            name="location",
            label='接受地址',
            schema={"data_type": DataType.TEXT}
        ),
    ],
    output_ports=[
        AgentOutputPort(name="introduction", schema={"data_type": DataType.JSON})
    ]
)


#
# # 校验
# ok, errs = agent.validate_input("config", {"threshold": 0.9})
# assert ok
#
# df = pd.DataFrame({"id": ["a"], "value": [1.2]})
# ok, errs = agent.validate_input("data", df)
# assert ok