```text
[AgentSpec]
  |
  |-- name: string
  |-- display_name: string
  |-- description: string
  |-- version: string
  |-- category: string
  |-- input_ports: [InputPort]
  |   |-- [0..*] InputPort
  |       |-- name: string
  |       |-- label: string
  |       |-- description: string
  |       |-- required: boolean
  |       |-- schema_: PortSchema
  |           |-- data_type: DataType (enum)
  |           |-- fields: [FieldSchema]
  |               |-- [0..*] FieldSchema
  |                   |-- name: string
  |                   |-- type: string
  |                   |-- required: boolean
  |                   |-- description: string
  |                   |-- example: any
  |                   |-- constraints: FieldConstraint
  |                       |-- min_value: number
  |                       |-- max_value: number
  |                       |-- min_length: integer
  |                       |-- max_length: integer
  |                       |-- pattern: string
  |                       |-- enum: [any]
  |
  |-- output_ports: [OutputPort]
      |-- [0..*] OutputPort
          |-- name: string
          |-- description: string
          |-- schema_: PortSchema (同上)
```