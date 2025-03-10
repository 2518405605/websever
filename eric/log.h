#ifndef __ERIC_LOG_H__
#define __ERIC_LOG_H__

#include<sstream>
#include <string>
#include<stdint.h>
#include<memory>
#include<list>
#include<fstream>
#include<vector>
#include<map>
#include"util.h"

#define ERIC_LOG_LEVEL(logger,level)\
    if(logger->getLevel()<=level)\
        eric::LogEventWarp(eric::LogEvent::ptr (new eric::LogEvent(logger,level,\
                                                __FILE__,__LINE__,0,eric::GetThreadId(), \
                                                eric::GetFiberId(),time(0)))).getSS()

#define ERIC_LOG_DEBUG(logger) ERIC_LOG_LEVEL(logger,eric::LogLevel::DEBUG)
#define ERIC_LOG_INFO(logger) ERIC_LOG_LEVEL(logger,eric::LogLevel::INFO)
#define ERIC_LOG_WARN(logger) ERIC_LOG_LEVEL(logger,eric::LogLevel::WARN)
#define ERIC_LOG_ERROR(logger) ERIC_LOG_LEVEL(logger,eric::LogLevel::ERROR)
#define ERIC_LOG_FATAL(logger) ERIC_LOG_LEVEL(logger,eric::LogLevel::FATAL)   //宏定义是为了方便每个汉书能够使用里面的宏初始__LINE__

namespace eric{

class Logger;
//日志级别
class LogLevel{
public:
    enum Level{
        UNKNOW=0,
        DEBUG=1,
        INFO=2,
        WARN=3,
        ERROR=4,
        FATAL=5
    };
    static const char * ToString(LogLevel::Level level);
};
//日志事件
class LogEvent{
public:
    typedef std::shared_ptr<LogEvent> ptr;
    LogEvent(std::shared_ptr<Logger> logger,LogLevel::Level level,const char*file, int32_t line,uint32_t elapse,
            uint32_t thread_id,uint32_t fiber_id,uint64_t time);
    const char * getFile()const{return m_file;}
    int32_t getLine()const{return m_line;}
    uint32_t getElapse()const{return m_elapse;}
    uint32_t getThread()const{return m_threadId;}
    uint32_t getFiber()const{return m_fiberId;}
    u_int64_t getTime()const{return m_time;}
    const std::string getContent()const{return m_ss.str();}
    std::stringstream& getSS() {return m_ss;}
    std::shared_ptr<Logger> getLogger(){return m_logger;}
    LogLevel::Level getLevel(){return m_level; }

    void format(const char*fmt, ...);
private:
    const char *m_file=nullptr;//文件名
    int32_t m_line=0;          //行号
    uint32_t m_elapse=0;        //程序启动到现在的毫秒数
    uint32_t m_threadId=0;     //线程号 
    uint32_t m_fiberId=0;      //协程id
    u_int64_t m_time;          //时间戳
    std::stringstream m_ss;
    std::shared_ptr<Logger> m_logger;
    LogLevel::Level m_level;
};
class LogEventWarp{
public:                                 //把自己写进logger ，析构时自动写入
    LogEventWarp(LogEvent::ptr e);
    ~LogEventWarp();
    std::stringstream& getSS();
private:
    LogEvent::ptr m_event;
};


class Logger;
//日志格式器
class LogFormatter{
public:
    typedef std::shared_ptr<LogFormatter> ptr;
    LogFormatter(const std::string &pattern);
    std::string format(std::shared_ptr<Logger> logger,LogLevel::Level level,LogEvent::ptr event);
public:
    class FormatItem{
    public:
        typedef std::shared_ptr<FormatItem> ptr;
        virtual ~FormatItem(){}
        virtual void format(std::ostream& os,std::shared_ptr<Logger> logger,LogLevel::Level level,LogEvent::ptr event)=0;
    };
    void init();
private:
    std::string m_pattern;
    std::vector<FormatItem::ptr> m_items;
};

//日志输出地
class LogAppender{
public:
    typedef std::shared_ptr<LogAppender> ptr;

    virtual void log(std::shared_ptr<Logger> logger,LogLevel::Level level,LogEvent::ptr event)=0;

    void setFormatter(LogFormatter::ptr val){m_formatter=val;}
    LogFormatter::ptr getFormatter()const {return m_formatter;}

    LogLevel::Level getLevel() const {return m_level;}
    void setLevel (LogLevel:: Level val){m_level=val;}
protected:
    LogLevel::Level m_level;
    LogFormatter::ptr m_formatter;
};

//日志器
class Logger:public std::enable_shared_from_this<Logger>
{
public:
    typedef std::shared_ptr<Logger> ptr;

    void log(LogLevel::Level level,const LogEvent::ptr event);
    Logger(const std::string& name="root");
    void debug(LogEvent::ptr event);
    void info (LogEvent::ptr event);
    void warn (LogEvent::ptr event);
    void error(LogEvent::ptr event);
    void fatal (LogEvent::ptr event);
    void addAppender (LogAppender::ptr appender);
    void delAppender(LogAppender::ptr appender);
    LogLevel ::Level getLevel ()const {return m_level;}
    void setLevel(LogLevel::Level val){m_level=val;}
    const std::string& getName() const {return m_name;}
private:
    std::string m_name;                             //日志名称
    LogLevel::Level m_level;                        //日志级别
    std::list<LogAppender::ptr> m_appenders;        //apeender集合
    LogFormatter ::ptr m_formatter;
};



//输出到控制台的Appender
class StdoutLogAppender:public LogAppender{
public:
    StdoutLogAppender();
    typedef std::shared_ptr<StdoutLogAppender> ptr;
    void log(Logger::ptr logger,LogLevel::Level level,LogEvent::ptr event) override;
};

class LoggerManager{
public:
    LoggerManager();
    Logger::ptr getLogger(const std::string& name);
    void init();
private:
    std::map<std::string,Logger::ptr> m_logger;
    Logger::ptr m_root;
};







//定义输出到文件的Appender
class FileLogAppender:public LogAppender{
public:
    typedef std::shared_ptr<FileLogAppender> ptr;
    FileLogAppender(const std::string& filename);
    void log(Logger::ptr logger,LogLevel::Level level,LogEvent:: ptr event)override;
    //重新打开文件，文件打开成功返回true
    bool reopen();
private:
    std::string m_filename;
    std::ofstream m_filestream;
};
}
#endif