#include"log.h"
#include<iostream>
#include<vector>
#include<string>
#include<functional>
#include<map>
namespace eric{

const char * LogLevel:: ToString(LogLevel::Level level){
    switch(level){//# 是 C/C++ 中的字符串化运算符 宏参数 name 转换为一个字符串常量
#define XX(name) \
    case LogLevel::name: \
        return #name; \    
        break;

    XX(DEBUG)  ;
    XX(INFO);
    XX(WARN);
    XX(ERROR);
    XX(FATAL);
#undef XX   
    default :
        return "UNKNOW";
    }
    return "UNKNOW";
}

LogEventWarp::LogEventWarp(LogEvent::ptr e)
    :m_event(e){
}

LogEventWarp::~LogEventWarp(){
    m_event->getLogger()->log(m_event->getLevel(),m_event);
}
std::stringstream& LogEventWarp::getSS(){
    return m_event->getSS();
}

// void LogEvent::format(const char* fmt, ...){
//     va_list al;
//     va_start(al,fmt);
//     format(fmt,al);
//     va_end(al);
// }
// void  LogEvent::format(const char* fmt,va_list al){
//     char*buf =nullptr;
//     int len =vasprintf(&buf,fmt,al);
//     if(len!=-1){
//         m_ss<<std::string(buf,len);
//         free (buf);
//     }
// }

class MessageFormatItem:public LogFormatter::FormatItem{
public:
    MessageFormatItem(const std::string& str =""){}
    void format(std::ostream& os,Logger::ptr logger,LogLevel::Level level,LogEvent::ptr event)override{
        os<<event->getContent();
    }
};

class LevelFormatItem:public LogFormatter::FormatItem{
public:
    LevelFormatItem(const std::string& str =""){}
    void format(std::ostream& os,Logger::ptr logger,LogLevel::Level level,LogEvent::ptr event)override{
        os<<LogLevel::ToString(level);
    }
};
class ElapseFormatItem:public LogFormatter::FormatItem{
public:
    ElapseFormatItem(const std::string& str =""){}
    void format(std::ostream& os,Logger::ptr logger,LogLevel::Level level,LogEvent::ptr event)override{
        os<<event->getElapse();
    }
};
class NameFormatItem:public LogFormatter::FormatItem{
public:
    NameFormatItem(const std::string& str =""){}
    void format(std::ostream& os,Logger::ptr logger,LogLevel::Level level,LogEvent::ptr event)override{
        os<<event->getElapse();
    }
};
class ThreadFormatItem:public LogFormatter::FormatItem{
public:
    ThreadFormatItem(const std::string& str =""){}
    void format(std::ostream& os,Logger::ptr logger,LogLevel::Level level,LogEvent::ptr event)override{
        os<<event->getThread();
    }
};
class FiberFormatItem:public LogFormatter::FormatItem{
public:
    FiberFormatItem(const std::string& str =""){}
    void format(std::ostream& os,Logger::ptr logger,LogLevel::Level level,LogEvent::ptr event)override{
        os<<event->getFiber();
    }
};
class DataTimeFormatItem:public LogFormatter::FormatItem{
public:
    DataTimeFormatItem(const std::string& format="%Y:%m:%d %H:%M:%S")
        :m_format(format){}
    void format(std::ostream& os,Logger::ptr logger,LogLevel::Level level,LogEvent::ptr event)override{
        os<<event->getTime();
    }
private:
    std::string m_format;
};
class FilenameFormatItem:public LogFormatter::FormatItem{
public:
    FilenameFormatItem(const std::string& str =""){}
    void format(std::ostream& os,Logger::ptr logger,LogLevel::Level level,LogEvent::ptr event)override{
        os<<event->getFile();
    }
};
class LineFormatItem:public LogFormatter::FormatItem{
public:
    LineFormatItem(const std::string& str =""){}
    void format(std::ostream& os,Logger::ptr logger,LogLevel::Level level,LogEvent::ptr event)override{
        os<<event->getLine();
    }
};

class NewLineFormatItem:public LogFormatter::FormatItem{
public:
    NewLineFormatItem(const std::string& str =""){}
    void format(std::ostream& os,Logger::ptr logger,LogLevel::Level level,LogEvent::ptr event)override{
        os<<event->getLine();
    }
};

class StringFormatItem:public LogFormatter::FormatItem{
public:
    StringFormatItem(const std::string& str )
        :m_string(str) {}
    void format(std::ostream& os,Logger::ptr logger,LogLevel::Level level,LogEvent::ptr event)override{
        os<<event->getLine();
    }
private:
    std::string m_string;
};

void Logger::log(LogLevel::Level level,const LogEvent::ptr event){
    if(level>=m_level){
        auto self=shared_from_this();
        for(auto i:m_appenders){
            i->log(self,level,event);
        }
    }
}
LogEvent::LogEvent(std::shared_ptr<Logger> logger,LogLevel::Level level,const char*file, int32_t line,uint32_t elapse,
            uint32_t thread_id,uint32_t fiber_id,uint64_t time)
            :m_file(file),
            m_line(line),
            m_elapse(elapse),
            m_threadId(thread_id),
            m_fiberId(fiber_id),
            m_time(time),
            m_logger(logger),
            m_level(level){}

Logger::Logger(const std::string& name)
    :m_name(name){
        m_formatter.reset(new LogFormatter("%d [%p] %f:%l %m %n"));
}   
void Logger::debug(LogEvent::ptr event){
    log(LogLevel::DEBUG,event);
}
void Logger::info (LogEvent::ptr event){
    log(LogLevel::INFO,event);
}
void Logger::warn (LogEvent::ptr event){
    log(LogLevel::WARN,event);
}
void Logger::error(LogEvent::ptr event){
    log(LogLevel::ERROR,event);
}
void Logger::fatal (LogEvent::ptr event){
    log(LogLevel::FATAL,event);
}

void Logger::addAppender(LogAppender::ptr appender){
    if(!appender->getFormatter()){//这个判断是干什么
        appender->setFormatter(m_formatter);
    }
    m_appenders.push_back(appender);
}
void Logger::delAppender(LogAppender::ptr appender){
    for(auto it=m_appenders.begin();it!=m_appenders.end();++it){
        if(*it==appender){
            m_appenders.erase(it);
            break;
        }
    }
}  


FileLogAppender:: FileLogAppender(const std::string& filename){

}
void FileLogAppender:: log(std::shared_ptr<Logger>logger,LogLevel::Level level,LogEvent:: ptr event){
    if(level>=m_level){
        m_filestream<<m_formatter->format(logger,level,event);
    }
}
bool FileLogAppender:: reopen(){
    if(m_filestream){
        m_filestream.close();
    }
    m_filestream.open(m_filename);
    return !!m_filestream;
}
void StdoutLogAppender:: log(std::shared_ptr<Logger>logger,LogLevel::Level level,LogEvent:: ptr event){
    if(level>=m_level){
        std::cout<<m_formatter->format(logger,level,event);
    }
}

//formatter

LogFormatter:: LogFormatter(const std::string &pattern)
    :m_pattern(pattern){
}
std::string LogFormatter:: format(std::shared_ptr<Logger>logger,LogLevel::Level level,LogEvent::ptr event){
    std::stringstream ss;
    for(auto& i:m_items){
        i->format(ss,logger,level,event);
    }
    return ss.str();
}
void LogFormatter:: init(){

    // 按顺序存储解析到的pattern项
    // 每个pattern包括一个整数类型和一个字符串，类型为0表示该pattern是常规字符串，为1表示该pattern需要转义
    // 日期格式单独用下面的dataformat存储
    std::vector<std::pair<int, std::string>> patterns;
    // 临时存储常规字符串
    std::string tmp;
    // 日期格式字符串，默认把位于%d后面的大括号对里的全部字符都当作格式字符，不校验格式是否合法
    std::string dateformat;
    // 是否解析出错
    bool error = false;
    
    // 是否正在解析常规字符，初始时为true
    bool parsing_string = true;
    // 是否正在解析模板字符，%后面的是模板字符
    // bool parsing_pattern = false;

    size_t i = 0;
    while(i < m_pattern.size()) {
        std::string c = std::string(1, m_pattern[i]);
        if(c == "%") {
            if(parsing_string==true) {
                if(!tmp.empty()) {
                    patterns.push_back(std::make_pair(0, tmp));
                }
                tmp.clear();
                parsing_string = false; // 在解析常规字符时遇到%，表示开始解析模板字符
                // parsing_pattern = true;
                i++;
                continue;
            } else {
                patterns.push_back(std::make_pair(1, c));
                parsing_string = true; // 在解析模板字符时遇到%，表示这里是一个%转义
                // parsing_pattern = false;
                i++;
                continue;
            }
        } else { // not %
            if(parsing_string) { // 持续解析常规字符直到遇到%，解析出的字符串作为一个常规字符串加入patterns
                tmp += c;
                i++;
                continue;
            } else { // 模板字符，直接添加到patterns中，添加完成后，状态变为解析常规字符，%d特殊处理
                patterns.push_back(std::make_pair(1, c));
                parsing_string = true; 
                // parsing_pattern = false;

                // 后面是对%d的特殊处理，如果%d后面直接跟了一对大括号，那么把大括号里面的内容提取出来作为dateformat
                if(c != "d") {
                    i++;
                    continue;
                }
                i++;
                if(i < m_pattern.size() && m_pattern[i] != '{') {
                    continue;
                }
                i++;
                while( i < m_pattern.size() && m_pattern[i] != '}') {
                    dateformat.push_back(m_pattern[i]);
                    i++;
                }
                if(m_pattern[i] != '}') {
                    // %d后面的大括号没有闭合，直接报错
                    std::cout << "[ERROR] LogFormatter::init() " << "pattern: [" << m_pattern << "] '{' not closed" << std::endl;
                    error = true;
                    break;
                }
                i++;
                continue;
            }
        }
    } // end while(i < m_pattern.size())


    // 模板解析结束之后剩余的常规字符也要算进去
    if(!tmp.empty()) {
        patterns.push_back(std::make_pair(0, tmp));
        tmp.clear();
    }

    // for debug 
    // std::cout << "patterns:" << std::endl;
    // for(auto &v : patterns) {
    //     std::cout << "type = " << v.first << ", value = " << v.second << std::endl;
    // }
    // std::cout << "dataformat = " << dateformat << std::endl;
    
    static std::map<std::string, std::function<FormatItem::ptr(const std::string& str)> > s_format_items = {
#define XX(str, C) \
     {#str, [](const std::string& fmt) { return FormatItem::ptr(new C(fmt));} }

        XX(m, MessageFormatItem),           // m:消息
        XX(p, LevelFormatItem),             // p:日志级别
        XX(c, NameFormatItem),        // c:日志器名称
        XX(d, DataTimeFormatItem),          // d:日期时间
        XX(r, ElapseFormatItem),            // r:累计毫秒数
        XX(f, FilenameFormatItem),          // f:文件名
        XX(l, LineFormatItem),              // l:行号
        XX(t, ThreadFormatItem),          // t:编程号
        XX(n, NewLineFormatItem),           // n:换行符
#undef XX
    };

    for(auto &v : patterns) {
        if(v.first == 0) {
            m_items.push_back(FormatItem::ptr(new StringFormatItem(v.second)));
        } else if( v.second =="d") {
            m_items.push_back(FormatItem::ptr(new DataTimeFormatItem(dateformat)));
        } else {
            auto it = s_format_items.find(v.second);
            if(it == s_format_items.end()) {
                std::cout << "[ERROR] LogFormatter::init() " << "pattern: [" << m_pattern << "] " << 
                "unknown format item: " << v.second << std::endl;
                error = true;
                break;
            } else {
                m_items.push_back(it->second(v.second));
            }
        }
    }


}
}