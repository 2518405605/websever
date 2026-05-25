# 1、部署milvus数据库服务
## 1.1 milvus介绍  
Milvus 是一个开源云原生向量数据库，专为在海量向量数据集上进行高性能相似性搜索而设计       
它建立在流行的向量搜索库（包括 Faiss、HNSW、DiskANN 和 SCANN）之上，可为人工智能应用和非结构化数据检索场景提供支持          
官方地址:https://milvus.io/docs/zh                

## 1.2 部署milvus数据库服务                  
参考官方文档进行安装部署 https://milvus.io/docs/zh/install_standalone-docker-compose.md           
**安装Docker:**           
官网链接如下:https://www.docker.com/ 根据自己的操作系统选择对应的Desktop版本下载安装                                    
安装成功之后启动Docker Desktop软件即可                 
**运行指令:**                  
打开命令行终端，进入到docker-compose.yml所在文件夹，运行以下指令:                           
docker compose up -d             

## 1.3 使用milvus
milvus数据库服务启动成功之后，安装官方提供的可视化客户端进行使用，参考如下说明进行安装部署                              
https://github.com/zilliztech/attu               
直接使用docker的方式进行部署使用也可以下载打包好的release包直接使用                  
http://localhost:8000                   


# 2、基于milvus进行知识库搭建       
首先创建数据库，其次根据业务数据定义schema、创建索引、创建集合，然后进行业务数据的插入，最终进行数据搜索                       
## 2.1 创建数据库      
打开命令行终端，运行 python 01_createDatabase.py 脚本          

## 2.2 创建集合    
打开命令行终端，运行 python 02_createCollection.py 脚本                  
根据要存储的业务数据进行schema定义、创建索引、集合创建，业务数据如下所示:             
{           
    "docId": "article_b7f27241-1c45-4422-8032-0ee0851e4883",             
    "title": "AI智能体是否能预测未来？字节跳动seed发布FutureX动态评测基准",                
    "link": "http://mp.weixin.qq.com/s?__biz=MzA3MzI4MjgzMw==&mid=2650988457&idx=3&sn=f7e1569141a6aaa26e20a9121c9a",             
    "pubDate": "2025.08.31 13:30:00",            
    "pubAuthor": "机器之心",              
    "content": "你有没有想过，AI 不仅能记住过去的一切，还能预见未知的未来？\n\n想象一下，让 AI 预测下周的股价……                
}            

## 2.3 插入数据 
打开命令行终端，运行 python 03_insertData.py 脚本                       

## 2.4 数据搜索
(1)语义搜索和查询测试                       
打开命令行终端，运行 python 04_basicSearch.py 脚本                       
(2)全文搜索测试(关键词全文匹配)                        
打开命令行终端，运行 python 05_fullTextSearch.py 脚本                       
(3)混合搜索测试(语义搜索+全文搜索)                        
打开命令行终端，运行 python 06_hybridTextSearch.py 脚本                          
  
