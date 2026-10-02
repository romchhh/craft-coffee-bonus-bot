#!/bin/bash
source /root/InterBuildBot/myenv/bin/activate
nohup python3 /root/InterBuildBot/main.py > /dev/null 2>&1 &
echo "Bot started"
