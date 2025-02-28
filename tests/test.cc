#include<iostream>
#include<stdio.h>
#include"../eric/log.h"
#include<time.h>
#include"../eric/util.h"

int main(int argc, char *argv[]){
    eric::Logger::ptr logger(new eric::Logger);
    logger->addAppender(eric::LogAppender::ptr(new eric::StdoutLogAppender));
    
    eric::LogEvent::ptr event(new eric::LogEvent(logger,eric::LogLevel::DEBUG,__FILE__,__LINE__,
                                                0,eric::GetThreadId(),eric::GetFiberId(),time(0)));  
    event->getSS()<<"hello slog";

    logger->log(eric::LogLevel::DEBUG,event);
    std::cout<<"heil sdf log"<<std::endl;


    return 0;
}