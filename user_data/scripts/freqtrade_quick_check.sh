#!/bin/bash
# 快速错误检查脚本 (cron调用)

LOG_FILE="/root/ft_userdata/user_data/logs/freqtrade.log"
ALERT_FILE="/root/ft_userdata/user_data/logs/freqtrade_alerts.log"
LAST_CHECK="/root/ft_userdata/user_data/scripts/.last_check_position"

# 获取上次检查位置
if [ -f "$LAST_CHECK" ]; then
    LAST_POS=$(cat "$LAST_CHECK")
else
    LAST_POS=0
fi

# 检查新错误
NEW_ERRORS=$(tail -c +$((LAST_POS + 1)) "$LOG_FILE" 2>/dev/null | grep -E "(UnboundLocalError|NameError|TypeError|AttributeError|ImportError|SyntaxError|RuntimeError|Traceback)" | head -5)

if [ -n "$NEW_ERRORS" ]; then
    echo "[$(date)] 检测到错误:" >> "$ALERT_FILE"
    echo "$NEW_ERRORS" >> "$ALERT_FILE"
    
    # 可选: 发送通知 (需要配置)
    # curl -s -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
    #   -d chat_id=<CHAT_ID> \
    #   -d text="Freqtrade Error: $NEW_ERRORS"
fi

# 更新检查位置
wc -c < "$LOG_FILE" > "$LAST_CHECK"
