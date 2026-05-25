# 1、封装milvus数据库搜索服务为MCP Server对外提供使用
## 1.1 关于MCP协议介绍
MCP官方简介:https://www.anthropic.com/news/model-context-protocol                                                                                           
MCP文档手册:https://modelcontextprotocol.io/introduction                                                        
MCP官方服务器列表:https://github.com/modelcontextprotocol/servers                                  
PythonSDK的github地址:https://github.com/modelcontextprotocol/python-sdk                  

## 1.2 关于MCP学习项目推荐
南哥AGI研习社MCP项目分享地址:https://github.com/NanGePlus/MCPServerTest                                  
建议大家可以通过下面这几期视频详细了解下MCP相关内容                   
【大模型应用开发-MCP系列】03 为什么会出现MCP？MCP新标准(03.26版)3种传输模式,STDIO、HTTP+SSE、Streamable HTTP                       
https://youtu.be/EId3Kbmb_Ao                             
https://www.bilibili.com/video/BV1ZHEgzXEP1/                             
【大模型应用开发-MCP系列】04 使用STDIO传输模式及底层MCP SDK实现MySQL MCP Server 支持数据表资源访问和增删改查及联表查询                     
https://youtu.be/1Z_6eIufr90                 
https://www.bilibili.com/video/BV1Td79z4Ehf/                        
对应的文件夹:03_MySQLMCPServerTest/01_stdioTransportTest                  
【大模型应用开发-MCP系列】05 使用HTTP+SSE传输模式及底层MCP SDK实现MySQL MCP Server 支持数据表资源访问和增删改查及联表查询                  
https://youtu.be/QRlHRoBTHvc                  
https://www.bilibili.com/video/BV1yeEwzkEaC/                    
对应的文件夹:03_MySQLMCPServerTest/02_sseTransportTest                      
【大模型应用开发-MCP系列】06 使用Streamable HTTP传输模式及底层MCP SDK实现MySQL MCP Server 支持数据表资源访问和增删改查及联表查询                 
https://youtu.be/mSgFtBN68RA                    
https://www.bilibili.com/video/BV1cMEBzTEFD/                     
对应的文件夹:03_MySQLMCPServerTest/03_streamableTransportTest                      
【大模型应用开发-MCP系列】07 高德地图MCP Server SSE+HTTP连接模式全流程实操演示 已覆盖12大核心服务接口，提供全场景覆盖的地图服务                    
https://youtu.be/OLVHObhEP0U                    
https://www.bilibili.com/video/BV172E1zWEQw/                          
对应的文件夹:04_AmapMCPServerTest                       

## 1.3 milvus数据库搜索MCP Server测试
打开命令行终端，首先运行 python streamableHttpStart.py 脚本启动MCP Server服务                  
再运行 python milvusSearchMCPServerTest.py 脚本测试，进行服务接口的单独验证测试                                
最后运行 python clientChatTest.py 脚本测试，使用大模型进行测试，在运行脚本之前，需要在.env文件中配置大模型相关的参数及在servers_config.json文件中配置需要使用的MCP Server      
按照如下参考问题进行测试:       
(1)不指定搜索类型和条件过滤                
搜索关于时序增强关系敏感知识迁移相关的文章，并给出文章的标题、链接、发布者                
(2)指定搜索类型和条件过滤    
全文搜索关于时序增强关系敏感知识迁移相关的文章，文章发布时间在2025.09.05之前，返回3篇文章并给出文章的标题、链接、发布者              
语义搜索关于时序增强关系敏感知识迁移相关的文章，文章发布时间在2025.09.05之前，返回3篇文章并给出文章的标题、链接、发布者               
混合搜索关于时序增强关系敏感知识迁移相关的文章，文章发布时间在2025.09.05之前，返回3篇文章并给出文章的标题、链接、发布者               
(3)不指定搜索类型但指定条件过滤(存在多个过滤条件)            
搜索关于时序增强关系敏感知识迁移相关的文章，文章发布时间在2025.09.05之前，发布者是新智元，返回3篇文章并给出文章的标题、链接、发布者            
(4)不指定搜索类型但指定条件过滤(存在无关过滤条件干扰)           
搜索关于时序增强关系敏感知识迁移相关的文章，文章发布时间在2025.09.05之前，发布者是新智元，字数在200字内，价格不超过500元，返回3篇文章并给出文章的标题、链接、发布者           

