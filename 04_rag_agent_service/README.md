# 1、项目介绍 
进入到如下项目进行Agent调用MCP Server的测试                             
https://github.com/2518405605/websever

本次测试代码是基于如下视频对应代码基础上进行调整:                              
【功能扩展】从零构建生产级AI Agent服务:新增历史会话管理和恢复、长期记忆管理、短期记忆管理、会话过期动态调整 API后端接口服务(含完整前端demo)                  
https://youtu.be/o47MzUybB3Y                 
https://www.bilibili.com/video/BV1tuNXzREmc/                       

测试代码已经提供，把 04_rag_agent_service 文件夹下载后放到该项目根目录下进行测试

**主要实现的功能:**                                 
- 使用FastAPI框架实现对外提供Agent智能体API后端接口服务                                         
- 使用LangGraph中预置的ReAct架构的Agent                                                        
- 支持Short-term(短期记忆)并使用PostgreSQL进行持久化存储                                                                     
- 支持Function Calling，包含自定义工具和MCP Server提供的工具                                                 
- 支持Human in the loop(HIL 人工审查)对工具调用提供人工审查功能，支持四种审查类型                                                                                     
- 支持多厂家大模型接口调用，OpenAI、阿里通义千问、本地开源大模型(Ollama)等                                           
- 支持Redis存储用户会话状态,支持客户端的故障恢复和服务端的故障恢复                                              
- 使用功能强大的rich库实现前端demo应用,与后端API接口服务联调                
- 支持动态调整会话的过期时间                                                 
- 支持用户登录到系统后自动打开最近一次使用的会话，若无则新建会话                                                                                     
- 支持历史会话管理和历史会话恢复                               
- 支持修剪短期记忆中的聊天历史以满足上下文对token数量或消息数量的限制                           
- 支持读取和写入长期记忆(如用户偏好设置等)                     


