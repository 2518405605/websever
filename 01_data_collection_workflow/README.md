
# 1、N8N介绍
N8N官网：https://n8n.io/                                
N8N Github地址：https://github.com/n8n-io/n8n                            
N8N介绍:Flexible AI workflow automation for technical teams                                               

# 2、部署N8N服务
N8N默认是使用sqlite数据库，这是一个轻量级的数据库，在生产环境建议使用postgres数据库，并发更强更安全稳定                    
## 2.1 下载安装Docker             
官网链接如下:https://www.docker.com/                           
根据自己的操作系统选择对应的Desktop版本下载安装                             
安装成功之后启动Docker Desktop软件即可          

## 2.2 Docker部署N8N
**运行指令:**                  
打开命令行终端，在终端中运行以下N8N部署指令,在运行指令之前请先阅读指令说明部分:                     
docker run -d --name n8n -p 5678:5678 -e GENERIC_TIMEZONE="Asia/Shanghai" -e TZ="Asia/Shanghai" -v /Volumes/Files/n8n:/home/node/.n8n -v /Volumes/Files/n8ndata:/home/node/n8ndata docker.n8n.io/n8nio/n8n               
**指令说明:**        
(1)--name n8n -p 5678:5678       
为设置容器的名称和服务所要运行的端口                   
(2)GENERIC_TIMEZONE和TZ            
都是设置时区，TZ是 Linux 标准时区变量，所有主流应用都兼容，GENERIC_TIMEZONE 是 n8n 的旧版参数(新版本推荐用TZ)            
(3)-v /Volumes/Files/n8n:/home/node/.n8n       
其中“:”左边的文件路径需要提前创建好n8n文件夹并获取绝对路径       
将主机路径 /Volumes/Files/n8n 映射到容器内的 /home/node/.n8n 目录        
/home/node/.n8n 是 n8n 的默认配置文件存储路径（如工作流、凭据和设置）,通过挂载，主机上的 /Volumes/Files/n8n 目录会持久化存储这些数据，即使容器被删除，配置也不会丢失                                                       
(4)-v /Volumes/Files/n8ndata:/home/node/n8ndata         
其中“:”左边的文件路径需要提前创建好n8ndata文件夹并获取绝对路径，将主机路径 /Volumes/Files/n8ndata 映射到容器内的 /home/node/n8ndata 目录，用于存储 n8n 的额外数据                                        
(5)docker.n8n.io/n8nio/n8n           
指定n8n的最新稳定版本，相当于显式指定 docker.n8n.io/n8nio/n8n:latest                                           
**汉化说明:**                 
N8N默认是英文版本无中文语言可设置，若需要进行汉化，参考如下:               
汉化包开源地址：https://github.com/other-blowsnow/n8n-i18n-chinese/releases                           
docker run -d --name n8n -p 5678:5678 -e GENERIC_TIMEZONE="Asia/Shanghai" -e TZ="Asia/Shanghai" -e N8N_DEFAULT_LOCALE=zh-CN -v /Volumes/Files/n8n:/home/node/.n8n -v /Volumes/Files/n8ndata:/home/node/n8ndata -v /Volumes/Files/n8n_zh/dist:/usr/local/lib/node_modules/n8n/node_modules/n8n-editor-ui/dist docker.n8n.io/n8nio/n8n               
**使用N8N服务:**           
服务部署完成后，浏览器打开 http://localhost:5678/ 进入到N8N web端页面，首次需要进行注册和登录                         

## 2.3、更新N8N服务
**步骤说明:**            
(1)拉取最新镜像                
N8N镜像列表：https://hub.docker.com/r/n8nio/n8n/tags                        
docker pull docker.n8n.io/n8nio/n8n:版本号                   
(2)清理旧容器                
docker stop n8n                           
docker rm n8n                     
(3)运行新容器                  
docker run -d --name n8n -p 5678:5678 -e GENERIC_TIMEZONE="Asia/Shanghai" -e TZ="Asia/Shanghai" -e N8N_DEFAULT_LOCALE=zh-CN -v /Volumes/Files/n8n:/home/node/.n8n -v /Volumes/Files/n8ndata:/home/node/n8ndata -v /Volumes/Files/n8n_zh/dist:/usr/local/lib/node_modules/n8n/node_modules/n8n-editor-ui/dist docker.n8n.io/n8nio/n8n:版本号               
(4)验证版本                      
docker exec n8n n8n --version                                                            
**注意事项:**             
(1)务必注意本地文件夹的映射地址要和原来的一致，否则数据会不同步                   
(2)尽量一个月要更新一次，避免版本太旧                  
(3)如果是更新到最新的稳定版，指令里面的版本号可以不填                        

# 3、自动获取公众号文章            
新建工作流，并直接导入01_data_collection_workflow文件夹中提供的 RSS公众号文章自动同步工作流.json 文件，并对该工作流节点进行配置修改
公众号文章RSS来源使用国内领先、稳定、快速的一站式公众号RSS订阅平台，专注于精品内容的开放                                              
注册链接:http://www.jintiankansha.me/account/signup?invite_code=PJIFQVLQKJ                   
json格式化工具:https://tool.browser.qq.com/jsonbeautify.html                     
